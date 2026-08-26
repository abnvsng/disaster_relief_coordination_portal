"""Declare a hazard and let reports arrive, so a demo has something to show.

Reports are generated through the real intake path: the SMS parser, the
duplicate window and the triage engine all run exactly as they would in the
field. Nothing is inserted straight into the table.
"""
import random

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.gateway.services import handle_inbound
from apps.geo.models import District, Habitation
from apps.hazards.models import HazardEvent
from apps.relief.models import Channel
from domain.vocab import Hazard, is_plausible

NEED_MIXES = [
    "WTR,RTN", "WTR,RTN,MED", "WTR,MED", "WTR,RTN,FDR",
    "RTN,SHL", "WTR,RTN,BBY", "RSQ,MED,WTR", "WTR,SAN,CLO",
]


class Command(BaseCommand):
    help = "Declare a hazard event and generate inbound reports through the gateway."

    def add_arguments(self, parser):
        parser.add_argument("--district", default="DBG", help="District code, e.g. DBG")
        parser.add_argument("--hazard", default="RIVERINE_FLOOD")
        parser.add_argument("--severity", type=int, default=4)
        parser.add_argument("--reports", type=int, default=14)
        parser.add_argument("--seed", type=int, default=7)

    def handle(self, *args, **options):
        random.seed(options["seed"])

        district = District.objects.filter(code=options["district"]).first()
        if district is None:
            raise CommandError(
                f"No district {options['district']}. Run seed_india first."
            )
        try:
            hazard = Hazard(options["hazard"])
        except ValueError:
            raise CommandError(f"{options['hazard']} is not a known hazard.")

        if not is_plausible(hazard, district.terrain_enum()):
            raise CommandError(
                f"{hazard.value} cannot happen on {district.terrain} terrain. "
                "That is the point of the plausibility rule, not a bug."
            )

        event = HazardEvent.objects.create(
            name=f"{hazard.value.replace('_', ' ').title()} in {district.name}",
            hazard=hazard.value,
            severity=options["severity"],
            imd_warning_ref=f"IMD/{timezone.now():%Y%m%d}/{district.code}",
        )
        event.districts.add(district)
        self.stdout.write(f"Declared: {event.name}")

        habitations = list(Habitation.objects.filter(block__district=district))
        if not habitations:
            raise CommandError("That district has no habitations. Run seed_india.")

        accepted = duplicates = rejected = 0
        for i in range(options["reports"]):
            hab = random.choice(habitations)
            members = random.randint(2, 12)
            needs = random.choice(NEED_MIXES)
            water_cm = random.choice([0, 0, 20, 45, 90, 130, 180])
            trapped = random.choice([0, 0, 0, 0, 0, 1, 3])
            body = f"HELP {hab.code} {members} {needs} {water_cm} {trapped}"

            result = handle_inbound(
                from_phone=f"+9190000{i:05d}",
                body=body,
                provider_message_id=f"SIM-{event.pk}-{i}",
                channel=random.choice([Channel.SMS, Channel.SMS, Channel.IVR]),
                language=random.choice(["en", "hi", "hi"]),
            )
            if not result.accepted:
                rejected += 1
            elif "added to it" in result.reply or getattr(result, "request", None) is None:
                accepted += 1
            else:
                accepted += 1

        from apps.relief.models import ReliefRequest
        duplicates = ReliefRequest.objects.filter(
            hazard_event=event, state="DUPLICATE"
        ).count()
        open_count = ReliefRequest.objects.filter(
            habitation__block__district=district
        ).exclude(state__in=["CLOSED", "CANCELLED", "DUPLICATE"]).count()

        self.stdout.write(self.style.SUCCESS(
            f"{options['reports']} reports sent: {open_count} open, "
            f"{duplicates} folded in as duplicates, {rejected} rejected at intake."
        ))
        self.stdout.write("Open /control/ to see the ranked queue.")
