"""Integration tests: Django, the ORM and the domain core together.

The unit tests in tests/ prove the rules. These prove the wiring.
"""
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role, UserProfile
from apps.gateway.models import OutboundMessage
from apps.gateway.services import handle_inbound
from apps.geo.models import Block, District, Habitation, State
from apps.hazards.models import HazardEvent
from apps.logistics.models import Depot, ResourceType, Stock
from apps.relief.models import ReliefRequest, StateLog
from apps.relief.services import IntakeRejected, service
from domain.statemachine import RequestState, TransitionError

PASSWORD = "test-pass-2026"


def make_geography():
    state = State.objects.create(name="Bihar", code="BR")
    district = District.objects.create(
        state=state, name="Darbhanga", code="DBG", terrain="GANGETIC_PLAIN",
        latitude=26.15, longitude=85.89,
    )
    block = Block.objects.create(district=district, name="Kiratpur")
    habitation = Habitation.objects.create(
        block=block, name="Bahadurpur Diara", code="DBG012",
        latitude=26.28, longitude=86.06, households=210, mobile_coverage="2G",
        is_island_or_char=True,
    )
    depot = Depot.objects.create(
        district=district, name="Kiratpur godown", latitude=26.21, longitude=86.01,
        boats_available=4, trucks_available=6,
    )
    for code, unit, weight in [
        ("WATER_20L", "L", 1.0), ("CHLORINE_TAB", "tablet", 0.0005),
        ("DRY_RATION_KIT", "kit", 15.0), ("FODDER", "kg", 1.0),
    ]:
        resource = ResourceType.objects.create(
            code=code, label=code.title(), unit=unit, unit_weight_kg=weight
        )
        Stock.objects.create(depot=depot, resource=resource, quantity=10000)
    return district, habitation, depot


def make_user(username, role, district=None):
    user = User.objects.create_user(username=username, password=PASSWORD)
    UserProfile.objects.update_or_create(
        user=user, defaults={"role": role, "district": district}
    )
    # Re-fetch: the post_save signal cached a citizen profile on this instance.
    return User.objects.get(pk=user.pk)


class SmsIntakeTests(TestCase):
    def setUp(self):
        self.district, self.habitation, self.depot = make_geography()
        event = HazardEvent.objects.create(
            name="Kosi flood", hazard="RIVERINE_FLOOD", severity=4
        )
        event.districts.add(self.district)

    def test_a_valid_sms_becomes_a_scored_request_with_an_acknowledgement(self):
        result = handle_inbound(
            from_phone="+919000000001",
            body="HELP DBG012 6 WTR,RTN,FDR 90 0",
            provider_message_id="SM-1",
            language="hi",
        )
        self.assertTrue(result.accepted)

        req = ReliefRequest.objects.get()
        self.assertEqual(req.total_members, 6)
        self.assertEqual(req.water_depth_m, 0.9)
        self.assertEqual(sorted(req.needs), ["FDR", "RTN", "WTR"])
        self.assertGreater(req.triage_score, 0)
        self.assertEqual(req.access_mode, "BOAT")     # 0.9 m of water, char island
        self.assertTrue(req.snapshots.exists())

        ack = OutboundMessage.objects.get()
        self.assertIn(str(req.pk), ack.body)
        self.assertEqual(ack.language, "hi")

    def test_a_malformed_sms_gets_format_help_and_files_nothing(self):
        result = handle_inbound(
            from_phone="+919000000002", body="pls send water",
            provider_message_id="SM-2",
        )
        self.assertFalse(result.accepted)
        self.assertIn("HELP", result.reply)
        self.assertEqual(ReliefRequest.objects.count(), 0)

    def test_an_unknown_habitation_code_is_refused(self):
        result = handle_inbound(
            from_phone="+919000000003", body="HELP ZZZ999 4 WTR",
            provider_message_id="SM-3",
        )
        self.assertFalse(result.accepted)
        self.assertEqual(ReliefRequest.objects.count(), 0)

    def test_a_retried_delivery_does_not_file_the_report_twice(self):
        body = "HELP DBG012 5 WTR,RTN"
        first = handle_inbound(from_phone="+91900", body=body, provider_message_id="SM-4")
        second = handle_inbound(from_phone="+91900", body=body, provider_message_id="SM-4")
        self.assertEqual(ReliefRequest.objects.count(), 1)
        self.assertEqual(first.reply, second.reply)

    def test_a_second_report_from_the_same_habitation_corroborates_the_first(self):
        handle_inbound(from_phone="+91901", body="HELP DBG012 5 WTR", provider_message_id="A")
        handle_inbound(from_phone="+91902", body="HELP DBG012 8 WTR,MED", provider_message_id="B")

        surviving = ReliefRequest.objects.exclude(state="DUPLICATE").get()
        duplicate = ReliefRequest.objects.get(state="DUPLICATE")
        self.assertEqual(duplicate.duplicate_of_id, surviving.pk)
        self.assertEqual(surviving.corroborating_reports, 1)

    def test_an_implausible_hazard_for_the_terrain_is_rejected_at_intake(self):
        rajasthan = State.objects.create(name="Rajasthan", code="RJ")
        barmer = District.objects.create(
            state=rajasthan, name="Barmer", code="BMR", terrain="DESERT",
            latitude=25.75, longitude=71.38,
        )
        block = Block.objects.create(district=barmer, name="Chohtan")
        hab = Habitation.objects.create(
            block=block, name="Bakhasar", code="BMR006", latitude=24.91, longitude=70.95
        )
        surge = HazardEvent.objects.create(
            name="Storm surge", hazard="STORM_SURGE", severity=4
        )
        surge.districts.add(barmer)

        with self.assertRaises(IntakeRejected):
            service.intake(habitation=hab, needs=["WTR"], total_members=4)


