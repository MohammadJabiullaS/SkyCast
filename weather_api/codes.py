"""WMO weather interpretation codes used by Open-Meteo."""

# code -> (description, theme, day icon, night icon)
WMO_CODES = {
    0: ("Clear sky", "clear", "☀️", "🌙"),
    1: ("Mainly clear", "clear", "🌤️", "🌙"),
    2: ("Partly cloudy", "partly", "⛅", "☁️"),
    3: ("Overcast", "cloudy", "☁️", "☁️"),
    45: ("Fog", "fog", "🌫️", "🌫️"),
    48: ("Depositing rime fog", "fog", "🌫️", "🌫️"),
    51: ("Light drizzle", "drizzle", "🌦️", "🌧️"),
    53: ("Moderate drizzle", "drizzle", "🌦️", "🌧️"),
    55: ("Dense drizzle", "drizzle", "🌧️", "🌧️"),
    56: ("Light freezing drizzle", "drizzle", "🌧️", "🌧️"),
    57: ("Dense freezing drizzle", "drizzle", "🌧️", "🌧️"),
    61: ("Slight rain", "rain", "🌦️", "🌧️"),
    63: ("Moderate rain", "rain", "🌧️", "🌧️"),
    65: ("Heavy rain", "rain", "🌧️", "🌧️"),
    66: ("Light freezing rain", "rain", "🌧️", "🌧️"),
    67: ("Heavy freezing rain", "rain", "🌧️", "🌧️"),
    71: ("Slight snowfall", "snow", "🌨️", "🌨️"),
    73: ("Moderate snowfall", "snow", "🌨️", "🌨️"),
    75: ("Heavy snowfall", "snow", "❄️", "❄️"),
    77: ("Snow grains", "snow", "🌨️", "🌨️"),
    80: ("Slight rain showers", "rain", "🌦️", "🌧️"),
    81: ("Moderate rain showers", "rain", "🌧️", "🌧️"),
    82: ("Violent rain showers", "rain", "⛈️", "⛈️"),
    85: ("Slight snow showers", "snow", "🌨️", "🌨️"),
    86: ("Heavy snow showers", "snow", "❄️", "❄️"),
    95: ("Thunderstorm", "storm", "⛈️", "⛈️"),
    96: ("Thunderstorm with slight hail", "storm", "⛈️", "⛈️"),
    99: ("Thunderstorm with heavy hail", "storm", "⛈️", "⛈️"),
}


def describe(code, is_day=True):
    """Return a display-ready description of a WMO code."""
    text, theme, day_icon, night_icon = WMO_CODES.get(code, ("Unknown", "cloudy", "❔", "❔"))
    return {
        "code": code,
        "text": text,
        "theme": theme,
        "icon": day_icon if is_day else night_icon,
    }


US_AQI_LEVELS = [
    (50, "Good", "#22c55e", "Air quality is great. Enjoy outdoor activities."),
    (100, "Moderate", "#eab308", "Unusually sensitive people should limit prolonged exertion outdoors."),
    (150, "Unhealthy for sensitive groups", "#f97316", "Sensitive groups should reduce prolonged outdoor exertion."),
    (200, "Unhealthy", "#ef4444", "Everyone should reduce prolonged outdoor exertion."),
    (300, "Very unhealthy", "#a855f7", "Avoid outdoor exertion; keep windows closed."),
    (10_000, "Hazardous", "#7f1d1d", "Health warning: everyone should avoid outdoor activity."),
]


def aqi_category(us_aqi):
    if us_aqi is None:
        return {"label": "Unavailable", "color": "#64748b", "advice": "No air quality data for this location."}
    for limit, label, color, advice in US_AQI_LEVELS:
        if us_aqi <= limit:
            return {"label": label, "color": color, "advice": advice}
