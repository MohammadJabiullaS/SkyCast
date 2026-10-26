"""Reshape Open-Meteo column-oriented payloads into rows and derive insights.

All values stay metric (°C, km/h, mm, m, hPa); the browser converts units so
switching units never needs a new request.

Insight text may contain unit tokens the frontend formats:
  {{t:12.3}} temperature, {{dt:4.1}} temperature difference,
  {{w:40}} wind speed, {{p:3.2}} precipitation amount.
"""
from datetime import date

from .codes import describe

# Open-Meteo variable -> short key used by the frontend
FIELD_MAP = {
    "time": "time",
    "temperature_2m": "temp",
    "apparent_temperature": "feels_like",
    "relative_humidity_2m": "humidity",
    "dew_point_2m": "dew_point",
    "precipitation": "precip",
    "precipitation_probability": "precip_prob",
    "weather_code": "code",
    "cloud_cover": "cloud_cover",
    "pressure_msl": "pressure",
    "wind_speed_10m": "wind_speed",
    "wind_direction_10m": "wind_dir",
    "wind_gusts_10m": "wind_gusts",
    "uv_index": "uv",
    "visibility": "visibility",
    "is_day": "is_day",
    "temperature_2m_max": "temp_max",
    "temperature_2m_min": "temp_min",
    "apparent_temperature_max": "feels_max",
    "apparent_temperature_min": "feels_min",
    "sunrise": "sunrise",
    "sunset": "sunset",
    "daylight_duration": "daylight",
    "uv_index_max": "uv_max",
    "precipitation_sum": "precip_sum",
    "precipitation_probability_max": "precip_prob_max",
    "wind_speed_10m_max": "wind_max",
    "wind_gusts_10m_max": "gusts_max",
    "wind_direction_10m_dominant": "wind_dir_dominant",
}

CURRENT_VARS = [
    "temperature_2m", "apparent_temperature", "relative_humidity_2m", "dew_point_2m",
    "precipitation", "weather_code", "cloud_cover", "pressure_msl", "wind_speed_10m",
    "wind_direction_10m", "wind_gusts_10m", "uv_index", "visibility", "is_day",
]
HOURLY_VARS = [
    "temperature_2m", "apparent_temperature", "relative_humidity_2m", "precipitation",
    "precipitation_probability", "weather_code", "cloud_cover", "wind_speed_10m",
    "wind_gusts_10m", "wind_direction_10m", "uv_index", "visibility", "is_day",
]
DAILY_VARS = [
    "weather_code", "temperature_2m_max", "temperature_2m_min", "apparent_temperature_max",
    "apparent_temperature_min", "sunrise", "sunset", "daylight_duration", "uv_index_max",
    "precipitation_sum", "precipitation_probability_max", "wind_speed_10m_max",
    "wind_gusts_10m_max", "wind_direction_10m_dominant",
]


def rename(record):
    return {FIELD_MAP.get(k, k): v for k, v in record.items()}


def columns_to_rows(block):
    """{"time": [...], "x": [...]} -> [{"time": .., "x": ..}, ...] with short keys."""
    if not block:
        return []
    keys = list(block)
    return [rename(dict(zip(keys, values))) for values in zip(*(block[k] for k in keys))]


def with_condition(row):
    if row.get("code") is not None:
        row["condition"] = describe(row["code"], bool(row.get("is_day", 1)))
    return row


def location_meta(raw, lat, lon):
    return {
        "latitude": raw.get("latitude", lat),
        "longitude": raw.get("longitude", lon),
        "elevation": raw.get("elevation"),
        "timezone": raw.get("timezone"),
        "timezone_abbreviation": raw.get("timezone_abbreviation"),
        "utc_offset_seconds": raw.get("utc_offset_seconds", 0),
    }


def build_weather(raw, lat, lon):
    current = with_condition(rename(raw.get("current", {})))
    # Long-range models can stop short of 16 days; drop the empty tail.
    hourly = [with_condition(r) for r in columns_to_rows(raw.get("hourly"))
              if r.get("temp") is not None and r.get("code") is not None]
    daily = [with_condition(r) for r in columns_to_rows(raw.get("daily"))
             if r.get("temp_max") is not None and r.get("code") is not None]
    minutely = columns_to_rows(raw.get("minutely_15"))

    now_hour = (current.get("time") or "")[:13]
    now_index = next((i for i, h in enumerate(hourly) if h["time"][:13] == now_hour), 0)

    return {
        "location": location_meta(raw, lat, lon),
        "current": current,
        "nowcast": build_nowcast(minutely),
        "now_index": now_index,
        "hourly": hourly,
        "daily": daily,
        "insights": build_insights(current, hourly[now_index:now_index + 24], daily),
    }


def build_nowcast(minutely):
    """Summarise the next two hours of 15-minute precipitation."""
    steps = [{"time": m["time"], "precip": m.get("precip") or 0} for m in minutely[:8]]
    wet = [s for s in steps if s["precip"] >= 0.1]
    if not steps:
        summary = "Short-term precipitation data unavailable."
    elif not wet:
        summary = "No precipitation expected in the next 2 hours."
    elif steps[0]["precip"] >= 0.1:
        dry = next((s for s in steps if s["precip"] < 0.1), None)
        summary = f"Precipitation now, easing around {dry['time'][11:16]}." if dry else "Precipitation continuing for the next 2 hours."
    else:
        summary = f"Precipitation likely starting around {wet[0]['time'][11:16]}."
    return {"summary": summary, "steps": steps, "total": round(sum(s["precip"] for s in steps), 1)}


