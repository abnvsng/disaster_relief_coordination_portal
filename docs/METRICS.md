# Software metrics report

District Relief Coordination Portal &middot; CS311P Software Engineering and Design Principles Lab

Regenerate with `python tools/metrics.py --write`. Size, complexity and Halstead are measured from the source on every run; the Function Point count is a design-time judgement recorded in `tools/metrics.py`.

## 1. Size

| Scope | Files | SLOC | Logical LOC | Comment lines |
|---|---:|---:|---:|---:|
| Production Python | 65 | 2475 | 1771 | 172 |
| Test Python | 4 | 546 | 408 | 26 |

**51 test cases** across the two suites.

Test to production ratio: **0.22**. Migrations are excluded throughout: they are generated, not written.

## 2. Halstead measures

Halstead is defined for a single program. For a system it is computed per module and summed - concatenating every module would merge their operand vocabularies and inflate difficulty into nonsense.

Across **27 modules** over 400 bytes:

| Measure | Symbol | Value |
|---|---|---:|
| Total length | sum N | 18,465 |
| Mean vocabulary per module | mean n | 144 |
| Total volume | sum V | 140,291 |
| Mean difficulty | mean D | 27.0 |
| Highest module difficulty | max D | 68.5 |
| Total effort | sum E | 5,449,916 |
| Time to implement | T = E/18 | 84 hours |
| Estimated delivered bugs | B = sum V/3000 | 46.8 |

Ten largest modules by volume:

| Module | n1 | n2 | N | Volume | Difficulty | Effort | Est. bugs |
|---|---:|---:|---:|---:|---:|---:|---:|
| `apps/relief/services.py` | 38 | 352 | 2806 | 24152 | 68.5 | 1,654,355 | 8.05 |
| `apps/portal/views.py` | 31 | 297 | 2014 | 16832 | 45.8 | 771,273 | 5.61 |
| `apps/geo/management/commands/seed_india.py` | 23 | 384 | 1707 | 14798 | 22.6 | 333,702 | 4.93 |
| `domain/triage.py` | 32 | 187 | 1307 | 10162 | 50.0 | 507,756 | 3.39 |
| `apps/relief/models.py` | 28 | 189 | 1216 | 9438 | 40.7 | 384,513 | 3.15 |
| `apps/logistics/models.py` | 23 | 115 | 741 | 5267 | 33.7 | 177,512 | 1.76 |
| `apps/relief/management/commands/simulate_event.py` | 28 | 150 | 689 | 5151 | 28.3 | 145,664 | 1.72 |
| `apps/geo/models.py` | 24 | 110 | 725 | 5123 | 35.1 | 179,954 | 1.71 |
| `domain/allocation.py` | 30 | 126 | 682 | 4969 | 36.4 | 181,001 | 1.66 |
| `domain/statemachine.py` | 26 | 100 | 708 | 4940 | 39.9 | 197,152 | 1.65 |

## 3. Cyclomatic complexity

**193 blocks** analysed (functions, methods, classes). Average complexity **2.65**.

| Band | Blocks | Share |
|---|---:|---:|
| A (1-5) | 170 | 88.1% |
| B (6-10) | 19 | 9.8% |
| C (11-20) | 4 | 2.1% |
| D and worse (21+) | 0 | 0.0% |

Ten most complex blocks:

| Block | Module | CC |
|---|---|---:|
| `_guard` | `domain/statemachine.py` | 19 |
| `compute_kit` | `domain/allocation.py` | 15 |
| `handle` | `apps/geo/management/commands/seed_india.py` | 15 |
| `parse_sms` | `apps/gateway/parser.py` | 11 |
| `resolve_access_mode` | `domain/triage.py` | 10 |
| `life_threat_score` | `domain/triage.py` | 9 |
| `Command` | `apps/geo/management/commands/seed_india.py` | 9 |
| `handle` | `apps/relief/management/commands/simulate_event.py` | 9 |
| `move` | `apps/relief/services.py` | 9 |
| `isolation_score` | `domain/triage.py` | 8 |

## 4. Maintainability index

