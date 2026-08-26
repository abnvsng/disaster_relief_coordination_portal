# Testing report

District Relief Coordination Portal &middot; CS311P Software Engineering and Design
Principles Lab

---

## 1. Strategy

The architecture decides the test strategy. Because `domain/` imports no
Django, the rules can be tested without a database, a migration or a fixture —
and because everything else is orchestration, the Django tests only have to
prove the wiring.

| Level | What it proves | Where | Needs a database |
|---|---|---|---|
| Unit | The rules: scoring, transitions, allocation | `tests/test_domain.py` | No |
| Integration | ORM, service layer, gateway and views working together | `apps/relief/tests.py` | Yes |
| System | The three management commands end to end | `apps/geo/tests.py` | Yes |
| Performance | Behaviour under a surge | `tools/` benchmark, section 5 | Yes |
| Manual | Browser round trips, HTML rendering, Leaflet | Section 6 | Yes |

```bash
pytest tests/ -q            # 21 unit tests, no DB, no Django  → 0.06 s
python manage.py test apps  # 30 integration and system tests  → 1.6 s
```

51 automated tests, whole suite under two seconds. That number matters: a
suite nobody waits for is a suite everybody runs.

---

## 2. Test inventory

### Unit — `tests/test_domain.py` (21)

**TriageEngine (7)** — score stays inside 0..100 under the worst input the
domain allows; identical context gives an identical score; a trapped person
forces RED regardless of arithmetic; a quiet request stays in a low band; an
unserved request climbs as it ages; every point carries a reason; access mode
follows water depth, char islands and hill terrain; a hazard impossible on the
terrain is refused.

**AllocationPolicy (5)** — a six-member household with six animals gets 54 L
water, 42 chlorine tablets, 2 ration kits and 90 kg fodder; heat raises the
water ration from 3 L to 5 L per person per day; a boat load over 400 kg
splits into trips while the same load by truck does not; SLA is missed when
the only route is a mule at 4 km/h; cold terrain gets blankets whether or not
anyone thought to ask.

**LifecyclePolicy (9)** — every state appears in the transition table; every
terminal state has no way out; every non-terminal state can still be
cancelled; the happy path walks REPORTED to CLOSED; a move outside the table
is refused; a citizen cannot verify their own report; delivery without proof
is refused; escalation waits for two failed attempts; prioritise needs a
score.

`test_every_state_appears_in_the_transition_table` is the one that keeps the
Experiment 9 diagram honest: add a state to the enum without adding it to
`TRANSITIONS` and the suite goes red.

### Integration — `apps/relief/tests.py` (19)

**SMS intake (6)** — a valid message becomes a scored request with an
acknowledgement in the sender's language; a malformed message gets format help
and files nothing; an unknown habitation code is refused; a retried carrier
delivery does not file the report twice; a second report from the same
habitation becomes corroboration; an implausible hazard is rejected at intake.

**Lifecycle (7)** — the full path from report to closed writes seven audit
rows; delivered stock leaves the depot and the reservation clears; a cancelled
request puts the stock back; escalation needs two failed attempts; an override
is recorded and never rewrites the score; an override survives a rescore; a
trapped-person report reaches the top of the queue.

**Views (6)** — public pages open without an account; the control room
redirects anonymous visitors to login; a signed-in officer reaches the
dashboard, queue, map and detail pages; the map feed carries no reporter
phone number; the public form files a request; a volunteer cannot override a
priority.

### System — `apps/geo/tests.py` (11)

Seeding creates geography, depots, stock and accounts; seeding twice is
idempotent; the four seeded districts sit on four different terrains; an event
declares a hazard and files reports through the real gateway; the same seed
produces the same run; a hazard impossible on the terrain is refused for both
Barmer and Darbhanga; a GLOF is accepted in the Himalaya; an unknown district
is refused; the ticker rescores open requests; an unserved request climbs as
it ages; breaches are reported on stdout.

---

## 3. Coverage

