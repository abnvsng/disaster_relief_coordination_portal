"""A declared hazard event. Requests hang off one of these."""
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from domain.vocab import Hazard, is_plausible


class HazardEvent(models.Model):
    name = models.CharField(max_length=96)
    hazard = models.CharField(
        max_length=24,
        choices=[(h.value, h.value.replace("_", " ").title()) for h in Hazard],
    )
    severity = models.SmallIntegerField(default=3, help_text="1 (light) to 5 (severe)")
    districts = models.ManyToManyField("geo.District", related_name="hazard_events")
    declared_at = models.DateTimeField(default=timezone.now)
    closed_at = models.DateTimeField(null=True, blank=True)
    imd_warning_ref = models.CharField(
        max_length=64, blank=True, help_text="IMD or CWC bulletin reference"
    )

    class Meta:
        ordering = ["-declared_at"]

    def __str__(self) -> str:
        return f"{self.name} ({self.hazard})"

    def is_open(self) -> bool:
        return self.closed_at is None

    def hazard_enum(self) -> Hazard:
        return Hazard(self.hazard)

    def clean(self):
        if not 1 <= self.severity <= 5:
            raise ValidationError({"severity": "Severity runs from 1 to 5."})

    def implausible_districts(self):
        """Districts where this hazard cannot physically happen."""
        return [
            d for d in self.districts.all()
            if not is_plausible(self.hazard_enum(), d.terrain_enum())
        ]
