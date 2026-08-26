"""Fill an empty database with a plausible slice of India.

Four districts on four terrains, so the terrain rules are visible: a storm
surge report from Barmer is rejected, a GLOF in Darbhanga is rejected, and
a char island in Darbhanga resolves to BOAT while Chamoli resolves to mule.
"""
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounts.models import Role, UserProfile
from apps.geo.models import Block, District, Habitation, State
from apps.logistics.models import Depot, ResourceType, Stock

RESOURCES = [
    ("WATER_20L", "Drinking water", "L", 1.0, 40000),
    ("CHLORINE_TAB", "Chlorine tablet", "tablet", 0.0005, 50000),
    ("DRY_RATION_KIT", "Dry ration kit", "kit", 15.0, 900),
    ("FODDER", "Cattle fodder", "kg", 1.0, 12000),
    ("FIRST_AID_MODULE", "First aid module", "module", 3.0, 300),
    ("ORS_SACHET", "ORS sachet", "sachet", 0.02, 20000),
    ("TARPAULIN", "Tarpaulin sheet", "sheet", 4.0, 1200),
    ("BLANKET", "Blanket", "piece", 1.5, 3000),
    ("INFANT_KIT", "Infant kit", "kit", 2.5, 400),
    ("HYGIENE_KIT", "Hygiene kit", "kit", 3.0, 800),
]

STATES = [
    ("Bihar", "BR", "0612-2294204"),
    ("Uttarakhand", "UK", "0135-2710334"),
    ("Odisha", "OD", "0674-2534177"),
    ("Rajasthan", "RJ", "0141-2227084"),
]

DISTRICTS = [
    # state, name, code, terrain, basin, seismic, population, lat, lon
    ("BR", "Darbhanga", "DBG", "GANGETIC_PLAIN", "Kosi-Bagmati", 5, 3937385, 26.1542, 85.8918),
    ("UK", "Chamoli", "CHM", "HIMALAYAN", "Alaknanda", 5, 391605, 30.4100, 79.3200),
    ("OD", "Kendrapara", "KDP", "COASTAL", "Mahanadi delta", 3, 1440361, 20.5000, 86.4200),
    ("RJ", "Barmer", "BMR", "DESERT", "Luni", 3, 2603751, 25.7500, 71.3800),
]

BLOCKS = {
    "DBG": ["Kiratpur", "Ghanshyampur", "Hanumannagar"],
    "CHM": ["Joshimath", "Dewal"],
    "KDP": ["Rajnagar", "Mahakalapada"],
    "BMR": ["Chohtan", "Sheo"],
}

# block, name, code, lat, lon, households, pop, elev, flood, char, heli, coverage
HABITATIONS = [
    ("Kiratpur", "Bahadurpur Diara", "DBG012", 26.2810, 86.0630, 210, 1180, 45, True, True, False, "2G"),
    ("Kiratpur", "Rasiyari", "DBG013", 26.2650, 86.0280, 340, 1860, 47, True, False, False, "4G"),
    ("Ghanshyampur", "Tarauni Char", "DBG021", 26.3120, 86.1180, 96, 520, 44, True, True, False, "NONE"),
    ("Hanumannagar", "Basudeopur", "DBG031", 26.1980, 86.0010, 410, 2240, 48, True, False, True, "4G"),
    ("Kiratpur", "Sahpur Bagh", "DBG014", 26.2900, 86.0450, 275, 1490, 46, True, False, False, "2G"),
    ("Kiratpur", "Naruar", "DBG015", 26.2410, 86.0700, 190, 1010, 45, True, False, False, "4G"),
    ("Ghanshyampur", "Belwara", "DBG022", 26.3350, 86.0900, 220, 1230, 43, True, False, False, "2G"),
    ("Ghanshyampur", "Mirzapur Diara", "DBG023", 26.3480, 86.1450, 88, 470, 42, True, True, False, "NONE"),
    ("Hanumannagar", "Kamtaul", "DBG032", 26.1750, 85.9600, 365, 1980, 49, False, False, False, "4G"),
    ("Hanumannagar", "Ekmi Ghat", "DBG033", 26.2200, 85.9350, 140, 760, 46, True, False, False, "2G"),
    ("Joshimath", "Raini", "CHM007", 30.5230, 79.6210, 68, 340, 2100, False, False, False, "2G"),
    ("Joshimath", "Tapovan", "CHM008", 30.4930, 79.5850, 120, 610, 1890, False, False, True, "2G"),
    ("Dewal", "Sutol", "CHM014", 30.2210, 79.6400, 54, 280, 2350, False, False, False, "NONE"),
    ("Rajnagar", "Rajnagar Jetty", "KDP004", 20.6600, 86.8400, 180, 940, 3, True, False, False, "4G"),
    ("Mahakalapada", "Batighar", "KDP009", 20.3300, 86.7100, 145, 780, 2, True, True, False, "2G"),
    ("Chohtan", "Bakhasar", "BMR006", 24.9100, 70.9500, 130, 700, 120, False, False, False, "2G"),
    ("Sheo", "Harsani", "BMR011", 26.1000, 71.0300, 160, 860, 140, False, False, False, "4G"),
]

