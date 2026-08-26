"""Re-score every open request and report the breaches.

Run from cron every five minutes. This is what makes the PRIORITISED state's
"track SLA countdown" real: an unserved request climbs the queue on its own.
"""
from django.core.management.base import BaseCommand

from apps.relief.models import ReliefRequest
from apps.relief.services import service


class Command(BaseCommand):
    help = "Recompute triage for open requests and list SLA breaches."

    def add_arguments(self, parser):
        parser.add_argument("--quiet", action="store_true")

    def handle(self, *args, **options):
        rows = ReliefRequest.objects.exclude(
            state__in=["CLOSED", "CANCELLED", "DUPLICATE", "DELIVERED"]
        ).select_related("habitation__block__district")

        breached = []
        for req in rows:
            service.run_triage(req)
            if req.sla_breached():
                breached.append(req)

        if not options["quiet"]:
            for req in breached:
                self.stdout.write(self.style.WARNING(
                    f"#{req.pk} {req.habitation.name}: {req.priority}, "
                    f"{abs(req.hours_left())} h past deadline"
                ))
        self.stdout.write(self.style.SUCCESS(
            f"Rescored {rows.count()} open requests, {len(breached)} past deadline."
        ))
