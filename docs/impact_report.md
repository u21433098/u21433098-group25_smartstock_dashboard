# SmartStock: impact, sustainability and scalability report

BFB 321, Group 25 (Claudia Aird, u21433098; Josua Olivier, u23524431)
Client: Mr Msiza, Adlers Vending Machine Operations, University of Pretoria

> **Read this first.** SmartStock has not yet been used at Adlers, so nothing here is a measurement of Mr Msiza's
> real week. Every "with SmartStock" number is produced by the working app on its **synthetic demo data**
> (12 machines, 15 products, 3 suppliers, 30 days of sales). Every "before" number comes from the proposal.
> Every assumption is listed in section 6. Section 7 explains how to measure the real effect once the system is in use.
> The numbers are regenerated from the code with `python scripts/impact_report.py`, so they cannot drift from what the app does.

---

## 1. Summary

| | Before | With SmartStock | Change |
|---|---|---|---|
| Stock tiers tracked digitally | 1 of 3 (machine only, in Moma) | **3 of 3** | +2 tiers; paper log replaced |
| Paper records moved into the database | 111 (96 drawer slots, 15 central products) | **0 on paper** | 100% digitised (O2) |
| Supplier trips for one order | 5 (one per product line) | **3 (one per supplier)** | **40% fewer** (O4 target: 25%) |
| Supplier driving per month | 8.7 h | **5.2 h** | **3.5 h saved** a month |
| Low-stock alerts Mr Msiza can see | 4 (machine tier only) | **12 (all three tiers)** | 3 times as many |
| Machine shortages that could be fixed on the spot from the drawer | not visible | **4 of 4** | every machine shortage shown with its fix |
| Screens to see one machine's full stock | 3 (Moma + two paper logs) | **1** | one combined view (O2) |
| Machines with a data-driven drawer ranking | 0 (guesswork) | **12 of 12** | O3 met for the whole fleet |
| Stock changes with who, when and why | 0% (paper, often misplaced) | **100%** | complete audit trail |

---

## 2. Before and after KPIs

| KPI | Objective | Before (source) | With SmartStock (how it is produced) |
|---|---|---|---|
| Stock tiers tracked digitally | O1, O2 | 1: Moma covers only the machine's sales compartment (proposal, section 2) | 3: machine, drawer and central tables (`app/models`) |
| Drawer and central records on paper | O2 | 100%, kept by hand (proposal, section 1) | 0%: 96 drawer slots and 15 central products in MySQL, every change audited |
| Screens to see one machine's stock | O2 | 3: Moma plus two paper logs | 1: the machine page shows all three tiers side by side |
| Drawer allocation | O3 | Guesswork, nothing written down (proposal, section 2) | A ranking from trailing 30-day turnover for 12 of 12 machines, recalculated on every visit to the page |
| Supplier trips for one order | O4 | One trip per product line that needs ordering: 5 on the demo data (`models/procurement.py`, "before" rule) | One trip per supplier with something to order: 3; **40% fewer**, against a 25% target |
| Supplier driving per month | O4 | 2 unplanned trips a week x 60 min = **8.7 h** (proposal, section 2) | 8.7 h x (1 - 40%) = **5.2 h**; at the 25% target it would be 6.5 h |
| Paperwork and planning time | O5 | Not measured yet; the target is to cut 3+ h a week (proposal, O5) | Not measurable without the time log described in section 7. What removes the work: no reconciling paper logs, a shopping list built automatically, alerts instead of checking |
| Low-stock alerts visible | Feature 6 | 4: only the machine tier (Moma) | 12: machine 4, drawer 3, central 5 |
| Machine shortages with a visible fix | Feature 6 | The buffer stock that could fix a shortage is invisible (proposal, section 2: "residual risk") | All 4 machine shortages are shown next to drawer stock that can fix them on the spot |
| Traceable stock changes | Governance | 0%: paper, "often misplaced" (proposal, section 1) | 100%: every change stores the user, the time, the old and new quantity, and why |

---

## 3. Charts

![Figure 1](impact/before_after.png)

**Figure 1. Four before-and-after measures on the demo data.** Grey is the situation described in the proposal
(paper logs and Moma); blue is SmartStock. Each panel has its own scale, and the note under each title says which
direction is better. Supplier trips fall from 5 to 3 for the same order. Mr Msiza sees three times as many alerts
because the drawer and central tiers are now monitored. One screen replaces three.

![Figure 2](impact/driving_hours.png)

**Figure 2. Supplier driving per month.** The baseline is the proposal's conservative estimate (two unplanned trips a
week of 60 minutes each). Ordering once per supplier cut the demo order from 5 trips to 3 (40%), which would save
about 3.5 hours a month, past the O4 target (the line at 6.5 h).

![Figure 3](impact/alerts_by_tier.png)

**Figure 3. Where today's demo alerts are.** Only the 4 machine-tier alerts would reach Mr Msiza through Moma.
The other 8 (3 drawer, 5 central storage) were only on paper before.

![Figure 4](impact/scalability.png)

