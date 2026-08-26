from django.contrib import admin

from .models import ReliefRequest, StateLog, TriageSnapshot


class StateLogInline(admin.TabularInline):
    model = StateLog
    extra = 0
    readonly_fields = ("from_state", "to_state", "actor", "actor_role", "note", "at")
    can_delete = False


class TriageSnapshotInline(admin.TabularInline):
    model = TriageSnapshot
    extra = 0
    readonly_fields = ("score", "priority", "access_mode", "sla_hours",
                       "breakdown", "reasons", "computed_at")
    can_delete = False


@admin.register(ReliefRequest)
class ReliefRequestAdmin(admin.ModelAdmin):
    list_display = ("id", "habitation", "priority", "triage_score", "state",
                    "channel", "reported_at")
    list_filter = ("state", "priority", "channel", "habitation__block__district")
    search_fields = ("habitation__name", "habitation__code", "reporter_phone")
    inlines = [TriageSnapshotInline, StateLogInline]


admin.site.register(StateLog)
admin.site.register(TriageSnapshot)