class LifecycleTests(TestCase):
    def setUp(self):
        self.district, self.habitation, self.depot = make_geography()
        event = HazardEvent.objects.create(
            name="Kosi flood", hazard="RIVERINE_FLOOD", severity=4
        )
        event.districts.add(self.district)
        self.volunteer = make_user("ravi", Role.VOLUNTEER, self.district)
        self.manager = make_user("depot", Role.DEPOT_MANAGER, self.district)
        self.admin = make_user("ddma", Role.DISTRICT_ADMIN, self.district)
        self.req = service.intake(
            habitation=self.habitation, needs=["WTR", "RTN", "FDR"],
            total_members=6, livestock_count=6, water_depth_m=0.9,
            reporter_phone="+919000000001",
        ).request

    def test_the_full_path_from_report_to_closed(self):
        service.move(self.req, RequestState.VERIFIED, actor=self.volunteer)
        service.move(self.req, RequestState.PRIORITISED, actor=self.admin)

        dispatch = service.plan_dispatch(self.req)
        self.assertEqual(dispatch.access_mode, "BOAT")
        self.assertGreater(dispatch.payload_kg, 0)
        self.assertEqual(dispatch.depot, self.depot)

        service.move(self.req, RequestState.ASSIGNED, actor=self.manager,
                     dispatch_id=dispatch.pk)
        service.move(self.req, RequestState.IN_TRANSIT, actor=self.manager)
        service.move(self.req, RequestState.DELIVERED, actor=self.manager,
                     proof_reference="OTP-4417")
        service.move(self.req, RequestState.CLOSED, actor=self.admin)

        self.req.refresh_from_db()
        self.assertEqual(self.req.state, "CLOSED")
        self.assertIsNotNone(self.req.served_at)
        self.assertIsNotNone(self.req.closed_at)
        self.assertEqual(StateLog.objects.filter(request=self.req).count(), 7)

    def test_delivered_stock_leaves_the_depot_and_the_reservation_clears(self):
        water = ResourceType.objects.get(code="WATER_20L")
        before = Stock.objects.get(depot=self.depot, resource=water).quantity

        service.move(self.req, RequestState.VERIFIED, actor=self.volunteer)
        service.move(self.req, RequestState.PRIORITISED, actor=self.admin)
        dispatch = service.plan_dispatch(self.req)

        reserved = Stock.objects.get(depot=self.depot, resource=water).reserved
        self.assertEqual(reserved, 54)          # 6 people x 3 L x 3 days

        service.move(self.req, RequestState.ASSIGNED, actor=self.manager,
                     dispatch_id=dispatch.pk)
        service.move(self.req, RequestState.IN_TRANSIT, actor=self.manager)
        service.move(self.req, RequestState.DELIVERED, actor=self.manager,
                     proof_reference="OTP-1")

        stock = Stock.objects.get(depot=self.depot, resource=water)
        self.assertEqual(stock.reserved, 0)
        self.assertEqual(stock.quantity, before - 54)

    def test_a_cancelled_request_puts_the_stock_back(self):
        water = ResourceType.objects.get(code="WATER_20L")
        before = Stock.objects.get(depot=self.depot, resource=water).quantity
        service.move(self.req, RequestState.VERIFIED, actor=self.volunteer)
        service.move(self.req, RequestState.PRIORITISED, actor=self.admin)
        dispatch = service.plan_dispatch(self.req)
        service.move(self.req, RequestState.ASSIGNED, actor=self.manager,
                     dispatch_id=dispatch.pk)
        service.move(self.req, RequestState.CANCELLED, actor=self.admin,
                     note="reporter withdrew")

        stock = Stock.objects.get(depot=self.depot, resource=water)
        self.assertEqual(stock.reserved, 0)
        self.assertEqual(stock.quantity, before)

    def test_escalation_needs_two_failed_attempts(self):
        service.move(self.req, RequestState.VERIFIED, actor=self.volunteer)
        service.move(self.req, RequestState.PRIORITISED, actor=self.admin)
        dispatch = service.plan_dispatch(self.req)
        service.move(self.req, RequestState.ASSIGNED, actor=self.manager,
                     dispatch_id=dispatch.pk)
        service.move(self.req, RequestState.IN_TRANSIT, actor=self.manager)
        service.move(self.req, RequestState.UNREACHABLE, actor=self.manager,
                     note="current too strong")

        with self.assertRaises(TransitionError):
            service.move(self.req, RequestState.ESCALATED, actor=self.admin)

        service.move(self.req, RequestState.PRIORITISED, actor=self.admin)
        dispatch = service.plan_dispatch(self.req)
        service.move(self.req, RequestState.ASSIGNED, actor=self.manager,
                     dispatch_id=dispatch.pk)
        service.move(self.req, RequestState.IN_TRANSIT, actor=self.manager)
        service.move(self.req, RequestState.UNREACHABLE, actor=self.manager,
                     note="boat turned back again")
        service.move(self.req, RequestState.ESCALATED, actor=self.admin)

        self.req.refresh_from_db()
        self.assertEqual(self.req.state, "ESCALATED")
        self.assertEqual(self.req.unreachable_attempts, 2)

    def test_an_override_is_recorded_and_never_rewrites_the_score(self):
        score_before = self.req.triage_score
        service.override_priority(
            self.req, "RED", actor=self.admin, reason="ANM confirmed cardiac case"
        )
        self.req.refresh_from_db()
        self.assertEqual(self.req.priority, "RED")
        self.assertEqual(self.req.triage_score, score_before)
        log = StateLog.objects.filter(request=self.req).last()
        self.assertIn("ANM confirmed cardiac case", log.note)

    def test_an_override_survives_a_rescore(self):
        service.override_priority(self.req, "RED", actor=self.admin, reason="officer call")
        service.run_triage(self.req)
        self.req.refresh_from_db()
        self.assertEqual(self.req.priority, "RED")

    def test_a_trapped_person_reaches_the_top_of_the_queue(self):
        calm = service.intake(
            habitation=self.habitation, needs=["RTN"], total_members=3
        )
        trapped = ReliefRequest.objects.create(
            habitation=self.habitation, needs=["RSQ"], total_members=4,
            people_trapped=4, reported_at=timezone.now(),
        )
        service.run_triage(trapped)
        queue = service.ranked_queue(district=self.district)
        self.assertEqual(queue[0].pk, trapped.pk)
        self.assertEqual(queue[0].priority, "RED")


