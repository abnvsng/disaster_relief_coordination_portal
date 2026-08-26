"""Every screen in the portal. Views orchestrate, they never decide.

A view is allowed to: check who you are, call ReliefService, and render.
It is not allowed to compute a score, pick a depot or change a state field.
"""
from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.accounts.models import Role
from apps.geo.models import District
from apps.hazards.models import HazardEvent
from apps.relief.models import ReliefRequest
from apps.relief.services import IntakeRejected, service
from domain.statemachine import RequestState, TransitionError
from domain.vocab import NEED_LABELS, NeedType

from .forms import MoveForm, OverrideForm, PublicReportForm

BAND_ORDER = ["RED", "ORANGE", "YELLOW", "GREEN"]


# ------------------------------------------------------------------- public


def public_home(request):
    open_events = HazardEvent.objects.filter(closed_at__isnull=True).prefetch_related(
        "districts"
    )
    return render(request, "portal/public_home.html", {
        "events": open_events,
        "need_labels": [(n.value, NEED_LABELS[n]) for n in NeedType],
    })


def report(request):
    """Anyone can file a report. No account, no login, no personal identifiers."""
    if request.method != "POST":
        return render(request, "portal/report.html", {"form": PublicReportForm()})

    form = PublicReportForm(request.POST)
    if not form.is_valid():
        return render(request, "portal/report.html", {"form": form})

    data = form.cleaned_data
    try:
        result = service.intake(
            habitation=form.habitation(),
            needs=data["needs"],
            channel="WEB",
            reporter=request.user if request.user.is_authenticated else None,
            reporter_phone=data["reporter_phone"],
            reporter_language=data["reporter_language"],
            **form.to_intake_kwargs(),
        )
    except IntakeRejected as exc:
        form.add_error(None, str(exc))
        return render(request, "portal/report.html", {"form": form})

    target = result.duplicate_of or result.request
    if result.created:
        messages.success(
            request, f"Report #{target.pk} recorded. Priority {target.priority}."
        )
    else:
        messages.info(
            request,
            f"A report from this habitation is already open as #{target.pk}. "
            f"Yours was added to it as corroboration.",
        )
    return redirect("track", pk=target.pk)


def track(request, pk: int):
    """What a reporter is allowed to see: their own request, no queue internals."""
    req = get_object_or_404(
        ReliefRequest.objects.select_related("habitation", "hazard_event"), pk=pk
    )
    return render(request, "portal/track.html", {
        "req": req,
        "snapshot": req.latest_snapshot(),
        "logs": req.state_logs.all(),
    })


# ------------------------------------------------------------- control room


def _scope(user):
    """A depot manager sees their district. A district admin sees theirs."""
    profile = getattr(user, "profile", None)
    return profile.district if profile and profile.district else None


@login_required
def dashboard(request):
    profile = getattr(request.user, "profile", None)
    if profile and profile.role == Role.CITIZEN:
        return redirect("my_reports")

    district = _scope(request.user)
    queue = service.ranked_queue(district=district)
    breached = service.breached(district=district)

    counts = {band: 0 for band in BAND_ORDER}
    for row in queue.values("priority").annotate(n=Count("id")):
        counts[row["priority"]] = row["n"]

    by_state = (
        ReliefRequest.objects.filter(
            **({"habitation__block__district": district} if district else {})
        )
        .values("state")
        .annotate(n=Count("id"))
        .order_by("-n")
    )

    return render(request, "portal/dashboard.html", {
        "district": district,
        "queue": queue[:12],
        "queue_size": queue.count(),
        "counts": counts,
        "breached": breached[:6],
        "breached_count": breached.count(),
        "by_state": by_state,
        "events": HazardEvent.objects.filter(closed_at__isnull=True)[:5],
    })


@login_required
def queue(request):
    """Paginated: performance testing showed an unpaginated queue rendering
    2,000 tags in ~500 ms, and a district in a real surge will exceed that."""
    district = _scope(request.user)
    band = request.GET.get("band", "")
    state = request.GET.get("state", "")

    rows = service.ranked_queue(district=district)
    if band:
        rows = rows.filter(priority=band)
    if state:
        rows = rows.filter(state=state)

    page = Paginator(rows, 50).get_page(request.GET.get("page"))
    query = request.GET.copy()
    query.pop("page", None)

    return render(request, "portal/queue.html", {
        "page": page,
        "rows": page.object_list,
        "total": page.paginator.count,
        "querystring": query.urlencode(),
        "band": band,
        "state": state,
        "states": [s.value for s in RequestState],
        "bands": BAND_ORDER,
        "district": district,
    })


@login_required
def my_reports(request):
    rows = ReliefRequest.objects.filter(reporter=request.user)
    return render(request, "portal/my_reports.html", {"rows": rows})


