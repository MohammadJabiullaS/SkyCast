from pathlib import Path

STATIC_DIR = Path(__file__).resolve().parent / 'static' / 'dashboard'


def asset_version(request):
    """Cache-busting token: changes whenever a CSS/JS file is edited."""
    newest = max((p.stat().st_mtime for p in STATIC_DIR.rglob('*') if p.is_file()), default=0)
    return {'asset_version': int(newest)}
