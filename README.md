# SkyCast ⛅

An interactive weather app built with **Django** (web app) and **FastAPI** (weather service),
powered by the free [Open-Meteo](https://open-meteo.com/) APIs. No API key needed.

```
Browser ──► Django :8000 ──(/api/weather/* proxy)──► FastAPI :8001 ──► Open-Meteo
             │ pages, favorites (SQLite), admin        │ caching, data shaping, insights
```

## Features

**🎯 Activity planner (what makes SkyCast different)**
- Pick an activity: run, cycle, walk, BBQ/picnic, dry laundry, golden-hour photos, stargazing or beach.
  SkyCast scores every hour of the next 7 days for it and suggests the **3 best time windows**
  (at most one per day), each with plain-language pros and cons.
- **Forecast confidence**: each window is checked against 82 ensemble forecast runs (ECMWF 51 + GFS 31),
  e.g. "99% of 82 forecast runs stay dry" or "Models disagree on rain (ECMWF 70%, GFS 10%)".
- An hour-by-hour suitability heatmap for the whole week, with adjustable activity length (1–6 h).
- Activity rules live in `weather_api/planner.py` (`ACTIVITIES`), so adding one is a few lines.

**Dashboard**
- City search with autocomplete and keyboard navigation (press `/` to focus), or 📍 geolocation
- Current conditions with a live local clock and weather-driven animated backgrounds (rain, snow, lightning, fog, stars)
- 2-hour precipitation nowcast in 15-minute steps
- Smart insights: umbrella alerts, strong gusts, UV, frost/heat, "feels like" gap, day-over-day change, best time to go outside
- 48-hour strip plus an interactive chart (temperature, precipitation, wind, humidity, UV)
- Up to 16-day forecast with temperature range bars; click a day to see its hourly detail
- Detail tiles: wind compass, sun arc, UV gauge, humidity and dew point, pressure, visibility, air quality (US/EU AQI and pollutants)
- Map: click anywhere for its forecast, see favorites, toggle an animated rain radar (RainViewer)
- Climate context: last 30 days observed, and today's date across the past 30 years (normals, records, trend per decade)
- °C/°F and km/h, mph, m/s, knots, converted in the browser with no extra requests
- Auto-refresh every 10 minutes

**Favorites**: stored in Django's database, with live temperatures, drag-to-reorder and Django admin.

**Compare**: compare up to 12 places side by side. Includes a leaderboard (warmest, coldest, windiest, wettest week) and 7-day charts.

## Run it

```bash
./run.sh
```

Or run the two servers separately:

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/python web/manage.py migrate
.venv/bin/uvicorn weather_api.main:app --port 8001 --reload       # terminal 1
.venv/bin/python web/manage.py runserver 127.0.0.1:8000            # terminal 2
```

Then open http://127.0.0.1:8000. The interactive FastAPI docs are at http://127.0.0.1:8001/docs.

## FastAPI endpoints (`/api/v1/…`)

| Endpoint | Description |
|---|---|
| `geocode?q=` | Place search |
| `weather?lat=&lon=` | Current, nowcast, hourly (16 days), daily, insights |
| `air-quality?lat=&lon=` | AQI, pollutants, 48-hour AQI |
| `history/recent?lat=&lon=&days=30` | Observed daily weather for the last N days |
| `history/on-this-day?lat=&lon=&years=30` | Today's date across past years, with stats and trend |
| `compare?points=lat,lon;lat,lon` | Several places in one request |
| `activities` | Activities the planner supports |
| `plan?lat=&lon=&activity=run&duration=1` | Best windows for an activity, with ensemble confidence |

All values are metric. Responses are cached in memory: forecasts for 10 minutes, air quality for 30 minutes, ensemble data for 1 hour, archive data and geocoding for 24 hours.

## Deploy to Vercel

`app.py` is the single entrypoint Vercel runs: the FastAPI service with the Django site mounted inside it.
Push to the connected GitHub repo, or run `vercel --prod`. Optional environment variables in Vercel:

- `DJANGO_SECRET_KEY`: set this so admin logins survive cold starts.
- `DATABASE_URL`: a Postgres URL (e.g. Vercel's Neon integration) so favorites persist. Without it,
  favorites live in a temporary SQLite file on each serverless instance and will disappear.

## Configuration

| Env var | Default |
|---|---|
| `WEATHER_API_URL` | `http://127.0.0.1:8001` (where Django finds FastAPI) |
| `DJANGO_SECRET_KEY` | dev key |
| `DJANGO_DEBUG` | `1` |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` |

## Tests

```bash
.venv/bin/python -m pytest tests                     # FastAPI service
.venv/bin/python web/manage.py test dashboard        # Django app
```

## Project layout

```
weather_api/          FastAPI service
  main.py             endpoints
  client.py           async Open-Meteo client + TTL cache
  transform.py        reshaping, nowcast, insights, climate stats
  planner.py          activity scoring, best windows, ensemble confidence
  codes.py            WMO weather codes, AQI categories
web/                  Django project (config/) and app (dashboard/)
  dashboard/views.py  pages, favorites API, proxy to FastAPI
  dashboard/static/   CSS + JS (Chart.js, Leaflet)
tests/                FastAPI tests
```

Weather data by Open-Meteo.com (CC BY 4.0). Map © OpenStreetMap contributors. Radar © RainViewer.
