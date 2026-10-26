from datetime import date

import pytest
from fastapi.testclient import TestClient

from weather_api import main, transform
from weather_api.codes import aqi_category, describe


def fake_forecast():
    hours = [f"2026-10-26T{h:02d}:00" for h in range(24)] + [f"2026-10-27T{h:02d}:00" for h in range(24)]
    n = len(hours)
    return {
        "latitude": 51.5, "longitude": -0.12, "elevation": 11, "timezone": "Europe/London",
        "timezone_abbreviation": "GMT", "utc_offset_seconds": 0,
        "current": {"time": "2026-10-26T10:15", "temperature_2m": 12.0, "apparent_temperature": 8.0,
                    "weather_code": 61, "is_day": 1, "wind_speed_10m": 20},
        "hourly": {
            "time": hours,
            "temperature_2m": [10 + (i % 24) / 2 for i in range(n)],
            "apparent_temperature": [9.0] * n,
            "precipitation_probability": [80 if i == 14 else 5 for i in range(n)],
            "weather_code": [3] * n,
            "wind_gusts_10m": [70 if i == 20 else 10 for i in range(n)],
            "wind_speed_10m": [10] * n,
            "uv_index": [2] * n,
            "is_day": [1 if 7 <= i % 24 <= 17 else 0 for i in range(n)],
        },
        "daily": {
            "time": ["2026-10-26", "2026-10-27", "2026-10-28"],
            "weather_code": [61, 0, None],
            "temperature_2m_max": [14.0, 20.0, None],
            "temperature_2m_min": [6.0, 8.0, None],
        },
        "minutely_15": {"time": ["2026-10-26T10:15", "2026-10-26T10:30", "2026-10-26T10:45"],
                        "precipitation": [0, 0.4, 0.2]},
    }


def test_describe_known_and_unknown_codes():
    assert describe(0, True)["icon"] == "☀️"
    assert describe(0, False)["icon"] == "🌙"
    assert describe(95)["theme"] == "storm"
    assert describe(1234)["text"] == "Unknown"


def test_aqi_category():
    assert aqi_category(10)["label"] == "Good"
    assert aqi_category(160)["label"] == "Unhealthy"
    assert aqi_category(None)["label"] == "Unavailable"


def test_build_weather_shapes_data_and_insights():
    data = transform.build_weather(fake_forecast(), 51.5, -0.12)
    assert data["now_index"] == 10
    assert data["current"]["condition"]["theme"] == "rain"
    assert len(data["daily"]) == 2  # trailing empty day dropped
    assert data["nowcast"]["summary"].startswith("Precipitation likely starting around 10:30")
    titles = {i["title"] for i in data["insights"]}
    assert {"Bring an umbrella", "Strong gusts", "Feels colder", "Tomorrow is warmer", "Best time outdoors"} <= titles
    gusts = next(i for i in data["insights"] if i["title"] == "Strong gusts")
    assert "{{w:70}}" in gusts["text"]


def test_on_this_day_stats_and_trend():
    times, maxes = [], []
    for year in range(2000, 2010):
        times += [f"{year}-10-25", f"{year}-10-26"]
        maxes += [0.0, 10.0 + (year - 2000)]
    raw = {"daily": {"time": times, "temperature_2m_max": maxes,
                     "temperature_2m_min": [m - 5 for m in maxes], "precipitation_sum": [0.0] * len(times)}}
    result = transform.build_on_this_day(raw, date(2026, 10, 26))
    stats = result["stats"]
    assert stats["count"] == 10
    assert stats["record_high"] == {"year": 2009, "value": 19.0}
    assert stats["trend_per_decade"] == 10.0


@pytest.fixture
def client(monkeypatch):
    async def fake_get(self, url, params, ttl):
        return fake_forecast()
    monkeypatch.setattr(main.OpenMeteoClient, "get", fake_get)
    with TestClient(main.app) as c:
        yield c


def test_weather_endpoint(client):
    r = client.get("/api/v1/weather", params={"lat": 51.5, "lon": -0.12})
    assert r.status_code == 200
    assert r.json()["location"]["timezone"] == "Europe/London"


def test_weather_endpoint_validates_coordinates(client):
    assert client.get("/api/v1/weather", params={"lat": 120, "lon": 0}).status_code == 422


def test_compare_rejects_bad_points(client):
    assert client.get("/api/v1/compare", params={"points": "abc"}).status_code == 422
    assert client.get("/api/v1/compare", params={"points": "95,0"}).status_code == 422
