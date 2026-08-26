"""Administrative geography: State > District > Block > Habitation.

Habitation is the unit relief actually reaches. A block is an addressing
convenience; nobody delivers water to a block.
"""
from math import asin, cos, radians, sin, sqrt

from django.db import models

from domain.vocab import Terrain


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great circle distance. Enough precision without a PostGIS dependency."""
    r = 6371.0
    dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
    a = (
        sin(dlat / 2) ** 2
        + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    )
    return round(2 * r * asin(sqrt(a)), 2)


class State(models.Model):
    name = models.CharField(max_length=64, unique=True)
    code = models.CharField(max_length=4, unique=True)
    sdrf_helpline = models.CharField(max_length=20, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class District(models.Model):
    state = models.ForeignKey(State, on_delete=models.CASCADE, related_name="districts")
    name = models.CharField(max_length=64)
    code = models.CharField(max_length=8, unique=True)
    terrain = models.CharField(
        max_length=24, choices=[(t.value, t.value.replace("_", " ").title()) for t in Terrain]
    )
    river_basin = models.CharField(max_length=64, blank=True)
    seismic_zone = models.SmallIntegerField(default=3)
    population = models.IntegerField(default=0)
    latitude = models.FloatField()
    longitude = models.FloatField()

    class Meta:
        ordering = ["name"]
        unique_together = [("state", "name")]

    def __str__(self) -> str:
        return f"{self.name}, {self.state.code}"

    def terrain_enum(self) -> Terrain:
        return Terrain(self.terrain)


class Block(models.Model):
    district = models.ForeignKey(District, on_delete=models.CASCADE, related_name="blocks")
    name = models.CharField(max_length=64)

    class Meta:
        ordering = ["name"]
        unique_together = [("district", "name")]

    def __str__(self) -> str:
        return f"{self.name} block"


class Habitation(models.Model):
    """A village, hamlet, char island or urban ward."""

    block = models.ForeignKey(Block, on_delete=models.CASCADE, related_name="habitations")
    name = models.CharField(max_length=96)
    code = models.CharField(
        max_length=12, unique=True,
        help_text="Short code a citizen can type into an SMS, e.g. DBG012",
    )
    latitude = models.FloatField()
    longitude = models.FloatField()
    households = models.IntegerField(default=0)
    population = models.IntegerField(default=0)
    elevation_m = models.FloatField(default=0)
    is_flood_prone = models.BooleanField(default=False)
    is_island_or_char = models.BooleanField(default=False)
    has_heli_pad = models.BooleanField(default=False)
    mobile_coverage = models.CharField(
        max_length=8,
        choices=[("4G", "4G"), ("2G", "2G"), ("NONE", "No coverage")],
        default="4G",
    )

    class Meta:
        ordering = ["name"]
        indexes = [models.Index(fields=["code"])]

    def __str__(self) -> str:
        return f"{self.name} ({self.code})"

    @property
    def district(self) -> District:
        return self.block.district

    def terrain(self) -> Terrain:
        return self.block.district.terrain_enum()

    def distance_to(self, lat: float, lon: float) -> float:
        return haversine_km(self.latitude, self.longitude, lat, lon)
