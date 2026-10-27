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
    assert any(c.startswith("Hot") for c in cons) and not any(c.startswith(("Chilly", "Cold")) for c in cons)
    pros, cons = planner.reasons(planner.ACTIVITIES["run"], [hour("2026-10-26T06:00", feels_like=19.5)])
    assert any(c.startswith("Warm") for c in cons)
    pros, cons = planner.reasons(planner.ACTIVITIES["run"], [hour("2026-10-26T06:00", feels_like=-3)])
    assert any(c.startswith("Cold") for c in cons)


def test_attach_air_matches_times_and_fills_forward():
    hourly = [hour(f"2026-10-26T{h:02d}:00") for h in (7, 8)] + [hour("2026-10-27T07:00")]
    air = {"hourly": {"time": ["2026-10-26T07:00", "2026-10-26T08:00"], "us_aqi": [40, 160],
                      "grass_pollen": [5.0, 80.0], "birch_pollen": [12.0, 1.0]}}
    planner.attach_air(hourly, air)
    assert hourly[0]["aqi"] == 40 and hourly[0]["pollen"] == 12.0 and hourly[0]["pollen_type"] == "birch"
    assert hourly[1]["pollen_type"] == "grass"
    # Past the end of the air data: same hour of day is reused and flagged as an estimate.
    assert hourly[2]["aqi"] == 40 and hourly[2]["air_estimated"]


def test_bad_air_and_pollen_lower_scores_and_show_as_cons():
    clean = planner.score_hour(planner.ACTIVITIES["walk"], hour("2026-10-26T10:00", aqi=20, pollen=2), {})
    dirty = planner.score_hour(planner.ACTIVITIES["walk"], hour("2026-10-26T10:00", aqi=180, pollen=150,
                                                                  pollen_type="grass"), {})
    assert clean > 85 > 40 > dirty
    pros, cons = planner.reasons(planner.ACTIVITIES["walk"],
                                 [hour("2026-10-26T10:00", aqi=180, pollen=150, pollen_type="grass")])
    assert "Air quality: Unhealthy (AQI 180)" in cons and "High grass pollen" in cons
    # Stargazing ignores air quality entirely.
    assert planner.score_hour(planner.ACTIVITIES["stars"], hour("2026-10-26T22:00", is_day=0, cloud_cover=0,
                                                                  aqi=300), {}) > 85


def test_commute_only_in_rush_hours():
    hourly = day_hours("2026-10-26") + day_hours("2026-10-27")
    result = planner.plan("commute", hourly, DAILY, now_index=0)
    assert result["windows"]
    assert all(int(w["start"][11:13]) in planner.COMMUTE_HOURS for w in result["windows"])


def test_verdict_go_wait_and_next():
    hourly = day_hours("2026-10-26") + day_hours("2026-10-27")
    go = planner.plan("walk", hourly, DAILY, now_index=10)["verdict"]
    assert go["status"] == "go" and go["blocked"] is None

    dark = planner.plan("walk", hourly, DAILY, now_index=21)["verdict"]
    assert dark["status"] == "wait" and dark["blocked"] == "it's dark"
    assert dark["next"]["start"].startswith("2026-10-27T07")

    stormy = day_hours("2026-10-26", {10: {"precip_prob": 95}})
    wet = planner.plan("walk", stormy + day_hours("2026-10-27"), DAILY, now_index=10)["verdict"]
    assert wet["status"] == "wait" and "95% chance of rain" in wet["cons"]
    assert wet["next"]["start"] == "2026-10-26T11:00"  # the soonest good hour, not just the best