`coverage run --source=domain,apps --omit='*/migrations/*,*/tests*'`

| Module | Statements | Missed | Coverage |
|---|---:|---:|---:|
| `domain/vocab.py` | 52 | 0 | 100% |
| `domain/context.py` | 59 | 1 | 98% |
| `domain/allocation.py` | 54 | 2 | 96% |
| `domain/statemachine.py` | 54 | 4 | 93% |
| `domain/triage.py` | 140 | 12 | 91% |
| `apps/relief/services.py` | 205 | 14 | 93% |
| `apps/relief/models.py` | 99 | 6 | 94% |
| `apps/gateway/services.py` | 50 | 5 | 90% |
| `apps/gateway/parser.py` | 64 | 10 | 84% |
| `apps/gateway/ports.py` | 44 | 13 | 70% |
| `apps/gateway/views.py` | 32 | 12 | 62% |
| `apps/portal/views.py` | 154 | 56 | 64% |
| `apps/relief/management/commands/check_slas.py` | 18 | 0 | 100% |
| `apps/relief/management/commands/simulate_event.py` | 53 | 5 | 91% |
| **Total** | **1522** | **168** | **89%** |

**Where the gaps are, and why.** `gateway/ports.py` at 70% is almost entirely
`TwilioGateway.send`, which cannot run without live credentials; its failure
branch is exercised through `MockSMSGateway.fail_numbers` instead.
`gateway/views.py` at 62% is the TwiML rendering for the IVR keypad path.
`portal/views.py` at 64% is the largest real gap: the browser round trips in
section 6 walk that code, but they are manual, so coverage does not see them.
Automating those with Django's test client is the first item on the next
iteration.

Coverage rose from 80% to 89% during this cycle, entirely by adding
`apps/geo/tests.py`. Before it, all three management commands sat at 0%.

---

## 4. Defects found and fixed

| # | Found by | Defect | Fix |
|---|---|---|---|
| 1 | Integration test | Infinite recursion: `build_context` called `stock_coverage`, which called `compute_kit`, which called `build_context` | Extracted `household_of()` so kit computation no longer needs a full context |
| 2 | Manual round trip | A corroborating sender was answered in the *first* reporter's language, not their own | `acknowledgement_for()` takes an explicit language |
| 3 | Integration test | Delivery could be recorded without an OTP through the service layer | Guard moved into `LifecyclePolicy._guard`, so every caller is covered |
| 4 | Test run | `ValueError: Missing staticfiles manifest entry` — the manifest storage requires `collectstatic`, which the test runner never runs | Switched to WhiteNoise's non-manifest compressed storage |
| 5 | Test harness | A role assigned right after `create_user` was invisible: the `post_save` signal caches a citizen profile on the instance | Test helper re-fetches the user; documented in a comment so it is not "fixed" back |
| 6 | Performance test | Queue view rendered every open request, unpaginated | `Paginator`, 50 per page |
| 7 | Performance test | Ranking and breach detection ran in Python over every open request | Band order pushed into SQL with `Case/When`; `deadline` denormalised and indexed |

Defect 5 is worth reading twice. The test was correct, the production code was
correct, and the harness was wrong — a fault in the test itself. It cost the
same debugging time as a real defect.

---

## 5. Performance testing

**Load.** 2,014 open requests in one district, generated through the real
intake path. A district the size of Darbhanga (3.9 million people, ~1,600
habitations) would exceed that only in a severe event, so this is a
deliberately pessimistic figure.

**Environment.** SQLite in WAL mode, single process. Medians over 20 to 300
iterations.

| Operation | Before | After | Change |
|---|---:|---:|---|
| `GET /control/queue/` | 494 ms | 19.4 ms | 25x |
| `GET /control/` (dashboard) | 128 ms | 20.4 ms | 6x |
| `ranked_queue`, first page | 106 ms | 5.3 ms | 20x |

Unchanged, and reported as measured:

