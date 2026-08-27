from django.contrib import admin

from .models import Block, District, Habitation, State

admin.site.register(State)


@admin.register(District)
class DistrictAdmin(admin.ModelAdmin):
    list_display = ("name", "state", "terrain", "river_basin", "population")
    list_filter = ("state", "terrain")


@admin.register(Block)
class BlockAdmin(admin.ModelAdmin):
    list_display = ("name", "district")
    list_filter = ("district",)


@admin.register(Habitation)
class HabitationAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "block", "households", "mobile_coverage",
                    "is_island_or_char")
    list_filter = ("block__district", "mobile_coverage", "is_island_or_char")
    search_fields = ("name", "code")
