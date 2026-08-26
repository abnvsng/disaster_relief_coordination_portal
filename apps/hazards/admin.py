from django.contrib import admin

from .models import HazardEvent


@admin.register(HazardEvent)
class HazardEventAdmin(admin.ModelAdmin):
    list_display = ("name", "hazard", "severity", "declared_at", "closed_at")
    list_filter = ("hazard", "severity")
    filter_horizontal = ("districts",)
