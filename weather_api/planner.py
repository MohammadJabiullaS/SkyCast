"""Activity planner: score every hour for an activity, find the best time windows,
and attach a confidence level derived from ensemble forecasts.

Hourly rows use the short keys from transform.py (temp, precip_prob, wind_speed ...).
Reasons may contain the same unit tokens as insights ({{t:..}}, {{w:..}}).
"""
from statistics import pstdev

from .codes import aqi_category

# Each rule: (field, ideal_low, ideal_high, hard_low, hard_high)
# Inside [ideal_low, ideal_high] costs nothing; the penalty grows linearly to 100 at the hard limits.
# Shared rules for breathing outdoors: US AQI and pollen (grains/m³, highest type).
AIR = [("aqi", 0, 50, None, 200)]
POLLEN = [("pollen", 0, 10, None, 200)]

# Each rule: (field, ideal_low, ideal_high, hard_low, hard_high)
# Inside [ideal_low, ideal_high] costs nothing; the penalty grows linearly to 100 at the hard limits.
ACTIVITIES = {
    "run": {
        "label": "Run", "icon": "🏃", "verb": "go for a run", "duration": 1, "daylight": "prefer",
        "rules": [("feels_like", 6, 17, -8, 30), ("precip_prob", 0, 20, None, 80), ("wind_speed", 0, 20, None, 45),
                  ("uv", 0, 6, None, 10), *AIR, *POLLEN],
    },
    "cycle": {
        "label": "Cycle", "icon": "🚴", "verb": "go cycling", "duration": 2, "daylight": "require",
        "rules": [("feels_like", 12, 24, 0, 34), ("precip_prob", 0, 15, None, 60), ("wind_speed", 0, 15, None, 35),
                  ("wind_gusts", 0, 30, None, 60), *AIR, *POLLEN],
    },
    "walk": {
        "label": "Walk", "icon": "🚶", "verb": "go for a walk", "duration": 1, "daylight": "require",
        "rules": [("feels_like", 12, 25, -5, 36), ("precip_prob", 0, 25, None, 85), ("wind_speed", 0, 25, None, 50),
                  *AIR, *POLLEN],
    },
    "commute": {
        "label": "Commute", "icon": "🚌", "verb": "commute", "duration": 1, "daylight": "commute",
        "rules": [("feels_like", 5, 25, -10, 38), ("precip_prob", 0, 20, None, 80), ("wind_speed", 0, 25, None, 55),
                  ("wind_gusts", 0, 40, None, 75), ("visibility", 5000, None, 500, None), *AIR],
    },
    "bbq": {
        "label": "BBQ / picnic", "icon": "🍖", "verb": "have a BBQ or picnic", "duration": 3, "daylight": "require",
        "rules": [("temp", 19, 29, 10, 38), ("precip_prob", 0, 10, None, 50), ("wind_speed", 0, 15, None, 35),
                  ("cloud_cover", 0, 60, None, 100), *AIR, *POLLEN],
    },
    "laundry": {
        "label": "Dry laundry", "icon": "👕", "verb": "hang the laundry out", "duration": 4, "daylight": "require",
        "rules": [("precip_prob", 0, 5, None, 40), ("humidity", 0, 60, None, 95), ("temp", 15, 40, 3, None),
                  ("wind_speed", 6, 25, 0, 50), *POLLEN],
    },
    "photo": {
        "label": "Golden hour", "icon": "📷", "verb": "shoot golden-hour photos", "duration": 1, "daylight": "golden",
        "rules": [("cloud_cover", 15, 60, None, 100), ("precip_prob", 0, 20, None, 70), ("visibility", 15000, None, 2000, None)],
    },
    "stars": {
        "label": "Stargazing", "icon": "🔭", "verb": "go stargazing", "duration": 2, "daylight": "night",
        "rules": [("cloud_cover", 0, 10, None, 70), ("precip_prob", 0, 10, None, 50), ("humidity", 0, 75, None, 100)],
    },
    "beach": {
        "label": "Beach", "icon": "🏖️", "verb": "go to the beach", "duration": 3, "daylight": "require",
        "rules": [("temp", 25, 33, 18, 40), ("precip_prob", 0, 10, None, 50), ("wind_speed", 0, 18, None, 40),
                  ("cloud_cover", 0, 40, None, 100), *AIR, *POLLEN],
    },
}

