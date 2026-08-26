"""Unit tests for the framework-free core.

These import no Django, touch no database and need no fixtures.
Run them alone with:  pytest tests/ -q
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from domain.allocation import AllocationPolicy
from domain.context import Household, RequestContext, SiteConditions
from domain.statemachine import (
    TERMINAL,
    TRANSITIONS,
    LifecyclePolicy,
    RequestState,
    TransitionError,
)
from domain.triage import BAND_RED, TriageEngine
from domain.vocab import AccessMode, Hazard, NeedType, Priority, Terrain, is_plausible

engine = TriageEngine()
alloc = AllocationPolicy()
policy = LifecyclePolicy()

NOW = datetime(2026, 8, 13, 6, 0, tzinfo=timezone.utc)


def ctx(**kw) -> RequestContext:
    base = dict(
        needs=frozenset({NeedType.WTR}),
        household=Household(total_members=4),
        site=SiteConditions(),
        reported_at=NOW,
        now_utc=NOW,
    )
    base.update(kw)
    return RequestContext(**base)


# --------------------------------------------------------------------- triage


def test_score_is_bounded_and_deterministic():
    c = ctx(
        people_trapped=9,
        household=Household(
            total_members=12, infants_under_2=4, elderly_over_60=4,
            persons_with_disability=3, pregnant_or_lactating=2,
            has_pucca_house=False, single_woman_headed=True,
        ),
        site=SiteConditions(
            hazard=Hazard.GLOF, hazard_severity=5, water_depth_m=2.4,
            road_status="WASHED_OUT", is_cut_off=True, mobile_network="NONE",
            distance_from_depot_km=80, terrain=Terrain.HIMALAYAN,
        ),
        now_utc=NOW + timedelta(hours=40),
    )
    first = engine.score_request(c)
    assert first.score == engine.score_request(c).score
    assert 0.0 <= first.score <= 100.0
    assert first.priority is Priority.RED


def test_trapped_person_forces_red_even_on_a_low_score():
    result = engine.score_request(ctx(people_trapped=1, needs=frozenset()))
    assert result.priority is Priority.RED
    assert result.sla_hours == 2


def test_quiet_request_lands_in_a_low_band():
    result = engine.score_request(
        ctx(site=SiteConditions(hazard=Hazard.DROUGHT, hazard_severity=1))
    )
    assert result.priority in (Priority.GREEN, Priority.YELLOW)
    assert result.score < BAND_RED


def test_unserved_request_climbs_the_queue():
    early = engine.score_request(ctx(now_utc=NOW))
    late = engine.score_request(ctx(now_utc=NOW + timedelta(hours=8)))
    assert late.score > early.score


def test_every_point_carries_a_reason():
    result = engine.score_request(
        ctx(people_trapped=2, household=Household(total_members=5, infants_under_2=1))
    )
    assert result.reasons
    assert sum(result.breakdown.values()) >= result.score - 0.01


def test_access_mode_follows_the_water():
    deep = SiteConditions(water_depth_m=0.9)
    assert engine.resolve_access_mode(deep) is AccessMode.BOAT
    char = SiteConditions(is_island_or_char=True, water_depth_m=0.0)
    assert engine.resolve_access_mode(char) is AccessMode.BOAT
    hill = SiteConditions(terrain=Terrain.HIMALAYAN, road_status="BLOCKED")
    assert engine.resolve_access_mode(hill) is AccessMode.MULE_PORTER
    fine = SiteConditions()
    assert engine.resolve_access_mode(fine) is AccessMode.ROAD


def test_hazard_must_be_possible_on_the_terrain():
    assert not is_plausible(Hazard.STORM_SURGE, Terrain.DESERT)
    assert not is_plausible(Hazard.GLOF, Terrain.GANGETIC_PLAIN)
    assert is_plausible(Hazard.RIVERINE_FLOOD, Terrain.GANGETIC_PLAIN)
    assert is_plausible(Hazard.GLOF, Terrain.HIMALAYAN)


# ----------------------------------------------------------------- allocation


def test_water_ration_and_fodder_for_a_six_member_household():
    lines = alloc.compute_kit(
        Household(total_members=6, livestock_count=6),
        {NeedType.WTR, NeedType.RTN, NeedType.FDR},
        Hazard.RIVERINE_FLOOD,
        Terrain.GANGETIC_PLAIN,
    )
    by_item = {line.item: line for line in lines}
    assert by_item["WATER_20L"].quantity == 54          # 6 x 3 L x 3 days
    assert by_item["CHLORINE_TAB"].quantity == 42       # 6 x 7 tablets
    assert by_item["DRY_RATION_KIT"].quantity == 2      # ceil(6 / 5)
    assert by_item["FODDER"].quantity == 90             # 6 x 5 kg x 3 days


def test_heat_raises_the_water_ration():
    hot = alloc.compute_kit(
        Household(total_members=6), {NeedType.WTR}, Hazard.HEATWAVE, Terrain.DESERT
    )
    assert hot[0].quantity == 90                        # 6 x 5 L x 3 days


def test_a_boat_load_splits_into_trips():
    lines = alloc.compute_kit(
        Household(total_members=40, livestock_count=20),
        {NeedType.WTR, NeedType.RTN, NeedType.FDR},
        Hazard.RIVERINE_FLOOD,
        Terrain.GANGETIC_PLAIN,
    )
    assert alloc.total_weight(lines) > 400
    assert alloc.trips_required(lines, AccessMode.BOAT) > 1
    assert alloc.trips_required(lines, AccessMode.ROAD) == 1


def test_sla_is_missed_when_the_only_route_is_a_mule():
    assert alloc.meets_sla(8, AccessMode.ROAD, sla_hours=2)
    assert not alloc.meets_sla(40, AccessMode.MULE_PORTER, sla_hours=2)


def test_cold_terrain_always_gets_bedding():
    lines = alloc.compute_kit(
        Household(total_members=3), {NeedType.WTR}, Hazard.COLD_WAVE, Terrain.HIMALAYAN
    )
    assert any(line.item == "BLANKET" for line in lines)


# --------------------------------------------------------------- state machine


def test_every_state_appears_in_the_transition_table():
    """Fails the moment the code and the Experiment 9 diagram drift apart."""
    assert set(TRANSITIONS) == set(RequestState)


def test_terminal_states_have_no_way_out():
    for state in TERMINAL:
        assert TRANSITIONS[state] == {}


def test_every_non_terminal_state_can_still_be_cancelled():
    for state, targets in TRANSITIONS.items():
        if state in TERMINAL or state is RequestState.DELIVERED:
            continue
        assert RequestState.CANCELLED in targets, state


def test_the_happy_path_walks_end_to_end():
    steps = [
        (RequestState.REPORTED, RequestState.VERIFIED, {"actor_role": "volunteer"}),
        (RequestState.VERIFIED, RequestState.PRIORITISED, {"triage_score": 61.5}),
        (RequestState.PRIORITISED, RequestState.ASSIGNED, {"dispatch_id": 7}),
        (RequestState.ASSIGNED, RequestState.IN_TRANSIT, {}),
        (RequestState.IN_TRANSIT, RequestState.DELIVERED, {"proof_reference": "OTP-4417"}),
        (RequestState.DELIVERED, RequestState.CLOSED, {}),
    ]
    for src, dst, data in steps:
        assert policy.transition(src, dst, data) is dst


def test_a_move_outside_the_table_is_refused():
    with pytest.raises(TransitionError):
        policy.transition(RequestState.REPORTED, RequestState.DELIVERED, {})


def test_a_citizen_cannot_verify_their_own_report():
    with pytest.raises(TransitionError):
        policy.transition(
            RequestState.REPORTED, RequestState.VERIFIED, {"actor_role": "citizen"}
        )


def test_delivery_without_proof_is_refused():
    with pytest.raises(TransitionError):
        policy.transition(RequestState.IN_TRANSIT, RequestState.DELIVERED, {})


def test_escalation_waits_for_two_failed_attempts():
    with pytest.raises(TransitionError):
        policy.transition(
            RequestState.UNREACHABLE,
            RequestState.ESCALATED,
            {"unreachable_attempts": 1},
        )
    assert (
        policy.transition(
            RequestState.UNREACHABLE,
            RequestState.ESCALATED,
            {"unreachable_attempts": 2},
        )
        is RequestState.ESCALATED
    )


def test_prioritise_needs_a_score():
    with pytest.raises(TransitionError):
        policy.transition(RequestState.VERIFIED, RequestState.PRIORITISED, {})
