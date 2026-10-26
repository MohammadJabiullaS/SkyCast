from django.urls import path

from . import views

app_name = 'dashboard'

urlpatterns = [
    path('', views.index, name='index'),
    path('compare/', views.compare, name='compare'),
    path('api/favorites/', views.favorites, name='favorites'),
    path('api/favorites/reorder/', views.reorder_favorites, name='favorites-reorder'),
    path('api/favorites/<int:pk>/', views.favorite_detail, name='favorite-detail'),
    path('api/weather/<path:endpoint>', views.weather_proxy, name='weather-proxy'),
]