# Typical rush hours (local time) used by the Commute activity.
COMMUTE_HOURS = {7, 8, 9, 16, 17, 18}
POLLEN_TYPES = ["alder", "birch", "grass", "mugwort", "olive", "ragweed"]


def pollen_level(value):
    """Rough cross-species scale in grains/m³ (individual species have their own thresholds)."""
    if value is None:
        return None
    if value < 1:
        return "None"
    if value < 10:
        return "Low"
    if value < 50:
        return "Moderate"
    if value < 200:
        return "High"
    return "Very high"


def attach_air(hourly, air_raw):
    """Copy hourly US AQI and the strongest pollen type onto the forecast rows, matched by time.

    The air-quality forecast stops after ~4-5 days. Later hours reuse the last known value for the
    same hour of day (a persistence estimate), so days past the data's end aren't favoured just
    because they have no air-quality penalty.
    """
    block = (air_raw or {}).get("hourly") or {}
    times = block.get("time") or []
    column = lambda name: block.get(name) or [None] * len(times)
    aqi_col = column("us_aqi")
    pollen_cols = {p: column(f"{p}_pollen") for p in POLLEN_TYPES}

    measured, last_by_hour = {}, {}
    for i, t in enumerate(times):
        reading = {}
        if aqi_col[i] is not None:
            reading["aqi"] = aqi_col[i]
        known = [(pollen_cols[p][i], p) for p in POLLEN_TYPES if pollen_cols[p][i] is not None]
        if known:
            value, kind = max(known)
            reading["pollen"], reading["pollen_type"] = value, kind
        if reading:
            measured[t] = reading
            last_by_hour.setdefault(t[11:13], {}).update(reading)

    last_time = max(measured) if measured else None
    for row in hourly:
        reading = measured.get(row["time"])
        if reading is None and last_time and row["time"] > last_time:
            reading = last_by_hour.get(row["time"][11:13])
            if reading:
                row["air_estimated"] = True
        if reading:
            row.update(reading)
    return hourly


def rule_penalty(value, ideal_lo, ideal_hi, hard_lo, hard_hi):
    if value is None:
        return 0
    if ideal_lo is not None and value < ideal_lo:
        if hard_lo is None:
            return 0
        return min(100, 100 * (ideal_lo - value) / max(ideal_lo - hard_lo, 1e-9))
    if ideal_hi is not None and value > ideal_hi:
        if hard_hi is None:
            return 0
        return min(100, 100 * (value - ideal_hi) / max(hard_hi - ideal_hi, 1e-9))
    return 0


def soft_penalty(value, ideal_lo, ideal_hi, *_):
    """Small cost for drifting from the middle of the ideal range, so ideal hours still rank."""
    if value is None or ideal_hi is None:
        return 0
    lo = ideal_lo or 0
    if not lo <= value <= ideal_hi:
        return 0
    if lo == 0:  # "less is better" fields such as rain chance or wind
        return 6 * value / max(ideal_hi, 1e-9)
    half = (ideal_hi - lo) / 2
    return 6 * ((value - lo - half) / max(half, 1e-9)) ** 2


def minutes(t):
    return int(t[11:13]) * 60 + int(t[14:16])


def light_penalty(mode, hour, sun):
    """sun: {"YYYY-MM-DD": (sunrise_min, sunset_min)}"""
    rise_set = sun.get(hour["time"][:10])
    is_day = bool(hour.get("is_day"))
    if mode == "require":
        return 0 if is_day else 100
    if mode == "prefer":
        return 0 if is_day else 25
    if mode == "night":
        return 0 if not is_day else 100
    if mode == "commute":
        return 0 if int(hour["time"][11:13]) in COMMUTE_HOURS else 100
    if mode == "golden" and rise_set:
        m = minutes(hour["time"]) + 30  # centre of the hour
        gap = min(abs(m - rise_set[0]), abs(m - rise_set[1]))
        return 0 if gap <= 60 else min(100, (gap - 60) * 2)
    return 0


