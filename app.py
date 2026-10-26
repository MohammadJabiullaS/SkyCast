"""Single ASGI entrypoint for Vercel: the FastAPI weather service with the Django site mounted inside it.

Locally you can still run the two servers separately (see run.sh), or this combined app:
    uvicorn app:app --port 8000
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "web"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

from django.conf import settings  # noqa: E402
from django.core.asgi import get_asgi_application  # noqa: E402

django_app = get_asgi_application()  # also runs django.setup()

if settings.DATABASES["default"]["ENGINE"].endswith("sqlite3") and os.environ.get("VERCEL"):
    # The /tmp database starts empty on every fresh instance.
    from django.core.management import call_command
    call_command("migrate", interactive=False, verbosity=0)

from weather_api.main import app  # noqa: E402


class WeatherAlias:
    """Answer the browser's /api/weather/* calls in-process instead of via Django's HTTP proxy."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["path"].startswith("/api/weather/"):
            path = "/api/v1/" + scope["path"][len("/api/weather/"):]
            scope = {**scope, "path": path, "raw_path": path.encode()}
        await self.app(scope, receive, send)


app.add_middleware(WeatherAlias)
app.mount("/", django_app)  # everything FastAPI doesn't handle goes to Django
