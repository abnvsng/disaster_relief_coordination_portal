"""The request itself, plus the two audit tables that keep it honest.

ReliefRequest.state is written only by ReliefService.move(), which asks
LifecyclePolicy first. Every change lands in StateLog. Every triage run
lands in TriageSnapshot. "The system decided" is never an audit answer.
"""
from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone

from domain.statemachine import RequestState
from domain.vocab import AccessMode, NeedType, Priority


class Channel(models.TextChoices):
    SMS = "SMS", "SMS"
    IVR = "IVR", "Voice / IVR"
    APP = "APP", "Volunteer app"
    WEB = "WEB", "Web form"


class ReliefRequest(models.Model):
    habitation = models.ForeignKey(
        "geo.Habitation", on_delete=models.PROTECT, related_name="requests"
    )
    hazard_event = models.ForeignKey(
        "hazards.HazardEvent", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="requests",
    )
    channel = models.CharField(max_length=4, choices=Channel.choices, default=Channel.WEB)

    # who reported, and how to answer them
    reporter = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="reports"
    )
    reporter_phone = models.CharField(max_length=20, blank=True)
    reporter_language = models.CharField(max_length=8, default="en")

    # what they asked for
    needs = models.JSONField(default=list)
    total_members = models.SmallIntegerField(default=1)
    infants_under_2 = models.SmallIntegerField(default=0)
    children_2_to_12 = models.SmallIntegerField(default=0)
    pregnant_or_lactating = models.SmallIntegerField(default=0)
    elderly_over_60 = models.SmallIntegerField(default=0)
    persons_with_disability = models.SmallIntegerField(default=0)
    chronically_ill = models.SmallIntegerField(default=0)
    livestock_count = models.SmallIntegerField(default=0)
    has_pucca_house = models.BooleanField(default=True)
    single_woman_headed = models.BooleanField(default=False)

    # what the site looks like
    road_status = models.CharField(
        max_length=12,
        choices=[("OPEN", "Open"), ("SLOW", "Slow"), ("BLOCKED", "Blocked"),
                 ("WASHED_OUT", "Washed out")],
        default="OPEN",
    )
    water_depth_m = models.FloatField(default=0)
    is_cut_off = models.BooleanField(default=False)
    people_trapped = models.SmallIntegerField(default=0)

    # what triage decided
    state = models.CharField(
        max_length=16,
        choices=[(s.value, s.value.replace("_", " ").title()) for s in RequestState],
        default=RequestState.REPORTED.value,
    )
    priority = models.CharField(
        max_length=8, choices=[(p.value, p.value) for p in Priority],
        default=Priority.GREEN.value,
    )
    triage_score = models.FloatField(default=0)
    sla_hours = models.SmallIntegerField(default=72)
    access_mode = models.CharField(
        max_length=16, choices=[(m.value, m.value) for m in AccessMode],
        default=AccessMode.ROAD.value,
    )

    # bookkeeping the lifecycle depends on
    duplicate_of = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="duplicates"
    )
    corroborating_reports = models.SmallIntegerField(default=0)
    unreachable_attempts = models.SmallIntegerField(default=0)
    verified_by_volunteer = models.BooleanField(default=False)
    priority_overridden = models.BooleanField(default=False)

    reported_at = models.DateTimeField(default=timezone.now)
    # Denormalised reported_at + sla_hours. Kept in sync by ReliefService so
    # the dashboard can find breaches with an indexed comparison instead of
    # loading every open request into Python.
    deadline = models.DateTimeField(null=True, blank=True, db_index=True)
    served_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-triage_score", "reported_at"]
        indexes = [
            # duplicate detection scans this every single intake
            models.Index(fields=["habitation", "state", "reported_at"]),
            models.Index(fields=["state", "-triage_score"]),
            models.Index(fields=["state", "deadline"]),
        ]

    def __str__(self) -> str:
        return f"Request #{self.pk} from {self.habitation.name}"

    # ------------------------------------------------------------- properties

    def state_enum(self) -> RequestState:
        return RequestState(self.state)

    def is_open(self) -> bool:
        return self.state_enum() not in {
            RequestState.CLOSED, RequestState.DUPLICATE, RequestState.CANCELLED
        }

    def need_labels(self) -> list[str]:
        from domain.vocab import NEED_LABELS
        out = []
        for code in self.needs:
            try:
                out.append(NEED_LABELS[NeedType(code)])
            except (ValueError, KeyError):
                out.append(code)
        return out

    def compute_deadline(self):
        return self.reported_at + timezone.timedelta(hours=self.sla_hours)

    def hours_left(self) -> float:
        if not self.is_open():
            return 0.0
        due = self.deadline or self.compute_deadline()
        return round((due - timezone.now()).total_seconds() / 3600, 1)

    def sla_breached(self) -> bool:
        due = self.deadline or self.compute_deadline()
        return self.is_open() and due < timezone.now()

    def latest_snapshot(self):
        return self.snapshots.order_by("-computed_at").first()


class StateLog(models.Model):
    """Append only. One row per lifecycle move, including manual overrides."""

    request = models.ForeignKey(
        ReliefRequest, on_delete=models.CASCADE, related_name="state_logs"
    )
    from_state = models.CharField(max_length=16)
    to_state = models.CharField(max_length=16)
    actor = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    actor_role = models.CharField(max_length=20, blank=True)
    note = models.CharField(max_length=240, blank=True)
    at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["at", "id"]

    def __str__(self) -> str:
        return f"#{self.request_id}: {self.from_state} -> {self.to_state}"


class TriageSnapshot(models.Model):
    """Why this score, at this moment. Never overwritten, only added to."""

    request = models.ForeignKey(
        ReliefRequest, on_delete=models.CASCADE, related_name="snapshots"
    )
    score = models.FloatField()
    priority = models.CharField(max_length=8)
    access_mode = models.CharField(max_length=16)
    sla_hours = models.SmallIntegerField()
    breakdown = models.JSONField(default=dict)
    reasons = models.JSONField(default=list)
    computed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-computed_at"]

    def __str__(self) -> str:
        return f"#{self.request_id} scored {self.score} ({self.priority})"
