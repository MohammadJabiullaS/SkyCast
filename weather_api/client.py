"""Async Open-Meteo client with a small in-memory TTL cache."""
import time

import httpx

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
AIR_QUALITY_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
ENSEMBLE_URL = "https://ensemble-api.open-meteo.com/v1/ensemble"


class UpstreamError(Exception):
    def __init__(self, message, status_code=502):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class TTLCache:
    def __init__(self, maxsize=512):
        self.maxsize = maxsize
        self._data = {}

    def get(self, key):
        entry = self._data.get(key)
        if entry is None:
            return None
        expires, value = entry
        if expires < time.monotonic():
            self._data.pop(key, None)
            return None
        return value

    def set(self, key, value, ttl):
        if len(self._data) >= self.maxsize:
            # Drop the entry closest to expiry.
            oldest = min(self._data, key=lambda k: self._data[k][0])
            self._data.pop(oldest, None)
        self._data[key] = (time.monotonic() + ttl, value)

    def clear(self):
        self._data.clear()


class OpenMeteoClient:
    def __init__(self, http: httpx.AsyncClient, cache: TTLCache | None = None):
        self.http = http
        self.cache = cache or TTLCache()

    async def get(self, url, params, ttl):
        key = url + "?" + "&".join(f"{k}={params[k]}" for k in sorted(params))
        cached = self.cache.get(key)
        if cached is not None:
            return cached
        try:
            resp = await self.http.get(url, params=params)
        except httpx.HTTPError as exc:
            raise UpstreamError(f"Could not reach Open-Meteo: {exc.__class__.__name__}") from exc
        if resp.status_code != 200:
            try:
                reason = resp.json().get("reason", resp.text)
            except ValueError:
                reason = resp.text
            status = 400 if resp.status_code == 400 else 502
            raise UpstreamError(f"Open-Meteo error: {reason}", status)
        data = resp.json()
        self.cache.set(key, data, ttl)
        return data
