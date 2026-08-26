"""TriageEngine — turns a RequestContext into a score, a band and an access mode.

Deterministic and pure: same context in, same result out, no clock reads,
no database, no randomness. Every point added carries a human-readable
reason so the portal can answer "why is this request ranked above mine?".
"""
from __future__ import annotations

from .context import Household, RequestContext, SiteConditions, TriageResult
from .vocab import (
    HAZARD_WEIGHT,
    SLA_HOURS,
    AccessMode,
    NeedType,
    Priority,
    Terrain,
)

# Weight ceilings per component. They sum to 100 before adjustments.
CAP_LIFE_THREAT = 40.0
CAP_VULNERABILITY = 20.0
CAP_ISOLATION = 15.0
CAP_HAZARD = 15.0
CAP_URGENCY = 10.0
CAP_ADJUSTMENT = 10.0

BAND_RED = 70.0
BAND_ORANGE = 50.0
BAND_YELLOW = 30.0


class TriageEngine:
    """Stateless. Instantiate freely or use the module-level `engine`."""

    # ---------------------------------------------------------------- scoring

    def life_threat_score(self, ctx: RequestContext) -> tuple[float, list[str]]:
        pts, why = 0.0, []
        if ctx.people_trapped > 0:
            pts += 30.0
            why.append(f"{ctx.people_trapped} person(s) reported trapped")
        if NeedType.RSQ in ctx.needs:
            pts += 8.0
            why.append("rescue or evacuation requested")
        if NeedType.MED in ctx.needs:
            pts += 8.0
            why.append("medical assistance requested")
        depth = ctx.site.water_depth_m
        if depth >= 1.5:
            pts += 12.0
            why.append(f"water depth {depth:.1f} m, above chest height")
        elif depth >= 0.9:
            pts += 8.0
            why.append(f"water depth {depth:.1f} m, above knee height")
        elif depth >= 0.3:
            pts += 4.0
            why.append(f"water depth {depth:.1f} m")
        if NeedType.WTR in ctx.needs and ctx.site.hazard.value in {
            "HEATWAVE", "DROUGHT"
        }:
            pts += 4.0
            why.append("drinking water requested during a heat or drought event")
        return min(pts, CAP_LIFE_THREAT), why

    def vulnerability_score(self, hh: Household) -> tuple[float, list[str]]:
        pts, why = 0.0, []
        buckets = [
            (hh.infants_under_2, 3.0, "infant under 2"),
            (hh.pregnant_or_lactating, 3.0, "pregnant or lactating woman"),
            (hh.persons_with_disability, 3.0, "person with disability"),
            (hh.chronically_ill, 2.5, "chronically ill member"),
            (hh.elderly_over_60, 2.0, "member over 60"),
            (hh.children_2_to_12, 1.0, "child aged 2 to 12"),
        ]
        for count, weight, label in buckets:
            if count > 0:
                gained = min(count * weight, weight * 3)
                pts += gained
                why.append(f"{count} {label}{'s' if count > 1 else ''}")
        if hh.single_woman_headed:
            pts += 2.5
            why.append("single woman headed household")
        if not hh.has_pucca_house:
            pts += 2.5
            why.append("kutcha house, no safe structure")
        return min(pts, CAP_VULNERABILITY), why

    def isolation_score(self, site: SiteConditions) -> tuple[float, list[str]]:
        pts, why = 0.0, []
        if site.is_cut_off:
            pts += 6.0
            why.append("habitation reported cut off")
        road = {"OPEN": 0.0, "SLOW": 1.5, "BLOCKED": 4.0, "WASHED_OUT": 6.0}
        if road.get(site.road_status, 0.0):
            pts += road[site.road_status]
            why.append(f"road status {site.road_status.replace('_', ' ').lower()}")
        if site.is_island_or_char:
            pts += 3.0
            why.append("island or river char, water crossing needed")
        if site.distance_from_depot_km >= 40:
            pts += 4.0
            why.append(f"{site.distance_from_depot_km:.0f} km from the nearest depot")
        elif site.distance_from_depot_km >= 15:
            pts += 2.0
            why.append(f"{site.distance_from_depot_km:.0f} km from the nearest depot")
        if site.mobile_network == "NONE":
            pts += 3.0
            why.append("no mobile coverage, no way to call back")
        elif site.mobile_network == "2G":
            pts += 1.0
            why.append("2G only coverage")
        return min(pts, CAP_ISOLATION), why

    def hazard_score(self, site: SiteConditions) -> tuple[float, list[str]]:
        weight = HAZARD_WEIGHT.get(site.hazard, 0.5)
        severity = max(1, min(5, site.hazard_severity))
        pts = CAP_HAZARD * weight * (severity / 5.0)
        why = [
            f"{site.hazard.value.replace('_', ' ').lower()} declared at severity "
            f"{severity} of 5"
        ]
        return round(min(pts, CAP_HAZARD), 2), why

    def urgency_decay_score(self, ctx: RequestContext) -> tuple[float, list[str]]:
        """An unserved request gets more urgent, not less. One point per hour."""
        hours = ctx.age_hours()
        pts = min(hours * 1.0, CAP_URGENCY)
        if pts <= 0:
            return 0.0, []
        return round(pts, 2), [f"unserved for {hours:.1f} hours"]

    def adjustment_score(self, ctx: RequestContext) -> tuple[float, list[str]]:
        pts, why = 0.0, []
        if ctx.verified_by_volunteer:
            pts += 4.0
            why.append("confirmed on site by a volunteer")
        if ctx.corroborating_reports > 0:
            gained = min(ctx.corroborating_reports * 2.0, 4.0)
            pts += gained
            why.append(f"{ctx.corroborating_reports} corroborating report(s)")
        if ctx.stock_coverage_ratio < 0.5:
            pts += 2.0
            why.append("depot holds less than half the required kit")
        return min(pts, CAP_ADJUSTMENT), why

    # ------------------------------------------------------------ access mode

    def resolve_access_mode(self, site: SiteConditions) -> AccessMode:
        """How a truck-load of relief can physically reach this habitation."""
        if site.is_island_or_char or site.water_depth_m >= 0.6:
            return AccessMode.BOAT
        if site.road_status == "WASHED_OUT":
            if site.terrain in (Terrain.HIMALAYAN, Terrain.NORTHEAST_HILLS):
                return AccessMode.HELI if site.has_heli_pad_nearby else AccessMode.MULE_PORTER
            if site.is_cut_off:
                return AccessMode.HELI if site.has_heli_pad_nearby else AccessMode.BOAT
            return AccessMode.FOOT
        if site.road_status == "BLOCKED":
            if site.terrain in (Terrain.HIMALAYAN, Terrain.NORTHEAST_HILLS):
                return AccessMode.MULE_PORTER
            return AccessMode.FOOT
        return AccessMode.ROAD

    # ------------------------------------------------------------- classifier

    def classify(self, score: float, people_trapped: int = 0) -> Priority:
        """A trapped person is RED regardless of what the arithmetic says."""
        if people_trapped > 0:
            return Priority.RED
        if score >= BAND_RED:
            return Priority.RED
        if score >= BAND_ORANGE:
            return Priority.ORANGE
        if score >= BAND_YELLOW:
            return Priority.YELLOW
        return Priority.GREEN

    # ------------------------------------------------------------------ entry

    def score_request(self, ctx: RequestContext) -> TriageResult:
        parts = {
            "life_threat": self.life_threat_score(ctx),
            "vulnerability": self.vulnerability_score(ctx.household),
            "isolation": self.isolation_score(ctx.site),
            "hazard": self.hazard_score(ctx.site),
            "urgency_decay": self.urgency_decay_score(ctx),
            "adjustment": self.adjustment_score(ctx),
        }
        breakdown = {name: round(value, 2) for name, (value, _) in parts.items()}
        reasons: list[str] = []
        for _, (_, why) in parts.items():
            reasons.extend(why)

        raw = sum(breakdown.values())
        score = round(max(0.0, min(100.0, raw)), 2)
        priority = self.classify(score, ctx.people_trapped)
        if ctx.people_trapped > 0 and score < BAND_RED:
            reasons.append("life threat override: trapped person forces RED")

        return TriageResult(
            score=score,
            priority=priority,
            sla_hours=SLA_HOURS[priority],
            access_mode=self.resolve_access_mode(ctx.site),
            reasons=tuple(reasons),
            breakdown=breakdown,
        )


engine = TriageEngine()