**Figure 4. Server time per page as the fleet grows**, measured on MySQL (section 5). Pages about one machine stay
almost flat; pages that add up the whole fleet grow in a straight line and are still well under 0.2 seconds at 200 machines.

---

## 4. Sustainability

### Economic
- **Time.** About **3.5 hours of driving a month** saved on the demo order (42 hours a year), before counting the
  paperwork time targeted by O5. That time can go back to restocking or to the café.
- **Fewer lost sales.** All 4 machine shortages on the demo data could have been fixed on the spot from the drawer.
  This is exactly the "residual risk" the proposal describes: the alert fired, but the stock to fix it was invisible.
- **No licence lock-in.** Adlers owns SmartStock outright instead of depending on a third-party app it cannot change.

### Environmental
- **Fuel and CO2.** 40% fewer trips is about 3.5 fewer trips a month. With the assumptions in section 6
  (15 km round trip, 8 L/100 km) that is about **52 km, 4.2 litres of petrol and 9.8 kg CO2e a month**
  (about 118 kg CO2e a year). This is small in absolute terms, but it grows with every machine added, and it costs nothing to achieve.
- **Paper.** The drawer and central paper logs are no longer needed.

### Social
- **Students and staff** find a working machine more often, because shortages that the drawer could fix are now visible and fixed sooner.
- **Mr Msiza** gets one tool he controls instead of two disconnected systems, and less mental load from reconciling paper.
  Helpers get their own accounts, so work can be shared without sharing a password.

### Technical (will the system last?)
- **Owned and documented:** README runbook, ERD, OpenAPI contract, end-to-end flow descriptions and this report.
- **Safe to change:** over 160 automated tests run on both SQLite and MySQL, including tests that fail if the API
  contract and the code drift apart; database changes go through versioned migrations with a rollback.
- **Open to integration:** the REST API (`docs/api.md`) means the sensor feed from objective O1 (a "sensor bridge"),
  a phone app or a supplier system can be connected without changing the core.
- **Accessible without JavaScript:** works on any phone browser; labelled forms, keyboard focus, and screen-reader
  announcements for messages and sorted columns.

---

## 5. Scalability

### Measured: 12 to 200 machines

The benchmark (`scripts/benchmark.py`) builds a fresh MySQL database for each fleet size, by copying the 12 demo
machines with their stock and 30 days of sales, and times each request inside the app (median and 95th percentile
of 15 runs after 2 warm-up runs; network time not included).
Measured on 2026-11-19 on MariaDB 10.11 (MySQL-compatible), Python 3.13, a 2-CPU Linux machine.

Median server time in milliseconds:

| Request | 12 machines | 50 | 100 | 200 | Grows with the fleet? |
|---|---|---|---|---|---|
| Machine detail page | 9.0 | 8.4 | 10.7 | 14.3 | Barely: one machine's rows, found through indexes |
| API: stock take (a write) | 5.6 | 5.0 | 5.7 | 5.1 | No: one indexed row, locked and updated |
| API: list machines (20 per page) | 6.6 | 6.5 | 9.5 | 13.6 | Slightly |
| Activity page (20 per page, paged in MySQL) | 8.6 | 9.8 | 13.3 | 18.7 | Slightly |
| Allocation page (one machine) | 11.9 | 12.8 | 16.9 | 22.0 | Slightly |
| Machines page (10 per page) | 8.5 | 11.0 | 17.0 | 24.3 | Yes: counts alerts across the fleet |
| Alerts page | 9.4 | 11.1 | 16.1 | 27.0 | Yes: scans every tier |
| Shopping list page | 15.1 | 26.9 | 39.4 | 64.9 | Yes: 30-day demand for the whole fleet |
| API: dashboard | 24.9 | 40.0 | 64.5 | 110.2 | Yes |
| Dashboard page | 26.8 | 48.8 | 75.3 | 129.3 | Yes: KPIs, alerts, shopping list and best sellers together |
| Sales rows in the database | 2,880 | 12,000 | 24,000 | 48,000 | |