| Module | MI | Rank |
|---|---:|---|
| `apps/relief/services.py` | 31.8 | A (maintainable) |
| `domain/triage.py` | 37.9 | A (maintainable) |
| `apps/portal/views.py` | 39.4 | A (maintainable) |
| `apps/logistics/models.py` | 49.2 | A (maintainable) |
| `domain/statemachine.py` | 52.8 | A (maintainable) |
| `apps/hazards/models.py` | 55.9 | A (maintainable) |
| `apps/gateway/parser.py` | 56.0 | A (maintainable) |
| `apps/geo/models.py` | 56.5 | A (maintainable) |
| `apps/relief/models.py` | 57.3 | A (maintainable) |
| `domain/allocation.py` | 58.2 | A (maintainable) |

Lowest maintainability index in the codebase: **31.8** (A (maintainable)). Nothing falls below the maintainable threshold of 20.

## 5. Function Point analysis

| Type | Count | Unadjusted points |
|---|---:|---:|
| ILF | 7 | 63 |
| EIF | 2 | 10 |
| EI | 17 | 66 |
| EO | 8 | 45 |
| EQ | 6 | 20 |
| **Total (UFP)** | **40** | **204** |

Total Degree of Influence across the 14 general system characteristics: **50**

Value Adjustment Factor = 0.65 + (0.01 x 50) = **1.15**

**Adjusted Function Points = 204 x 1.15 = 235**

### Component detail

**Internal Logical Files (ILF)**

| Function | Complexity | Points | Basis |
|---|---|---:|---|
| Relief request store | High | 15 | 3 RETs (ReliefRequest, StateLog, TriageSnapshot), ~55 DETs |
| Geography register | Average | 10 | 4 RETs (State, District, Block, Habitation), ~30 DETs |
| Depot and stock | Average | 10 | 3 RETs (Depot, Stock, ResourceType), ~20 DETs |
| Dispatch record | Low | 7 | 2 RETs (Dispatch, DispatchLine), ~13 DETs |
| Hazard event register | Low | 7 | 1 RET, 7 DETs |
| User and role | Low | 7 | 2 RETs (User, UserProfile), ~14 DETs |
| Message log | Low | 7 | 2 RETs (InboundMessage, OutboundMessage), ~16 DETs |

**External Interface Files (EIF)**

| Function | Complexity | Points | Basis |
|---|---|---:|---|
| Telecom gateway message feed | Low | 5 | Twilio inbound payload, 6 DETs |
| OpenStreetMap tile service | Low | 5 | read-only basemap |

**External Inputs (EI)**

| Function | Complexity | Points | Basis |
|---|---|---:|---|
| Submit report over SMS | High | 6 | 4 FTRs (request, habitation, hazard, outbound), parse plus validate |
| Submit report over web form | High | 6 | 4 FTRs, ~18 DETs |
| Submit report over IVR | Average | 4 | 3 FTRs, keypad grammar |
| Plan dispatch and reserve stock | High | 6 | 5 FTRs (request, depot, stock, dispatch, dispatch line) |
| Verify report on site | Low | 3 | 1 FTR, guarded by role |
| Prioritise request | Low | 3 | 1 FTR, guarded on triage score |
| Depart depot (mark in transit) | Low | 3 | 2 FTRs |
| Record proof of delivery | Average | 4 | 3 FTRs, releases reservations |
| Record unreachable with reason | Average | 4 | 2 FTRs, increments attempts |
| Escalate to district | Low | 3 | 1 FTR, two-attempt guard |
| Cancel request | Low | 3 | 2 FTRs, restores stock |
| Close request | Low | 3 | 1 FTR |
| Override priority with reason | Average | 4 | 2 FTRs, writes audit entry |
| Declare hazard event | Average | 4 | 2 FTRs, terrain plausibility check |
| Re-run triage | Average | 4 | 3 FTRs, appends a snapshot |
| Authenticate | Low | 3 | 1 FTR |
| Seed geography and depots | Low | 3 | bulk maintenance of 2 ILFs |

**External Outputs (EO)**

| Function | Complexity | Points | Basis |
|---|---|---:|---|
| Ranked queue with SLA flags | High | 7 | 3 FTRs, sort plus derived hours left |
| Triage score ledger | High | 7 | derived breakdown against caps, reasons |
| Relief kit computation | High | 7 | derived quantities, weights, trips, ETA |
| Acknowledgement in reporter language | Average | 5 | derived priority and SLA |
| Dashboard counters and breach list | Average | 5 | aggregates across 2 FTRs |
| Map GeoJSON feed | Average | 5 | derived breach flag and hours left |
| SLA breach report | Average | 5 | batch recompute, derived overdue hours |
| Format help on a malformed message | Low | 4 | no FTR, derived from grammar |

