"""Depots, what they hold, and what leaves them."""
from django.db import models
from django.utils import timezone

from domain.vocab import AccessMode
from apps.geo.models import haversine_km


class ResourceType(models.Model):
    code = models.CharField(max_length=24, unique=True)
    label = models.CharField(max_length=64)
    unit = models.CharField(max_length=16)
    unit_weight_kg = models.FloatField(default=1.0)

    class Meta:
        ordering = ["label"]

    def __str__(self) -> str:
        return self.label


class Depot(models.Model):
    district = models.ForeignKey(
        "geo.District", on_delete=models.CASCADE, related_name="depots"
    )
    name = models.CharField(max_length=96)
    latitude = models.FloatField()
    longitude = models.FloatField()
    boats_available = models.SmallIntegerField(default=0)
    trucks_available = models.SmallIntegerField(default=0)
    mules_available = models.SmallIntegerField(default=0)
    has_heli_pad = models.BooleanField(default=False)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def supports(self, mode: str) -> bool:
        """Can this depot physically serve a request needing this access mode?"""
        mode = AccessMode(mode)
        if mode is AccessMode.BOAT:
            return self.boats_available > 0
        if mode is AccessMode.ROAD:
            return self.trucks_available > 0
        if mode is AccessMode.HELI:
            return self.has_heli_pad
        if mode is AccessMode.MULE_PORTER:
            return self.mules_available > 0
        return True  # FOOT needs nothing but people

    def distance_to(self, lat: float, lon: float) -> float:
        return haversine_km(self.latitude, self.longitude, lat, lon)


class Stock(models.Model):
    depot = models.ForeignKey(Depot, on_delete=models.CASCADE, related_name="stock")
    resource = models.ForeignKey(ResourceType, on_delete=models.CASCADE)
    quantity = models.FloatField(default=0)
    reserved = models.FloatField(default=0)

    class Meta:
        unique_together = [("depot", "resource")]

    def __str__(self) -> str:
        return f"{self.resource.code} at {self.depot.name}"

    def available(self) -> float:
        return round(self.quantity - self.reserved, 3)


class Dispatch(models.Model):
    request = models.ForeignKey(
        "relief.ReliefRequest", on_delete=models.CASCADE, related_name="dispatches"
    )
    depot = models.ForeignKey(Depot, on_delete=models.PROTECT, related_name="dispatches")
    access_mode = models.CharField(max_length=16, choices=[(m.value, m.value) for m in AccessMode])
    status = models.CharField(
        max_length=16,
        choices=[("PLANNED", "Planned"), ("EN_ROUTE", "En route"),
                 ("COMPLETED", "Completed"), ("ABORTED", "Aborted")],
        default="PLANNED",
    )
    trips_planned = models.SmallIntegerField(default=1)
    payload_kg = models.FloatField(default=0)
    distance_km = models.FloatField(default=0)
    eta_hours = models.FloatField(default=0)
    proof_reference = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "dispatches"

    def __str__(self) -> str:
        return f"Dispatch #{self.pk} from {self.depot.name}"


class DispatchLine(models.Model):
    dispatch = models.ForeignKey(Dispatch, on_delete=models.CASCADE, related_name="lines")
    resource = models.ForeignKey(ResourceType, on_delete=models.PROTECT)
    quantity = models.FloatField()

    def __str__(self) -> str:
        return f"{self.quantity} {self.resource.unit} {self.resource.code}"

    def weight_kg(self) -> float:
        return round(self.quantity * self.resource.unit_weight_kg, 3)