BLOCKED_REASON = {
    "require": "it's dark",
    "night": "it's still light",
    "golden": "it isn't golden hour",
    "commute": "it's outside commute hours (07:00–10:00, 16:00–19:00)",
}


def score_hour(activity, hour, sun):
    worst, total, soft = 0, 0, 0
    for field, *limits in activity["rules"]:
        p = rule_penalty(hour.get(field), *limits)
        worst, total = max(worst, p), total + p
        soft += soft_penalty(hour.get(field), *limits)
    light = light_penalty(activity["daylight"], hour, sun)
    if light >= 100:
        return 0
    # One bad factor should sink the hour, several mild ones add up.
    return max(0, round(100 - worst * 0.7 - total * 0.15 - light - soft))


def reasons(activity, hours):
    """Plain-language pros and cons for a window, using the same limits as the score.

    A factor only counts as a con once its penalty is noticeable, so a 97-point
    window doesn't list "windy" for a breeze that's barely over the ideal.
    """
    rule = {r[0]: r[1:] for r in activity["rules"]}
    pros, cons = [], []

    def worst(field, pick=max):
        values = [h.get(field) for h in hours if h.get(field) is not None]
        return pick(values) if values else None

    def penalty(field, value):
        return rule_penalty(value, *rule[field]) if field in rule and value is not None else 0

    t_field = "feels_like" if "feels_like" in rule else "temp" if "temp" in rule else None
    if t_field:
        t_lo, t_hi = worst(t_field, min), worst(t_field)
        temp_txt = f"{{{{t:{t_lo}}}}}" if round(t_lo) == round(t_hi) else f"{{{{t:{t_lo}}}}}–{{{{t:{t_hi}}}}}"
        ideal_lo, ideal_hi = rule[t_field][0], rule[t_field][1]
        cold, hot = penalty(t_field, t_lo), penalty(t_field, t_hi)
        if ideal_lo is not None and t_lo < ideal_lo and cold >= 15:
            cons.append(f"{'Cold' if cold >= 50 else 'Chilly'}, {temp_txt}")
        elif ideal_hi is not None and t_hi > ideal_hi and hot >= 15:
            cons.append(f"{'Hot' if hot >= 50 else 'Warm'}, {temp_txt}")
        else:
            pros.append(f"Comfortable {temp_txt}")

    rain = worst("precip_prob") or 0
    if penalty("precip_prob", rain) >= 15:
        cons.append(f"{rain}% chance of rain")
    else:
        pros.append("Dry" if rain <= 10 else f"Mostly dry ({rain}% chance)")

    if "wind_speed" in rule:
        wind_hi, wind_lo = worst("wind_speed"), worst("wind_speed", min)
        if penalty("wind_speed", wind_hi) >= 15:
            cons.append(f"Windy, {{{{w:{wind_hi}}}}}")
        elif penalty("wind_speed", wind_lo) >= 15:
            cons.append("Little breeze")
        else:
            pros.append("Good breeze" if rule["wind_speed"][0] else "Light wind")

    if "cloud_cover" in rule:
        cloud = sum(h.get("cloud_cover") or 0 for h in hours) / len(hours)
        if penalty("cloud_cover", cloud) >= 15:
            cons.append(f"{round(cloud)}% cloud")
        elif activity["daylight"] == "golden" and cloud >= 15:
            pros.append("Some clouds for colour")
        elif cloud <= 20:
            pros.append("Clear skies")

    if "humidity" in rule:
        hum = sum(h.get("humidity") or 0 for h in hours) / len(hours)
        (cons if penalty("humidity", hum) >= 15 else pros).append(f"{round(hum)}% humidity")

    if "aqi" in rule and penalty("aqi", worst("aqi")) >= 15:
        cons.append(f"Air quality: {aqi_category(worst('aqi'))['label']} (AQI {worst('aqi')})")
    if "pollen" in rule and penalty("pollen", worst("pollen")) >= 15:
        peak = max((h for h in hours if h.get("pollen") is not None), key=lambda h: h["pollen"])
        cons.append(f"{pollen_level(peak['pollen'])} {peak['pollen_type']} pollen")
    if "uv" in rule and penalty("uv", worst("uv")) >= 15:
        cons.append(f"High UV ({worst('uv'):.0f})")
    if activity["daylight"] == "golden":
        pros.append("Golden-hour light")
    return pros, cons


