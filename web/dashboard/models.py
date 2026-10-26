from django.db import models


class FavoriteLocation(models.Model):
    name = models.CharField(max_length=120)
    admin1 = models.CharField(max_length=120, blank=True)
    country = models.CharField(max_length=120, blank=True)
    country_code = models.CharField(max_length=2, blank=True)
    latitude = models.DecimalField(max_digits=7, decimal_places=4)
    longitude = models.DecimalField(max_digits=8, decimal_places=4)
    timezone = models.CharField(max_length=64, blank=True)
    position = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['position', 'created_at']
        constraints = [
            models.UniqueConstraint(fields=['latitude', 'longitude'], name='unique_favorite_coords'),
        ]

    def __str__(self):
        return f'{self.name}, {self.country}' if self.country else self.name

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'admin1': self.admin1,
            'country': self.country,
            'country_code': self.country_code,
            'latitude': float(self.latitude),
            'longitude': float(self.longitude),
            'timezone': self.timezone,
            'position': self.position,
        }
