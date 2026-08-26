from django.contrib import admin

from .models import Depot, Dispatch, DispatchLine, ResourceType, Stock


class StockInline(admin.TabularInline):
    model = Stock
    extra = 0


@admin.register(Depot)
class DepotAdmin(admin.ModelAdmin):
    list_display = ("name", "district", "trucks_available", "boats_available",
                    "mules_available", "has_heli_pad")
    list_filter = ("district",)
    inlines = [StockInline]


class DispatchLineInline(admin.TabularInline):
    model = DispatchLine
    extra = 0


@admin.register(Dispatch)
class DispatchAdmin(admin.ModelAdmin):
    list_display = ("id", "request", "depot", "access_mode", "status",
                    "payload_kg", "eta_hours")
    list_filter = ("status", "access_mode", "depot")
    inlines = [DispatchLineInline]


admin.site.register(ResourceType)
admin.site.register(Stock)