DEPOTS = [
    ("DBG", "Kiratpur godown", 26.2100, 86.0100, 4, 6, 0, False),
    ("DBG", "Darbhanga central store", 26.1542, 85.8918, 1, 12, 0, True),
    ("CHM", "Gopeshwar store", 30.4100, 79.3200, 0, 4, 8, True),
    ("KDP", "Kendrapara godown", 20.5000, 86.4200, 5, 5, 0, False),
    ("BMR", "Barmer central store", 25.7500, 71.3800, 0, 8, 4, False),
]

STAFF = [
    ("ddma_darbhanga", Role.DISTRICT_ADMIN, "DBG", None),
    ("depot_kiratpur", Role.DEPOT_MANAGER, "DBG", "Kiratpur godown"),
    ("ravi_volunteer", Role.VOLUNTEER, "DBG", None),
    ("ngo_goonj", Role.NGO, "DBG", None),
    ("ddma_chamoli", Role.DISTRICT_ADMIN, "CHM", None),
    ("sunita_citizen", Role.CITIZEN, None, None),
]

PASSWORD = "relief2026"


class Command(BaseCommand):
    help = "Seed states, districts, habitations, depots, stock and staff accounts."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true",
                            help="Delete existing geography and depots first.")

    @transaction.atomic
    def handle(self, *args, **options):
        if options["reset"]:
            Depot.objects.all().delete()
            State.objects.all().delete()
            self.stdout.write("cleared existing geography")

        states = {}
        for name, code, helpline in STATES:
            states[code], _ = State.objects.get_or_create(
                code=code, defaults={"name": name, "sdrf_helpline": helpline}
            )

        districts = {}
        for scode, name, code, terrain, basin, zone, pop, lat, lon in DISTRICTS:
            districts[code], _ = District.objects.get_or_create(
                code=code,
                defaults={
                    "state": states[scode], "name": name, "terrain": terrain,
                    "river_basin": basin, "seismic_zone": zone, "population": pop,
                    "latitude": lat, "longitude": lon,
                },
            )

        blocks = {}
        for dcode, names in BLOCKS.items():
            for name in names:
                blocks[name], _ = Block.objects.get_or_create(
                    district=districts[dcode], name=name
                )

        for (bname, name, code, lat, lon, hh, pop, elev,
             flood, char, heli, coverage) in HABITATIONS:
            Habitation.objects.get_or_create(
                code=code,
                defaults={
                    "block": blocks[bname], "name": name, "latitude": lat,
                    "longitude": lon, "households": hh, "population": pop,
                    "elevation_m": elev, "is_flood_prone": flood,
                    "is_island_or_char": char, "has_heli_pad": heli,
                    "mobile_coverage": coverage,
                },
            )

        resources = {}
        for code, label, unit, weight, _qty in RESOURCES:
            resources[code], _ = ResourceType.objects.get_or_create(
                code=code,
                defaults={"label": label, "unit": unit, "unit_weight_kg": weight},
            )

        depots = {}
        for dcode, name, lat, lon, boats, trucks, mules, heli in DEPOTS:
            depot, _ = Depot.objects.get_or_create(
                name=name,
                defaults={
                    "district": districts[dcode], "latitude": lat, "longitude": lon,
                    "boats_available": boats, "trucks_available": trucks,
                    "mules_available": mules, "has_heli_pad": heli,
                },
            )
            depots[name] = depot
            for code, _l, _u, _w, qty in RESOURCES:
                Stock.objects.get_or_create(
                    depot=depot, resource=resources[code],
                    defaults={"quantity": qty, "reserved": 0},
                )

        for username, role, dcode, depot_name in STAFF:
            user, created = User.objects.get_or_create(
                username=username, defaults={"is_staff": role == Role.DISTRICT_ADMIN}
            )
            if created:
                user.set_password(PASSWORD)
                user.save()
            profile, _ = UserProfile.objects.get_or_create(user=user)
            profile.role = role
            profile.district = districts.get(dcode) if dcode else None
            profile.depot = depots.get(depot_name) if depot_name else None
            profile.save()

        if not User.objects.filter(username="admin").exists():
            admin = User.objects.create_superuser("admin", "", PASSWORD)
            UserProfile.objects.filter(user=admin).update(
                role=Role.DISTRICT_ADMIN, district=districts["DBG"]
            )

        self.stdout.write(self.style.SUCCESS(
            f"Seeded {District.objects.count()} districts, "
            f"{Habitation.objects.count()} habitations, "
            f"{Depot.objects.count()} depots, "
            f"{User.objects.count()} accounts."
        ))
        self.stdout.write(f"Every seeded account uses the password: {PASSWORD}")