**What this shows.** Work about one machine or one row does not slow down as the fleet grows, because the indexes
from the data model (for example `sales (machine_id, product_id, sale_date)` and the stock primary keys) go
straight to the rows needed. Pages that summarise the whole fleet grow in a straight line, about 0.5 ms per extra
machine for the dashboard. At 200 machines (more than 16 times Adlers' current fleet), the slowest page is still
built in about 0.13 seconds.

**What to improve first if the fleet grows much further.** The dashboard and the shopping list re-add 30 days of
sales on every visit. A nightly summary table (units sold per product per day for the whole fleet), or caching the
dashboard for a minute, would make them roughly flat. The alert count in the navigation bar is also recalculated on
every page and could be cached the same way. None of this is needed at Adlers' size.

### Multi-site

The proposal expects SmartStock to grow to more machines and possibly other operators. The data model is ready for
that with one addition:

1. A `sites` table (for example "Hatfield campus", "Groenkloof campus", or another operator), and a `site_id` column
   on `machines` and on `central_stock`, so each site has its own central storage pool. This is one Flask-Migrate
   migration, with a rollback, like the existing one.
2. The services filter by the logged-in user's site. The shopping list then becomes one order per supplier
   **per site**, or one combined order when sites share a supplier run.
3. Nothing in the supply chain models (`models/`) changes: they work on numbers, not on sites.

### Multi-role

Roles are defined in one place (`ROLE_PERMISSIONS` in `app/services/user_service.py`) and checked by the services,
not only by the pages or the API. A new role is one line, for example:

| Role | Could | Example |
|---|---|---|
| `viewer` | view only | Adlers management watching the KPIs |
| `site_manager` | change stock and manage accounts, for one site | a second campus |
| `supplier` | see only their own order | a supplier preparing the next delivery |

The web pages, the API and the tests all use the same check, so a new role works everywhere at once.

### More traffic

The app does not keep anything in memory between requests (the session is in the cookie, the data in MySQL), so it
can run several worker processes behind a web server, or several servers behind one database. Lists are paged (at
most 100 items per API page) and the busiest lookups are indexed.

---

## 6. Assumptions

| Assumption | Value | Source |
|---|---|---|
| Unplanned supplier trips per week (baseline) | 2 | Proposal, section 2 |
| Minutes per trip | 60 | Proposal, section 2 |
| O4 target reduction | 25% | Proposal, objective O4 |
| Round trip per supplier visit | 15 km | **Assumed** (not measured): café to a Pretoria supplier and back |
| Fuel use | 8 litres per 100 km | **Assumed** (not measured): small delivery car |
| CO2e per litre of petrol | 2.345 kg | UK Government GHG conversion factors 2023 (BEIS/Defra), "Petrol (100% mineral petrol)" |
| Trip saving on the demo data | 40% | Calculated by SmartStock: 5 products to order from 3 suppliers |

**About the proposal's driving estimate.** Section 5 of the proposal estimated "approximately 5 to 6 hours of
driving a month" saved at the 25% target. Using the proposal's own baseline (2 trips a week of 60 minutes, so
8.7 hours a month), a 25% cut saves about **2.2 hours** a month, and the 40% cut on the demo data saves about
**3.5 hours**. This report uses the arithmetic from the baseline. The 5 to 6 hour figure would need a higher baseline
(about 5 trips a week).

**About the demo data.** The 40% trip saving depends on how many products need ordering and from how many suppliers.
With 3 suppliers and 15 products, the saving per order cycle is 1 - (suppliers with an order / products to order).
It is higher when more products from the same supplier run low together.

---

## 7. How to measure the real impact at Adlers

| KPI | How to measure | When |
|---|---|---|
| Supplier trips per week | Count trips in a simple log for 4 weeks before and 4 weeks after go-live | Months 1 and 4 |
| Paperwork and planning time (O5) | Mr Msiza notes minutes spent on stock records and purchase planning each day, for 2 weeks before and 2 weeks after | Months 1 and 4 |
| Stock-outs | Count machine-tier alerts at qty 0 per week in the activity log and on the alerts page | Weekly |
| Shortages fixed from the drawer | Restock visits where the drawer covered a machine shortage (activity log, tier "Drawer") | Monthly |
| Use of the system | Stock changes per week in the activity log (`GET /api/v1/movements`) | Monthly |

---

## 8. Limitations

- All numbers are from synthetic demo data and modelled assumptions, not from Adlers' real operation (see section 7).
- Machine stock is entered by hand: the sensor feed (O1) depends on access to the data Moma uses, which is still
  unconfirmed (proposal, section 4). The API endpoint for machine counts is ready for a sensor bridge.
- The benchmark measures server time on one test machine; real response times also include the network.

---

## 9. Reproducing this report

```
pip install matplotlib                     # only for the charts
python scripts/benchmark.py --database-url mysql+pymysql://smartstock:PASSWORD@localhost:3306/smartstock_test
python scripts/impact_report.py            # writes docs/impact/metrics.json and the four charts
```

`benchmark.py` **wipes** the database it is given, so use the test database, never the real one.

**Chart design.** The charts follow a validated, colour-blind-safe palette: grey for "before" and blue for SmartStock,
plus four checked series colours on the scalability chart. Every chart labels its values or lines directly, so
colour is never the only way to tell series apart.

---

**Turnitin similarity:** ____ % (fill in after the Turnitin check, as the guide requires: must be 15% or less).

## References

- Group 25 (2026) *SmartStock Proposal*, BFB 321, University of Pretoria. Baseline figures, objectives O1 to O5.
- UK Department for Energy Security and Net Zero / BEIS (2023) *Greenhouse gas reporting: conversion factors 2023*,
  "Petrol (100% mineral petrol)", 2.34503 kg CO2e per litre. Retrieved via Climatiq:
  https://www.climatiq.io/data/emission-factor/f03e72c3-1b83-4346-8e05-19af184766f7
- Barros, Cortez and Carvalho (2021); Gonçalves, Carvalho and Cortez (2020); Hübner and Kuhn (2024): the safety-stock
  and allocation methods behind O3 and O4, as cited in the proposal.
