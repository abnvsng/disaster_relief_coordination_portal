"""Who may do what.

The Experiment 5 use case diagram names five actors. Django's User answers
"who are you"; UserProfile answers "in which district, at which depot, in
which role" - the three facts every LifecyclePolicy guard asks about.
"""
from django.conf import settings
from django.contrib.auth.models import User
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver


class Role(models.TextChoices):
    CITIZEN = "citizen", "Affected citizen"
    VOLUNTEER = "volunteer", "Field volunteer"
    NGO = "ngo", "NGO coordinator"
    DEPOT_MANAGER = "depot_manager", "Depot manager"
    DISTRICT_ADMIN = "district_admin", "District admin (DDMA)"


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.CITIZEN)
    phone = models.CharField(max_length=20, blank=True)
    language = models.CharField(max_length=8, default="en")
    district = models.ForeignKey(
        "geo.District", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="staff",
    )
    depot = models.ForeignKey(
        "logistics.Depot", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="managers",
    )

    class Meta:
        verbose_name = "user profile"

    def __str__(self) -> str:
        return f"{self.user.username} ({self.get_role_display()})"

    # -- capability checks used by views and templates -----------------------

    @property
    def can_verify(self) -> bool:
        return self.role in {Role.VOLUNTEER, Role.NGO, Role.DISTRICT_ADMIN}

    @property
    def can_dispatch(self) -> bool:
        return self.role in {Role.DEPOT_MANAGER, Role.DISTRICT_ADMIN}

    @property
    def can_override(self) -> bool:
        return self.role == Role.DISTRICT_ADMIN

    @property
    def sees_control_room(self) -> bool:
        return self.role != Role.CITIZEN


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def ensure_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.get_or_create(user=instance)
