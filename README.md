# District Relief Coordination Portal

A working relief coordination system for an Indian district: citizens report a
need by SMS, IVR or web; the portal scores every report by the same published
rules, ranks it, cuts a relief kit, picks a depot, and tracks the request to
handover. Every ranking decision is explainable and every manual override is
recorded against a name.

Built for **CS311P, Software Engineering & Design Principles Lab, KIET**.
The code is the implementation of the Experiment 5, 6, 7 and 9 UML models.

---

## Run it in three minutes

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python manage.py migrate
python manage.py seed_india
python manage.py simulate_event --district DBG --reports 22
python manage.py runserver
```

Open http://127.0.0.1:8000/

| Account | Role | Password |
|---|---|---|
| `ddma_darbhanga` | District admin (DDMA) | `relief2026` |
| `depot_kiratpur` | Depot manager | `relief2026` |
| `ravi_volunteer` | Field volunteer | `relief2026` |
| `ngo_goonj` | NGO coordinator | `relief2026` |
| `admin` | Django admin | `relief2026` |

Citizens need no account at all. `/report/` and `/gateway/simulator/` are open.

### Tests and metrics

```bash
pytest tests/ -q            # 21 domain tests, no database, no Django, ~0.06 s
python manage.py test apps  # 30 integration and system tests, ~1.6 s

pip install radon coverage
python tools/metrics.py --write   # regenerates docs/METRICS.md
coverage run --source=domain,apps --omit='*/migrations/*,*/tests*' manage.py test apps
coverage report
```

- [`docs/METRICS.md`](docs/METRICS.md) — Halstead, cyclomatic complexity,
  maintainability index, Function Point analysis and a COCOMO cross-check.
  Three of the four are computed from source on every run.
- [`docs/TESTING.md`](docs/TESTING.md) — test strategy, inventory, 89%
  coverage, seven defects found and fixed, and performance results under a
  2,000-request surge.

---

## The demo path, in order

1. **`/gateway/simulator/`** — send `HELP DBG012 6 WTR,RTN,FDR 90 0`.
   Watch the acknowledgement come back in Hindi. Send it again to see the
   second report folded into the first as corroboration.
2. Send `pls send water` — the parser refuses it and replies with the grammar.
3. **`/control/`** as `ddma_darbhanga` — the ranked queue, the SLA counters,
   the breach list.
4. Open the top request — the **score ledger** shows each component against
   its cap and the reasons on record.
5. Sign in as `ravi_volunteer` and move it to VERIFIED. As `depot_kiratpur`,
   press **Plan dispatch**: nearest capable depot, kit lines, trip count, ETA.
6. Move to IN_TRANSIT, then DELIVERED with an OTP. Try DELIVERED without one
   and the guard refuses.
7. As `ddma_darbhanga`, override a priority. The computed score does not move;
   an audit line appears.
8. **`/control/map/`** — open requests on OpenStreetMap tiles.

Terrain rules worth demonstrating:

```bash
python manage.py simulate_event --district BMR --hazard STORM_SURGE  # refused
python manage.py simulate_event --district DBG --hazard GLOF         # refused
python manage.py simulate_event --district CHM --hazard GLOF         # accepted
```

---

## Architecture

```
domain/                     framework-free core. Imports no Django.
  vocab.py                  Terrain, Hazard, Priority, AccessMode, NeedType
  context.py                frozen dataclasses crossing the boundary
  triage.py                 TriageEngine   - score, band, access mode
  statemachine.py           LifecyclePolicy - the transition table
  allocation.py             AllocationPolicy - kit, weight, trips, ETA

apps/
  accounts/                 UserProfile: role, district, depot
  geo/                      State > District > Block > Habitation, haversine
  hazards/                  HazardEvent
  relief/                   ReliefRequest, StateLog, TriageSnapshot
    services.py             ReliefService - the ONLY ORM/domain seam
  logistics/                Depot, Stock, Dispatch, DispatchLine
  gateway/                  MessageGateway port, mock + Twilio adapters, parser
  portal/                   views and templates
```

**The rule that keeps it honest:** views, management commands and the SMS
worker all call `ReliefService`. None of them re-implement a rule, and
`ReliefRequest.state` is written in exactly one place — `ReliefService.move()`,
which asks `LifecyclePolicy` first.

**Dependency inversion, not as a slogan:** `apps/gateway/ports.py` defines
`MessageGateway`. `MockSMSGateway` and `TwilioGateway` implement it.
`SMS_BACKEND` in the environment picks one. No caller changes.

**Diagram-code consistency:** `test_every_state_appears_in_the_transition_table`
fails the moment `domain/statemachine.py` and the Experiment 9 state machine
diagram drift apart.

---

## Deploying free

Target: one EC2 instance, Docker Compose, SQLite on a volume, Caddy for
automatic HTTPS, OpenStreetMap tiles, DuckDNS for a hostname. No paid service.

```bash
# on the instance
sudo apt update && sudo apt install -y docker.io docker-compose-v2 git
sudo usermod -aG docker $USER && newgrp docker

git clone <your repo> && cd relief-portal
cp .env.example .env && nano .env      # set SECRET_KEY, hosts, SITE_ADDRESS
./deploy/first-run.sh
```

Set `SITE_ADDRESS` to your DuckDNS name (`relief-portal.duckdns.org`) and Caddy
gets a certificate on first boot. Leave it as `:80` for a plain IP demo.

Check your AWS account's free tier terms in the billing console: accounts
opened after mid-2025 are on a credit-based plan rather than the older
12-month 750-hour allowance.

---

## Known limitations, stated plainly

**SMS to Indian numbers is simulated by default.** Application-to-person SMS
in India requires DLT registration with a telecom operator under TRAI rules,
which a student project cannot hold. `TwilioGateway` is real, working code and
switches on with three environment variables — but on a trial account it will
only reach numbers you have verified, and Indian delivery may be blocked
outright. The simulator at `/gateway/simulator/` runs the identical parser,
service and acknowledgement path, so nothing about the logic is faked; only
the transport is.

**SQLite, one gunicorn worker.** Correct at district demo scale, with WAL mode
and a 20-second busy timeout. Adding workers before moving to Postgres buys
"database is locked" errors, not throughput. The switch is one settings block.

**The SLA ticker is a five-minute loop, not Celery.** A t3.micro has 1 GB of
RAM; Redis plus a Celery worker plus a beat scheduler would eat most of it for
a job that runs one query. Swap it for Celery when the workload justifies it.

**Distances are straight-line haversine**, not routed road distance. On a
flooded plain the road distance can be double. Real deployment wants OSRM or a
routing API; the interface (`Depot.distance_to`) does not change.

**Kit quantities are Sphere-standard approximations**, not a state relief
manual. `domain/allocation.py` holds them in one place, in named constants,
so a district can tune them without touching anything else. Note that the
figures here (54 L water, 42 chlorine tablets, 90 kg fodder for a six-member
household with six animals) match the Experiment 7 sequence diagram, but the
diagram's total of 118.6 kg predates the ration and fodder line weights used
here — update the diagram from the running numbers before the viva.

**No caste, income, religion or Aadhaar field exists.** Vulnerability is
counts of observable dependants, verifiable at the door and minimal under the
Digital Personal Data Protection Act.

---

## What to build next

- Volunteer mobile view with offline queue and photo proof upload
- Postgres, then more than one gunicorn worker
- OSRM for routed distance and terrain-aware ETA
- Depot-to-depot stock transfer when the nearest depot cannot cover the kit
- State-level SDRF escalation view above the district