class ViewTests(TestCase):
    def setUp(self):
        self.district, self.habitation, self.depot = make_geography()
        self.admin = make_user("ddma", Role.DISTRICT_ADMIN, self.district)
        self.req = service.intake(
            habitation=self.habitation, needs=["WTR"], total_members=4
        ).request

    def test_public_pages_open_without_an_account(self):
        for name, args in [("public_home", []), ("report", []),
                           ("track", [self.req.pk]), ("sms_simulator", [])]:
            self.assertEqual(self.client.get(reverse(name, args=args)).status_code, 200)

    def test_the_control_room_is_closed_to_anonymous_visitors(self):
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response["Location"])

    def test_a_signed_in_officer_sees_the_queue_and_the_detail_page(self):
        self.client.login(username="ddma", password=PASSWORD)
        for name, args in [("dashboard", []), ("queue", []), ("map", []),
                           ("request_detail", [self.req.pk])]:
            self.assertEqual(self.client.get(reverse(name, args=args)).status_code, 200)

    def test_the_map_feed_carries_no_reporter_details(self):
        response = self.client.get(reverse("map_json"))
        payload = response.json()
        self.assertEqual(payload["type"], "FeatureCollection")
        self.assertTrue(payload["features"])
        properties = payload["features"][0]["properties"]
        self.assertNotIn("reporter_phone", properties)
        self.assertIn("priority", properties)

    def test_the_public_report_form_files_a_request(self):
        response = self.client.post(reverse("report"), {
            "habitation_code": "DBG012", "needs": ["WTR", "RTN"],
            "total_members": 5, "infants_under_2": 1, "children_2_to_12": 0,
            "pregnant_or_lactating": 0, "elderly_over_60": 1,
            "persons_with_disability": 0, "chronically_ill": 0,
            "livestock_count": 0, "road_status": "BLOCKED",
            "people_trapped": 0, "water_depth_cm": 40,
            "reporter_phone": "+919000000009", "reporter_language": "en",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ReliefRequest.objects.count(), 2)

    def test_a_volunteer_cannot_override_a_priority(self):
        volunteer = make_user("ravi", Role.VOLUNTEER, self.district)
        self.client.login(username="ravi", password=PASSWORD)
        self.client.post(reverse("override", args=[self.req.pk]),
                         {"priority": "RED", "reason": "because"})
        self.req.refresh_from_db()
        self.assertFalse(self.req.priority_overridden)
