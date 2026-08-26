"""Immutable value objects handed to the domain core.

The ORM never crosses this line. ReliefService builds these from Django
models; TriageEngine, AllocationPolicy and LifecyclePolicy see only these.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from .vocab import AccessMode, Hazard, NeedType, Priority, Terrain


@dataclass(frozen=True)
class Household:
    """Counts of observable dependants. No caste, income, religion or Aadhaar."""
    total_members: int = 1
    infants_under_2: int = 0
    children_2_to_12: int = 0
    pregnant_or_lactating: int = 0
    elderly_over_60: int = 0
    persons_with_disability: int = 0
    chronically_ill: int = 0
    livestock_count: int = 0
    has_pucca_house: bool = True
    single_woman_headed: bool = False

    def dependants(self) -> int:
        return (
            self.infants_under_2
            + self.children_2_to_12
            + self.pregnant_or_lactating
            + self.elderly_over_60
            + self.persons_with_disability
            + self.chronically_ill
        )


@dataclass(frozen=True)
class SiteConditions:
    terrain: Terrain = Terrain.GANGETIC_PLAIN
    hazard: Hazard = Hazard.RIVERINE_FLOOD
    hazard_severity: int = 3          # 1..5, as declared by the district
    road_status: str = "OPEN"         # OPEN | SLOW | BLOCKED | WASHED_OUT
    water_depth_m: float = 0.0
    is_cut_off: bool = False
    mobile_network: str = "4G"        # 4G | 2G | NONE
    distance_from_depot_km: float = 0.0
    is_island_or_char: bool = False
    has_heli_pad_nearby: bool = False


@dataclass(frozen=True)
class RequestContext:
    """Everything TriageEngine is allowed to know about one request."""
    needs: frozenset[NeedType] = frozenset()
    household: Household = field(default_factory=Household)
    site: SiteConditions = field(default_factory=SiteConditions)
    reported_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    now_utc: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    people_trapped: int = 0
    verified_by_volunteer: bool = False
    corroborating_reports: int = 0
    stock_coverage_ratio: float = 1.0   # 0..1, how much of the kit the depot holds

    def age_hours(self) -> float:
        return max(0.0, (self.now_utc - self.reported_at) / timedelta(hours=1))


@dataclass(frozen=True)
class TriageResult:
    score: float
    priority: Priority
    sla_hours: int
    access_mode: AccessMode
    reasons: tuple[str, ...]
    breakdown: dict[str, float]


@dataclass(frozen=True)
class KitLine:
    item: str          # ResourceType.code
    quantity: float
    unit: str
    unit_weight_kg: float

    def weight_kg(self) -> float:
        return round(self.quantity * self.unit_weight_kg, 3)
