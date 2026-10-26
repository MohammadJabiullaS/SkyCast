from django.contrib import admin

from .models import FavoriteLocation


@admin.register(FavoriteLocation)
class FavoriteLocationAdmin(admin.ModelAdmin):
    list_display = ('name', 'admin1', 'country', 'latitude', 'longitude', 'position', 'created_at')
    list_editable = ('position',)
    search_fields = ('name', 'country', 'admin1')