**External Inquiries (EQ)**

| Function | Complexity | Points | Basis |
|---|---|---:|---|
| Request detail with audit trail | Average | 4 | 4 FTRs |
| Queue filtered by band and stage | Average | 4 | 2 FTRs |
| Track a request by id | Low | 3 | 2 FTRs |
| My reports list | Low | 3 | 1 FTR |
| Gateway inbox and outbox | Low | 3 | 1 FTR |
| Open hazard events | Low | 3 | 1 FTR |

### General system characteristics

| Characteristic | Rating | Why |
|---|---:|---|
| Data communications | 4 | SMS, IVR, HTTP form and inbound webhooks |
| Distributed data processing | 2 | single node, one external gateway |
| Performance | 3 | SLA countdown drives ranking; load is modest |
| Heavily used configuration | 2 | targets a 1 GB t3.micro |
| Transaction rate | 3 | arrives in surges during an event |
| Online data entry | 5 | every intake path is online |
| End-user efficiency | 4 | control room desktop and 2G feature phone |
| Online update | 5 | all ILFs are updated interactively |
| Complex processing | 4 | triage scoring, guarded state machine, allocation |
| Reusability | 4 | framework-free domain core, reusable per district |
| Installation ease | 3 | docker compose plus one seed command |
| Operational ease | 3 | healthcheck, restart policy, SLA ticker |
| Multiple sites | 4 | multi-district and multi-state by design |
| Facilitate change | 4 | settings-driven backends, one ORM/domain seam |

## 6. Estimation cross-check

Backfiring at 27 SLOC per function point for Python predicts **6,345 SLOC** for 235 adjusted function points. Measured production size is **2,475 SLOC**, **-61%** against the prediction.

The codebase comes in well under the backfiring estimate. Two reasons, both visible in the source: the domain rules are table-driven (`TRANSITIONS`, `PLAUSIBLE_HAZARDS`, `HAZARD_WEIGHT`) rather than written out as branches, and Django supplies the admin, authentication and ORM behind several of the counted functions without a line being written here. Backfiring ratios assume hand-written code, so a framework-heavy project should be expected to land below them.

Basic COCOMO, organic mode, on the measured 2.48 KLOC:

| Quantity | Formula | Value |
|---|---|---:|
| Effort | 2.4 x KLOC^1.05 | 6.2 person-months |
| Schedule | 2.5 x E^0.38 | 5.0 months |
| Average staffing | E / D | 1.2 people |

Read this as the model's opinion, not a fact about the project. COCOMO was calibrated on hand-written procedural code; it has no way to know that Django supplies the admin, ORM and auth layers here.

## 7. What the numbers say

- **Average cyclomatic complexity of 2.65** puts the codebase in band A. The distribution matters more than the mean: no block exceeds 20.
- **The complexity hotspots are deliberate and flat, not nested.** `LifecyclePolicy._guard` scores high because it is a sequence of independent one-line validations, each raising with its own message. Rewriting it as a dispatch table would lower the number and make the code harder to read, so the number stays.
- **The metric did drive one refactor.** `portal.views.report` measured CC 14 in its first version, because it introspected `Model._meta` to decide which cleaned fields to forward. Moving that decision into `PublicReportForm.to_intake_kwargs()` cut it to 7 and put the knowledge where it belongs.
- **Mean Halstead difficulty per module is 27.0**, with the worst module at 68.5. Difficulty rises with the number of distinct operands a module juggles, which is why the orchestration layers score above the domain core: they name more things.
- **Halstead predicts 47 delivered defects (B = sum V / 3000).** Treat that as a size proxy rather than a forecast: the constant 3000 was fitted to 1970s assembly and Fortran, and the estimator has never validated well on high-level languages. What the project actually has against it is 51 test cases across 3 files and 546 SLOC, running in under two seconds.
- **Every module ranks A on maintainability.** The two lowest are `relief/services.py` and `portal/views.py`, which is the right place for the pressure: services.py is the deliberate seam between the ORM and the domain, and views.py is orchestration. Both are the layers designed to absorb change.
