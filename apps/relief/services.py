"""ReliefService - the seam between Django and the domain core.

Views, management commands and the SMS worker all call this. None of them
re-implement a rule. If you find domain arithmetic anywhere else in the
Django tree, it belongs here or, better, in domain/.
"""
from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings
from django.db import transaction
from django.db.models import Case, IntegerField, Value, When
from django.utils import timezone

from domain.allocation import AllocationPolicy
from domain.context import Household, RequestContext, SiteConditions
from domain.statemachine import LifecyclePolicy, RequestState, TransitionError
from domain.triage import TriageEngine
from domain.vocab import AccessMode, Hazard, NeedType, Terrain, is_plausible

from apps.geo.models import Habitation
from apps.logistics.models import Depot, Dispatch, DispatchLine, ResourceType, Stock
from apps.relief.models import Channel, ReliefRequest, StateLog, TriageSnapshot

triage_engine = TriageEngine()
allocation = AllocationPolicy()
lifecycle = LifecyclePolicy()


class IntakeRejected(Exception):
    """The report cannot become a request at all."""


@dataclass
class IntakeResult:
    request: ReliefRequest
    created: bool
    duplicate_of: ReliefRequest | None = None


class ReliefService:
    """Stateless orchestration. Safe to instantiate per request."""

    # ------------------------------------------------------------------ intake

    def default_hazard_for(self, habitation: Habitation):
        """The open hazard event covering this habitation's district, if any."""
        from apps.hazards.models import HazardEvent

        return (
            HazardEvent.objects.filter(
                districts=habitation.block.district, closed_at__isnull=True
            )
            .order_by("-severity", "-declared_at")
            .first()
        )

    def check_plausible(self, hazard: Hazard, terrain: Terrain) -> None:
        if not is_plausible(hazard, terrain):
            raise IntakeRejected(
                f"{hazard.value.replace('_', ' ').title()} does not occur on "
                f"{terrain.value.replace('_', ' ').lower()} terrain. "
                "Check the habitation code and the hazard."
            )

    def find_duplicate(self, habitation: Habitation) -> ReliefRequest | None:
        window = timezone.now() - timezone.timedelta(
            hours=settings.DUPLICATE_WINDOW_HOURS
        )
        return (
            ReliefRequest.objects.filter(
                habitation=habitation,
                reported_at__gte=window,
            )
            .exclude(state__in=[
                RequestState.CLOSED.value,
                RequestState.CANCELLED.value,
                RequestState.DUPLICATE.value,
            ])
            .order_by("reported_at")
            .first()
        )

    @transaction.atomic
    def intake(self, *, habitation: Habitation, needs: list[str], channel: str = Channel.WEB,
               reporter=None, reporter_phone: str = "", reporter_language: str = "en",
               hazard_event=None, **fields) -> IntakeResult:
        """Create a request, or fold it into an open one from the same habitation."""
        hazard_event = hazard_event or self.default_hazard_for(habitation)
        if hazard_event:
            self.check_plausible(hazard_event.hazard_enum(), habitation.terrain())

        existing = self.find_duplicate(habitation)

        request = ReliefRequest(
            habitation=habitation,
            hazard_event=hazard_event,
            channel=channel,
            reporter=reporter,
            reporter_phone=reporter_phone,
            reporter_language=reporter_language,
            needs=[str(n) for n in needs],
            **fields,
        )

        if existing:
            request.state = RequestState.DUPLICATE.value
            request.duplicate_of = existing
            request.save()
            existing.corroborating_reports += 1
            existing.save(update_fields=["corroborating_reports"])
            self._log(request, RequestState.REPORTED, RequestState.DUPLICATE,
                      note=f"Same habitation as open request #{existing.pk}")
            self.run_triage(existing)          # corroboration moves the score
            return IntakeResult(request=request, created=False, duplicate_of=existing)

        request.save()
        self._log(request, RequestState.REPORTED, RequestState.REPORTED,
                  note=f"Reported over {channel}")
        self.run_triage(request)
        return IntakeResult(request=request, created=True)

    # ------------------------------------------------------------------ triage

    @staticmethod
    def household_of(req: ReliefRequest) -> Household:
        return Household(
            total_members=req.total_members,
            infants_under_2=req.infants_under_2,
            children_2_to_12=req.children_2_to_12,
            pregnant_or_lactating=req.pregnant_or_lactating,
            elderly_over_60=req.elderly_over_60,
            persons_with_disability=req.persons_with_disability,
            chronically_ill=req.chronically_ill,
            livestock_count=req.livestock_count,
            has_pucca_house=req.has_pucca_house,
            single_woman_headed=req.single_woman_headed,
        )

    def build_context(self, req: ReliefRequest) -> RequestContext:
        habitation = req.habitation
        depot, distance = self.nearest_depot(req)
        hazard = (
            req.hazard_event.hazard_enum() if req.hazard_event else Hazard.RIVERINE_FLOOD
        )
        severity = req.hazard_event.severity if req.hazard_event else 2
        household = self.household_of(req)
        site = SiteConditions(
            terrain=habitation.terrain(),
            hazard=hazard,
            hazard_severity=severity,
            road_status=req.road_status,
            water_depth_m=req.water_depth_m,
            is_cut_off=req.is_cut_off,
            mobile_network=habitation.mobile_coverage,
            distance_from_depot_km=distance,
            is_island_or_char=habitation.is_island_or_char,
            has_heli_pad_nearby=habitation.has_heli_pad or (depot.has_heli_pad if depot else False),
        )
        return RequestContext(
            needs=frozenset(self._need_enums(req.needs)),
            household=household,
            site=site,
            reported_at=req.reported_at,
            now_utc=timezone.now(),
            people_trapped=req.people_trapped,
            verified_by_volunteer=req.verified_by_volunteer,
            corroborating_reports=req.corroborating_reports,
            stock_coverage_ratio=self.stock_coverage(req, depot),
        )

    def run_triage(self, req: ReliefRequest) -> TriageSnapshot:
        """Score the request, persist the answer and the reasons behind it."""
        result = triage_engine.score_request(self.build_context(req))

        req.triage_score = result.score
        req.sla_hours = result.sla_hours
        req.access_mode = result.access_mode.value
        if not req.priority_overridden:
            req.priority = result.priority.value
        req.deadline = req.compute_deadline()
        req.save(update_fields=[
            "triage_score", "sla_hours", "access_mode", "priority", "deadline"
        ])

        return TriageSnapshot.objects.create(
            request=req,
            score=result.score,
            priority=result.priority.value,
            access_mode=result.access_mode.value,
            sla_hours=result.sla_hours,
            breakdown=result.breakdown,
            reasons=list(result.reasons),
        )

    # --------------------------------------------------------------- lifecycle

    @transaction.atomic
    def move(self, req: ReliefRequest, to_state: RequestState, *, actor=None,
             note: str = "", **data) -> ReliefRequest:
        """The only writer of ReliefRequest.state anywhere in the codebase."""
        src = req.state_enum()
        role = ""
        if actor is not None and getattr(actor, "is_authenticated", False):
            role = getattr(getattr(actor, "profile", None), "role", "")

        payload = {
            "actor_role": role,
            "triage_score": req.triage_score,
            "duplicate_of": req.duplicate_of_id,
            "unreachable_attempts": req.unreachable_attempts,
            "note": note,
            **data,
        }
        if to_state is RequestState.ASSIGNED and "dispatch_id" not in payload:
            latest = req.dispatches.order_by("-created_at").first()
            payload["dispatch_id"] = latest.pk if latest else None
        if to_state is RequestState.DELIVERED and "proof_reference" not in payload:
            latest = req.dispatches.order_by("-created_at").first()
            payload["proof_reference"] = latest.proof_reference if latest else ""

        lifecycle.transition(src, to_state, payload)   # raises TransitionError

        req.state = to_state.value
        self._on_enter(req, to_state, payload)
        req.save()
        self._log(req, src, to_state, actor=actor, actor_role=role, note=note)
        return req

    def _on_enter(self, req: ReliefRequest, state: RequestState, data: dict) -> None:
        """Entry actions transcribed from the Experiment 9 state machine."""
        now = timezone.now()
        if state is RequestState.VERIFIED:
            req.verified_by_volunteer = True
        elif state is RequestState.UNREACHABLE:
            req.unreachable_attempts += 1
            for dispatch in req.dispatches.filter(status="EN_ROUTE"):
                dispatch.status = "ABORTED"
                dispatch.save(update_fields=["status"])
        elif state is RequestState.IN_TRANSIT:
            req.dispatches.filter(status="PLANNED").update(status="EN_ROUTE")
        elif state is RequestState.DELIVERED:
            req.served_at = now
            self.release_reservations(req, completed=True)
        elif state is RequestState.CLOSED:
            req.closed_at = now
        elif state in (RequestState.CANCELLED, RequestState.DUPLICATE):
            req.closed_at = now
            self.release_reservations(req, completed=False)

    def allowed_moves(self, req: ReliefRequest) -> dict[RequestState, str]:
        return lifecycle.allowed_targets(req.state_enum())

    def override_priority(self, req: ReliefRequest, priority: str, *, actor, reason: str):
        """A human outranks the engine, but never silently.

        The computed score is left untouched; the override is an audit entry,
        so the original ranking stays reconstructable.
        """
        if not reason.strip():
            raise TransitionError("An override needs a recorded reason.")
        before = req.priority
        req.priority = priority
        req.priority_overridden = True
        req.save(update_fields=["priority", "priority_overridden"])
        self._log(
            req, req.state_enum(), req.state_enum(), actor=actor,
            actor_role=getattr(getattr(actor, "profile", None), "role", ""),
            note=f"Priority {before} -> {priority}. {reason.strip()}",
        )
        return req

    # -------------------------------------------------------------- fulfilment

    def nearest_depot(self, req: ReliefRequest, mode: str | None = None):
        """Closest depot in the district that can serve the required access mode."""
        habitation = req.habitation
        depots = list(Depot.objects.filter(district=habitation.block.district))
        if not depots:
            return None, 0.0
        ranked = sorted(
            depots, key=lambda d: d.distance_to(habitation.latitude, habitation.longitude)
        )
        mode = mode or req.access_mode
        for depot in ranked:
            if depot.supports(mode):
                return depot, depot.distance_to(habitation.latitude, habitation.longitude)
        best = ranked[0]
        return best, best.distance_to(habitation.latitude, habitation.longitude)

    def compute_kit(self, req: ReliefRequest):
        household = self.household_of(req)
        hazard = req.hazard_event.hazard_enum() if req.hazard_event else Hazard.RIVERINE_FLOOD
        return allocation.compute_kit(
            household, set(self._need_enums(req.needs)), hazard, req.habitation.terrain()
        )

    def stock_coverage(self, req: ReliefRequest, depot: Depot | None) -> float:
        """Fraction of the requested kit the depot can actually hand over."""
        if depot is None:
            return 0.0
        lines = self.compute_kit(req)
        if not lines:
            return 1.0
        held, wanted = 0.0, 0.0
        stock = {s.resource.code: s for s in depot.stock.select_related("resource")}
        for line in lines:
            wanted += line.quantity
            entry = stock.get(line.item)
            held += min(line.quantity, entry.available()) if entry else 0.0
        return round(held / wanted, 3) if wanted else 1.0

    @transaction.atomic
    def plan_dispatch(self, req: ReliefRequest) -> Dispatch:
        """Pick a depot, cut the kit, reserve the stock, size the trips."""
        mode = AccessMode(req.access_mode)
        depot, distance = self.nearest_depot(req, mode.value)
        if depot is None:
            raise TransitionError(
                f"No depot in {req.habitation.block.district.name} can serve this "
                f"request. Escalate to the state SDRF."
            )
        if not depot.supports(mode.value):
            raise TransitionError(
                f"{depot.name} has no {mode.value.lower().replace('_', ' ')} capacity. "
                "Escalate to the state SDRF."
            )

        lines = self.compute_kit(req)
        if not lines:
            raise TransitionError("Nothing to send: the request lists no material needs.")

        trips = allocation.trips_required(lines, mode)
        dispatch = Dispatch.objects.create(
            request=req,
            depot=depot,
            access_mode=mode.value,
            trips_planned=trips,
            payload_kg=allocation.total_weight(lines),
            distance_km=distance,
            eta_hours=allocation.eta_hours(distance, mode, trips),
        )
        for line in lines:
            resource, _ = ResourceType.objects.get_or_create(
                code=line.item,
                defaults={"label": line.item.replace("_", " ").title(),
                          "unit": line.unit, "unit_weight_kg": line.unit_weight_kg},
            )
            DispatchLine.objects.create(
                dispatch=dispatch, resource=resource, quantity=line.quantity
            )
            stock, _ = Stock.objects.get_or_create(depot=depot, resource=resource)
            stock.reserved = round(stock.reserved + min(line.quantity, stock.available()), 3)
            stock.save(update_fields=["reserved"])
        return dispatch

    def release_reservations(self, req: ReliefRequest, *, completed: bool) -> None:
        """Delivered stock leaves the depot. Cancelled stock goes back on the shelf."""
        for dispatch in req.dispatches.exclude(status__in=["COMPLETED", "ABORTED"]):
            for line in dispatch.lines.select_related("resource"):
                stock = Stock.objects.filter(
                    depot=dispatch.depot, resource=line.resource
                ).first()
                if not stock:
                    continue
                stock.reserved = max(0.0, round(stock.reserved - line.quantity, 3))
                if completed:
                    stock.quantity = max(0.0, round(stock.quantity - line.quantity, 3))
                stock.save(update_fields=["reserved", "quantity"])
            dispatch.status = "COMPLETED" if completed else "ABORTED"
            dispatch.save(update_fields=["status"])

    # ------------------------------------------------------------------ queues

    # Priority is a label, not a sort key: RED must outrank ORANGE regardless
    # of score. This puts that ordering in the database so the queue can be
    # paginated with LIMIT/OFFSET instead of sorted in Python.
    BAND_RANK = Case(
        When(priority="RED", then=Value(0)),
        When(priority="ORANGE", then=Value(1)),
        When(priority="YELLOW", then=Value(2)),
        When(priority="GREEN", then=Value(3)),
        default=Value(9),
        output_field=IntegerField(),
    )

    def ranked_queue(self, district=None, states=None):
        qs = ReliefRequest.objects.select_related(
            "habitation", "habitation__block", "habitation__block__district", "hazard_event"
        )
        states = states or [
            RequestState.REPORTED.value, RequestState.VERIFIED.value,
            RequestState.PRIORITISED.value, RequestState.ASSIGNED.value,
            RequestState.IN_TRANSIT.value, RequestState.UNREACHABLE.value,
            RequestState.ESCALATED.value,
        ]
        qs = qs.filter(state__in=states)
        if district is not None:
            qs = qs.filter(habitation__block__district=district)
        return qs.annotate(band_rank=self.BAND_RANK).order_by(
            "band_rank", "-triage_score", "reported_at"
        )

    def breached(self, district=None):
        """Open requests past their deadline, found with an indexed compare."""
        return self.ranked_queue(district=district).filter(
            deadline__lt=timezone.now()
        )

    def sla_breached(self, req: ReliefRequest) -> bool:
        return req.sla_breached()

    # ------------------------------------------------------------------ helper

    @staticmethod
    def _need_enums(codes) -> list[NeedType]:
        out = []
        for code in codes or []:
            try:
                out.append(NeedType(str(code).upper()))
            except ValueError:
                continue
        return out

    @staticmethod
    def _log(req, src, dst, *, actor=None, actor_role="", note=""):
        StateLog.objects.create(
            request=req,
            from_state=src.value if hasattr(src, "value") else str(src),
            to_state=dst.value if hasattr(dst, "value") else str(dst),
            actor=actor if actor is not None and getattr(actor, "is_authenticated", False) else None,
            actor_role=actor_role,
            note=note[:240],
        )


service = ReliefService()
