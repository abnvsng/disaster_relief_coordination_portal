# District Relief Coordination Portal

A working relief coordination system for an Indian district: citizens report a
need by SMS, IVR or web; the portal scores every report by the same published
rules, ranks it, cuts a relief kit, picks a depot, and tracks the request to
handover. Every ranking decision is explainable and every manual override is
recorded against a name.


---

## Run it

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python manage.py migrate
python manage.py seed_india
python manage.py simulate_event --district DBG --reports 22
python manage.py runserver
```

Open http://127.0.0.1:8000/


Citizens need no account at all. `/report/` and `/gateway/simulator/` are open.



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


## What to build next

- Volunteer mobile view with offline queue and photo proof upload
- Postgres, then more than one gunicorn worker
- OSRM for routed distance and terrain-aware ETA
- Depot-to-depot stock transfer when the nearest depot cannot cover the kit
- State-level SDRF escalation view above the district
