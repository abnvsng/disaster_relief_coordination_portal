"""Controlled vocabulary for the relief domain.

Framework-free. Nothing in this package may import Django.
Mirrors the enumerations in the Experiment 6 class diagram.
"""
from __future__ import annotations

from enum import Enum


class Terrain(str, Enum):
    HIMALAYAN = "HIMALAYAN"
    NORTHEAST_HILLS = "NORTHEAST_HILLS"
    GANGETIC_PLAIN = "GANGETIC_PLAIN"
    COASTAL = "COASTAL"
    ISLAND = "ISLAND"
    DESERT = "DESERT"
    DECCAN_PLATEAU = "DECCAN_PLATEAU"
    URBAN_METRO = "URBAN_METRO"


class Hazard(str, Enum):
    RIVERINE_FLOOD = "RIVERINE_FLOOD"
    FLASH_FLOOD = "FLASH_FLOOD"
    CLOUDBURST = "CLOUDBURST"
    GLOF = "GLOF"
    LANDSLIDE = "LANDSLIDE"
    CYCLONE = "CYCLONE"
    STORM_SURGE = "STORM_SURGE"
    URBAN_FLOOD = "URBAN_FLOOD"
    HEATWAVE = "HEATWAVE"
    COLD_WAVE = "COLD_WAVE"
    DROUGHT = "DROUGHT"
    EARTHQUAKE = "EARTHQUAKE"
    LIGHTNING = "LIGHTNING"


class Priority(str, Enum):
    RED = "RED"
    ORANGE = "ORANGE"
    YELLOW = "YELLOW"
    GREEN = "GREEN"


class AccessMode(str, Enum):
    ROAD = "ROAD"
    BOAT = "BOAT"
    HELI = "HELI"
    MULE_PORTER = "MULE_PORTER"
    FOOT = "FOOT"


class NeedType(str, Enum):
    WTR = "WTR"          # drinking water
    RTN = "RTN"          # dry ration
    FDR = "FDR"          # cattle fodder
    MED = "MED"          # medical
    SHL = "SHL"          # shelter / tarpaulin
    CLO = "CLO"          # clothing / blankets
    BBY = "BBY"          # infant supplies
    SAN = "SAN"          # sanitation / hygiene
    RSQ = "RSQ"          # rescue / evacuation


NEED_LABELS = {
    NeedType.WTR: "Drinking water",
    NeedType.RTN: "Dry ration",
    NeedType.FDR: "Cattle fodder",
    NeedType.MED: "Medical help",
    NeedType.SHL: "Shelter material",
    NeedType.CLO: "Blankets / clothing",
    NeedType.BBY: "Infant supplies",
    NeedType.SAN: "Sanitation kit",
    NeedType.RSQ: "Rescue / evacuation",
}


# Which hazards are physically possible on which terrain.
# Used at intake: a storm surge report from Barmer (DESERT) is rejected.
PLAUSIBLE_HAZARDS: dict[Terrain, set[Hazard]] = {
    Terrain.HIMALAYAN: {
        Hazard.FLASH_FLOOD, Hazard.CLOUDBURST, Hazard.GLOF, Hazard.LANDSLIDE,
        Hazard.EARTHQUAKE, Hazard.COLD_WAVE, Hazard.LIGHTNING, Hazard.DROUGHT,
    },
    Terrain.NORTHEAST_HILLS: {
        Hazard.FLASH_FLOOD, Hazard.CLOUDBURST, Hazard.LANDSLIDE, Hazard.EARTHQUAKE,
        Hazard.RIVERINE_FLOOD, Hazard.LIGHTNING,
    },
    Terrain.GANGETIC_PLAIN: {
        Hazard.RIVERINE_FLOOD, Hazard.FLASH_FLOOD, Hazard.HEATWAVE, Hazard.COLD_WAVE,
        Hazard.DROUGHT, Hazard.EARTHQUAKE, Hazard.LIGHTNING, Hazard.URBAN_FLOOD,
    },
    Terrain.COASTAL: {
        Hazard.CYCLONE, Hazard.STORM_SURGE, Hazard.RIVERINE_FLOOD, Hazard.URBAN_FLOOD,
        Hazard.FLASH_FLOOD, Hazard.HEATWAVE, Hazard.LIGHTNING,
    },
    Terrain.ISLAND: {
        Hazard.CYCLONE, Hazard.STORM_SURGE, Hazard.EARTHQUAKE, Hazard.FLASH_FLOOD,
    },
    Terrain.DESERT: {
        Hazard.DROUGHT, Hazard.HEATWAVE, Hazard.COLD_WAVE, Hazard.FLASH_FLOOD,
        Hazard.EARTHQUAKE, Hazard.LIGHTNING,
    },
    Terrain.DECCAN_PLATEAU: {
        Hazard.DROUGHT, Hazard.HEATWAVE, Hazard.RIVERINE_FLOOD, Hazard.FLASH_FLOOD,
        Hazard.EARTHQUAKE, Hazard.LIGHTNING,
    },
    Terrain.URBAN_METRO: {
        Hazard.URBAN_FLOOD, Hazard.HEATWAVE, Hazard.COLD_WAVE, Hazard.EARTHQUAKE,
        Hazard.CYCLONE, Hazard.LIGHTNING,
    },
}


def is_plausible(hazard: Hazard, terrain: Terrain) -> bool:
    """True when this hazard can physically occur on this terrain."""
    return hazard in PLAUSIBLE_HAZARDS.get(terrain, set())


# Baseline danger weight per hazard, 0..1. Scaled by the declared severity.
HAZARD_WEIGHT: dict[Hazard, float] = {
    Hazard.GLOF: 1.00,
    Hazard.STORM_SURGE: 0.95,
    Hazard.FLASH_FLOOD: 0.90,
    Hazard.CLOUDBURST: 0.85,
    Hazard.EARTHQUAKE: 0.95,
    Hazard.LANDSLIDE: 0.85,
    Hazard.CYCLONE: 0.85,
    Hazard.RIVERINE_FLOOD: 0.70,
    Hazard.URBAN_FLOOD: 0.55,
    Hazard.HEATWAVE: 0.50,
    Hazard.COLD_WAVE: 0.50,
    Hazard.LIGHTNING: 0.40,
    Hazard.DROUGHT: 0.35,
}


# Service level agreement per priority band, in hours.
SLA_HOURS: dict[Priority, int] = {
    Priority.RED: 2,
    Priority.ORANGE: 12,
    Priority.YELLOW: 24,
    Priority.GREEN: 72,
}