@login_required
def request_detail(request, pk: int):
    req = get_object_or_404(
        ReliefRequest.objects.select_related(
            "habitation", "habitation__block", "habitation__block__district", "hazard_event"
        ),
        pk=pk,
    )
    profile = getattr(request.user, "profile", None)
    depot, distance = service.nearest_depot(req)
    snapshot = req.latest_snapshot()
    breakdown = []
    if snapshot:
        caps = {"life_threat": 40, "vulnerability": 20, "isolation": 15,
                "hazard": 15, "urgency_decay": 10, "adjustment": 10}
        for key, cap in caps.items():
            value = snapshot.breakdown.get(key, 0)
            breakdown.append({
                "key": key.replace("_", " "),
                "value": value,
                "cap": cap,
                "pct": round(100 * value / cap, 1) if cap else 0,
            })

    return render(request, "portal/request_detail.html", {
        "req": req,
        "snapshot": snapshot,
        "breakdown": breakdown,
        "logs": req.state_logs.all(),
        "dispatches": req.dispatches.prefetch_related("lines__resource"),
        "moves": service.allowed_moves(req),
        "kit": service.compute_kit(req),
        "depot": depot,
        "distance": distance,
        "override_form": OverrideForm(initial={"priority": req.priority}),
        "can_verify": bool(profile and profile.can_verify),
        "can_dispatch": bool(profile and profile.can_dispatch),
        "can_override": bool(profile and profile.can_override),
    })


# ---------------------------------------------------------------- actions


@login_required
@require_POST
def move(request, pk: int):
    req = get_object_or_404(ReliefRequest, pk=pk)
    form = MoveForm(request.POST)
    if not form.is_valid():
        messages.error(request, "That action was not understood.")
        return redirect("request_detail", pk=pk)

    data = form.cleaned_data
    try:
        target = RequestState(data["to_state"])
    except ValueError:
        messages.error(request, f"{data['to_state']} is not a state.")
        return redirect("request_detail", pk=pk)

    extra = {}
    if data.get("proof_reference"):
        extra["proof_reference"] = data["proof_reference"]

    try:
        service.move(req, target, actor=request.user, note=data.get("note", ""), **extra)
    except TransitionError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f"Request #{pk} is now {target.value}.")
        if target is RequestState.PRIORITISED:
            service.run_triage(req)
    return redirect("request_detail", pk=pk)


@login_required
@require_POST
def plan_dispatch(request, pk: int):
    req = get_object_or_404(ReliefRequest, pk=pk)
    profile = getattr(request.user, "profile", None)
    if not (profile and profile.can_dispatch):
        messages.error(request, "Only a depot manager or district admin can dispatch.")
        return redirect("request_detail", pk=pk)
    try:
        dispatch = service.plan_dispatch(req)
        service.move(req, RequestState.ASSIGNED, actor=request.user,
                     note=f"Dispatch #{dispatch.pk} from {dispatch.depot.name}",
                     dispatch_id=dispatch.pk)
    except TransitionError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(
            request,
            f"Dispatch #{dispatch.pk}: {dispatch.payload_kg} kg, "
            f"{dispatch.trips_planned} trip(s) by {dispatch.access_mode}, "
            f"ETA {dispatch.eta_hours} h.",
        )
    return redirect("request_detail", pk=pk)


@login_required
@require_POST
def override(request, pk: int):
    req = get_object_or_404(ReliefRequest, pk=pk)
    profile = getattr(request.user, "profile", None)
    if not (profile and profile.can_override):
        messages.error(request, "Only a district admin can override a priority.")
        return redirect("request_detail", pk=pk)
    form = OverrideForm(request.POST)
    if not form.is_valid():
        messages.error(request, "An override needs a priority and a written reason.")
        return redirect("request_detail", pk=pk)
    service.override_priority(
        req, form.cleaned_data["priority"], actor=request.user,
        reason=form.cleaned_data["reason"],
    )
    messages.success(request, "Override recorded in the audit trail.")
    return redirect("request_detail", pk=pk)


@login_required
@require_POST
def rescore(request, pk: int):
    req = get_object_or_404(ReliefRequest, pk=pk)
    snapshot = service.run_triage(req)
    messages.success(request, f"Rescored: {snapshot.score} ({snapshot.priority}).")
    return redirect("request_detail", pk=pk)


# -------------------------------------------------------------- map feed


def map_view(request):
    return render(request, "portal/map.html", {
        "districts": District.objects.all(),
    })


def map_json(request):
    """GeoJSON for the Leaflet layer. Open data only: no phone, no reporter."""
    district_id = request.GET.get("district")
    qs = ReliefRequest.objects.select_related("habitation").filter(
        state__in=[s.value for s in RequestState if s.value not in
                   ("CLOSED", "CANCELLED", "DUPLICATE")]
    )
    if district_id:
        qs = qs.filter(habitation__block__district_id=district_id)

    features = [{
        "type": "Feature",
        "geometry": {
            "type": "Point",
            "coordinates": [r.habitation.longitude, r.habitation.latitude],
        },
        "properties": {
            "id": r.pk,
            "habitation": r.habitation.name,
            "priority": r.priority,
            "score": r.triage_score,
            "state": r.state,
            "needs": r.need_labels(),
            "access_mode": r.access_mode,
            "hours_left": r.hours_left(),
            "breached": r.sla_breached(),
        },
    } for r in qs]

    return JsonResponse({"type": "FeatureCollection", "features": features})