# ---------- Ensemble confidence ----------

def ensemble_by_time(raw):
    """Collapse ensemble members into per-hour stats.

    Returns {time: {"rain_frac": .., "temp_sd": .., "runs": n, "models": {model: rain_frac}}}.
    Keys look like "precipitation_member07_ecmwf_ifs025" or "temperature_2m_gfs025" (control run).
    """
    hourly = (raw or {}).get("hourly") or {}
    times = hourly.get("time") or []
    precip, temp = {}, {}  # key -> values
    for key, values in hourly.items():
        if key.startswith("precipitation"):
            precip[key] = values
        elif key.startswith("temperature_2m"):
            temp[key] = values

    def model_of(key, var):
        rest = key[len(var):].lstrip("_")
        parts = rest.split("_", 1)
        if parts[0].startswith("member"):
            return parts[1] if len(parts) > 1 else "ensemble"
        return rest or "ensemble"

    out = {}
    for i, t in enumerate(times):
        rain_flags, by_model = [], {}
        for key, values in precip.items():
            v = values[i]
            if v is None:
                continue
            wet = v >= 0.2
            rain_flags.append(wet)
            by_model.setdefault(model_of(key, "precipitation"), []).append(wet)
        temps = [values[i] for values in temp.values() if values[i] is not None]
        if not rain_flags:
            continue
        out[t] = {
            "rain_frac": sum(rain_flags) / len(rain_flags),
            "temp_sd": pstdev(temps) if len(temps) > 1 else 0,
            "runs": len(rain_flags),
            "models": {m: sum(f) / len(f) for m, f in by_model.items()},
        }
    return out


MODEL_NAMES = {"ecmwf_ifs025": "ECMWF", "gfs025": "GFS"}


def window_confidence(window_hours, ens):
    stats = [ens[h["time"]] for h in window_hours if h["time"] in ens]
    if not stats:
        return None
    rain = max(s["rain_frac"] for s in stats)
    temp_sd = max(s["temp_sd"] for s in stats)
    # Rain uncertainty peaks when runs split 50/50; temperature uncertainty grows with spread.
    u_rain = 4 * rain * (1 - rain)
    u_temp = min(temp_sd / 4, 1)
    value = max(0.0, 1 - 0.65 * u_rain - 0.35 * u_temp)
    level = "high" if value >= 0.75 else "medium" if value >= 0.5 else "low"

    models = {}
    for s in stats:
        for m, frac in s["models"].items():
            models[m] = max(models.get(m, 0), frac)
    runs = stats[0]["runs"]
    if len(models) >= 2 and max(models.values()) - min(models.values()) >= 0.4:
        parts = ", ".join(f"{MODEL_NAMES.get(m, m)} {round(f * 100)}%" for m, f in models.items())
        summary = f"Models disagree on rain ({parts})"
    elif rain <= 0.1:
        summary = f"{round((1 - rain) * 100)}% of {runs} forecast runs stay dry"
    elif rain >= 0.9:
        summary = f"{round(rain * 100)}% of {runs} forecast runs show rain"
    else:
        summary = f"Runs split: {round(rain * 100)}% of {runs} show rain"
    if level != "low" and temp_sd >= 2.5:
        summary += f"; temperature uncertain (±{{{{dt:{round(temp_sd, 1)}}}}})"
    return {"level": level, "value": round(value, 2), "summary": summary, "rain_runs": round(rain * 100)}


# ---------- Planning ----------

