"""LifecyclePolicy — the only place a ReliefRequest may change state.

This module is the source of truth transcribed by the Experiment 9 state
machine diagram. tests/test_statemachine.py fails if the two drift apart.
"""
from __future__ import annotations

from enum import Enum


class RequestState(str, Enum):
    REPORTED = "REPORTED"
    VERIFIED = "VERIFIED"
    PRIORITISED = "PRIORITISED"
    ASSIGNED = "ASSIGNED"
    IN_TRANSIT = "IN_TRANSIT"
    DELIVERED = "DELIVERED"
    CLOSED = "CLOSED"
    DUPLICATE = "DUPLICATE"
    ESCALATED = "ESCALATED"
    UNREACHABLE = "UNREACHABLE"
    CANCELLED = "CANCELLED"


S = RequestState

TERMINAL: set[RequestState] = {S.CLOSED, S.DUPLICATE, S.CANCELLED}

# source -> {target: event label}
TRANSITIONS: dict[RequestState, dict[RequestState, str]] = {
    S.REPORTED: {
        S.VERIFIED: "verify",
        S.DUPLICATE: "mark duplicate",
        S.CANCELLED: "cancel",
    },
    S.VERIFIED: {
        S.PRIORITISED: "prioritise",
        S.DUPLICATE: "mark duplicate",
        S.CANCELLED: "cancel",
    },
    S.PRIORITISED: {
        S.ASSIGNED: "assign",
        S.ESCALATED: "escalate to district",
        S.CANCELLED: "cancel",
    },
    S.ASSIGNED: {
        S.IN_TRANSIT: "depart depot",
        S.PRIORITISED: "release back to queue",
        S.CANCELLED: "cancel",
    },
    S.IN_TRANSIT: {
        S.DELIVERED: "hand over",
        S.UNREACHABLE: "could not reach",
        S.CANCELLED: "cancel",
    },
    S.UNREACHABLE: {
        S.PRIORITISED: "retry",
        S.ESCALATED: "escalate",
        S.CANCELLED: "cancel",
    },
    S.ESCALATED: {
        S.PRIORITISED: "return to queue",
        S.ASSIGNED: "re-assign",
        S.CANCELLED: "cancel",
    },
    S.DELIVERED: {
        S.CLOSED: "close",
        S.ESCALATED: "reopen on complaint",
    },
    S.CLOSED: {},
    S.DUPLICATE: {},
    S.CANCELLED: {},
}

VERIFYING_ROLES = {"volunteer", "ngo", "district_admin"}
DISPATCHING_ROLES = {"depot_manager", "district_admin"}
CANCELLING_ROLES = {"citizen", "district_admin"}


class TransitionError(Exception):
    """Raised when a move is not on the transition table, or a guard says no."""


class LifecyclePolicy:
    TRANSITIONS = TRANSITIONS
    TERMINAL = TERMINAL

    def can_transition(self, src: RequestState, dst: RequestState) -> bool:
        return dst in self.TRANSITIONS.get(src, {})

    def allowed_targets(self, src: RequestState) -> dict[RequestState, str]:
        return dict(self.TRANSITIONS.get(src, {}))

    def transition(
        self, src: RequestState, dst: RequestState, data: dict | None = None
    ) -> RequestState:
        data = data or {}
        if not self.can_transition(src, dst):
            raise TransitionError(
                f"{src.value} cannot move to {dst.value}. "
                f"Allowed: {', '.join(t.value for t in self.TRANSITIONS.get(src, {})) or 'none'}"
            )
        self._guard(src, dst, data)
        return dst

    # ------------------------------------------------------------------ guards

    def _guard(self, src: RequestState, dst: RequestState, data: dict) -> None:
        role = data.get("actor_role", "")

        if dst is S.VERIFIED and role not in VERIFYING_ROLES:
            raise TransitionError(
                "Only a volunteer, NGO coordinator or district admin can verify a report."
            )
        if dst is S.PRIORITISED and src is S.VERIFIED and not data.get("triage_score"):
            raise TransitionError("A request cannot be prioritised before it is scored.")
        if dst is S.DUPLICATE and not data.get("duplicate_of"):
            raise TransitionError("Marking a duplicate requires the surviving request id.")
        if dst is S.ASSIGNED and not data.get("dispatch_id"):
            raise TransitionError("Assign needs a dispatch with allocated stock.")
        if dst is S.DELIVERED and not data.get("proof_reference"):
            raise TransitionError("Delivery needs an OTP or a photo reference.")
        if dst is S.ESCALATED and src is S.UNREACHABLE:
            if int(data.get("unreachable_attempts", 0)) < 2:
                raise TransitionError(
                    "Escalate to the district only after two failed attempts."
                )
        if dst is S.CANCELLED and role not in CANCELLING_ROLES:
            raise TransitionError(
                "Only the reporter or a district admin can cancel a request."
            )
        if dst is S.UNREACHABLE and not data.get("note"):
            raise TransitionError("Record why the habitation could not be reached.")


policy = LifecyclePolicy()
