# -*- coding: utf-8 -*-
"""DRG year two: 01 Jan - 09 Sep 2026, sprints 27-44. DRG-79 .. DRG-130.

Neha Chauhan (QA) joins 15 Jun 2026. Amit Shinde (BA) joins 24 Aug 2026.
Today is 09 Sep 2026, inside sprint 44.
"""

from backlog_common import I, G, D, V, N, A, S

YEAR2 = [

# ---------------------------------------------------------- Sprints 27-30
I("DRG-79", "Story", "Combined EV and heat pump scenario engine", "Done",
  """
As a planner
I want EV and heat pump adoption applied together to the same households
So that the combined effect on peak is measurable rather than assumed.

* a scenario is an adoption rate for each technology, applied per household
* the two loads are superimposed on the household's own baseline demand
* neighbourhood demand is re-aggregated from the modified households, never
  scaled at the aggregate level
  """,
  parent="DRG-6", assignee=D, priority="Highest", points="8",
  components="Simulation", labels="simulation", created="2026-01-05 09:20:00",
  resolved="2026-01-23 15:40:00",
  comments=[
    ("2026-01-07 10:30:00", D, "Re-aggregating from households is the whole point. Two households with an EV and a heat pump do not both plug in at 18:00, and only a bottom-up model can express that."),
    ("2026-01-23 15:35:00", G, "Accepted. And it immediately produced a result that looked wrong - see DRG-80."),
  ]),

I("DRG-80", "Bug", "Diversity lost - combined peak came out additive", "Done",
  """
Observed: the combined EV and heat pump scenario produced a peak amplification
almost exactly equal to the sum of the two technologies applied separately.
That is not what happens physically - the two loads peak at overlapping but
not identical times.

Diagnosis: the household profiles were being combined after each technology's
demand had already been aggregated to the neighbourhood and re-peaked. The
aggregation was applied twice and the second one destroyed the time offsets
between households.

Impact: none published. The additive figure would have overstated the peak by
roughly 29 percentage points at the highest scenario, in the direction that
makes the finding sound more alarming - which is the worst direction to be
wrong in.

Fix: superimpose per household at half-hourly resolution, aggregate once, at
the end.
  """,
  parent="DRG-6", assignee=D, reporter=G, priority="Highest", points="5",
  components="Simulation", labels="simulation;silent",
  created="2026-01-13 10:20:00", resolved="2026-01-22 15:10:00",
  comments=[
    ("2026-01-13 10:40:00", G, "The tell was that the combined number was suspiciously close to the sum. Physical systems very rarely add exactly, and when they do it usually means the model has lost the thing that would have made them not add."),
    ("2026-01-15 11:30:00", D, "Confirmed - aggregating twice. Fixing it so aggregation happens exactly once, at the end, and adding an assertion that the combined peak is strictly below the sum of the individual peaks."),
    ("2026-01-19 09:45:00", G, "That assertion is a good one because it encodes a physical fact rather than a code expectation. If it ever fails, either the model is wrong or something genuinely surprising is happening, and both are worth stopping for."),
    ("2026-01-22 15:05:00", D, "Fixed. EV alone at 80% gives +154%, heat pumps alone at 70% give +113%, together +237% rather than +267%. The 29 point gap is diversity, and it is now the headline rather than a caveat."),
  ]),

I("DRG-81", "Story", "Scenario sweep and peak amplification metrics", "Done",
  """
Five scenarios from base to high adoption, with the metrics a planner needs.

* peak amplification against base, energy growth, and the resulting stress
  frequency and mean event duration
* after-diversity maximum demand per EV and per heat pump printed in every
  scenario summary
* results written to the run report so the published table regenerates
  """,
  parent="DRG-6", assignee=D, points="5", components="Simulation",
  labels="simulation;metrics", created="2026-01-26 09:20:00",
  resolved="2026-02-06 15:30:00",
  comments=[
    ("2026-02-03 10:20:00", D, "Printing ADMD in every summary rather than in an appendix. It is the number a DNO planner will check against their own planning assumptions to decide whether to believe the rest of the table."),
    ("2026-02-06 15:25:00", G, "1.20 kW per EV and 1.30 kW per heat pump, both inside the range used in UK planning practice. That is the credibility check passed."),
  ]),

I("DRG-82", "Story", "Stress under electrification scenarios", "Done",
  """
Apply the DRG-68 thresholds - fixed at each site's historical P95 - to the
simulated scenario demand.

The thresholds do not move with the scenario. The question is how much more
often a neighbourhood exceeds what used to be its top 5%, which is only
meaningful if the bar stays where it was.
  """,
  parent="DRG-5", assignee=G, priority="High", points="5", components="Stress",
  labels="stress;simulation", created="2026-01-26 09:25:00",
  resolved="2026-02-13 15:50:00",
  comments=[
    ("2026-01-28 09:50:00", G, "Holding the threshold at the historical value is the crux. Recomputing P95 under each scenario would define stress away - the top 5% is always 5% - and produce the reassuring answer that nothing changes."),
    ("2026-02-13 15:45:00", D, "Base 4.4% of half-hours in stress, rising to 46.8% at the highest scenario. Roughly ten times more often, with mean event duration going from 2.2 to 6.9 hours."),
    ("2026-02-16 09:30:00", G, "The duration change may matter more than the frequency to an operator. A two-hour event is manageable; a seven-hour one covers the whole evening peak and leaves no recovery window."),
  ]),

I("DRG-83", "Task", "Q1 2026 planning and RAID review", "Done",
  """
Replan for 2026 and review risks.

* simulation closing, replay and sensitivity next
* QA resourcing still open, four months after it was raised
* new risk: the dashboard and API have no consumer yet, so we are building
  the interface before validating the workflow with a planner
  """,
  parent="DRG-16", assignee=S, points="2", components="Governance",
  labels="raid;ceremony", created="2026-01-05 09:15:00",
  resolved="2026-01-16 15:20:00",
  comments=[
    ("2026-01-16 15:10:00", S, "Raising the interface risk deliberately. We are about to spend two quarters building a dashboard for a user we have described rather than met, which is a pattern that ends with a beautiful tool nobody opens."),
    ("2026-01-19 10:20:00", G, "Agreed. Mitigation: get a network planner in front of the scenario results before the dashboard design is fixed, even if what we show them is a notebook."),
  ]),

I("DRG-84", "Story", "Scenario reporting artefacts", "Done",
  """
The figures and tables that carry the electrification finding: peak
amplification by scenario, the diversity gap, stress frequency and duration,
and the load shape overlay showing where in the day the amplification lands.

All regenerated by run-all, all written to artifacts.
  """,
  parent="DRG-6", assignee=D, points="5", components="Simulation",
  labels="reporting", created="2026-02-09 09:20:00",
  resolved="2026-02-20 15:10:00",
  comments=[
    ("2026-02-18 11:15:00", D, "The load shape overlay is the most persuasive of these. It shows the evening peak growing and widening rather than just a bigger number, and that is what makes the duration finding land."),
  ]),

# ---------------------------------------------------------- Sprints 31-34
I("DRG-85", "Story", "Near-real-time replay engine", "Done",
  """
As an operator
I want historical half-hours streamed at accelerated wall-clock speed
So that the system can be demonstrated and tested as if it were live.

* configurable acceleration - one half-hour of history per second
* each step produces a forecast, a stress evaluation and an explanation
* driven by event time from the data, not by the clock - see DRG-87
* a replayed window reproduces exactly the output it produced before
  """,
  parent="DRG-9", assignee=V, priority="High", points="8",
  components="Streaming", labels="streaming;replay",
  created="2026-02-16 09:20:00", resolved="2026-03-06 16:00:00",
  comments=[
    ("2026-02-18 10:30:00", V, "Replay is the only way to test the operational path without waiting for real time to pass. It has to be deterministic or it is a demo rather than a test."),
    ("2026-03-06 15:55:00", G, "Accepted. Two runs over the same window produce byte-identical output, which means the streaming path is now assertable."),
  ]),

I("DRG-86", "Story", "Carbon intensity feed", "Done",
  """
Live and historical grid carbon intensity from a key-free public API, so
demand and stress can be read alongside the carbon cost of meeting it.

* same caching and degradation contract as the weather feed (DRG-41)
* regional where the API supports it, national otherwise, and the page says
  which it is showing
  """,
  parent="DRG-9", assignee=V, points="5", components="Streaming",
  labels="external;carbon", created="2026-02-23 09:20:00",
  resolved="2026-03-06 15:20:00",
  comments=[
    ("2026-03-04 10:40:00", V, "Stating national versus regional on the page. It is a small honesty that stops someone quoting a national average as if it were their substation."),
  ]),

I("DRG-87", "Bug", "Replay windows driven by wall clock rather than event time", "Done",
  """
Observed: replaying the same window twice produced slightly different stress
event boundaries.

Cause: the rolling feature windows inside the replay loop were built from the
wall-clock time of processing rather than the event time of the data. A slow
step let a window advance further than it should have.

Impact: the replay path was non-deterministic and therefore untestable, and
the difference was small enough to look like noise rather than a defect.

Fix: every window and every timestamp inside replay derives from the event
time carried by the record. Wall clock controls only the pacing of the loop.
Assert identical output across two runs of the same window.
  """,
  parent="DRG-9", assignee=V, reporter=D, priority="High", points="5",
  components="Streaming", labels="streaming;determinism",
  created="2026-02-27 10:20:00", resolved="2026-03-10 14:40:00",
  comments=[
    ("2026-02-27 10:35:00", D, "Noticed because two replays of the same day disagreed on when an event ended. A one-period difference, which is exactly the size that gets dismissed as noise."),
    ("2026-03-02 09:40:00", V, "Confirmed. Wall clock had leaked into the window logic. This is the same lesson as the training-time leakage bugs in a different costume: something that should be derived from the data was derived from the environment."),
    ("2026-03-10 14:35:00", V, "Fixed and asserted. The pacing is the only thing the clock controls now."),
  ]),

I("DRG-88", "Story", "External feed degradation and reporting", "Done",
  """
No external feed may be load-bearing.

* a failed or rate-limited call falls back to cached data, then to a
  documented default, and records which of the three was used
* the run report and the dashboard both state when a feed was unavailable
* a degraded run is still a valid run, and is never silently presented as a
  fully-fed one
  """,
  parent="DRG-9", assignee=V, points="5", components="Streaming",
  labels="resilience", created="2026-03-09 09:20:00",
  resolved="2026-03-20 15:30:00",
  comments=[
    ("2026-03-18 11:20:00", V, "The three-level fallback with provenance recorded is the important part. A cached value silently substituted for a live one is how a demo shows yesterday's weather as if it were today's."),
    ("2026-03-20 15:25:00", S, "Closing the external dependency risk in the RAID log on the back of this. It moves from a delivery risk to a documented operational behaviour."),
  ]),

I("DRG-89", "Task", "Simulation handover notes", "Done",
  """
The equivalent of DRG-78 for the simulation stage: adoption sampling and why
it is consumption-weighted, the EV and heat pump profile assumptions, the
diversity result and how DRG-80 was found, and the ADMD sanity checks.

Second half of the knowledge concentration mitigation from DRG-50.
  """,
  parent="DRG-15", assignee=D, points="3", components="Docs",
  labels="docs;raid", created="2026-03-09 09:25:00",
  resolved="2026-03-24 14:20:00",
  comments=[
    ("2026-03-23 10:15:00", G, "Ran the scenario sweep from these notes without asking Divya anything, which is the acceptance test we used last time."),
    ("2026-03-24 14:15:00", S, "Knowledge concentration risk now closed rather than watched. Both critical stages are documented well enough to be operated by the other analyst."),
  ]),

# ---------------------------------------------------------- Sprints 35-36
I("DRG-90", "Story", "Sensitivity sweep framework", "Done",
  """
As the project
I want to sweep the assumptions and see how the conclusions move
So that we can say which assumptions the findings actually depend on.

* sweep any config parameter across a range, re-running the affected stages
* parameters in scope: adoption rates, charger power, heat pump COP, the
  stress percentile, and the event duration rules
* results tabulated so one assumption's effect is readable in isolation
  """,
  parent="DRG-7", assignee=G, points="8", components="Analysis",
  labels="sensitivity", created="2026-03-23 09:20:00",
  resolved="2026-04-03 16:00:00",
  comments=[
    ("2026-03-25 10:20:00", G, "Sweeping the stress percentile itself is the one people forget. If the entire finding changes between P90 and P95, then the finding is about our choice of percentile rather than about electrification."),
  ]),

I("DRG-91", "Story", "Sensitivity of stress frequency and duration", "Done",
  """
Objective 5 delivered: how stress frequency and mean event duration respond to
each assumption, across all four neighbourhoods.

Reported as the change in output per unit change in assumption, so the
assumptions can be ranked by how much they matter.
  """,
  parent="DRG-7", assignee=G, priority="High", points="5",
  components="Analysis", labels="sensitivity", created="2026-04-06 09:20:00",
  resolved="2026-04-17 15:40:00",
  comments=[
    ("2026-04-14 11:15:00", G, "Adoption rate dominates everything else by a wide margin. Charger power and COP matter within plausible ranges but do not change the direction or the order of magnitude, and the stress percentile shifts the absolute numbers without changing the ratio between scenarios."),
    ("2026-04-17 15:35:00", D, "Which is the reassuring version of this result. The conclusion is about electrification, not about our parameter choices."),
  ]),

I("DRG-92", "Task", "Publish which assumptions the conclusions depend on", "Done",
  """
Write up the sensitivity findings in the form a planner can use.

The claim we can defend: the ratio between scenarios is robust; the absolute
stress frequency depends on the percentile chosen; and everything depends on
the adoption rate, which is the one number we are not forecasting and should
not pretend to.
  """,
  parent="DRG-7", assignee=G, points="3", components="Docs",
  labels="sensitivity;honesty", created="2026-04-13 09:15:00",
  resolved="2026-04-24 14:30:00",
  comments=[
    ("2026-04-24 14:25:00", G, "Saying plainly that we do not forecast adoption is important. DRG tells you what happens if adoption reaches a level; it does not tell you whether it will, and conflating those two is how a scenario tool gets quoted as a prediction."),
  ]),

# ---------------------------------------------------------- Sprints 36-38
I("DRG-93", "Story", "SHAP global explanations", "Done",
  """
Objective 6: explain the primary model's forecasts.

* SHAP over the XGBoost model on the test window
* global driver ranking with each feature's share of total attribution
* cross-checked against the model's own feature importances - they should
  broadly agree, and a disagreement is worth investigating rather than
  ignoring
  """,
  parent="DRG-8", assignee=G, points="8", components="Explain",
  labels="xai;shap", created="2026-04-20 09:20:00",
  resolved="2026-05-08 15:50:00",
  comments=[
    ("2026-05-05 10:30:00", G, "lag_336 at 39%, lag_1 at 27%, lag_48 at 7.6%, time of day at 4%. That matches the autocorrelation analysis from DRG-36 fifteen months ago, which is a satisfying consistency check across two completely independent methods."),
    ("2026-05-08 15:45:00", D, "And it validates the feature design decision retrospectively. The weekly lag was the right thing to build first."),
  ]),

I("DRG-94", "Story", "SHAP during stress periods", "Done",
  """
The same attribution, restricted to half-hours that are actually in stress.

The operationally interesting question is whether stress is driven by
different factors than normal demand. If it is, the alarm needs a different
explanation; if it is not, that is reassuring and worth stating.
  """,
  parent="DRG-8", assignee=G, priority="High", points="5",
  components="Explain", labels="xai;stress", created="2026-05-04 09:20:00",
  resolved="2026-05-15 15:30:00",
  comments=[
    ("2026-05-13 11:20:00", G, "Same drivers, but the lag terms take a larger share during stress - lag_336 holds at 39%, lag_1 rises to 29%, lag_48 to 10.7%, and time of day falls. High-demand half-hours are more strongly recurrent than ordinary ones."),
    ("2026-05-15 15:25:00", D, "Which is the useful operational sentence: the stressful periods are the predictable ones. That is what makes them manageable rather than merely alarming."),
  ]),

I("DRG-95", "Bug", "SHAP values computed on scaled features and reported as raw", "Done",
  """
Observed: SHAP attributions for temperature were an order of magnitude
smaller than the lag features, which did not match the model's own importance
ranking.

Cause: explanations were computed on the standardised feature matrix but
labelled and plotted with the raw feature names and units, so contributions
were not comparable across features with different original scales.

Impact: the temperature driver looked negligible when it is not. Caught
before publication.

Fix: attribute in the model's feature space and report contributions as a
share of total absolute attribution, which is scale-free and comparable.
  """,
  parent="DRG-8", assignee=G, reporter=D, priority="High", points="3",
  components="Explain", labels="xai;silent",
  created="2026-05-11 10:20:00", resolved="2026-05-20 14:40:00",
  comments=[
    ("2026-05-11 10:35:00", D, "Flagged it because the SHAP ranking disagreed with the XGBoost feature importances, and DRG-93 said explicitly that a disagreement is worth investigating. That check earned its keep."),
    ("2026-05-20 14:35:00", G, "Fixed by reporting shares rather than absolute contributions. Also means the numbers are comparable between models, which will matter when the registry holds more than one."),
  ]),

I("DRG-96", "Story", "Dashboard shell and chart theme", "Done",
  """
As an operator
I want one application with a page per question
So that the analysis is usable without running Python.

* Streamlit multipage shell, neighbourhood and date range selected once and
  respected everywhere
* a single chart theme: fixed colour per neighbourhood across all pages,
  sequential ramps for magnitude only, no dual axes
* every page states the as-of date and the data source - real or synthetic
  """,
  parent="DRG-11", assignee=D, points="5", components="Dashboard",
  labels="dashboard;design-system", created="2026-04-27 09:20:00",
  resolved="2026-05-15 16:10:00",
  comments=[
    ("2026-04-29 10:15:00", D, "Theme before the first chart. The rule that matters most here is fixed colour per neighbourhood - four sites across six pages, and if the colours shuffle the reader has to relearn the legend every time."),
    ("2026-05-14 11:30:00", G, "The 'real or synthetic' badge is not optional. Someone will screenshot a synthetic run into a planning document otherwise, and the numbers are plausible enough that nobody would catch it."),
  ]),

I("DRG-97", "Story", "Demand and forecast page", "Done",
  """
The default view: actual demand, the forecast, the stress threshold and the
detected stress events for the selected neighbourhood and window.

* forecast error summarised for the visible window, not just overall
* stress events shaded, with duration on hover
* the model version behind the forecast shown on the page
  """,
  parent="DRG-11", assignee=D, points="5", components="Dashboard",
  labels="dashboard", created="2026-05-11 09:20:00",
  resolved="2026-05-29 15:40:00",
  comments=[
    ("2026-05-27 10:40:00", D, "Error for the visible window rather than the headline test figure. A planner looking at a cold week wants to know how the model did that week, and the overall number can hide a bad one."),
  ]),

# ---------------------------------------------------------- Sprints 39-40
I("DRG-98", "Task", "Prepare QA onboarding", "Done",
  """
Everything in place before the QA analyst starts on 15 June, so week one is
work rather than access requests.

* accounts, repository access, environment runbook
* a written first-week goal: run the pipeline, then write down what is not
  covered
* the modelling and simulation handover notes as reading material
  """,
  parent="DRG-16", assignee=S, points="2", components="Governance",
  labels="onboarding", created="2026-06-01 09:15:00",
  resolved="2026-06-12 15:20:00",
  comments=[
    ("2026-06-01 09:40:00", S, "Six months after it was raised at the year-end review. Recording the delay because the cost is visible: five of the defects since January were silent, and a QA perspective would have caught at least the SHAP scaling one sooner."),
    ("2026-06-12 15:15:00", V, "Runbook dry-run from a clean machine. run-all from a fresh clone works with no dataset and no keys, which is the whole point of the DRG-23 decision paying off eighteen months later."),
  ]),

I("DRG-99", "Task", "QA onboarding - Neha Chauhan", "Done",
  """
First week for the QA analyst joining 15 June 2026.

* environment up, full pipeline run end to end
* walk through the stage contract, the leakage rules and the stress definition
* deliverable: a written gap analysis of what the current tests do not cover
  """,
  parent="DRG-17", assignee=N, points="3", components="Quality",
  labels="onboarding", created="2026-06-15 09:30:00",
  resolved="2026-06-26 16:00:00",
  comments=[
    ("2026-06-16 11:20:00", N, "run-all worked first time from the runbook, on synthetic data, with no credentials. That is rarer than it should be and it made the first day useful rather than administrative."),
    ("2026-06-19 14:30:00", N, "Read the modelling notes. The striking thing is that of the eight significant defects on this project, seven produced a plausible wrong number rather than a failure. That shapes what I should be testing: agreement between stages, not behaviour of functions."),
    ("2026-06-26 15:50:00", N, "Gap analysis done. No coverage at all on the simulation, the API contract, or anything checking that a model artefact matches the feature spec it claims. The third one is the quiet risk - the DRG-63 check exists but nothing tests that it fires."),
    ("2026-06-26 16:10:00", G, "That last point is a good catch and it is exactly the kind of thing we could not see from inside. Raising it into the gate work."),
  ]),

I("DRG-100", "Story", "Test strategy and per-stage regression scope", "Done",
  """
As the team
I want a written statement of what is asserted at each stage
So that 'covered' means something specific.

* per stage - ingestion, features, models, stress, simulation, replay, API,
  dashboard - what is asserted, what is deliberately not, and why
* the leakage rules from DRG-46, DRG-58 and DRG-69 restated as standing
  assertions rather than remembered incidents
* gaps listed as tickets rather than as prose
  """,
  parent="DRG-17", assignee=N, points="5", components="Quality",
  labels="testing;strategy", created="2026-06-22 09:20:00",
  resolved="2026-07-03 15:40:00",
  comments=[
    ("2026-06-30 10:20:00", N, "Turning the three leakage incidents into one standing rule with a test each: anything estimated from data is fitted on train only. That was already written in the modelling notes as a rule; it just was not enforced anywhere."),
    ("2026-07-03 15:35:00", G, "Which is the difference between a lesson and a control. We wrote the rule down in November and still had to remember it."),
  ]),

I("DRG-101", "Story", "FastAPI service and forecast endpoint", "Done",
  """
As another system
I want forecasts over HTTP
So that DRG is consumable without running its dashboard.

* FastAPI with OpenAPI docs
* forecast endpoint: neighbourhood, horizon, returns the series with the
  stress threshold and predicted stress flags
* health and readiness endpoints that distinguish 'running' from 'has a model'
* every response carries the model version and an as-of timestamp
  """,
  parent="DRG-10", assignee=V, points="8", components="API",
  labels="api", created="2026-06-08 09:20:00", resolved="2026-06-26 15:50:00",
  comments=[
    ("2026-06-10 10:30:00", V, "Readiness separate from health. A container that is up but has no model loaded should not receive traffic, and conflating the two is how you serve 500s to a load balancer that thinks everything is fine."),
    ("2026-06-24 11:15:00", N, "Reviewed the contract before the implementation was finished, which was the right order. Asked for the error shape to be specified too - a documented success response and an undocumented failure response is half a contract."),
  ]),

I("DRG-102", "Story", "Stress, scenario and explanation endpoints", "Done",
  """
* stress endpoint: current and historical stress state for a neighbourhood
* scenario endpoint: run an adoption scenario and return peak amplification,
  energy growth and stress statistics
* explanation endpoint: SHAP contributions for a specific forecast
* scenario runs are bounded and reject parameter values outside the ranges
  the simulation was validated over
  """,
  parent="DRG-10", assignee=V, points="8", components="API",
  labels="api", created="2026-06-29 09:20:00", resolved="2026-07-17 15:40:00",
  comments=[
    ("2026-07-08 10:40:00", V, "Rejecting out-of-range scenario parameters rather than extrapolating. A 100% adoption request would return a number, and that number would be outside anything the simulation was sanity-checked against."),
    ("2026-07-15 14:20:00", N, "Tested the boundaries. It refuses cleanly with a message naming the valid range, which is what an integrator needs rather than a stack trace."),
  ]),

I("DRG-103", "Bug", "API responses omitted the model version", "Done",
  """
Observed: the forecast endpoint returned values with no indication of which
model produced them, despite DRG-63 making the version available.

Impact: a forecast retrieved through the API could not be reproduced or
attributed later. For a system whose output feeds planning decisions, that is
the difference between an auditable number and an anecdote.

Fix: model version, artefact hash and as-of timestamp on every response from
every endpoint, and a contract test that fails if any endpoint omits them.
  """,
  parent="DRG-10", assignee=V, reporter=N, priority="High", points="3",
  components="API", labels="api;traceability",
  created="2026-07-06 11:20:00", resolved="2026-07-14 14:30:00",
  comments=[
    ("2026-07-06 11:35:00", N, "Raising it against the contract rather than the code - the OpenAPI schema promised a version field and the responses did not carry one. Those disagreeing is the actual defect."),
    ("2026-07-09 09:50:00", V, "Fair, and the contract test is the right fix. Doing it endpoint by endpoint would leave the next endpoint to remember."),
    ("2026-07-14 14:25:00", N, "Contract test asserts it across every route, including ones added later. Verified."),
  ]),

I("DRG-104", "Story", "Scenario comparison page", "Done",
  """
The page that carries the project's headline finding.

* scenarios side by side: peak amplification, energy growth, stress frequency
  and mean duration
* the load shape overlay showing where in the day the amplification lands
* the diversity result stated on the page - EV alone, heat pumps alone, and
  the combined figure that is 29 points below their sum
* ADMD per device shown, so the assumptions are auditable from the interface
  """,
  parent="DRG-11", assignee=D, priority="High", points="8",
  components="Dashboard", labels="dashboard;simulation",
  created="2026-06-22 09:25:00", resolved="2026-07-10 16:00:00",
  comments=[
    ("2026-07-01 10:20:00", D, "Putting the diversity number on the page rather than in a tooltip. It is the most defensible thing we have found and it is also the thing most likely to be lost if the page only shows the scary total."),
    ("2026-07-10 15:55:00", G, "Accepted. A planner can now see the amplification, where in the day it lands, and the per-device assumptions behind it, in one view."),
  ]),

# ---------------------------------------------------------- Sprints 41-42
I("DRG-105", "Story", "Model registry", "Done",
  """
As the platform
I want every trained model recorded with its metrics and provenance
So that 'the current model' is a fact rather than a convention.

* versioned entries with metrics, training window, config and data hashes
* a pointer to the current production model
* history retained, so a regression can be compared against what it replaced
  """,
  parent="DRG-12", assignee=V, points="5", components="MLOps",
  labels="mlops;registry", created="2026-07-06 09:20:00",
  resolved="2026-07-17 15:20:00",
  comments=[
    ("2026-07-16 10:30:00", V, "Built on the DRG-63 metadata rather than inventing a second format. The registry is an index over artefacts that already describe themselves."),
  ]),

I("DRG-106", "Story", "Model promotion gate", "Done",
  """
As the project
I want a model to have to earn promotion
So that a regression cannot reach the API by being the most recent thing
trained.

Gate criteria, all against the current production model on the same window:
* MAE no worse by more than a configured tolerance
* stress-alarm F1 no worse at all
* the feature spec matches what the serving path will supply
* the model beats the seasonal naive baseline - a floor, not a formality

A failed gate blocks promotion and reports which criterion failed.
  """,
  parent="DRG-12", assignee=V, priority="High", points="8",
  components="MLOps", labels="mlops;gate", created="2026-07-06 09:25:00",
  resolved="2026-07-24 15:50:00",
  comments=[
    ("2026-07-08 10:20:00", G, "Stress F1 with no tolerance at all, unlike MAE. The whole platform exists to detect stress, and trading that away for average error is precisely the trade we must not make silently."),
    ("2026-07-20 11:30:00", N, "Added the feature-spec check Neha raised in onboarding - the artefact declares its features and the gate asserts the serving path supplies exactly those. It caught a column ordering difference on the first run."),
    ("2026-07-24 15:45:00", V, "Gate live. And it blocked a promotion within a fortnight, which is the point - see DRG-107."),
  ]),

I("DRG-107", "Bug", "A retrained model improved MAE and got worse at stress", "Done",
  """
Observed: a scheduled retrain produced a model with MAE 0.68 against the
incumbent's 0.70, and the promotion gate blocked it.

Diagnosis: not a defect in the model or the gate - the gate working. The new
model's stress-alarm F1 was 0.87 against the incumbent's 0.90. It had improved
on the quiet half-hours, which are the bulk of the data, and got worse at the
peaks, which are the point.

Cause: the extra training data included an unusually mild period, shifting the
model toward the middle of the distribution.

Outcome: promotion refused, incumbent retained, and the retrain window
adjusted to weight recent peak periods more heavily.
  """,
  parent="DRG-12", assignee=G, reporter=V, priority="High", points="5",
  components="MLOps", labels="mlops;gate", created="2026-07-27 10:20:00",
  resolved="2026-08-07 15:10:00",
  comments=[
    ("2026-07-27 10:35:00", V, "Filing this as a bug so the reasoning is recorded somewhere findable, though the system behaved correctly. Without the gate we would have shipped a better-looking model that was worse at the job."),
    ("2026-07-29 09:40:00", G, "This is the clearest possible justification for putting stress F1 in the gate with zero tolerance. A single headline metric would have promoted it and nobody would have noticed until an event was missed."),
    ("2026-08-05 11:15:00", N, "Adding a regression test that constructs exactly this case - better MAE, worse F1 - and asserts the gate refuses it. Otherwise a future refactor could relax the gate and nothing would catch it."),
    ("2026-08-07 15:05:00", G, "Retrain window reweighted and the next candidate passed on both. Keeping this ticket linked from the MLOps epic as the worked example."),
  ]),

I("DRG-108", "Story", "SHAP explanation page", "Done",
  """
Global drivers, drivers during stress, and per-forecast explanations for a
selected half-hour.

* contributions as shares, per DRG-95, so features are comparable
* the stress-period ranking shown next to the global one, since the
  comparison is the finding
* plain-language note that these are model attributions, not causes
  """,
  parent="DRG-11", assignee=D, points="5", components="Dashboard",
  labels="dashboard;xai", created="2026-07-20 09:20:00",
  resolved="2026-07-31 15:30:00",
  comments=[
    ("2026-07-29 10:40:00", D, "The attribution-not-causation note is on the page rather than in documentation. Someone will otherwise read 'lag_336 drives 39% of demand' as a statement about the world instead of about the model."),
  ]),

I("DRG-109", "Story", "Regression pack: data and features", "Done",
  """
* 48 half-hours per household per UTC day, including across both clock changes
* no forward filling in aggregation; gaps propagate as nulls and are counted
* every fitted transform is fitted on train only - the standing rule from
  DRG-100, asserted per transform
* no feature correlates with the target above the leakage threshold
* two runs on the same seed produce identical processed artefacts
  """,
  parent="DRG-17", assignee=N, points="5", components="Quality",
  labels="testing;data", created="2026-07-06 09:30:00",
  resolved="2026-07-24 16:10:00",
  comments=[
    ("2026-07-14 10:20:00", N, "The clock-change case is a fixture that spans both October and March, so the assertion is exercised rather than theoretical. It is cheap and it covers the defect that started this project's data quality work."),
    ("2026-07-24 16:05:00", D, "Determinism assertion is the one I am most glad of. It is the property everything else quietly depends on."),
  ]),

I("DRG-110", "Bug", "Dashboard served one neighbourhood's data under another's label", "Done",
  """
Observed: switching neighbourhood in the sidebar updated the title and the
threshold line but not the demand series, until the page was reloaded.

Impact: a chart showing site A's demand labelled as site B. Visually plausible,
completely wrong, and the kind of thing that gets screenshotted into a
planning document.

Cause: the cached data loader was keyed on the date range only, so a
neighbourhood change was a cache hit.

Fix: every cache key includes the full selection. Plus a smoke test that
switches neighbourhood and asserts the rendered series changes.
  """,
  parent="DRG-11", assignee=D, reporter=N, priority="High", points="3",
  components="Dashboard", labels="dashboard;silent",
  created="2026-07-21 11:15:00", resolved="2026-07-29 14:20:00",
  comments=[
    ("2026-07-21 11:30:00", N, "Found it by clicking through the sites in order and noticing the peak did not move. Two of the four sites have similar magnitudes, so on those it is genuinely undetectable by eye."),
    ("2026-07-23 09:45:00", D, "A cache key missing part of its input, which is the same class of defect as the API missing its version field - the identity of the thing was incomplete."),
    ("2026-07-29 14:15:00", N, "Fixed and covered. The smoke test asserts the data changes, not just that the page renders."),
  ]),

# ---------------------------------------------------------- Sprints 42-43
I("DRG-111", "Story", "Azure infrastructure as Bicep", "Done",
  """
The full footprint as code: storage, container registry, key vault,
monitoring, Container Apps and an Azure ML workspace.

* module per concern, parameter file per environment
* no secrets in parameters - key vault references throughout
* managed identity between services rather than connection strings
* non-production scales to zero
  """,
  parent="DRG-13", assignee=V, points="13", components="Infrastructure",
  labels="azure;bicep", created="2026-07-20 09:25:00",
  resolved="2026-08-14 15:40:00",
  comments=[
    ("2026-07-30 10:30:00", V, "Bicep over Terraform here specifically because of the ML workspace. The first-party templates for AML are simply better maintained, and this estate is entirely Azure so the portability argument does not apply."),
    ("2026-08-12 11:20:00", V, "Managed identity throughout. No connection strings in configuration means no connection strings to leak, and it removes the rotation problem entirely."),
    ("2026-08-14 15:35:00", S, "Deploys clean into the non-production subscription. Recording in the RAID log that the shared environment risk from January is now closed."),
  ]),

I("DRG-112", "Story", "Azure ML training job", "Done",
  """
Training runs as an AML job rather than on a laptop.

* environment definition pinned, job definition in the repository
* the same pipeline code as local - no separate cloud training path
* metrics and artefacts logged to the workspace and to the registry
  """,
  parent="DRG-13", assignee=V, points="8", components="Infrastructure",
  labels="azure;aml", created="2026-08-03 09:20:00",
  resolved="2026-08-21 15:30:00",
  comments=[
    ("2026-08-19 10:40:00", V, "Same code path locally and in AML. A separate cloud training script is how the two silently diverge and the cloud model stops matching what was validated."),
  ]),

I("DRG-113", "Story", "Managed online endpoint for scoring", "In Progress",
  """
Serve the promoted model from an AML managed online endpoint.

* deployment and endpoint definitions in the repository
* only a model that passed the gate may be deployed
* scoring script shares the feature construction code with training
* endpoint verified against a known request and expected response before
  traffic is shifted
  """,
  parent="DRG-13", assignee=V, points="8", components="Infrastructure",
  labels="azure;aml", created="2026-08-17 09:20:00",
  comments=[
    ("2026-08-26 11:15:00", V, "The scoring path shares feature construction with training rather than reimplementing it. Training-serving skew from two copies of the same logic is the classic way a deployed model quietly stops matching its evaluation."),
    ("2026-09-07 14:30:00", V, "Endpoint deploys and scores. Verification script and the traffic-shift step are what remain."),
  ]),

I("DRG-114", "Task", "Infrastructure cost pass", "Done",
  """
Cost the environments and bring non-production down to a defensible level.

* Container Apps scaled to zero outside working hours
* AML compute on low-priority for training, deallocating when idle
* storage lifecycle rules to cool tier
* the estimate committed alongside the Bicep so a change that raises it is
  visible in the diff
  """,
  parent="DRG-13", assignee=V, points="3", components="Infrastructure",
  labels="azure;cost", created="2026-08-17 09:25:00",
  resolved="2026-08-28 15:10:00",
  comments=[
    ("2026-08-20 10:20:00", V, "The compute that was going to cost the most was AML idling. Low-priority with aggressive deallocation takes training cost down to something that is genuinely rounding error for a nightly job."),
    ("2026-08-28 15:05:00", S, "Attached to the August stakeholder report. Non-production comes in under the threshold that would need a conversation, which is the practical test."),
  ]),

I("DRG-115", "Task", "BA onboarding - Amit Shinde", "Done",
  """
First week for the business analyst joining 24 August 2026.

* environment, repository and dashboard access
* walk through the proposal objectives and where each is answered in the code
* introductions to the network planning, sustainability and academic
  stakeholders
* deliverable: the gap between what the BRD promised and what exists
  """,
  parent="DRG-18", assignee=A, points="3", components="Governance",
  labels="onboarding", created="2026-08-24 09:30:00",
  resolved="2026-09-04 15:40:00",
  comments=[
    ("2026-08-25 15:20:00", A, "Started with the objectives table in the README, which maps each proposal objective to the module that answers it. That is an unusually good front door - most projects make you infer that mapping."),
    ("2026-08-28 11:30:00", A, "Halfway through the stakeholder conversations. The recurring theme is not doubt about the numbers, it is that different groups want different cuts - planners want per-substation, sustainability wants carbon, the academic partner wants the method. One dashboard is currently trying to be all three."),
    ("2026-09-04 15:35:00", A, "Gap list done. Nine items: four already answered by something they had not seen, three genuine gaps, and two that are out of scope by design - power flow and adoption forecasting - which need saying clearly rather than being left open."),
    ("2026-09-04 16:00:00", G, "Those last two are exactly the non-goals from DRG-31. Good to have them confirmed as live stakeholder expectations rather than hypothetical ones."),
  ]),

I("DRG-116", "Story", "Regression pack: models and stress", "Done",
  """
* the model ladder runs and every model reports on the same window
* the naive baseline is present in every comparison
* stress thresholds are derived from the training window only
* stress events respect the minimum duration and gap-bridging rules
* a model that regresses on stress F1 fails the gate (the DRG-107 case)
  """,
  parent="DRG-17", assignee=N, points="5", components="Quality",
  labels="testing;models", created="2026-08-03 09:30:00",
  resolved="2026-08-21 15:50:00",
  comments=[
    ("2026-08-14 10:30:00", N, "Asserting the baseline is present in the comparison, not just that it scores well. The failure mode is someone dropping it from the table for looking bad, and then no result is anchored to anything."),
  ]),

I("DRG-117", "Story", "Replay page", "Done",
  """
The operational view: replay a historical window at accelerated speed with
live forecast, stress state and explanation updating as it advances.

* replay controls, speed, and a clear indication that this is replay of
  historical data rather than a live feed
* stress alarms surfaced as they would be to an operator
  """,
  parent="DRG-11", assignee=D, points="5", components="Dashboard",
  labels="dashboard;streaming", created="2026-08-10 09:20:00",
  resolved="2026-08-28 15:20:00",
  comments=[
    ("2026-08-26 10:40:00", D, "Labelling it as replay prominently. A convincing operational view of historical data is exactly the thing that gets mistaken for a live system in a demo."),
  ]),

# --------------------------------------------------------------- Sprint 44
I("DRG-118", "Story", "Business requirements refresh", "In Progress",
  """
Bring the BRD in line with what was built, and separate what changed from
what was learned.

* each original requirement marked delivered, changed, or out of scope, with
  the reason
* the non-goals restated in business language, since two stakeholder groups
  are currently expecting them
* the findings that were not requirements - diversity, the recurrence of
  stress periods - added as delivered value
  """,
  parent="DRG-18", assignee=A, points="5", components="Docs",
  labels="ba;requirements", created="2026-08-31 09:20:00",
  comments=[
    ("2026-09-03 10:30:00", A, "Most of this is not gap-filling. The document describes an ambition and the code has since answered it more precisely - the refresh is mostly replacing intentions with findings."),
    ("2026-09-08 11:20:00", A, "Two thirds through. The diversity result is the clearest example: nobody asked for it, and it is arguably the most planning-relevant thing here."),
  ]),

I("DRG-119", "Story", "Requirements traceability matrix", "In Progress",
  """
Each requirement traced to the module that implements it, the artefact that
evidences it, the dashboard view that shows it and the test that covers it.

Gaps appear as empty cells rather than absent rows.
  """,
  parent="DRG-18", assignee=A, points="5", components="Docs",
  labels="ba;traceability", created="2026-08-31 09:25:00",
  comments=[
    ("2026-09-07 14:20:00", A, "Twenty-one of twenty-six requirements traced. Two have a dashboard view and no test, which Neha is picking up, and one has a test and no view - the sensitivity results are computed and reported but there is nowhere to look at them, which is DRG-122."),
    ("2026-09-08 09:50:00", N, "Taking the two untested ones into the simulation pack this sprint."),
  ]),

I("DRG-120", "Story", "Regression pack: simulation and scenarios", "In Progress",
  """
The last uncovered stage, and the one carrying the headline finding.

* adoption sampling honours the requested rate within tolerance
* the combined peak is strictly below the sum of individual peaks - the
  DRG-80 assertion, as a permanent control
* ADMD per device stays inside the validated range for every scenario
* scenario output is deterministic for a given seed
* stress thresholds do not move between scenarios
  """,
  parent="DRG-17", assignee=N, points="8", components="Quality",
  labels="testing;simulation", created="2026-08-31 09:30:00",
  comments=[
    ("2026-09-02 10:20:00", N, "The combined-below-additive assertion is the one I care most about, because it encodes a physical fact rather than a coding expectation. If it ever fails, something real has changed."),
    ("2026-09-08 15:30:00", N, "Sampling, determinism and threshold stability are in and passing. ADMD range checks are what remain."),
  ]),

I("DRG-121", "Story", "UAT pack and stakeholder sign-off", "To Do",
  """
* scripted scenarios per stakeholder group in business language
* expected results derived from the requirements and the modelling notes, not
  from the current dashboard output
* a defect log with a defined route back into the backlog
* written sign-off per group, recorded against the traceability matrix
  """,
  parent="DRG-17", assignee=N, points="5", components="Quality",
  labels="uat;testing", created="2026-09-07 09:20:00",
  comments=[
    ("2026-09-08 15:45:00", N, "Expected results come from the requirements rather than from what the dashboard currently shows. Deriving them from the dashboard tests that it agrees with itself, which it always will."),
    ("2026-09-08 16:00:00", A, "I will facilitate and take sign-offs into the matrix. Network planning first - they have the most at stake in the scenario numbers."),
  ]),

I("DRG-122", "Story", "Sensitivity page", "To Do",
  """
Surface the sensitivity results, which are currently computed and reported to
artefacts but have nowhere to be seen.

* how stress frequency and duration move with each assumption
* the assumptions ranked by how much they matter
* the statement that adoption rate dominates, and that DRG does not forecast
  adoption
  """,
  parent="DRG-11", assignee=D, points="5", components="Dashboard",
  labels="dashboard;sensitivity", created="2026-09-07 09:25:00",
  comments=[
    ("2026-09-07 14:30:00", A, "Flagging this from the traceability work - the sensitivity requirement is delivered in code and invisible in the product, which is the one row with a test and no view."),
  ]),

I("DRG-123", "Story", "Scheduled retrain", "In Progress",
  """
A scheduled AML job that retrains, evaluates and offers the model to the
promotion gate.

* runs on a schedule; promotion is never automatic, the gate decides
* a blocked promotion notifies rather than failing silently
* the incumbent stays serving until something better passes
  """,
  parent="DRG-13", assignee=V, points="5", components="Infrastructure",
  labels="azure;mlops", created="2026-08-31 09:35:00",
  comments=[
    ("2026-09-04 11:20:00", V, "Retrain is scheduled, promotion is gated. Automating the retrain is safe; automating the promotion would mean the DRG-107 model shipped itself at 3am."),
  ]),

I("DRG-124", "Task", "Monitoring and alerting with a named owner", "To Do",
  """
Application and model monitoring, routed to someone who is expected to act.

* endpoint availability and latency; job success and failure
* forecast error tracked against the evaluation baseline, so drift is visible
* deliberately blocked on agreeing an owner and a response expectation -
  routing to a rota that does not exist is worse than not alerting
  """,
  parent="DRG-13", assignee=V, points="5", components="Infrastructure",
  labels="azure;monitoring;blocked", created="2026-09-07 09:30:00",
  comments=[
    ("2026-09-07 09:50:00", V, "The infrastructure creates the action group already. Nothing routes to it, and that is deliberate rather than unfinished."),
    ("2026-09-08 10:15:00", S, "This is an organisational decision, not a technical one, and it is on the October steering agenda. Recording it in the RAID log as the largest open operational gap."),
  ]),

I("DRG-125", "Story", "Operator runbook panel", "To Do",
  """
What an operator should do when a stress alarm fires: what the alarm means,
what it does not mean, what to check, and where the number came from.

The alarm is only useful if the person receiving it knows what action it
implies. Written with the network planning group rather than for them.
  """,
  parent="DRG-11", assignee=G, points="5", components="Dashboard",
  labels="dashboard;operations", created="2026-09-07 09:35:00",
  comments=[
    ("2026-09-08 11:50:00", G, "'What it does not mean' is the important half. A stress alarm is not a capacity breach, and an operator acting as though it were would be acting on a claim we have never made."),
  ]),

# ----------------------------------------------------------------- Backlog
I("DRG-126", "Story", "Probabilistic forecasts with prediction intervals", "To Do",
  """
Move from point forecasts to quantiles, so a planner sees the range rather
than a single number.

Why it has waited: the point forecast had to be trustworthy first, and the
stress framing is currently binary. Intervals change what the alarm means and
that is a stakeholder conversation, not just a modelling change.

Trigger: the first time someone asks how confident the forecast is - which
has now happened twice.
  """,
  parent="DRG-4", assignee=G, sprint="", points="13", components="Models",
  labels="backlog;modelling", created="2026-05-18 10:20:00",
  comments=[
    ("2026-05-18 10:35:00", G, "Raising it at the point of deciding not to do it, with the trigger written down."),
    ("2026-09-08 10:40:00", A, "Asked twice in my stakeholder conversations. Moving it up the backlog for the October planning."),
  ]),

I("DRG-127", "Story", "Network topology and power flow integration", "To Do",
  """
Integrate real network topology and transformer ratings, so stress can be
expressed against actual capacity rather than statistically.

Why it has waited: it is the stated non-goal of the current system, and it
needs DNO asset data we do not have and may not be able to obtain.

What it would unlock: 'this feeder exceeds its rating' rather than 'this
neighbourhood is above its own P95'. A different and stronger claim.

This is a data access negotiation before it is an engineering task.
  """,
  parent="DRG-5", assignee=S, sprint="", points="13", components="Stress",
  labels="backlog;scope", created="2026-02-24 10:30:00",
  comments=[
    ("2026-02-24 10:45:00", S, "Recording it as a backlog item rather than leaving it as a non-goal only, so the boundary is visible as a choice with a route past it rather than as a permanent limitation."),
    ("2026-09-04 16:10:00", A, "Two stakeholder groups expect this. Worth being explicit with them that it is out of scope by design today, and what it would take."),
  ]),

I("DRG-128", "Story", "Scale beyond four neighbourhoods", "To Do",
  """
Generalise from four calibrated neighbourhoods to an arbitrary set.

Why it has waited: four sites are enough to demonstrate the method and small
enough to reason about. Scaling changes the training strategy - one shared
model may not hold across a hundred heterogeneous sites.

Trigger: a partner supplying data for more sites.
  """,
  parent="DRG-4", assignee=G, sprint="", points="13", components="Models",
  labels="backlog;scale", created="2026-06-08 10:15:00",
  comments=[
    ("2026-06-08 10:30:00", G, "The shared-model finding from DRG-59 was tested on four sites. It is not safe to assume it holds at a hundred, and that is the first thing to check rather than the last."),
  ]),

I("DRG-129", "Story", "Drift detection on the live feed", "To Do",
  """
Detect data that is structurally valid and quietly different: a meter
population change, a shift in the demand distribution, weather data that
stops updating.

Why it has waited: the quality checks catch broken data; drift needs a
baseline history to compare against, and the deployed system has only just
started producing one.
  """,
  parent="DRG-12", assignee=N, sprint="", points="8", components="Quality",
  labels="backlog;monitoring", created="2026-08-11 11:20:00",
  comments=[
    ("2026-08-11 11:35:00", N, "Raising it now so the run history is retained in a shape that makes it possible later. Discovering in six months that we discarded the baseline would be annoying."),
  ]),

I("DRG-130", "Story", "Shadow deployment for candidate models", "To Do",
  """
Run a candidate model alongside the incumbent on live traffic, comparing
predictions without serving them.

Why it has waited: the gate compares on a held-out window, which is adequate
while there is one endpoint and a nightly retrain. Shadow evaluation earns its
place when a candidate passes the gate and we still want evidence before
switching.

Related: DRG-107 is exactly the case where shadow evidence would have been
informative.
  """,
  parent="DRG-12", assignee=V, sprint="", points="8", components="MLOps",
  labels="backlog;mlops", created="2026-08-07 15:20:00",
  comments=[
    ("2026-08-07 15:30:00", V, "Raised off the back of the blocked promotion. The gate made the right call on the evidence it had; shadow traffic would have told us whether it was right in production too."),
  ]),

]
