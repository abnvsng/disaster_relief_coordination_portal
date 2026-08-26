"""AllocationPolicy — how much material a household gets and how it travels.

Sphere-style minimums scaled to a 3 day relief cycle. Pure arithmetic:
no depot lookups, no stock reads. ReliefService supplies the numbers.
"""
from __future__ import annotations

import math

from .context import Household, KitLine
from .vocab import AccessMode, Hazard, NeedType, Terrain

RELIEF_CYCLE_DAYS = 3

# Water litres per person per day, raised when the body is losing more.
WATER_LPD_NORMAL = 3.0
WATER_LPD_HEAT = 5.0

# mode -> (average speed km/h, payload kg per trip)
TRANSPORT: dict[AccessMode, tuple[float, float]] = {
    AccessMode.ROAD: (35.0, 1500.0),
    AccessMode.BOAT: (18.0, 400.0),
    AccessMode.HELI: (180.0, 800.0),
    AccessMode.MULE_PORTER: (4.0, 80.0),
    AccessMode.FOOT: (4.0, 25.0),
}

# Fixed loading and handover overhead per trip, in hours.
TURNAROUND_H = 0.5


class AllocationPolicy:
    def compute_kit(
        self,
        household: Household,
        needs: set[NeedType] | frozenset[NeedType],
        hazard: Hazard,
        terrain: Terrain,
    ) -> list[KitLine]:
        members = max(1, household.total_members)
        lines: list[KitLine] = []

        if NeedType.WTR in needs:
            lpd = (
                WATER_LPD_HEAT
                if hazard in (Hazard.HEATWAVE, Hazard.DROUGHT)
                else WATER_LPD_NORMAL
            )
            litres = members * lpd * RELIEF_CYCLE_DAYS
            lines.append(KitLine("WATER_20L", litres, "L", 1.0))
            lines.append(
                KitLine("CHLORINE_TAB", members * 7, "tablet", 0.0005)
            )

        if NeedType.RTN in needs:
            kits = math.ceil(members / 5)
            lines.append(KitLine("DRY_RATION_KIT", kits, "kit", 15.0))

        if NeedType.FDR in needs and household.livestock_count > 0:
            fodder = household.livestock_count * 5.0 * RELIEF_CYCLE_DAYS
            lines.append(KitLine("FODDER", fodder, "kg", 1.0))

        if NeedType.MED in needs:
            lines.append(KitLine("FIRST_AID_MODULE", 1, "module", 3.0))
            lines.append(KitLine("ORS_SACHET", members * 6, "sachet", 0.02))

        if NeedType.SHL in needs:
            sheets = 1 + math.ceil(members / 5)
            lines.append(KitLine("TARPAULIN", sheets, "sheet", 4.0))

        if NeedType.CLO in needs:
            lines.append(KitLine("BLANKET", members, "piece", 1.5))

        if NeedType.BBY in needs and household.infants_under_2 > 0:
            lines.append(
                KitLine("INFANT_KIT", household.infants_under_2, "kit", 2.5)
            )

        if NeedType.SAN in needs:
            lines.append(KitLine("HYGIENE_KIT", math.ceil(members / 5), "kit", 3.0))

        # Cold terrain always gets bedding, whether or not anyone thought to ask.
        if terrain in (Terrain.HIMALAYAN, Terrain.NORTHEAST_HILLS) and not any(
            l.item == "BLANKET" for l in lines
        ):
            lines.append(KitLine("BLANKET", members, "piece", 1.5))

        return lines

    def total_weight(self, lines: list[KitLine]) -> float:
        return round(sum(line.weight_kg() for line in lines), 2)

    def trips_required(self, lines: list[KitLine], mode: AccessMode) -> int:
        weight = self.total_weight(lines)
        if weight <= 0:
            return 0
        _, payload = TRANSPORT[mode]
        return max(1, math.ceil(weight / payload))

    def eta_hours(self, km: float, mode: AccessMode, trips: int = 1) -> float:
        speed, _ = TRANSPORT[mode]
        travel = (km / speed) * (2 * trips - 1)  # last leg is one way
        return round(travel + TURNAROUND_H * trips, 2)

    def meets_sla(self, km: float, mode: AccessMode, sla_hours: int, trips: int = 1) -> bool:
        return self.eta_hours(km, mode, trips) <= sla_hours


policy = AllocationPolicy()
