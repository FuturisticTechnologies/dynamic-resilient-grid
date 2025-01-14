# -*- coding: utf-8 -*-
"""DRG epics.

DRG-1..DRG-16 were cut in the inception workshop on 02 Jan 2025.
DRG-17 (Quality Engineering) was added in June 2026 when the QA analyst joined.
DRG-18 (Business Analysis) was added in August 2026 ahead of the BA starting.
"""

from backlog_common import I, G, D, V, N, A, S

EPICS = [

I("DRG-1", "Epic", "Data Foundations and Ingestion", "Done",
  """
Get half-hourly smart-meter demand into a shape the rest of the platform can
trust, and make the project runnable by anyone without the licensed dataset.

Scope: the Low Carbon London loader, the calibrated synthetic generator used
when LCL is unavailable, config, IO and logging utilities, and the raw ->
interim -> processed data contract.

Explicit non-goal: no physical power-flow modelling. DRG is a demand-side
tool and the boundary is stated so nobody expects load-flow results from it.
  """,
  epic_name="Data Foundations", assignee=D, priority="Highest",
  components="Data;Platform", labels="year1;foundation",
  created="2025-01-02 09:20:00", resolved="2025-03-14 16:20:00",
  comments=[
    ("2025-01-02 09:55:00", G, "The constraint that shapes this epic: the LCL dataset is licensed and we cannot assume a reviewer, a new joiner or a CI runner has it. Everything must run end to end on synthetic data that is calibrated to the real thing, or the project is undemonstrable."),
    ("2025-01-02 11:10:00", V, "Agreed, and I want that to be the default path rather than a fallback nobody exercises. If the synthetic route is only used in emergencies it will be broken when we need it."),
    ("2025-03-14 16:18:00", D, "Closing. Loader handles LCL, the synthetic generator reproduces its seasonality and household spread, and a clean clone runs with no key and no dataset."),
  ]),

I("DRG-2", "Epic", "Neighbourhood Consumption Analysis", "Done",
  """
Objective 1 of the proposal: understand how neighbourhood consumption actually
behaves before modelling it.

Scope: profiling by time of day, day of week and season; household
heterogeneity within a neighbourhood; the daily and weekly shapes that later
justify the lag features; and the reporting figures that go into the design
document.
  """,
  epic_name="Consumption Analysis", assignee=G, priority="High",
  components="Analysis", labels="year1;eda",
  created="2025-01-02 09:22:00", resolved="2025-04-25 15:40:00",
  comments=[
    ("2025-01-20 10:30:00", G, "The point of this epic is not charts. It is to find out what the weekly cycle looks like, because if weekly seasonality dominates then lag_336 is the single most important feature we will build and everything downstream follows from that."),
    ("2025-04-25 15:38:00", G, "Closed, and it did dominate. That finding drives the feature set, the model choice and eventually the SHAP story."),
  ]),

I("DRG-3", "Epic", "Feature Engineering", "Done",
  """
Turn a half-hourly series into a supervised learning problem without leaking
the future into the past.

Scope: calendar features, cyclical encodings of time of day and day of week,
lag features at 1, 48 and 336 half-hours, rolling statistics, weather joins,
and the chronological split contract every model must honour.
  """,
  epic_name="Feature Engineering", assignee=D, priority="Highest",
  components="Features", labels="year1;features",
  created="2025-01-02 09:24:00", resolved="2025-06-06 16:10:00",
  comments=[
    ("2025-02-10 09:45:00", D, "Every feature in this epic gets one question asked of it: at the moment we would make this prediction in production, is this value knowable? If the answer is no or unclear, it does not go in."),
    ("2025-06-06 16:05:00", G, "Closed. DRG-58 was the reason that question needed a test behind it rather than a habit."),
  ]),

I("DRG-4", "Epic", "Forecasting Model Ladder", "Done",
  """
Objective 2: short-term half-hourly demand forecasting, with every model
measured against the operational status quo.

The ladder, all evaluated on the same held-out chronological window:
seasonal naive (the thing an operator does today), linear/Ridge, XGBoost as
the primary model, and an optional deep sequence model.

Rule for the epic: the naive baseline is a first-class published result. A
model that cannot beat "same half-hour yesterday" does not get deployed.
  """,
  epic_name="Model Ladder", assignee=G, priority="Highest",
  components="Models", labels="year1;modelling",
  created="2025-01-02 09:26:00", resolved="2025-09-19 16:30:00",
  comments=[
    ("2025-06-16 09:40:00", G, "Naive first, then linear, then trees, then deep - in that order, and each one has to earn its place against the one below it. Starting with XGBoost would mean never finding out that Ridge gets within 0.13 MAE of it for a fraction of the complexity."),
    ("2025-08-11 10:20:00", D, "Rolling-origin CV over five expanding folds rather than a single split, so we know the test result is not a lucky window."),
    ("2025-09-19 16:25:00", G, "Closed. XGBoost at 0.70 MAE against seasonal naive at 1.54, and the CV band is 0.74 to 0.95 RMSE so the headline is honest."),
  ]),

I("DRG-5", "Epic", "Statistical Stress Detection", "Done",
  """
Objective 3: define grid stress from data rather than from an assumed
capacity limit, which we do not have.

Stress is a half-hour above a percentile of that neighbourhood's own
historical demand distribution. Each site is compared against itself, so a
dense urban feeder and a suburban one are both measurable without knowing
either one's rating.

Scope: threshold derivation, event detection, frequency and duration metrics,
and the alarm quality measures that let a forecast be judged on stress rather
than only on error.
  """,
  epic_name="Stress Detection", assignee=G, priority="High",
  components="Stress", labels="year1;stress",
  created="2025-01-02 09:28:00", resolved="2025-11-14 15:50:00",
  comments=[
    ("2025-09-29 10:15:00", G, "The honest framing, which goes in the design doc: we do not have transformer ratings, so we cannot say a neighbourhood is over capacity. What we can say is that it is in the top 5% of its own history, and that this is happening ten times more often under an electrification scenario. That is a defensible claim and the other one is not."),
    ("2025-11-14 15:45:00", D, "Closed. P95 per site, events detected with a minimum duration, and stress-alarm F1 published alongside MAE for every model."),
  ]),

I("DRG-6", "Epic", "Electrification Scenario Simulation", "Done",
  """
Objective 4: simulate EV and heat-pump adoption from the bottom up and
quantify how much they amplify peak demand.

Scope: per-household adoption sampling, EV charging profiles, heat-pump
profiles driven by temperature, diversity between the two loads, and scenario
sweeps from base through to high adoption.

Every scenario reports its after-diversity maximum demand per device and its
energy per vehicle per day, so the assumptions can be audited against DNO
planning practice rather than taken on trust.
  """,
  epic_name="Electrification Simulation", assignee=D, priority="Highest",
  components="Simulation", labels="year1;simulation",
  created="2025-01-02 09:30:00", resolved="2026-02-13 16:40:00",
  comments=[
    ("2025-11-24 09:50:00", D, "The number that will decide whether this is credible is diversity. If EV and heat pump peaks are simply added, we will overstate the problem and a DNO planner will stop reading."),
    ("2026-01-16 14:20:00", G, "And that turned out to be the finding rather than a caveat - see DRG-80. EV alone at 80% gives +154%, heat pumps alone at 70% give +113%, together +237%. Twenty-nine percentage points less than additive."),
    ("2026-02-13 16:35:00", D, "Closed. Five scenarios, ADMD printed per scenario at 1.20 kW per EV and 1.30 kW per heat pump, which lands inside the range DNOs actually plan with."),
  ]),

I("DRG-7", "Epic", "Sensitivity Analysis", "Done",
  """
Objective 5: how sensitive are stress frequency and duration to the
assumptions we chose?

Scope: sweeping adoption rates, charging behaviour, heat-pump COP and the
stress percentile itself; reporting how each output moves; and identifying
which assumptions the conclusions actually depend on.
  """,
  epic_name="Sensitivity Analysis", assignee=G, priority="High",
  components="Analysis", labels="year2;sensitivity",
  created="2025-01-02 09:32:00", resolved="2026-04-10 15:20:00",
  comments=[
    ("2026-02-23 10:40:00", G, "A single scenario number with no sensitivity around it invites the reader to argue about the assumption instead of the conclusion. This epic exists so we can say which assumptions matter and which do not."),
    ("2026-04-10 15:15:00", G, "Closed. The conclusion is robust to charging behaviour and COP within plausible ranges, and highly sensitive to the adoption rate itself - which is the honest answer and also the one planners can act on."),
  ]),

I("DRG-8", "Epic", "Explainable AI", "Done",
  """
Objective 6: explain the forecasts, globally and during stress specifically.

Scope: SHAP over the primary model, global driver ranking, a separate ranking
restricted to stress half-hours, and per-prediction explanations surfaced in
the dashboard and the API.

An operator being asked to act on a stress alarm needs to know why the model
expects it, or the alarm is just a number they will learn to ignore.
  """,
  epic_name="Explainable AI", assignee=G, priority="High",
  components="Explain", labels="year2;xai",
  created="2025-01-02 09:34:00", resolved="2026-05-22 16:00:00",
  comments=[
    ("2026-04-20 11:15:00", G, "Explaining stress periods separately from all periods is the part I care about. If the drivers differ, that is operationally interesting; if they do not, that is reassuring. Either way it is worth knowing rather than assuming."),
    ("2026-05-22 15:55:00", D, "Closed. lag_336 at 39% globally and 39% during stress, and its share grows on the other lags during stress - high-demand half-hours are strongly recurrent, which is exactly why they are forecastable."),
  ]),

I("DRG-9", "Epic", "Near-Real-Time Replay and External Feeds", "Done",
  """
Objective 7, part one: make the system behave like something operational
rather than a batch study.

Scope: a replay engine that streams historical half-hours at accelerated wall
clock, live weather and carbon-intensity feeds from key-free public APIs, and
a graceful path when a feed is unavailable.

Replay is event-time driven, so a replayed window reproduces exactly the
forecasts and alarms it produced the first time.
  """,
  epic_name="Replay & Feeds", assignee=V, priority="High",
  components="Streaming", labels="year2;streaming",
  created="2025-01-02 09:36:00", resolved="2026-03-27 16:10:00",
  comments=[
    ("2026-02-16 09:30:00", V, "Two rules, both borrowed from painful experience. Event time, never wall clock, or the replay is untestable. And no external feed is allowed to be load-bearing - if the weather API is down, the run degrades and says so, it does not fail."),
    ("2026-03-27 16:05:00", V, "Closed. Replay reproduces its output exactly across runs and both feeds are key-free, so this works on a laptop with no credentials."),
  ]),

I("DRG-10", "Epic", "Forecast and Scenario REST API", "Done",
  """
Objective 7, part two: serve forecasts, stress state and scenarios over HTTP
so DRG can be consumed by something other than its own dashboard.

Scope: FastAPI service, forecast and stress endpoints, scenario invocation,
health and readiness, OpenAPI docs, and a model version stamped on every
response so any answer can be reproduced later.
  """,
  epic_name="REST API", assignee=V, priority="High",
  components="API", labels="year2;api",
  created="2025-01-02 09:38:00", resolved="2026-06-19 15:30:00",
  comments=[
    ("2026-05-11 10:20:00", V, "Every response carries the model version and the as-of timestamp. A forecast you cannot trace back to a model artefact is a number you cannot defend three months later when someone asks why the plan said what it said."),
    ("2026-06-19 15:25:00", G, "Closed. Endpoints for forecast, stress, scenario and explanation, all versioned."),
  ]),

I("DRG-11", "Epic", "Operator Dashboard", "In Progress",
  """
The interface a network planner actually uses: demand and forecast, current
stress state, scenario comparison, SHAP drivers, and the replay view.

Scope: the Streamlit application, a shared chart theme, one page per question
the proposal asks, and a plain statement on every page of what the numbers
can and cannot tell you.
  """,
  epic_name="Operator Dashboard", assignee=D, priority="High",
  components="Dashboard", labels="year2;dashboard",
  created="2025-01-02 09:40:00",
  comments=[
    ("2026-04-27 09:35:00", D, "One chart theme before the first chart. Fixed colour per neighbourhood across every page, sequential ramps for magnitude only, and no dual axes - the same rules that stopped us shipping misleading charts elsewhere."),
    ("2026-09-07 11:40:00", D, "Remaining: the sensitivity page and the operator runbook panel. Everything else has shipped."),
  ]),

I("DRG-12", "Epic", "MLOps: Registry, Gates and Promotion", "In Progress",
  """
Stop "the model" meaning whatever is in someone's artefacts folder.

Scope: a model registry with versioned artefacts and metrics, a promotion
gate with explicit thresholds, a model spec that travels with the artefact,
and a promotion pipeline that refuses to ship a model that has regressed.

The gate checks stress-alarm F1 as well as error, because a model can improve
MAE while getting worse at the thing the platform exists to detect.
  """,
  epic_name="MLOps", assignee=V, priority="High",
  components="MLOps", labels="year2;mlops",
  created="2025-01-02 09:42:00",
  comments=[
    ("2026-06-01 10:30:00", V, "The gate is not a formality. It should have teeth, and it should occasionally stop us shipping something we were pleased with."),
    ("2026-07-13 14:15:00", G, "It already has - DRG-107 was a model with better MAE and worse stress F1, which is precisely the trade the gate exists to catch."),
  ]),

I("DRG-13", "Epic", "Azure Deployment and Infrastructure", "In Progress",
  """
Everything runs on laptops. There is no shared environment, no scheduled
retrain and no way for a stakeholder to see the system without one of us
running it.

Scope: Bicep for the Azure footprint - storage, container registry, key
vault, monitoring, Container Apps and an Azure ML workspace; AML training
jobs and managed online endpoints; and deployment scripts for both shells.
  """,
  epic_name="Azure Infrastructure", assignee=V, priority="High",
  components="Infrastructure", labels="year2;azure",
  created="2025-01-02 09:44:00",
  comments=[
    ("2026-06-22 09:50:00", V, "Bicep rather than Terraform here because the whole target estate is Azure and the ML workspace is the awkward part - the first-party templates are simply better maintained for AML."),
    ("2026-09-04 15:20:00", V, "Infrastructure deploys clean. The managed endpoint and the scheduled retrain are the two blocks left."),
  ]),

I("DRG-14", "Epic", "Engineering Practice and CI/CD", "Done",
  """
The habits that keep a research codebase usable: one command to run
everything, a real test suite, lint and format on every push, and a build
that fails when the pipeline does.

Scope: the CLI, the orchestrated end-to-end pipeline, GitHub Actions for CI
and for model and infrastructure deployment, containerisation, and the
developer setup scripts.
  """,
  epic_name="Engineering Practice", assignee=V, priority="High",
  components="Platform;CI", labels="foundation;ci",
  created="2025-01-02 09:46:00", resolved="2026-07-31 16:20:00",
  comments=[
    ("2025-01-13 11:20:00", V, "run-all exists from week two, not from month twelve. If the full pipeline is not runnable in one command early, every stage after it gets built against a slightly different idea of what came before."),
    ("2026-07-31 16:15:00", V, "Closed. CI runs the full pipeline on synthetic data on every push, in about seven minutes."),
  ]),

I("DRG-15", "Epic", "Documentation and Data Governance", "In Progress",
  """
What the system does, what it does not do, and what may be done with the data.

Scope: the architecture document, the business requirements document, the
README as the front door, the modelling notes, and the governance position on
the licensed dataset - what is redistributable, what is not, and why the
synthetic path exists.
  """,
  epic_name="Docs & Governance", assignee=G, priority="Medium",
  components="Docs", labels="docs;governance",
  created="2025-01-02 09:48:00",
  comments=[
    ("2025-02-24 10:10:00", G, "The non-goals section is the most important part of the architecture document. DRG does no power-flow modelling, and if that is not stated plainly on page one somebody will eventually present it as if it did."),
    ("2026-09-08 10:25:00", A, "Picking up the business requirements refresh. The original BRD predates about half of what has been built."),
  ]),

I("DRG-16", "Epic", "Delivery Management and Governance", "In Progress",
  """
Running the project: sprint ceremonies, the RAID log, stakeholder reporting,
onboarding, and the dependency and risk tracking that keeps a twenty-month
programme from drifting.

Owned by the project coordinator, and deliberately a real epic rather than
invisible overhead - the risks it tracks have changed delivery decisions.
  """,
  epic_name="Delivery Management", assignee=S, priority="Medium",
  components="Governance", labels="delivery;governance",
  created="2025-01-02 09:50:00",
  comments=[
    ("2025-01-02 10:05:00", S, "Cadence agreed: two-week sprints from Monday 6 January, planning on the first Monday, review and retro on the second Friday, written standups daily. Monthly stakeholder report on the first working day of the month."),
    ("2025-01-02 10:15:00", S, "RAID log is open. First entry is the LCL licence - we do not yet know whether we can redistribute any of it, and a lot depends on the answer."),
    ("2026-09-08 09:20:00", S, "Twenty months in. 43 sprints, six people, three of whom joined mid-flight. The onboarding pattern from DRG-99 and DRG-115 is now our standard."),
  ]),

I("DRG-17", "Epic", "Quality Engineering and Test Automation", "In Progress",
  """
Cut in June 2026 when the QA analyst joined.

Scope: a written test strategy per layer, regression packs for data,
features, models, stress, simulation and the API, dashboard smoke tests,
CI gating, and the UAT process with the stakeholder groups.

The premise, from the gap analysis in DRG-99: almost every defect on this
project has been silent - a plausible wrong number rather than a crash - so
coverage is about assertions between stages, not about counting tests.
  """,
  epic_name="Quality Engineering", assignee=N, priority="High",
  components="Quality", labels="qa;testing",
  created="2026-06-15 14:00:00",
  comments=[
    ("2026-06-15 14:20:00", S, "Cut this the day Neha started rather than folding QA work into other epics, so the coverage gap is visible on the board instead of being everyone's second priority."),
    ("2026-06-26 16:10:00", N, "First pass of the gap analysis is in. Three areas with no coverage at all: the simulation, the API contract, and anything asserting that a model artefact matches the spec it claims."),
    ("2026-09-08 15:40:00", N, "Data, features, models and stress now have regression packs. Simulation is in progress, UAT starts next sprint."),
  ]),

I("DRG-18", "Epic", "Business Analysis and Stakeholder Enablement", "In Progress",
  """
Cut in August 2026, ahead of the BA joining on 24 Aug.

Scope: refreshing the business requirements against what was actually built,
requirements traceability from the BRD through to modules and dashboard
views, the stakeholder-facing glossary, and UAT facilitation with the network
planning teams.

Why it exists late: for twenty months the modelling lead and the coordinator
carried the stakeholder relationship between them. That stopped scaling once
DNO planners, the sustainability team and the academic partner all wanted
different cuts of the same results.
  """,
  epic_name="Business Analysis", assignee=S, priority="Medium",
  components="Docs;Governance", labels="ba;stakeholders",
  created="2026-08-17 11:00:00",
  comments=[
    ("2026-08-17 11:15:00", S, "Creating this a week early so there is a real backlog on day one. Amit starts 24 Aug."),
    ("2026-08-25 10:40:00", A, "First read of the BRD against the repository. The gap is not that things are missing - it is that the document describes an ambition and the code has since answered it more precisely. The refresh is mostly replacing intentions with findings."),
  ]),

]
