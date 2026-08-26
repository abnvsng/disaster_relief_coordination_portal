"""The three management commands are part of the product, so they get tests.

seed_india is how a district is stood up, simulate_event is how the demo and
the load check are driven, and check_slas is the ticker that makes the
PRIORITISED state's countdown real. Untested, all three rot quietly.
"""
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from apps.geo.models import District, Habitation, State
from apps.hazards.models import HazardEvent
from apps.logistics.models import Depot, Stock
from apps.relief.models import ReliefRequest


class SeedIndiaTests(TestCase):
    def test_seeding_creates_geography_depots_stock_and_accounts(self):
        out = StringIO()
        call_command("seed_india", stdout=out)

        self.assertEqual(State.objects.count(), 4)
        self.assertEqual(District.objects.count(), 4)
        self.assertTrue(Habitation.objects.count() >= 15)
        self.assertEqual(Depot.objects.count(), 5)
        self.assertTrue(Stock.objects.filter(quantity__gt=0).exists())

        from django.contrib.auth.models import User
        self.assertTrue(User.objects.filter(username="ddma_darbhanga").exists())
        self.assertTrue(User.objects.filter(username="admin", is_superuser=True).exists())
        self.assertIn("Seeded", out.getvalue())

    def test_seeding_twice_is_idempotent(self):
        call_command("seed_india", stdout=StringIO())
        before = Habitation.objects.count()
        call_command("seed_india", stdout=StringIO())
        self.assertEqual(Habitation.objects.count(), before)

    def test_the_four_districts_sit_on_four_different_terrains(self):
        call_command("seed_india", stdout=StringIO())
        terrains = set(District.objects.values_list("terrain", flat=True))
        self.assertEqual(len(terrains), 4)


class SimulateEventTests(TestCase):
    def setUp(self):
        call_command("seed_india", stdout=StringIO())

    def test_an_event_declares_a_hazard_and_files_reports_through_the_gateway(self):
        out = StringIO()
        call_command("simulate_event", district="DBG", reports=10, seed=3, stdout=out)

        event = HazardEvent.objects.get()
        self.assertEqual(event.hazard, "RIVERINE_FLOOD")
        self.assertTrue(event.is_open())

        self.assertEqual(ReliefRequest.objects.count(), 10)

        # Every surviving request went through triage and carries a snapshot.
        surviving = ReliefRequest.objects.exclude(state="DUPLICATE")
        self.assertTrue(surviving.exists())
        self.assertTrue(all(r.snapshots.exists() for r in surviving))

        # A duplicate is filed and linked, but never scored: it is not a
        # separate need, it is corroboration of one already in the queue.
        for dup in ReliefRequest.objects.filter(state="DUPLICATE"):
            self.assertFalse(dup.snapshots.exists())
            self.assertIsNotNone(dup.duplicate_of_id)

        self.assertIn("reports sent", out.getvalue())

    def test_the_same_seed_produces_the_same_run(self):
        call_command("simulate_event", district="DBG", reports=8, seed=42, stdout=StringIO())
        first = list(ReliefRequest.objects.order_by("id").values_list(
            "habitation__code", "total_members", "people_trapped"
        ))
        ReliefRequest.objects.all().delete()
        HazardEvent.objects.all().delete()

        call_command("simulate_event", district="DBG", reports=8, seed=42, stdout=StringIO())
        second = list(ReliefRequest.objects.order_by("id").values_list(
            "habitation__code", "total_members", "people_trapped"
        ))
        self.assertEqual(first, second)

    def test_a_hazard_impossible_on_the_terrain_is_refused(self):
        with self.assertRaises(CommandError):
            call_command("simulate_event", district="BMR", hazard="STORM_SURGE",
                         stdout=StringIO())
        with self.assertRaises(CommandError):
            call_command("simulate_event", district="DBG", hazard="GLOF",
                         stdout=StringIO())

    def test_a_glacial_lake_outburst_is_accepted_in_the_himalaya(self):
        call_command("simulate_event", district="CHM", hazard="GLOF", reports=4,
                     stdout=StringIO())
        self.assertEqual(HazardEvent.objects.get().hazard, "GLOF")

    def test_an_unknown_district_is_refused(self):
        with self.assertRaises(CommandError):
            call_command("simulate_event", district="XXX", stdout=StringIO())


class CheckSlasTests(TestCase):
    def setUp(self):
        call_command("seed_india", stdout=StringIO())
        call_command("simulate_event", district="DBG", reports=6, seed=5,
                     stdout=StringIO())

    def test_the_ticker_rescores_open_requests(self):
        req = ReliefRequest.objects.exclude(
            state__in=["CLOSED", "CANCELLED", "DUPLICATE", "DELIVERED"]
        ).first()
        snapshots_before = req.snapshots.count()

        call_command("check_slas", quiet=True, stdout=StringIO())

        req.refresh_from_db()
        self.assertEqual(req.snapshots.count(), snapshots_before + 1)

    def test_an_unserved_request_climbs_as_it_ages(self):
        req = ReliefRequest.objects.exclude(
            state__in=["CLOSED", "CANCELLED", "DUPLICATE", "DELIVERED"]
        ).first()
        score_before = req.triage_score

        req.reported_at = timezone.now() - timezone.timedelta(hours=9)
        req.save(update_fields=["reported_at"])
        call_command("check_slas", quiet=True, stdout=StringIO())

        req.refresh_from_db()
        self.assertGreater(req.triage_score, score_before)

    def test_breaches_are_reported_on_stdout(self):
        req = ReliefRequest.objects.exclude(
            state__in=["CLOSED", "CANCELLED", "DUPLICATE", "DELIVERED"]
        ).first()
        req.reported_at = timezone.now() - timezone.timedelta(hours=200)
        req.save(update_fields=["reported_at"])

        out = StringIO()
        call_command("check_slas", stdout=out)
        text = out.getvalue()
        self.assertIn("past deadline", text)
        self.assertIn(str(req.pk), text)
