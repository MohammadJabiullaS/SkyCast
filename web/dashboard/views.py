import json
from decimal import Decimal, InvalidOperation

import httpx
from django.conf import settings
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_http_methods

from .models import FavoriteLocation

# Endpoints of the FastAPI service the browser may reach through Django.
PROXY_ENDPOINTS = {'geocode', 'weather', 'air-quality', 'history/recent', 'history/on-this-day', 'compare',
                    'activities', 'plan'}


@ensure_csrf_cookie
def index(request):
    return render(request, 'dashboard/index.html', {'page': 'dashboard'})


@ensure_csrf_cookie
def compare(request):
    return render(request, 'dashboard/compare.html', {'page': 'compare'})


@require_GET
def weather_proxy(request, endpoint):
    """Forward whitelisted GET requests to the FastAPI weather service."""
    endpoint = endpoint.strip('/')
    if endpoint not in PROXY_ENDPOINTS:
        return JsonResponse({'detail': 'Unknown endpoint'}, status=404)
    url = f"{settings.WEATHER_API_URL.rstrip('/')}/api/v1/{endpoint}"
    try:
        resp = httpx.get(url, params=request.GET, timeout=settings.WEATHER_API_TIMEOUT)
    except httpx.HTTPError:
        return JsonResponse(
            {'detail': 'Weather service is unavailable. Is the FastAPI server running on '
                       f'{settings.WEATHER_API_URL}?'},
            status=503,
        )
    try:
        payload = resp.json()
    except ValueError:
        payload = {'detail': 'Invalid response from weather service'}
    return JsonResponse(payload, status=resp.status_code, safe=False)


def _parse_favorite(data):
    try:
        lat = Decimal(str(data['latitude'])).quantize(Decimal('0.0001'))
        lon = Decimal(str(data['longitude'])).quantize(Decimal('0.0001'))
    except (KeyError, InvalidOperation, TypeError):
        raise ValueError('latitude and longitude are required numbers')
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError('coordinates out of range')
    name = str(data.get('name') or '').strip()[:120]
    if not name:
        raise ValueError('name is required')
    return {
        'name': name,
        'admin1': str(data.get('admin1') or '')[:120],
        'country': str(data.get('country') or '')[:120],
        'country_code': str(data.get('country_code') or '')[:2].upper(),
        'latitude': lat,
        'longitude': lon,
        'timezone': str(data.get('timezone') or '')[:64],
    }


@require_http_methods(['GET', 'POST'])
def favorites(request):
    if request.method == 'GET':
        return JsonResponse({'results': [f.to_dict() for f in FavoriteLocation.objects.all()]})

    try:
        fields = _parse_favorite(json.loads(request.body or b'{}'))
    except (ValueError, json.JSONDecodeError) as exc:
        return JsonResponse({'detail': str(exc)}, status=400)
    existing = FavoriteLocation.objects.filter(latitude=fields['latitude'], longitude=fields['longitude']).first()
    if existing:
        return JsonResponse(existing.to_dict(), status=200)
    last = FavoriteLocation.objects.order_by('-position').first()
    fields['position'] = (last.position + 1) if last else 0
    try:
        with transaction.atomic():
            fav = FavoriteLocation.objects.create(**fields)
    except IntegrityError:  # lost a race with a concurrent insert
        fav = FavoriteLocation.objects.get(latitude=fields['latitude'], longitude=fields['longitude'])
        return JsonResponse(fav.to_dict(), status=200)
    return JsonResponse(fav.to_dict(), status=201)


@require_http_methods(['DELETE', 'PATCH'])
def favorite_detail(request, pk):
    fav = get_object_or_404(FavoriteLocation, pk=pk)
    if request.method == 'DELETE':
        fav.delete()
        return JsonResponse({}, status=204)
    try:
        data = json.loads(request.body or b'{}')
    except json.JSONDecodeError:
        return JsonResponse({'detail': 'Invalid JSON'}, status=400)
    if 'name' in data and str(data['name']).strip():
        fav.name = str(data['name']).strip()[:120]
        fav.save(update_fields=['name'])
    return JsonResponse(fav.to_dict())


@require_http_methods(['POST'])
def reorder_favorites(request):
    try:
        ids = [int(i) for i in json.loads(request.body or b'{}').get('order', [])]
    except (ValueError, TypeError, json.JSONDecodeError):
        return JsonResponse({'detail': 'order must be a list of ids'}, status=400)
    favs = {f.id: f for f in FavoriteLocation.objects.filter(id__in=ids)}
    for position, fav_id in enumerate(ids):
        if fav_id in favs:
            favs[fav_id].position = position
    FavoriteLocation.objects.bulk_update(favs.values(), ['position'])
    return JsonResponse({'results': [f.to_dict() for f in FavoriteLocation.objects.all()]})
