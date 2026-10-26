from weather_api import planner


def hour(t, **kw):
    base = {"time": t, "temp": 15, "feels_like": 12, "precip_prob": 0, "wind_speed": 8, "wind_gusts": 15,
            "humidity": 55, "cloud_cover": 30, "uv": 2, "visibility": 30000, "is_day": 1,
            "condition": {"icon": "☀️"}}
    base.update(kw)
    return base


def day_hours(date, overrides_by_hour=None):
    rows = []
    for h in range(24):
        kw = {"is_day": 1 if 7 <= h <= 17 else 0}
        kw.update((overrides_by_hour or {}).get(h, {}))
        rows.append(hour(f"{date}T{h:02d}:00", **kw))
    return rows


DAILY = [{"time": "2026-10-26", "sunrise": "2026-10-26T06:45", "sunset": "2026-10-26T16:45"},
         {"time": "2026-10-27", "sunrise": "2026-10-27T06:47", "sunset": "2026-10-27T16:43"}]


def test_rule_penalty_ranges():
    assert planner.rule_penalty(10, 5, 15, 0, 25) == 0
    assert planner.rule_penalty(20, 5, 15, 0, 25) == 50
    assert planner.rule_penalty(30, 5, 15, 0, 25) == 100
    assert planner.rule_penalty(-100, 5, 15, None, 25) == 0  # no lower limit


def test_rainy_hours_are_avoided():
    rain = {h: {"precip_prob": 90} for h in range(7, 12)}
    hourly = day_hours("2026-10-26", rain) + day_hours("2026-10-27")
    result = planner.plan("walk", hourly, DAILY, now_index=0, duration=1)
    for w in result["windows"]:
        assert not ("2026-10-26T07" <= w["start"] < "2026-10-26T12")
    assert result["windows"][0]["score"] >= 85


def test_daylight_required_and_night_activities():
    hourly = day_hours("2026-10-26") + day_hours("2026-10-27")
    walk = planner.plan("walk", hourly, DAILY, now_index=0)
    assert all(7 <= int(w["start"][11:13]) <= 17 for w in walk["windows"])
    stars = planner.plan("stars", [dict(h, cloud_cover=0) for h in hourly], DAILY, now_index=0)
    assert stars["windows"] and all(not 7 <= int(w["start"][11:13]) <= 17 for w in stars["windows"])


def test_one_window_per_day_and_reasons():
    hourly = day_hours("2026-10-26") + day_hours("2026-10-27")
    result = planner.plan("run", hourly, DAILY, now_index=0)
    days = [w["start"][:10] for w in result["windows"]]
    assert len(days) == len(set(days)) == 2
    assert "Dry" in result["windows"][0]["pros"]


def ensemble(times, ecmwf_wet, gfs_wet):
    hourly = {"time": times}
    for m, wet_frac, n in (("ecmwf_ifs025", ecmwf_wet, 10), ("gfs025", gfs_wet, 10)):
        for i in range(n):
            hourly[f"precipitation_member{i:02d}_{m}"] = [1.0 if i < wet_frac * n else 0.0] * len(times)
            hourly[f"temperature_2m_member{i:02d}_{m}"] = [12.0] * len(times)
    return {"hourly": hourly}


def test_confidence_levels():
    times = ["2026-10-26T10:00", "2026-10-26T11:00"]
    hours = [hour(t) for t in times]
    agree_dry = planner.window_confidence(hours, planner.ensemble_by_time(ensemble(times, 0, 0)))
    assert agree_dry["level"] == "high" and "stay dry" in agree_dry["summary"]
    split = planner.window_confidence(hours, planner.ensemble_by_time(ensemble(times, 0.9, 0.1)))
    assert split["level"] == "low" and "Models disagree" in split["summary"]
    assert planner.window_confidence(hours, {}) is None


def test_hot_window_is_labelled_hot_not_chilly():
    hours = [hour("2026-10-26T06:00", feels_like=25, temp=25)]
    pros, cons = planner.reasons(planner.ACTIVITIES["run"], hours)
    assert any(c.startswith("Hot") for c in cons) and not any(c.startswith("Chilly") for c in cons)
    pros, cons = planner.reasons(planner.ACTIVITIES["run"], [hour("2026-10-26T06:00", feels_like=-3)])
    assert any(c.startswith("Chilly") for c in cons)
