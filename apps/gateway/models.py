"""Everything that leaves the portal by phone, and everything that arrives."""
from django.db import models
from django.utils import timezone


class OutboundMessage(models.Model):
    to_phone = models.CharField(max_length=20)
    body = models.TextField()
    language = models.CharField(max_length=8, default="en")
    request = models.ForeignKey(
        "relief.ReliefRequest", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="messages",
    )
    backend = models.CharField(max_length=16, default="mock")
    delivered = models.BooleanField(default=False)
    error = models.CharField(max_length=240, blank=True)
    sent_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-sent_at"]

    def __str__(self) -> str:
        return f"to {self.to_phone}: {self.body[:40]}"


class InboundMessage(models.Model):
    """Kept for idempotency: a telecom gateway retries, we must not duplicate."""

    provider_message_id = models.CharField(max_length=64, unique=True)
    from_phone = models.CharField(max_length=20)
    body = models.TextField()
    channel = models.CharField(max_length=4, default="SMS")
    request = models.ForeignKey(
        "relief.ReliefRequest", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="inbound",
    )
    accepted = models.BooleanField(default=False)
    reply = models.TextField(blank=True)
    received_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-received_at"]

    def __str__(self) -> str:
        return f"from {self.from_phone}: {self.body[:40]}"
