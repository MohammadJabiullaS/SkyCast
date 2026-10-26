"""SkyCast weather service: a FastAPI layer over the Open-Meteo APIs.

Run with:  uvicorn weather_api.main:app --port 8001 --reload
"""
import asyncio
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone

import httpx
from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import planner, transform
from .client import (
    AIR_QUALITY_URL, ARCHIVE_URL, ENSEMBLE_URL, FORECAST_URL, GEOCODING_URL,
    OpenMeteoClient, TTLCache, UpstreamError,
)
from .codes import aqi_category, describe

LAT = Query(..., ge=-90, le=90, description="Latitude in decimal degrees")
LON = Query(..., ge=-180, le=180, description="Longitude in decimal degrees")


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with httpx.AsyncClient(timeout=20, headers={"User-Agent": "SkyCast/1.0"}) as http:
        app.state.meteo = OpenMeteoClient(http, TTLCache())
        yield


app = FastAPI(
    title="SkyCast Weather API",
    version="1.0.0",
    description="Forecasts, air quality, nowcasting and climate history powered by Open-Meteo.",
    lifespan=lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"])


@app.exception_handler(UpstreamError)
async def upstream_error_handler(request: Request, exc: UpstreamError):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


def meteo(request: Request) -> OpenMeteoClient:
    # Serverless hosts may skip lifespan events, so create the client on first use.
    client = getattr(request.app.state, "meteo", None)
    if client is None:
        http = httpx.AsyncClient(timeout=20, headers={"User-Agent": "SkyCast/1.0"})
        client = request.app.state.meteo = OpenMeteoClient(http, TTLCache())
    return client


def round_coord(value):
    # ~1 km precision keeps cache hit rates high without visible accuracy loss
    return round(value, 3)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/api/v1/geocode", summary="Search places by name")
async def geocode(request: Request, q: str = Query(..., min_length=2, max_length=80),
                  count: int = Query(8, ge=1, le=20), language: str = "en"):
    raw = await meteo(request).get(
        GEOCODING_URL, {"name": q, "count": count, "language": language, "format": "json"}, ttl=86400)
    return {
        "results": [
            {
                "id": r.get("id"),
                "name": r.get("name"),
                "admin1": r.get("admin1"),
                "country": r.get("country"),
                "country_code": r.get("country_code"),
                "latitude": r.get("latitude"),
                "longitude": r.get("longitude"),
                "timezone": r.get("timezone"),
                "population": r.get("population"),
                "elevation": r.get("elevation"),
            }
            for r in raw.get("results", [])
        ]
    }


async def fetch_forecast(request, lat, lon):
    """Full forecast; shared by /weather and /plan so they hit the same cache entry."""
    return await meteo(request).get(FORECAST_URL, {
        "latitude": lat,
        "longitude": lon,
        "current": ",".join(transform.CURRENT_VARS),
        "hourly": ",".join(transform.HOURLY_VARS),
        "daily": ",".join(transform.DAILY_VARS),
        "minutely_15": "precipitation",
        "forecast_minutely_15": 8,
        "forecast_days": 16,
        "timezone": "auto",
    }, ttl=600)


@app.get("/api/v1/weather", summary="Current conditions, nowcast, 16-day forecast and insights")
async def weather(request: Request, lat: float = LAT, lon: float = LON):
    lat, lon = round_coord(lat), round_coord(lon)
    raw = await fetch_forecast(request, lat, lon)
    data = transform.build_weather(raw, lat, lon)
    data["fetched_at"] = datetime.now(timezone.utc).isoformat()
    return data


@app.get("/api/v1/air-quality", summary="Current air quality, pollutants and 2-day AQI outlook")
async def air_quality(request: Request, lat: float = LAT, lon: float = LON):
    lat, lon = round_coord(lat), round_coord(lon)
    raw = await meteo(request).get(AIR_QUALITY_URL, {
        "latitude": lat,
        "longitude": lon,
        "current": "us_aqi,european_aqi,pm10,pm2_5,carbon_monoxide,nitrogen_dioxide,sulphur_dioxide,ozone,dust",
        "hourly": "us_aqi",
        "forecast_days": 2,
        "timezone": "auto",
    }, ttl=1800)
    current = raw.get("current", {})
    return {
        "current": current,
        "category": aqi_category(current.get("us_aqi")),
        "hourly": transform.columns_to_rows(raw.get("hourly")),
    }


@app.get("/api/v1/history/recent", summary="Observed daily weather for the last N days")
async def history_recent(request: Request, lat: float = LAT, lon: float = LON,
                         days: int = Query(30, ge=7, le=92)):
    lat, lon = round_coord(lat), round_coord(lon)
    raw = await meteo(request).get(FORECAST_URL, {
        "latitude": lat,
        "longitude": lon,
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum",
        "past_days": days,
        "forecast_days": 1,
        "timezone": "auto",
    }, ttl=3600)
    rows = transform.columns_to_rows(raw.get("daily"))[:-1]  # drop today (incomplete)
    return {"location": transform.location_meta(raw, lat, lon), "daily": rows}


@app.get("/api/v1/history/on-this-day", summary="Today's date across past decades (climate context)")
async def on_this_day(request: Request, lat: float = LAT, lon: float = LON,
                      years: int = Query(30, ge=5, le=80)):
    lat, lon = round_coord(lat), round_coord(lon)
    utc_today = datetime.now(timezone.utc).date()
    # The reanalysis archive lags real time by a few days.
    end = utc_today - timedelta(days=6)
    start = date(utc_today.year - years, 1, 1)
    raw = await meteo(request).get(ARCHIVE_URL, {
        "latitude": lat,
        "longitude": lon,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum",
        "timezone": "auto",
    }, ttl=86400)
    offset = timedelta(seconds=raw.get("utc_offset_seconds", 0))
    local_today = (datetime.now(timezone.utc) + offset).date()
    return transform.build_on_this_day(raw, local_today)


@app.get("/api/v1/compare", summary="Current conditions and 7-day outlook for several places at once")
async def compare(request: Request, points: str = Query(
        ..., description="Semicolon-separated lat,lon pairs, e.g. 51.5,-0.12;40.7,-74.0")):
    coords = []
    for chunk in filter(None, points.split(";")):
        try:
            lat_s, lon_s = chunk.split(",")
            lat, lon = float(lat_s), float(lon_s)
        except ValueError:
            return JSONResponse(status_code=422, content={"detail": f"Invalid point: {chunk!r}"})
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            return JSONResponse(status_code=422, content={"detail": f"Out of range: {chunk!r}"})
        coords.append((round_coord(lat), round_coord(lon)))
    if not 1 <= len(coords) <= 12:
        return JSONResponse(status_code=422, content={"detail": "Provide between 1 and 12 points."})

    raw = await meteo(request).get(FORECAST_URL, {
        "latitude": ",".join(str(c[0]) for c in coords),
        "longitude": ",".join(str(c[1]) for c in coords),
        "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,"
                   "wind_speed_10m,precipitation,is_day",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
        "forecast_days": 7,
        "timezone": "auto",
    }, ttl=600)
    items = raw if isinstance(raw, list) else [raw]
    results = []
    for (lat, lon), item in zip(coords, items):
        current = transform.rename(item.get("current", {}))
        current["condition"] = describe(current.get("code"), bool(current.get("is_day", 1)))
        results.append({
            "query": {"latitude": lat, "longitude": lon},
            "location": transform.location_meta(item, lat, lon),
            "current": current,
            "daily": [transform.with_condition(r) for r in transform.columns_to_rows(item.get("daily"))],
        })
    return {"results": results}


@app.get("/api/v1/activities", summary="Activities the planner can score")
async def activities():
    return {"results": [
        {"key": k, "label": a["label"], "icon": a["icon"], "duration": a["duration"]}
        for k, a in planner.ACTIVITIES.items()
    ]}


@app.get("/api/v1/plan", summary="Best time windows for an activity, with ensemble-based confidence")
async def plan(request: Request, lat: float = LAT, lon: float = LON,
               activity: str = Query("run", pattern="^(" + "|".join(planner.ACTIVITIES) + ")$"),
               duration: int | None = Query(None, ge=1, le=8, description="Window length in hours"),
               days: int = Query(7, ge=1, le=7)):
    lat, lon = round_coord(lat), round_coord(lon)
    ensemble_req = meteo(request).get(ENSEMBLE_URL, {
        "latitude": lat,
        "longitude": lon,
        "hourly": "temperature_2m,precipitation",
        "models": "ecmwf_ifs025,gfs025",
        "forecast_days": 7,
        "timezone": "auto",
    }, ttl=3600)
    raw, ensemble = await asyncio.gather(fetch_forecast(request, lat, lon), ensemble_req, return_exceptions=True)
    if isinstance(raw, Exception):
        raise raw
    if isinstance(ensemble, Exception):
        ensemble = None  # confidence is optional; the plan still works without it

    data = transform.build_weather(raw, lat, lon)
    return planner.plan(activity, data["hourly"], data["daily"], data["now_index"],
                        duration=duration, ensemble=ensemble, days=days)