def plan(activity_key, hourly, daily, now_index, duration=None, ensemble=None, days=7, top=3):
    activity = ACTIVITIES[activity_key]
    duration = duration or activity["duration"]
    sun = {d["time"]: (minutes(d["sunrise"]), minutes(d["sunset"])) for d in daily if d.get("sunrise") and d.get("sunset")}
    ens = ensemble_by_time(ensemble) if ensemble else {}

    horizon = hourly[now_index:now_index + days * 24]
    scores = [score_hour(activity, h, sun) for h in horizon]

    windows = []
    for i in range(len(horizon) - duration + 1):
        chunk = scores[i:i + duration]
        hours = horizon[i:i + duration]
        if hours[-1]["time"][:10] != hours[0]["time"][:10] and activity["daylight"] != "night":
            continue  # don't split a daytime window across midnight
        score = round(0.6 * sum(chunk) / duration + 0.4 * min(chunk))
        windows.append((score, i))

    # Greedy pick of the best non-overlapping windows, at most one per day for variety.
    picked, used_days = [], set()
    for score, i in sorted(windows, key=lambda w: (-w[0], w[1])):
        if score < 40 or len(picked) >= top:
            break
        day = horizon[i]["time"][:10]
        if day in used_days or any(abs(i - j) < duration for _, j in picked):
            continue
        picked.append((score, i))
        used_days.add(day)

    def describe(score, i):
        hours = horizon[i:i + duration]
        pros, cons = reasons(activity, hours)
        return {
            "start": hours[0]["time"],
            "end": hours[-1]["time"][:11] + f"{(int(hours[-1]['time'][11:13]) + 1) % 24:02d}:00",
            "score": score,
            "rating": rating(score),
            "pros": pros,
            "cons": cons,
            "icon": hours[len(hours) // 2]["condition"]["icon"],
            "confidence": window_confidence(hours, ens) if ens else None,
        }

    best = [describe(s, i) for s, i in sorted(picked, key=lambda w: w[1])]
    best.sort(key=lambda w: -w["score"])
    verdict = build_verdict(activity, horizon, scores, windows, duration, sun, describe)

    # Per-day best score for the heat strip summary.
    by_day = {}
    for h, s in zip(horizon, scores):
        by_day.setdefault(h["time"][:10], []).append({"time": h["time"], "score": s})

    return {
        "activity": {"key": activity_key, "label": activity["label"], "icon": activity["icon"],
                     "verb": activity["verb"], "duration": duration},
        "verdict": verdict,
        "windows": best,
        "days": [{"date": d, "best": max(x["score"] for x in hrs), "hours": hrs} for d, hrs in by_day.items()],
        "ensemble_available": bool(ens),
    }


def build_verdict(activity, horizon, scores, windows, duration, sun, describe):
    """One clear answer for right now: go, go with care, or wait (and until when)."""
    if len(horizon) < duration:
        return None
    now_hours = horizon[:duration]
    now_scores = scores[:duration]
    now_score = round(0.6 * sum(now_scores) / duration + 0.4 * min(now_scores))
    blocked = next((BLOCKED_REASON.get(activity["daylight"]) for h in now_hours
                    if light_penalty(activity["daylight"], h, sun) >= 100), None)

    if blocked:
        status = "wait"
    elif now_score >= 70:
        status = "go"
    elif now_score >= 50:
        status = "caution"
    else:
        status = "wait"

    # Next clearly better window: the soonest one that's good in its own right and beats now.
    target = max(70, now_score + 10)
    later = [(s, i) for s, i in windows if i > 0 and s >= target]
    nxt = min(later, key=lambda w: w[1]) if later else None
    if nxt is None and status != "go":
        nxt = max(((s, i) for s, i in windows if i > 0), default=None)

    now = describe(now_score, 0)
    return {
        "status": status,
        "score": now_score,
        "blocked": blocked,
        "pros": now["pros"],
        "cons": now["cons"],
        "confidence": now["confidence"],
        "next": describe(*nxt) if nxt and nxt[0] >= 40 else None,
    }


def rating(score):
    if score >= 85:
        return "Excellent"
    if score >= 70:
        return "Good"
    if score >= 55:
        return "Fair"
    return "Poor"