def build_insights(current, next24, daily):
    insights = []

    def add(kind, icon, title, text):
        insights.append({"kind": kind, "icon": icon, "title": title, "text": text})

    if not next24:
        return insights

    today = (current.get("time") or next24[0]["time"])[:10]

    def when(h):
        prefix = "" if h["time"][:10] == today else "tomorrow "
        return f"{prefix}{h['time'][11:16]}"

    # Upcoming rain
    rainy = [h for h in next24 if (h.get("precip_prob") or 0) >= 60]
    if rainy:
        first = rainy[0]
        add("warn", "☔", "Bring an umbrella",
            f"{first['precip_prob']}% chance of rain around {when(first)}.")

    # Wind
    max_gust = max((h.get("wind_gusts") or 0) for h in next24)
    if max_gust >= 60:
        add("alert", "💨", "Strong gusts", f"Gusts up to {{{{w:{max_gust}}}}} in the next 24 hours.")

    # UV
    uv_peak = max(next24, key=lambda h: h.get("uv") or 0)
    if (uv_peak.get("uv") or 0) >= 6:
        add("warn", "🧴", "High UV", f"UV index peaks at {uv_peak['uv']:.0f} around {when(uv_peak)}. Use sunscreen.")

    # Temperature extremes
    temps = [h["temp"] for h in next24 if h.get("temp") is not None]
    if temps and min(temps) <= 0:
        add("info", "🥶", "Frost risk", f"Temperatures drop to {{{{t:{min(temps)}}}}}. Watch for icy surfaces.")
    if temps and max(temps) >= 35:
        add("alert", "🥵", "Heat alert", f"Temperatures reach {{{{t:{max(temps)}}}}}. Stay hydrated.")

    # Feels-like gap
    t, fl = current.get("temp"), current.get("feels_like")
    if t is not None and fl is not None and abs(t - fl) >= 3:
        word = "colder" if fl < t else "warmer"
        add("info", "🌡️", f"Feels {word}", f"Wind and humidity make it feel like {{{{t:{fl}}}}}.")

    # Day-over-day change
    if len(daily) >= 2 and daily[0].get("temp_max") is not None and daily[1].get("temp_max") is not None:
        diff = round(daily[1]["temp_max"] - daily[0]["temp_max"], 1)
        if abs(diff) >= 4:
            word = "warmer" if diff > 0 else "cooler"
            add("info", "📈" if diff > 0 else "📉", f"Tomorrow is {word}",
                f"Highs {{{{dt:{abs(diff)}}}}} {word} than today.")

    # Best time outdoors (daylight hours only)
    def score(h):
        return (abs((h.get("temp") or 0) - 21)
                + (h.get("precip_prob") or 0) * 0.3
                + (h.get("wind_speed") or 0) / 3
                + (8 if (h.get("uv") or 0) >= 8 else 0))

    daylight = [h for h in next24 if h.get("is_day")]
    if daylight:
        best = min(daylight, key=score)
        dry = (best.get("precip_prob") or 0) < 30
        add("good", "🚶", "Best time outdoors",
            f"Around {when(best)}: {{{{t:{best['temp']}}}}} and {'dry' if dry else 'some chance of rain'}.")

    if not insights:
        add("good", "✨", "Calm conditions", "No notable weather in the next 24 hours.")
    return insights


def build_on_this_day(raw, today: date):
    """Filter decades of daily archive data down to today's calendar date."""
    rows = columns_to_rows(raw.get("daily"))
    md = today.strftime("%m-%d")
    years = []
    for r in rows:
        r_md = r["time"][5:10]
        if r_md == md or (md == "02-29" and r_md == "02-28"):
            if r.get("temp_max") is None:
                continue
            years.append({
                "year": int(r["time"][:4]),
                "temp_max": r["temp_max"],
                "temp_min": r.get("temp_min"),
                "precip_sum": r.get("precip_sum"),
            })
    if md == "02-29":  # keep a single entry per year
        years = list({y["year"]: y for y in years}.values())

    if not years:
        return {"date": today.isoformat(), "years": [], "stats": None}

    maxes = [y["temp_max"] for y in years]
    mins = [y["temp_min"] for y in years if y["temp_min"] is not None]
    hottest = max(years, key=lambda y: y["temp_max"])
    coldest = min((y for y in years if y["temp_min"] is not None), key=lambda y: y["temp_min"], default=None)
    rainy_years = sum(1 for y in years if (y["precip_sum"] or 0) >= 1)

    return {
        "date": today.isoformat(),
        "years": years,
        "stats": {
            "count": len(years),
            "avg_max": round(sum(maxes) / len(maxes), 1),
            "avg_min": round(sum(mins) / len(mins), 1) if mins else None,
            "record_high": {"year": hottest["year"], "value": hottest["temp_max"]},
            "record_low": {"year": coldest["year"], "value": coldest["temp_min"]} if coldest else None,
            "rain_chance": round(100 * rainy_years / len(years)),
            "trend_per_decade": linear_trend([y["year"] for y in years], maxes),
        },
    }


def linear_trend(xs, ys):
    """Least-squares slope, expressed per 10 x-units."""
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    denom = sum((x - mx) ** 2 for x in xs)
    if denom == 0:
        return None
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / denom
    return round(slope * 10, 2)