| Operation | Result |
|---|---|
| `TriageEngine.score_request` | 78,759 per second (12.7 &micro;s each) |
| Full SMS intake, parse to acknowledgement | median 7.4 ms, p95 9.5 ms, max 15.6 ms |
| `GET /control/map.json` | median 82.4 ms |
| `check_slas` sweep over 2,014 requests | 4.5 s (2.2 ms each) |

**Reading the numbers.**

The triage engine is not the bottleneck and never was: 12.7 &micro;s means a
district could rescore its entire open queue in well under a second if the
database were not in the way. The 2.2 ms per request in the `check_slas`
sweep is almost all ORM round trips — one `UPDATE` and one `INSERT` per
request. Batching those would cut the sweep to under a second, but a 4.5 s
job that runs every five minutes is not costing anyone anything, so it stays
simple.

`map.json` at 82 ms is now the slowest endpoint. It loads every open request
and computes `hours_left()` per feature in Python. A map legitimately needs
every point, so the fix is a bounding-box parameter rather than pagination.
Listed as next work, not fixed here.

**The lesson from rows 6 and 7 of the defect table:** both were invisible at
demo scale. With 22 seeded requests the queue rendered in 8 ms and nothing
looked wrong. They only appeared once the load matched a real surge, which is
the only load that matters for a disaster system.

---

## 6. Manual test log

Browser round trips against the running server. These cover HTML rendering,
Leaflet and the CSRF and session paths that the test client short-circuits.

| # | Steps | Expected | Result |
|---|---|---|---|
| M1 | Send `HELP DBG012 6 WTR,RTN,FDR 90 0` from the simulator, language Hindi | Acknowledgement in Hindi with request number, priority and SLA | Pass — "Anurodh #38 darj hua. Prathmikta RED. Sahayata 2 ghante mein." |
| M2 | Send the same message again | Folded in as corroboration, not a new request | Pass |
| M3 | Send `pls send water` | Format help returned over the same channel | Pass — "Message must start with HELP. Format: HELP..." |
| M4 | Sign in as `ravi_volunteer`, verify a request | Moves to VERIFIED, audit row written | Pass |
| M5 | Sign in as `depot_kiratpur`, press Plan dispatch | Depot chosen, kit cut, stock reserved, ETA shown | Pass — "Dispatch #1: 107.36 kg, 1 trip by ROAD, ETA 1.4 h" |
| M6 | Attempt DELIVERED with no proof reference | Refused with a readable message | Pass — "Delivery needs an OTP or a photo reference." |
| M7 | Retry with `OTP-4417` | Delivered, stock leaves the depot | Pass |
| M8 | Sign in as `ddma_darbhanga`, override a priority with a reason | Priority changes, score unchanged, audit row written | Pass |
| M9 | Attempt the same override as `ravi_volunteer` | Refused | Pass |
| M10 | Open `/control/map/` | Markers coloured by band, popups link to the request | Pass |
| M11 | Open `/control/` while signed out | Redirected to login | Pass |
| M12 | Narrow the browser to 380 px | Tag rows reflow, score block moves below | Pass |

---

## 7. What is not tested

Stated plainly, because an untested area you have named is a risk and an
untested area you have not is a surprise.

- **`TwilioGateway` against the live carrier.** No DLT registration exists, so
  the real network path has never run. The adapter is exercised only through
  its exception branch.
- **The IVR keypad grammar with real DTMF input.** The webhook is tested with
  synthetic `Digits`; a real caller pressing a wrong key mid-sequence is not.
- **Concurrency.** SQLite in WAL mode with one gunicorn worker is assumed, not
  proven. Two simultaneous writers have never been tried, which is exactly why
  the deployment pins one worker.
- **Browser compatibility beyond one engine.** Leaflet and the CSS grid layout
  have been checked in one browser only.
- **Data at district scale.** 2,014 requests and 17 habitations were tested;
  a real Darbhanga has around 1,600 habitations, and the duplicate-detection
  index has never been measured against that many distinct codes.
