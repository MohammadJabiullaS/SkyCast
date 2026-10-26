import json
from unittest import mock

import httpx
from django.test import TestCase

from .models import FavoriteLocation


class FavoritesApiTests(TestCase):
    def post(self, data):
        return self.client.post('/api/favorites/', json.dumps(data), content_type='application/json')

    def test_create_list_and_delete(self):
        r = self.post({'name': 'Oslo', 'country': 'Norway', 'country_code': 'no', 'latitude': 59.9127, 'longitude': 10.7461})
        self.assertEqual(r.status_code, 201)
        fav = r.json()
        self.assertEqual(fav['country_code'], 'NO')

        listed = self.client.get('/api/favorites/').json()['results']
        self.assertEqual([f['name'] for f in listed], ['Oslo'])

        self.assertEqual(self.client.delete(f"/api/favorites/{fav['id']}/").status_code, 204)
        self.assertFalse(FavoriteLocation.objects.exists())

    def test_duplicate_coordinates_return_existing(self):
        self.post({'name': 'Oslo', 'latitude': 59.9127, 'longitude': 10.7461})
        r = self.post({'name': 'Oslo again', 'latitude': 59.9127, 'longitude': 10.7461})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(FavoriteLocation.objects.count(), 1)

    def test_validation(self):
        self.assertEqual(self.post({'name': 'Nowhere', 'latitude': 200, 'longitude': 0}).status_code, 400)
        self.assertEqual(self.post({'latitude': 1, 'longitude': 1}).status_code, 400)

    def test_reorder(self):
        a = self.post({'name': 'A', 'latitude': 1, 'longitude': 1}).json()
        b = self.post({'name': 'B', 'latitude': 2, 'longitude': 2}).json()
        r = self.client.post('/api/favorites/reorder/', json.dumps({'order': [b['id'], a['id']]}),
                             content_type='application/json')
        self.assertEqual([f['name'] for f in r.json()['results']], ['B', 'A'])


class ProxyTests(TestCase):
    def test_unknown_endpoint_is_rejected(self):
        self.assertEqual(self.client.get('/api/weather/admin').status_code, 404)

    def test_forwards_to_fastapi(self):
        fake = httpx.Response(200, json={'results': []})
        with mock.patch('dashboard.views.httpx.get', return_value=fake) as get:
            r = self.client.get('/api/weather/geocode', {'q': 'Paris'})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(get.call_args.args[0].endswith('/api/v1/geocode'))

    def test_service_down(self):
        with mock.patch('dashboard.views.httpx.get', side_effect=httpx.ConnectError('down')):
            r = self.client.get('/api/weather/weather', {'lat': 1, 'lon': 1})
        self.assertEqual(r.status_code, 503)

    def test_pages_render(self):
        self.assertContains(self.client.get('/'), 'SkyCast')
        self.assertContains(self.client.get('/compare/'), 'Compare locations')
