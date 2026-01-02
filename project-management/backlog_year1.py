# -*- coding: utf-8 -*-
"""DRG year one: 02 Jan - 31 Dec 2025, sprints 1-26. DRG-19 .. DRG-78.

Team for this stretch is four: Geetha (modelling), Divya (data, features,
simulation), Devendranath (platform) and Sabitha (coordination). QA joins in
June 2026, the BA in August 2026.
"""

from backlog_common import I, G, D, V, S

YEAR1 = [

# ---------------------------------------------------------------- Sprint 1
I("DRG-19", "Task", "Project kickoff, ways of working and the RAID log", "Done",
  """
Agree how the project runs before it starts running.

* two-week sprints from Mon 06 Jan; planning first Monday, review and retro
  second Friday, written standups daily
* definition of done: merged, tested, runnable from the CLI, documented
* RAID log opened and reviewed at every planning session
* monthly stakeholder report on the first working day of the month
  """,
  parent="DRG-16", assignee=S, sprint=None, points="2", components="Governance",
  labels="kickoff", created="2025-01-02 09:15:00", resolved="2025-01-09 15:20:00",
  comments=[
    ("2025-01-02 10:20:00", S, "Definition of done includes 'runnable from the CLI'. On a twenty-month research project the failure mode is a pile of notebooks nobody else can execute, and the cheapest defence is to make runnability part of done from day one."),
    ("2025-01-06 11:30:00", V, "Strongly agree. I would add that it has to run without the licensed dataset, otherwise 'runnable' means runnable by whoever has the data."),
    ("2025-01-09 15:15:00", S, "Both in. RAID log open with three initial risks: the LCL licence, PyTorch on Windows, and single points of knowledge across a small team."),
  ]),

I("DRG-20", "Story", "Repository scaffold and packaging", "Done",
  """
As an engineer
I want a src-layout package that installs cleanly
So that imports behave the same in tests, CLI and notebooks.

* src/drg with analysis, data, features, models, stress, simulation, explain,
  streaming, api, dashboard, mlops, utils
* pyproject.toml, editable install, console entry point
* artifacts/ and data/ gitignored with their structure documented
  """,
  parent="DRG-14", assignee=V, points="3", components="Platform",
  labels="setup", created="2025-01-06 09:20:00", resolved="2025-01-10 14:40:00",
  comments=[
    ("2025-01-07 10:15:00", V, "src layout rather than a flat package. It costs one line in pyproject and it means a test can never accidentally import the working directory instead of the installed package - which is how you get a green suite against code that would not ship."),
    ("2025-01-10 14:35:00", D, "Verified from a clean venv on Windows and Linux."),
  ]),

I("DRG-21", "Task", "Split dependencies into core, deep, azure and dev tiers", "Done",
  """
Keep the base install small enough that a reviewer can run the project.

* requirements.txt - everything needed for run-all
* requirements-deep.txt - PyTorch, optional
* requirements-azure.txt - Azure SDKs, MLflow, optional
* requirements-dev.txt - pytest, ruff, black
* README states which tier is needed for which command
  """,
  parent="DRG-14", assignee=V, points="2", components="Platform",
  labels="setup", created="2025-01-06 09:25:00", resolved="2025-01-14 11:20:00",
  comments=[
    ("2025-01-13 10:40:00", V, "Torch is deliberately not in the base install. It is a large download, it is optional to the argument the project is making, and on Windows it needs a system runtime we cannot assume - which is already RAID risk 2 and will bite us later."),
  ]),

I("DRG-22", "Story", "Low Carbon London smart-meter loader", "Done",
  """
As the platform
I want the LCL half-hourly household dataset loaded into a canonical frame
So that every downstream stage sees the same shape regardless of source.

* household id, timestamp, kWh, tariff group, neighbourhood
* half-hourly index validated: no duplicates, no gaps within a household
* memory-conscious chunked read; the raw files are large
* canonical schema documented, and the synthetic generator must match it
  """,
  parent="DRG-1", assignee=D, points="8", components="Data",
  labels="ingestion;lcl", created="2025-01-06 09:30:00",
  resolved="2025-01-17 16:10:00",
  comments=[
    ("2025-01-08 11:20:00", D, "Defining the canonical frame first and making both the LCL loader and the synthetic generator targets of it, rather than letting the real loader define the shape and retrofitting synthetic to match. Otherwise the synthetic path is permanently second class."),
    ("2025-01-15 09:50:00", G, "That is the right call. The moment the two diverge, every result becomes 'which loader produced this?'"),
    ("2025-01-17 16:05:00", D, "Loaded and validated. It found real gaps in the source, which is DRG-37's problem rather than the loader's - it reports them and does not paper over them."),
  ]),

I("DRG-23", "Task", "Review the LCL licence and what may be redistributed", "Done",
  """
RAID risk 1. Establish what we can commit, publish and ship.

Question to answer: can any of the licensed dataset live in the repository,
in CI, or in a stakeholder demo?

Outcome required either way: a written position in the governance section,
and a plan that does not depend on a favourable answer.
  """,
  parent="DRG-15", assignee=S, points="2", components="Governance",
  labels="raid;licence", created="2025-01-06 09:35:00",
  resolved="2025-01-31 15:40:00",
  comments=[
    ("2025-01-20 14:20:00", S, "Chasing this. Flagging early that the answer being 'no' is the likely case and we should not plan as if it will be 'yes'."),
    ("2025-01-31 15:30:00", S, "Answer: no redistribution, no committing extracts, no shipping it in a container. Derived aggregate statistics are fine. So the synthetic generator is not a convenience - it is the only way this project is demonstrable, and DRG-24 moves up the plan accordingly."),
    ("2025-01-31 16:05:00", G, "That is a better outcome than it sounds. It forces the synthetic path to be first class, which means every reviewer, every CI run and every new joiner exercises the same route."),
  ]),

# ---------------------------------------------------------------- Sprint 2
I("DRG-24", "Story", "Calibrated synthetic smart-meter generator", "Done",
  """
As anyone without the licensed dataset
I want a generator that produces realistic half-hourly household demand
So that the entire pipeline runs end to end with no data and no API key.

* daily double-peak shape, weekday/weekend difference, seasonal amplitude
* household heterogeneity - base load and peak behaviour vary per household
* calibrated against LCL aggregate statistics, not invented
* seeded and reproducible; the same seed gives the same dataset
* emits the canonical frame from DRG-22
  """,
  parent="DRG-1", assignee=D, priority="Highest", points="8", components="Data",
  labels="synthetic;foundation", created="2025-01-20 09:20:00",
  resolved="2025-01-31 16:30:00",
  comments=[
    ("2025-01-21 10:30:00", D, "Calibrated means the summary statistics match: mean and spread of household daily consumption, the morning and evening peak ratio, the weekday to weekend difference, and the winter to summer amplitude. Those come out of the LCL analysis and go in as targets."),
    ("2025-01-27 15:15:00", G, "Checked the output against the LCL aggregates I have. Load shapes overlay well and the household spread is right. It will not fool anyone into thinking it is real data, and it does not need to - it needs to exercise the same code paths and produce conclusions of the same shape."),
    ("2025-01-31 16:25:00", D, "Done. Full run on synthetic takes about four minutes on a laptop, which keeps CI viable."),
  ]),

I("DRG-25", "Story", "CLI and the run-all pipeline", "Done",
  """
As anyone
I want one command that runs ingest, EDA, features, train, stress, scenarios
and SHAP
So that the project is reproducible rather than a sequence of remembered steps.

* python -m drg.cli run-all, and each stage individually
* stages read and write the documented data contract, not each other's memory
* a failed stage stops the run and names itself
* run report written to artifacts/reports/run_report.json
  """,
  parent="DRG-14", assignee=V, points="5", components="Platform",
  labels="cli;pipeline", created="2025-01-20 09:25:00",
  resolved="2025-02-04 15:50:00",
  comments=[
    ("2025-01-22 11:40:00", V, "Building run-all now, in week three, when there are two stages to orchestrate. Doing it at the end means every stage gets built against a slightly different idea of what the previous one produced, and the integration is then a project of its own."),
    ("2025-02-04 15:45:00", G, "Accepted. The run report is the part I did not expect to value as much as I do - every headline number in the README regenerates from it."),
  ]),

I("DRG-26", "Story", "Configuration, IO and logging utilities", "Done",
  """
As the codebase
I want one config object, one IO helper and one logger setup
So that paths, seeds and parameters are not redefined in nine modules.

* configs/config.yaml as the single source of tunable parameters
* typed access, with defaults and validation at load
* IO helpers that create parent directories and record what was written
* structured logging with a consistent stage prefix
  """,
  parent="DRG-1", assignee=V, points="3", components="Platform",
  labels="setup", created="2025-01-20 09:30:00", resolved="2025-01-30 14:20:00",
  comments=[
    ("2025-01-28 09:45:00", V, "The stress percentile, the adoption rates, the split dates and the seed all live in config.yaml. Anything a reviewer might reasonably want to change should not require reading source."),
  ]),

I("DRG-27", "Bug", "Half-hourly index breaks at the British Summer Time change", "Done",
  """
Observed: the loader reports duplicate timestamps on the last Sunday in
October and missing ones on the last Sunday in March, for every household.

Impact: two corrupt days per year in every series. Small in volume, and
exactly the kind of thing that silently distorts a daily-profile average and
then propagates into every lag feature built on it.

Cause: timestamps parsed as naive local time. At the autumn change 01:00-02:00
occurs twice; at the spring change it does not occur at all.

Fix: parse as UTC, carry a separate local-time column for the calendar
features that genuinely need local hour. Add a check asserting exactly 48
half-hours per household per UTC day.
  """,
  parent="DRG-1", assignee=D, reporter=G, priority="High", points="3",
  components="Data", labels="timezone;data-quality",
  created="2025-01-27 11:15:00", resolved="2025-02-03 12:40:00",
  comments=[
    ("2025-01-27 11:30:00", G, "Found it plotting a daily profile that had a step in it on exactly two days of the year. Worth saying out loud that this is the single most common bug in UK half-hourly energy data and it will not be the last time it costs us an afternoon."),
    ("2025-01-29 10:20:00", D, "Confirmed. Modelling in UTC and deriving local hour for the calendar features. The alternative - keeping everything local - means the index is not monotonic twice a year and every rolling window quietly misbehaves around it."),
    ("2025-02-03 12:35:00", D, "Fixed, with the 48-per-day assertion. It now also catches genuinely missing meter reads, which is how DRG-37 got found."),
  ]),

# ---------------------------------------------------------------- Sprint 3
I("DRG-28", "Story", "The raw to interim to processed data contract", "Done",
  """
As the pipeline
I want each stage to read and write a documented location and schema
So that stages can be run, re-run and tested independently.

* data/raw untouched; data/interim cleaned and typed; data/processed model-ready
* schema documented per layer, including units and timezone
* every processed artefact stamped with the config hash and generator seed
  """,
  parent="DRG-1", assignee=D, points="5", components="Data",
  labels="contract", created="2025-02-03 09:20:00", resolved="2025-02-13 15:10:00",
  comments=[
    ("2025-02-05 10:30:00", D, "The config hash on every artefact is what stops the classic research failure: a figure in a report that nobody can regenerate because the parameters have moved since."),
    ("2025-02-13 15:05:00", S, "Noting this in the RAID log as closing the reproducibility risk. It was the one I was most worried about."),
  ]),

I("DRG-29", "Story", "Neighbourhood aggregation from household meters", "Done",
  """
As the analysis
I want household reads aggregated to neighbourhood half-hourly demand
So that stress and forecasting operate at the level a planner cares about.

* four neighbourhoods, roughly 120 households each
* aggregation handles partial households explicitly - a neighbourhood total
  built from a varying household count is not comparable over time
* household count per half-hour retained alongside the total
  """,
  parent="DRG-1", assignee=D, points="5", components="Data",
  labels="aggregation", created="2025-02-03 09:25:00",
  resolved="2025-02-14 16:00:00",
  comments=[
    ("2025-02-07 11:20:00", D, "Keeping the contributing household count is the important bit. Without it, a neighbourhood whose meters drop out for a week looks like a neighbourhood whose demand fell, and that is indistinguishable in the aggregate."),
    ("2025-02-14 15:55:00", G, "Agreed, and it means we can normalise per household when comparing sites of different sizes."),
  ]),

I("DRG-30", "Task", "CI on every push", "Done",
  """
* .github/workflows/ci.yml: lint, format check, tests, and a full run-all on
  synthetic data
* under ten minutes
* red build blocks merge
* no licensed data and no API keys required, per DRG-23
  """,
  parent="DRG-14", assignee=V, points="5", components="CI",
  labels="ci", created="2025-02-03 09:30:00", resolved="2025-02-14 15:20:00",
  comments=[
    ("2025-02-12 14:10:00", V, "Running the whole pipeline in CI rather than only unit tests. It costs four minutes and it is the only thing that proves the stages still fit together."),
    ("2025-02-14 15:15:00", D, "First green run caught a stage that only worked because I had a stale interim file locally."),
  ]),

I("DRG-31", "Task", "Architecture document, with the non-goals stated first", "Done",
  """
Write docs/ARCHITECTURE.md covering the stage pipeline, the data contract,
the module boundaries and the deployment target.

Non-goals, stated explicitly and early:
* no physical power-flow or load-flow modelling
* no network topology, no transformer ratings, no voltage analysis
* stress is statistical and relative to a site's own history, not a capacity
  breach

DRG is a demand-side scenario tool. Someone will eventually present it as
more than that unless the boundary is written down where they will see it.
  """,
  parent="DRG-15", assignee=G, points="3", components="Docs",
  labels="architecture;docs", created="2025-02-04 09:15:00",
  resolved="2025-02-24 14:30:00",
  comments=[
    ("2025-02-24 14:25:00", G, "Non-goals are section two, ahead of the architecture itself. The single biggest reputational risk on a project like this is someone in a planning meeting believing we modelled the network."),
    ("2025-02-25 09:40:00", S, "Adding that to the RAID log as a live risk with the document as its mitigation, so it stays visible rather than being considered handled."),
  ]),

# ---------------------------------------------------------------- Sprint 4
I("DRG-32", "Story", "Daily and weekly load shape profiling", "Done",
  """
As the analysis
I want average load shapes by time of day, day of week and season
So that the modelling decisions rest on the data's actual structure.

* half-hourly profile per neighbourhood, weekday against weekend
* seasonal overlay - winter, spring, summer, autumn
* peak timing and magnitude quantified per site, not eyeballed
  """,
  parent="DRG-2", assignee=G, points="5", components="Analysis",
  labels="eda", created="2025-02-17 09:20:00", resolved="2025-02-28 15:40:00",
  comments=[
    ("2025-02-20 11:15:00", G, "Clear evening peak between 17:00 and 20:00 across all four sites, a weaker morning peak, and a weekend shape that is flatter and shifted later. Nothing surprising, which is itself worth confirming before building on it."),
    ("2025-02-28 15:35:00", D, "The weekday/weekend split is stark enough that day-of-week has to be a feature rather than an afterthought."),
  ]),

I("DRG-33", "Story", "Household heterogeneity within a neighbourhood", "Done",
  """
As the simulation, later
I want to know how much households differ inside one neighbourhood
So that EV and heat-pump adoption can be sampled realistically rather than
applied uniformly.

* distribution of household mean daily consumption per site
* how much of neighbourhood peak comes from the top decile of households
* whether high-consumption households peak at the same time as everyone else
  """,
  parent="DRG-2", assignee=G, points="5", components="Analysis",
  labels="eda;simulation", created="2025-02-17 09:25:00",
  resolved="2025-03-06 16:10:00",
  comments=[
    ("2025-03-04 10:40:00", G, "Wide spread - the top decile of households uses roughly three times the median. That matters for DRG-73: if EV adoption is sampled uniformly we will understate the peak, because early EV adopters are not a random draw from the population."),
    ("2025-03-06 16:05:00", D, "Noted and carried into the simulation design as an explicit assumption to test rather than a correction to apply silently."),
  ]),

I("DRG-34", "Task", "Monthly stakeholder report pack", "Done",
  """
A repeatable one-page monthly report: what shipped, what is next, RAID
movements, and the current headline numbers straight from the run report.

Generated from artifacts rather than retyped, so the report cannot drift from
what the pipeline actually produces.
  """,
  parent="DRG-16", assignee=S, points="3", components="Governance",
  labels="reporting", created="2025-02-17 09:30:00", resolved="2025-02-28 14:20:00",
  comments=[
    ("2025-02-26 11:30:00", S, "Pulling the numbers from run_report.json rather than copying them into a slide. On a twenty-month project the report and the code will diverge otherwise, and the report is what people remember."),
  ]),

I("DRG-35", "Story", "Data quality checks on the meter feed", "Done",
  """
As the platform
I want the meter data checked on every run
So that a bad load is caught before it becomes a bad model.

* 48 half-hours per household per UTC day (from DRG-27)
* no negative consumption; zero runs flagged above a threshold
* household count per neighbourhood stable within tolerance
* results written to the run report with pass, warn or fail per check
  """,
  parent="DRG-1", assignee=D, points="5", components="Data",
  labels="quality", created="2025-02-18 09:15:00", resolved="2025-03-07 15:30:00",
  comments=[
    ("2025-03-03 10:20:00", D, "Warn rather than fail for the zero runs. A genuinely empty property reads zero for weeks and that is real data, not an error - failing on it would train us to ignore the output."),
    ("2025-03-07 15:25:00", G, "Right. A check that fires on normal conditions is a check nobody reads."),
  ]),

# ---------------------------------------------------------------- Sprint 5
I("DRG-36", "Story", "Seasonal decomposition and the weekly cycle finding", "Done",
  """
As the modelling
I want the strength of daily, weekly and annual seasonality quantified
So that the feature set is justified rather than assumed.

* decomposition per neighbourhood
* autocorrelation at 1, 48 and 336 half-hours reported explicitly
* the finding written up in the modelling notes
  """,
  parent="DRG-2", assignee=G, points="5", components="Analysis",
  labels="eda;seasonality", created="2025-03-03 09:20:00",
  resolved="2025-03-14 15:50:00",
  comments=[
    ("2025-03-10 11:20:00", G, "Autocorrelation at 336 half-hours - the same half-hour last week - is stronger than at 48, the same half-hour yesterday. That is the single most useful thing this epic has produced, and it predicts the whole shape of the feature set."),
    ("2025-03-14 15:45:00", D, "It also predicts what SHAP will eventually say. If lag_336 does not come out on top later, one of the two analyses is wrong."),
  ]),

I("DRG-37", "Bug", "Missing half-hours silently forward-filled during aggregation", "Done",
  """
Observed: neighbourhood totals looked complete even for periods where the
loader had reported missing household reads.

Impact: gaps became flat lines rather than gaps. A forward-filled evening peak
is a fabricated peak, and it feeds the percentile that later defines stress.

Cause: the resample step used a fill method by default, so an absent read
became the previous read rather than a null.

Fix: no filling during aggregation. Missing stays missing, is counted, and is
handled once, explicitly, with the rule written down.
  """,
  parent="DRG-1", assignee=D, reporter=D, priority="High", points="3",
  components="Data", labels="data-quality;silent",
  created="2025-03-05 10:20:00", resolved="2025-03-12 14:10:00",
  comments=[
    ("2025-03-05 10:35:00", D, "Raising against my own work. The 48-per-day assertion from DRG-27 is what surfaced it - the check said data was missing while the aggregate said it was fine, and both could not be true."),
    ("2025-03-06 09:40:00", G, "That disagreement between two views of the same thing is worth more than either view on its own. Worth keeping as a habit: assert the same fact in two places and let them argue."),
    ("2025-03-12 14:05:00", D, "Fixed. Gaps propagate as nulls, are counted in the run report, and are handled once at the feature stage where the decision is visible."),
  ]),

I("DRG-38", "Story", "Container images for pipeline, API and dashboard", "Done",
  """
Three Dockerfiles sharing a base layer, so the same code runs locally, in CI
and eventually on Container Apps.

* docker/Dockerfile.pipeline, .api, .dashboard
* docker-compose for the local stack
* images build without the deep or azure dependency tiers
  """,
  parent="DRG-14", assignee=V, points="5", components="Platform",
  labels="docker", created="2025-03-03 09:25:00", resolved="2025-03-14 16:00:00",
  comments=[
    ("2025-03-11 15:20:00", V, "Three images rather than one that does everything. The dashboard does not need XGBoost and the pipeline does not need Streamlit, and a single fat image means every deploy ships all of it."),
  ]),

# ---------------------------------------------------------------- Sprint 6
I("DRG-39", "Story", "EDA figure set and reporting artefacts", "Done",
  """
The figures that go into the design document and the monthly report, all
regenerated by the pipeline rather than exported by hand from a notebook.

* load shape, seasonal overlay, household distribution, autocorrelation
* written to artifacts/figures with a consistent style
* every figure regenerable from run-all
  """,
  parent="DRG-2", assignee=G, points="5", components="Analysis",
  labels="eda;reporting", created="2025-03-17 09:20:00",
  resolved="2025-03-28 15:20:00",
  comments=[
    ("2025-03-26 10:15:00", G, "No figure in any document that cannot be regenerated by a command. A chart exported by hand from a notebook is a chart nobody can reproduce in six months, including the person who made it."),
  ]),

I("DRG-40", "Task", "Q1 review and replan", "Done",
  """
Quarter one review with stakeholders, and replan for Q2.

Delivered: data foundations, synthetic generator, CLI and run-all, CI,
neighbourhood aggregation, and the consumption analysis.

Not delivered and deliberately deferred: any forecasting model. The quarter
was spent making the data trustworthy, which is the sequencing we chose.
  """,
  parent="DRG-16", assignee=S, points="2", components="Governance",
  labels="ceremony", created="2025-03-17 09:25:00", resolved="2025-03-28 16:30:00",
  comments=[
    ("2025-03-28 16:20:00", S, "Question from the stakeholder session, recorded because it will come back: 'when do we see a forecast?' The answer is Q3, and the reason is that a forecast built on data with two corrupt days a year and forward-filled gaps would have been ready in March and wrong."),
    ("2025-03-31 09:40:00", G, "That framing helped. Worth reusing verbatim next time."),
  ]),

I("DRG-41", "Story", "Weather feed from a key-free public API", "Done",
  """
As the model
I want temperature and related weather history joined to the demand series
So that heating and cooling driven demand is explainable.

* key-free public API, so a clean clone works with no credentials
* historical backfill for the modelling window, and current for replay later
* responses cached to disk; a failed call degrades the run rather than
  killing it, and says so in the run report
  """,
  parent="DRG-1", assignee=D, points="5", components="Data",
  labels="weather;external", created="2025-03-18 09:15:00",
  resolved="2025-04-04 15:40:00",
  comments=[
    ("2025-03-20 11:30:00", V, "Key-free is a hard requirement, not a preference. The moment a demo needs a credential, it needs someone with the credential, and the project stops being self-service."),
    ("2025-04-04 15:35:00", D, "Cached to disk with the fetch timestamp, so a run is reproducible even if the upstream revises history - which weather APIs do."),
  ]),

# ------------------------------------------------------------- Sprints 7-8
I("DRG-42", "Story", "Calendar and cyclical time features", "Done",
  """
As the model
I want time encoded in a form a tree or a linear model can use
So that the daily and weekly cycles are learnable.

* half-hour of day, day of week, month, holiday flag (England and Wales)
* sine and cosine encodings of time of day and day of week, so 23:30 and
  00:00 are adjacent rather than 47 apart
* local time used for calendar features, UTC for the index, per DRG-27
  """,
  parent="DRG-3", assignee=D, points="5", components="Features",
  labels="features", created="2025-04-07 09:20:00", resolved="2025-04-16 15:30:00",
  comments=[
    ("2025-04-09 10:20:00", D, "Cyclical encoding matters more for the linear models than for the trees, but it costs two columns and it means the baseline is a fair comparison rather than one handicapped by a representation choice."),
  ]),

I("DRG-43", "Story", "Lag features at 1, 48 and 336 half-hours", "Done",
  """
As the model
I want the previous half-hour, the same half-hour yesterday and the same
half-hour last week
So that the seasonality found in DRG-36 is available to the model.

* lag_1, lag_48, lag_336, per neighbourhood
* lags computed within a neighbourhood, never across sites
* rows without a full lag history are dropped, not imputed
  """,
  parent="DRG-3", assignee=D, priority="High", points="5", components="Features",
  labels="features;lags", created="2025-04-07 09:25:00",
  resolved="2025-04-18 16:00:00",
  comments=[
    ("2025-04-11 11:15:00", D, "Dropping the first week rather than imputing it. An imputed lag_336 is a made-up value in the most important feature in the model, and it would be concentrated entirely at the start of the series."),
    ("2025-04-18 15:55:00", G, "Agreed. Losing a week of training data is cheap; poisoning the strongest feature is not."),
  ]),

I("DRG-44", "Task", "The chronological split contract", "Done",
  """
Train, validation and test are contiguous and in time order. No shuffling,
ever, anywhere in this codebase.

* split dates in config, not scattered through modules
* validation used for early stopping; test touched only for final reporting
* the rule and the reason written into the modelling notes
  """,
  parent="DRG-3", assignee=G, priority="High", points="2", components="Features",
  labels="split;leakage", created="2025-04-08 09:15:00",
  resolved="2025-04-17 12:20:00",
  comments=[
    ("2025-04-08 09:40:00", G, "Writing this down before the first model exists. Random splits on a time series produce beautiful scores and worthless models, and the failure is invisible in the metrics - which is exactly the class of mistake that needs a written rule and a test rather than good intentions."),
    ("2025-04-17 12:15:00", D, "In config, and I have added an assertion that the split boundaries are ordered and non-overlapping."),
  ]),

I("DRG-45", "Story", "Rolling statistics features", "Done",
  """
Rolling mean and standard deviation over trailing windows, to give the model
recent level and volatility.

* windows of 48 (one day) and 336 (one week) half-hours
* trailing and closed on the left - the current half-hour is never in its own
  window, see DRG-46
  """,
  parent="DRG-3", assignee=D, points="3", components="Features",
  labels="features", created="2025-04-21 09:20:00",
  resolved="2025-04-30 15:10:00",
  comments=[
    ("2025-04-30 15:05:00", D, "Left-closed windows, asserted in a test. The default in most libraries includes the current observation and that is a leak that will not show up as an error."),
  ]),

I("DRG-46", "Bug", "Rolling window included the half-hour being predicted", "Done",
  """
Observed: validation MAE of 0.11 kWh on the first Ridge run - roughly six
times better than anything plausible for half-hourly demand.

Diagnosis: the rolling mean window was centred rather than trailing, so the
feature for 18:00 included the 18:00 value itself. The model was being handed
a smoothed version of its own target.

Impact: none published - caught before any result left the team. Had it
shipped, the model would have looked outstanding in backtest and collapsed the
moment it saw a genuinely unseen half-hour.

Fix: trailing, left-closed windows, plus an assertion that no feature column
correlates with the target above a threshold that only leakage explains.
  """,
  parent="DRG-3", assignee=D, reporter=G, priority="High", points="3",
  components="Features", labels="leakage;silent",
  created="2025-04-28 10:30:00", resolved="2025-05-02 14:20:00",
  comments=[
    ("2025-04-28 10:45:00", G, "0.11 MAE was the tell. A result that is far better than the problem is hard is not a good result, it is a symptom - and it is worth building the reflex to be suspicious rather than pleased."),
    ("2025-04-29 11:20:00", D, "Confirmed and fixed. Adding the correlation assertion so the next one is caught by CI rather than by someone's instinct."),
    ("2025-05-02 14:15:00", G, "Ridge is now at 0.83 MAE, which is a believable number for this problem. Much less exciting and much more useful."),
  ]),

I("DRG-47", "Task", "Lint, format and pre-commit", "Done",
  """
ruff and black, enforced in CI and available as a pre-commit hook, with the
configuration in pyproject rather than in five separate files.
  """,
  parent="DRG-14", assignee=V, points="2", components="CI",
  labels="tooling", created="2025-04-21 09:25:00", resolved="2025-04-25 11:40:00",
  comments=[
    ("2025-04-25 11:35:00", V, "Formatting decided by a tool so it stops being decided in review. Review time is better spent on whether the window is left-closed."),
  ]),

# ------------------------------------------------------------ Sprints 9-10
I("DRG-48", "Story", "Weather features and lagged temperature", "Done",
  """
Temperature, and derived heating and cooling degree terms, joined to the
demand series.

* current temperature, plus lags - a cold morning still affects an evening
* heating and cooling degree hours against a configurable base temperature
* the join is on UTC, and a missing weather hour does not silently become zero
  """,
  parent="DRG-3", assignee=D, points="5", components="Features",
  labels="features;weather", created="2025-05-05 09:20:00",
  resolved="2025-05-16 15:30:00",
  comments=[
    ("2025-05-12 10:40:00", D, "Lagged temperature earns its place - buildings have thermal mass, so yesterday evening's cold is still in the walls this morning. The un-lagged version underfits exactly the cold snaps we care most about."),
    ("2025-05-16 15:25:00", G, "This also sets up the heat-pump simulation later, since that has to be temperature-driven to be credible."),
  ]),

I("DRG-49", "Story", "Feature sanity pass before modelling", "Done",
  """
Before any model is fitted, check the feature matrix behaves.

* no feature is constant, no feature is a duplicate of another
* no feature correlates with the target beyond a leakage threshold (DRG-46)
* every feature is knowable at prediction time - stated per feature, in code
* feature list and the reason for each is in the modelling notes
  """,
  parent="DRG-3", assignee=G, points="3", components="Features",
  labels="features;quality", created="2025-05-05 09:25:00",
  resolved="2025-05-15 14:40:00",
  comments=[
    ("2025-05-14 11:20:00", G, "The 'knowable at prediction time' note per feature is the useful artefact here. It turns an assumption everyone holds loosely into something a reviewer can check line by line."),
  ]),

I("DRG-50", "Task", "RAID review: licence closed, PyTorch risk raised", "Done",
  """
Mid-year risk review.

* LCL licence risk closed - position documented, synthetic path is primary
* PyTorch on Windows raised from watch to active: the deep model is planned
  for Q3 and the runtime dependency is unresolved
* new risk: single points of knowledge. The simulation exists only in Divya's
  head and the model ladder only in Geetha's
  """,
  parent="DRG-16", assignee=S, points="2", components="Governance",
  labels="raid", created="2025-05-19 09:15:00", resolved="2025-05-30 15:20:00",
  comments=[
    ("2025-05-19 09:40:00", S, "The knowledge concentration risk is the one I would most like a mitigation for. Two people, twenty months, and no overlap in what they own is fine until somebody takes leave."),
    ("2025-05-23 10:30:00", G, "Mitigation proposed: the modelling notes and the design document have to be good enough that the other person can run the stage. That is a real deliverable rather than a promise, so it goes on the board."),
    ("2025-05-30 15:15:00", S, "Accepted and tracked. It is also why DRG-78 exists."),
  ]),

I("DRG-51", "Story", "Materialise the processed model-ready dataset", "Done",
  """
One processed artefact per neighbourhood, feature-complete and split-labelled,
so training does not rebuild features on every run.

* written to data/processed with the config hash
* rebuilt only when the config or the upstream data changes
* the split label is part of the artefact, so no stage can choose its own
  """,
  parent="DRG-3", assignee=D, points="5", components="Features",
  labels="features;pipeline", created="2025-05-19 09:20:00",
  resolved="2025-06-02 15:50:00",
  comments=[
    ("2025-06-02 15:45:00", D, "The split label travelling with the data is the part that matters. If each model stage decides its own split, comparisons between models stop being comparisons."),
  ]),

# ----------------------------------------------------------- Sprints 11-13
I("DRG-52", "Story", "Seasonal naive baseline", "Done",
  """
As the project
I want the operational status quo implemented as a model
So that every later model has something real to beat.

The baseline is what a control room does today: assume this half-hour looks
like the same half-hour in the recent past.

* implemented on the same interface and evaluated on the same window as
  everything else
* published as a first-class result, never as a footnote
  """,
  parent="DRG-4", assignee=G, priority="High", points="3", components="Models",
  labels="baseline", created="2025-06-02 09:20:00", resolved="2025-06-11 15:10:00",
  comments=[
    ("2025-06-03 10:15:00", G, "This is the model to beat and it deserves the same care as the others. A weak baseline makes every subsequent result look better than it is, which is a comfortable mistake and a corrosive one."),
    ("2025-06-11 15:05:00", D, "1.54 MAE on the test window. That is the bar."),
  ]),

I("DRG-53", "Bug", "Seasonal naive used yesterday instead of last week", "Done",
  """
Observed: the naive baseline scored better than expected and its errors were
oddly structured around weekends.

Cause: the shift was 48 half-hours - the same half-hour yesterday - while the
autocorrelation analysis in DRG-36 says the weekly lag of 336 is stronger.
Both are defensible baselines, but the code claimed one and implemented the
other.

Fix: publish both. Daily-naive is what an operator actually does; weekly-naive
is the stronger statistical baseline. Name them separately and report both, so
nobody has to guess which one a later comparison beat.
  """,
  parent="DRG-4", assignee=G, reporter=D, priority="Medium", points="2",
  components="Models", labels="baseline;definitions",
  created="2025-06-09 11:20:00", resolved="2025-06-13 14:30:00",
  comments=[
    ("2025-06-09 11:40:00", D, "Not strictly a bug in the maths - it is a bug in the label. The docstring said 'same half-hour last week' and the code shifted 48."),
    ("2025-06-10 09:30:00", G, "Which is worse than a maths bug in some ways, because the number was right for a thing nobody had agreed to. Publishing both and naming them is the honest fix."),
    ("2025-06-13 14:25:00", G, "Both in. Daily-naive is the headline baseline because it is what the control room does, and weekly-naive is reported alongside it."),
  ]),

I("DRG-54", "Story", "Linear and Ridge baselines", "Done",
  """
An interpretable linear model on the full feature set, with regularisation.

* standardised features, Ridge with the penalty selected on the validation
  window
* coefficients reported - this model exists partly to be readable
* same evaluation harness as every other model
  """,
  parent="DRG-4", assignee=G, points="5", components="Models",
  labels="baseline;linear", created="2025-06-16 09:20:00",
  resolved="2025-06-27 15:40:00",
  comments=[
    ("2025-06-25 10:30:00", G, "0.83 MAE, against 1.54 for daily-naive. A regularised linear model on good features gets most of the way, which is worth knowing before anyone concludes the problem needed gradient boosting."),
    ("2025-06-27 15:35:00", D, "And it is the model we can explain to a planner in one sentence, which will matter when we get to the dashboard."),
  ]),

I("DRG-55", "Story", "Evaluation harness", "Done",
  """
One harness, one held-out window, one set of metrics, applied identically to
every model in the ladder.

* MAE, RMSE, MAPE, R squared
* stress-alarm precision, recall and F1 once DRG-72 lands
* results written to the run report; the comparison table regenerates from it
* no model may report a metric computed its own way
  """,
  parent="DRG-4", assignee=G, priority="High", points="5", components="Models",
  labels="evaluation", created="2025-06-16 09:25:00",
  resolved="2025-06-30 16:00:00",
  comments=[
    ("2025-06-18 11:15:00", G, "Every model computing its own metrics is how you get a comparison table where the numbers are not comparable. One harness, and models only supply predictions."),
    ("2025-06-30 15:55:00", D, "Accepted. The README table is generated from the run report, so it cannot drift from what the code produced."),
  ]),

I("DRG-56", "Task", "Guard MAPE against near-zero demand half-hours", "Done",
  """
MAPE is unstable when the denominator approaches zero, which happens in the
small hours at low-occupancy sites.

* MAPE computed with a documented floor, and the excluded fraction reported
* RMSE and MAE remain the primary metrics; MAPE is reported because
  stakeholders ask for a percentage, with its limitation labelled
  """,
  parent="DRG-4", assignee=G, points="2", components="Models",
  labels="evaluation;honesty", created="2025-06-23 09:15:00",
  resolved="2025-06-30 12:20:00",
  comments=[
    ("2025-06-30 12:15:00", G, "Reporting the excluded fraction next to the number. A percentage error that quietly drops its most difficult observations is a flattering statistic, and stakeholders will quote it."),
  ]),

I("DRG-57", "Story", "Train, validation and test window definition", "Done",
  """
Fix the windows once, in config, for the whole project.

* training from the start of the usable series
* validation window for early stopping and hyperparameter selection
* 60-day chronological held-out test window, untouched until final reporting
* the same windows for every model, enforced by the harness
  """,
  parent="DRG-4", assignee=D, points="3", components="Models",
  labels="split", created="2025-06-16 09:30:00", resolved="2025-06-26 14:10:00",
  comments=[
    ("2025-06-26 14:05:00", D, "60 days of test gives roughly 2,880 half-hours per site, which is enough to say something about stress events rather than only about average error."),
  ]),

I("DRG-58", "Bug", "Lag features computed across the train and test boundary", "Done",
  """
Observed: test-window scores that did not degrade at all relative to
validation, which is unusual for a chronological split.

Diagnosis: features were engineered on the full series and split afterwards.
The lag and rolling features for the first rows of the test window were
therefore built from training data - which is legitimate - but the feature
pipeline was also being fitted (scaler statistics) on the full series,
including the test window. Standardisation had seen the future.

Impact: none published. Found before the model ladder results were written up.

Fix: fit every transform on the training window only and apply to the others.
Assert it in a test that fits on train, then checks the scaler's statistics
against a train-only recomputation.
  """,
  parent="DRG-3", assignee=D, reporter=G, priority="Highest", points="5",
  components="Features", labels="leakage;silent",
  created="2025-06-24 10:20:00", resolved="2025-07-04 15:30:00",
  comments=[
    ("2025-06-24 10:40:00", G, "Second leakage bug in two months, and a subtler one than DRG-46 - the lags themselves were fine, it was the scaler that had seen the whole series. This is the failure mode of doing feature engineering before splitting."),
    ("2025-06-25 09:50:00", D, "Restructuring so the split happens before any fitted transform, and the transform is fitted inside the pipeline rather than beside it. That makes the mistake structurally hard rather than something we have to remember."),
    ("2025-06-30 11:15:00", G, "Which is the right lesson. We have caught two of these by being suspicious of good numbers, and that will not scale - the third one will slip through unless it is impossible by construction."),
    ("2025-07-04 15:25:00", D, "Fixed and asserted. Ridge moved from 0.79 to 0.83 MAE, which is the honest number."),
  ]),

# ----------------------------------------------------------- Sprints 14-16
I("DRG-59", "Story", "XGBoost forecasting model", "Done",
  """
As the project
I want a gradient boosted model as the primary forecaster
So that the non-linear interactions between time, weather and recent demand
are captured.

* early stopping on the validation window, never on test
* categorical handling for neighbourhood, so one model serves all sites
* feature importance exported for cross-checking against SHAP later
* same harness, same window, same metrics
  """,
  parent="DRG-4", assignee=G, priority="Highest", points="8",
  components="Models", labels="xgboost;modelling",
  created="2025-07-07 09:20:00", resolved="2025-07-25 16:10:00",
  comments=[
    ("2025-07-14 10:30:00", G, "One model across all four neighbourhoods with site as a feature, rather than four models. There is not enough data per site to justify four, and the shared model can borrow strength across them - which is a testable claim, so I will test it."),
    ("2025-07-21 11:20:00", D, "Tested: the shared model beats per-site models on three of four sites and ties on the fourth. Worth recording in the notes because it is a question that will be asked again."),
    ("2025-07-25 16:05:00", G, "0.70 MAE, 0.95 RMSE, R squared 0.986. Against daily-naive at 1.54 that is a substantial improvement, and against Ridge at 0.83 it is real but modest - which is the honest way to describe it."),
  ]),

I("DRG-60", "Story", "Hyperparameter search", "Done",
  """
Structured search over the XGBoost parameters, scored on the validation
window with a time-aware split.

* search space and the selected values recorded in the run report
* the search never sees the test window
* the improvement over default parameters reported, so the effort is
  justified rather than assumed
  """,
  parent="DRG-4", assignee=G, points="5", components="Models",
  labels="tuning", created="2025-07-28 09:20:00", resolved="2025-08-08 15:20:00",
  comments=[
    ("2025-08-08 15:15:00", G, "Tuning bought about 0.04 MAE over sensible defaults. Recording that, because it is a useful counterweight to the instinct that more search is always worth it - the features did far more than the hyperparameters."),
  ]),

I("DRG-61", "Story", "Rolling-origin cross-validation", "Done",
  """
As the project
I want the headline result validated across multiple time windows
So that we know the test score is not a lucky split.

* five expanding-window folds, each training on everything before its
  validation window
* per-fold and aggregate metrics reported
* the fold range published alongside the headline number
  """,
  parent="DRG-4", assignee=D, priority="High", points="5", components="Models",
  labels="validation", created="2025-08-11 09:20:00",
  resolved="2025-08-22 16:00:00",
  comments=[
    ("2025-08-11 09:45:00", D, "A single held-out window on a two-year series is one draw from a distribution. Five expanding folds tell us how much the answer moves depending on where you cut it."),
    ("2025-08-22 15:55:00", G, "RMSE 0.74 to 0.95 across folds, with the headline test at 0.95 - so the headline sits at the pessimistic end of the range rather than the flattering one. That is the version to publish."),
  ]),

I("DRG-62", "Task", "Model comparison report", "Done",
  """
The ladder in one table, generated from the run report: naive, Ridge, XGBoost
and the sequence model, on MAE, RMSE, MAPE, R squared and stress-alarm F1.

Ordered by MAE, with the naive baseline always shown, never omitted for
looking bad.
  """,
  parent="DRG-4", assignee=G, points="3", components="Models",
  labels="reporting", created="2025-08-11 09:25:00",
  resolved="2025-08-29 15:10:00",
  comments=[
    ("2025-08-29 15:05:00", G, "The baseline row stays in the table permanently. The moment it is dropped for being uninteresting, the table stops answering the only question that matters: is this better than what they do today?"),
  ]),

I("DRG-63", "Story", "Model artefact persistence and metadata", "Done",
  """
As the platform
I want every trained model saved with the context needed to reproduce it
So that a forecast can be traced back to an artefact months later.

* model binary, feature list, config hash, data hash, metrics, training window
* a version identifier that later appears in API responses
* loading a model validates that its feature list matches what is being fed to
  it, and refuses rather than silently misaligning columns
  """,
  parent="DRG-12", assignee=V, points="5", components="MLOps",
  labels="artefacts", created="2025-08-25 09:20:00",
  resolved="2025-09-05 15:40:00",
  comments=[
    ("2025-09-02 10:20:00", V, "The feature-list check on load is the one that will save someone. Feeding columns in a different order to a tree model produces predictions rather than an error, and they will look approximately reasonable."),
    ("2025-09-05 15:35:00", G, "Accepted. This is also the foundation the promotion gate sits on next year."),
  ]),

# ----------------------------------------------------------- Sprints 17-19
I("DRG-64", "Story", "PyTorch LSTM and GRU sequence models", "Done",
  """
As the project
I want a deep sequence model in the ladder
So that we can say whether sequence learning adds anything over gradient
boosting on this problem.

* LSTM and GRU over a lookback window of past half-hours
* same split, same harness, same metrics
* optional dependency tier - the base install must not require torch
  """,
  parent="DRG-4", assignee=G, points="8", components="Models",
  labels="deep;optional", created="2025-09-08 09:20:00",
  resolved="2025-09-26 15:50:00",
  comments=[
    ("2025-09-15 11:20:00", G, "Framing this as a question rather than an ambition: does sequence modelling beat XGBoost here? If it does not, that is a publishable finding and we stop, rather than spending a quarter tuning it into a tie."),
    ("2025-09-26 15:45:00", G, "It does not, on this data volume. Competitive but not better, and far more expensive to train and serve. Recorded as a finding and the ladder keeps XGBoost as primary."),
  ]),

I("DRG-65", "Bug", "PyTorch import fails on Windows without the MSVC runtime", "Done",
  """
Observed: torch installs successfully from pip on a clean Windows machine and
then raises an OSError on import - a DLL load failure.

Impact: the deep model stage crashed the whole run-all on two of three
Windows machines, including a stakeholder demo box. RAID risk 2, realised.

Cause: the Windows torch wheels link against the Microsoft Visual C++
redistributable, which is not installed by default and is not a pip
dependency, so a successful install is no evidence that import will work.

Fix, in two parts:
* detect the failure at import and fall back to the torch-free sequence model
  (DRG-66) rather than crashing the pipeline
* document the redistributable in the README next to the deep tier install,
  with the download link
  """,
  parent="DRG-4", assignee=V, reporter=G, priority="High", points="3",
  components="Models;Platform", labels="windows;dependencies;raid",
  created="2025-09-16 10:15:00", resolved="2025-09-24 14:20:00",
  comments=[
    ("2025-09-16 10:30:00", G, "Lost an hour to this before realising the install had succeeded and the import had not. pip reporting success is genuinely misleading here."),
    ("2025-09-16 11:40:00", V, "Known issue with the Windows wheels - they need the MSVC redistributable and it is not something pip can pull in. This was RAID risk 2 from January, so at least it was not a surprise."),
    ("2025-09-18 09:50:00", S, "Marking the risk as realised and mitigated rather than closing it quietly. The mitigation - graceful fallback plus a documented prerequisite - is the reusable part."),
    ("2025-09-24 14:15:00", V, "Fixed. The import is guarded, the fallback is automatic and reported in the run log, and the README says what to install. A missing optional dependency should degrade the run, not end it."),
  ]),

I("DRG-66", "Story", "Torch-free sequence model fallback", "Done",
  """
As anyone without a working PyTorch install
I want a neural sequence model that runs on scikit-learn alone
So that the ladder is complete on a base install.

* MLP over a flattened lookback window
* same interface, same harness, so it slots into the ladder unchanged
* selected automatically when torch cannot be imported, and the substitution
  is stated in the run report rather than being silent
  """,
  parent="DRG-4", assignee=G, points="5", components="Models",
  labels="fallback;models", created="2025-09-18 09:20:00",
  resolved="2025-09-30 15:30:00",
  comments=[
    ("2025-09-25 10:40:00", G, "0.78 MAE, so it sits between Ridge and XGBoost. It was built as a fallback and it turns out to be a legitimate rung on the ladder, which is a better outcome than intended."),
    ("2025-09-30 15:25:00", V, "And it is stated in the run report when it substitutes. A silent fallback would mean a comparison table where one row is secretly a different model than it claims."),
  ]),

I("DRG-67", "Task", "Publish the model ladder results", "Done",
  """
Write up the ladder: what each model is, what it scored, and what the
comparison means.

The finding worth stating plainly: XGBoost more than halves the error of the
operational baseline, and a regularised linear model gets most of the way.
The problem is dominated by recent history and weekly seasonality, which is
why relatively simple models do well.
  """,
  parent="DRG-4", assignee=G, points="3", components="Docs",
  labels="reporting;modelling", created="2025-09-29 09:15:00",
  resolved="2025-10-10 15:20:00",
  comments=[
    ("2025-10-10 15:15:00", G, "Stating that simple models do well is not undermining the work - it is the finding. It tells a network operator that this is tractable with modest infrastructure, which is far more actionable than a marginal accuracy claim."),
  ]),

# ----------------------------------------------------------- Sprints 20-22
I("DRG-68", "Story", "Percentile stress thresholds per neighbourhood", "Done",
  """
As the analysis
I want stress defined from each neighbourhood's own historical distribution
So that sites are measurable without knowing their capacity.

* threshold at a configurable percentile, default P95, per site
* computed on the training window only - see DRG-69
* thresholds published per site, with the underlying distribution, so the
  definition is inspectable rather than a magic number
  """,
  parent="DRG-5", assignee=G, priority="High", points="5", components="Stress",
  labels="stress;definitions", created="2025-10-13 09:20:00",
  resolved="2025-10-24 15:40:00",
  comments=[
    ("2025-10-13 09:45:00", G, "The honest wording, which goes everywhere this number appears: this is not a capacity breach. We do not have ratings. It is the top 5% of a site's own history, and the interesting claim is how much more often that happens under electrification."),
    ("2025-10-24 15:35:00", D, "Per site rather than global. A dense urban feeder and a suburban one have completely different distributions and a shared threshold would just rank sites by size."),
  ]),

I("DRG-69", "Bug", "Stress threshold computed on the full series including test", "Done",
  """
Observed: stress-alarm F1 was suspiciously stable across every model,
including the naive baseline.

Diagnosis: the P95 threshold was computed over the entire series, test window
included. Every model was being scored against a threshold derived partly
from the data it was being tested on - a lookahead, and one that flatters all
models equally, which is why it did not show up as an odd ranking.

Impact: none published. Found while preparing the stress results for the Q4
review.

Fix: thresholds computed on the training window only, then applied unchanged
to validation and test. Asserted in a test.
  """,
  parent="DRG-5", assignee=G, reporter=D, priority="High", points="3",
  components="Stress", labels="leakage;silent",
  created="2025-10-27 10:20:00", resolved="2025-11-04 14:30:00",
  comments=[
    ("2025-10-27 10:40:00", D, "Spotted it because the naive baseline's stress F1 was 0.85, which is high for a model that is just repeating yesterday. The threshold knowing about the test window was making the task easier for everyone."),
    ("2025-10-28 09:30:00", G, "Third leakage bug of the year, and the pattern is consistent: it is never the model, it is always something fitted on more data than it should have seen. Scaler, rolling window, now a threshold."),
    ("2025-10-30 11:15:00", G, "Proposing a rule rather than another fix: anything that is estimated from data - a scaler, a threshold, a percentile, a category encoding - is fitted on train and applied elsewhere, and there is a test for each one. Otherwise we will find the fourth in February."),
    ("2025-11-04 14:25:00", D, "Rule adopted and written into the modelling notes. Thresholds now train-only, F1 numbers moved slightly and the ranking held."),
  ]),

I("DRG-70", "Story", "Stress event detection with a minimum duration", "Done",
  """
As a planner
I want stress reported as events rather than as isolated half-hours
So that the output matches how the network is actually operated.

* contiguous half-hours above threshold form one event
* a configurable minimum duration, so a single spike is not an event
* small gaps below threshold do not split one event into two
* event start, end, duration and peak recorded
  """,
  parent="DRG-5", assignee=G, points="5", components="Stress",
  labels="stress", created="2025-11-03 09:20:00", resolved="2025-11-14 15:30:00",
  comments=[
    ("2025-11-07 10:30:00", G, "The gap-bridging rule matters more than it sounds. Demand oscillating around a threshold produces dozens of one-period events, which is noise dressed as a finding, and it would make the duration statistics meaningless."),
    ("2025-11-14 15:25:00", D, "Both parameters are in config and reported with the results, so the sensitivity work next year can sweep them."),
  ]),

I("DRG-71", "Story", "Stress frequency and duration metrics", "Done",
  """
The headline stress statistics per site and per scenario.

* share of half-hours in stress
* event count, mean and maximum duration
* time-of-day and seasonal distribution of stress events
* all computed from the event structure in DRG-70, not from raw exceedances
  """,
  parent="DRG-5", assignee=D, points="5", components="Stress",
  labels="stress;metrics", created="2025-11-17 09:20:00",
  resolved="2025-11-28 15:20:00",
  comments=[
    ("2025-11-26 11:15:00", D, "Base case is 4.4% of half-hours in stress with a mean event duration of 2.2 hours. That is the number every electrification scenario will be compared against, so it is worth being precise about how it was computed."),
  ]),

I("DRG-72", "Story", "Stress-alarm precision, recall and F1", "Done",
  """
As the project
I want forecasts judged on whether they predict stress, not only on error
So that model selection reflects what the platform is for.

* a forecast raises an alarm when the predicted half-hour exceeds the
  threshold; the truth is whether the actual half-hour did
* precision, recall and F1 per model, reported next to MAE
* the asymmetry stated: a missed stress event costs more than a false alarm,
  and the operating point can be tuned for that
  """,
  parent="DRG-5", assignee=G, priority="High", points="5", components="Stress",
  labels="stress;evaluation", created="2025-11-17 09:25:00",
  resolved="2025-12-05 15:40:00",
  comments=[
    ("2025-11-20 10:20:00", G, "A model can improve MAE by getting the easy quiet half-hours slightly better while getting worse at the peaks. Without this metric we would select for the wrong thing and never know."),
    ("2025-12-05 15:35:00", D, "XGBoost at 0.90 F1, daily-naive at 0.85. A smaller gap than the MAE difference suggests, which is itself informative - the peaks are the recurrent, forecastable part."),
  ]),

# ----------------------------------------------------------- Sprints 23-26
I("DRG-73", "Story", "Per-household EV adoption sampling", "Done",
  """
As the simulation
I want EV adoption assigned to individual households, not applied as a
uniform uplift
So that diversity between households is preserved.

* adoption rate as a scenario parameter; households sampled, not scaled
* sampling weighted by household consumption, per the DRG-33 finding that
  early adopters are not a random draw
* the sampling assumption stated in every scenario output
  """,
  parent="DRG-6", assignee=D, priority="High", points="5",
  components="Simulation", labels="simulation;ev",
  created="2025-12-01 09:20:00", resolved="2025-12-12 15:30:00",
  comments=[
    ("2025-12-03 10:40:00", D, "Bottom-up rather than a percentage uplift on the aggregate. A uniform uplift assumes every household charges at the same time, which is the assumption that would make the whole result wrong in the direction of alarming."),
    ("2025-12-10 11:20:00", G, "And the consumption weighting is a real assumption with an effect, so it needs to be visible and sweepable in the sensitivity work rather than buried."),
  ]),

I("DRG-74", "Story", "EV charging profiles", "Done",
  """
Half-hourly charging demand per EV household.

* arrival time distribution and charge duration, not a fixed schedule
* charger power as a parameter, with the resulting after-diversity maximum
  demand reported per scenario
* daily energy per vehicle reported, so the assumption can be sanity checked
  against average UK mileage
  """,
  parent="DRG-6", assignee=D, points="8", components="Simulation",
  labels="simulation;ev", created="2025-12-01 09:25:00",
  resolved="2025-12-19 15:40:00",
  comments=[
    ("2025-12-15 10:30:00", D, "Reporting kWh per car per day in every scenario summary. It comes out at 5.3, which is about 1,900 kWh a year and consistent with average UK car mileage - and that is the number a planner will check first to decide whether to trust the rest."),
    ("2025-12-19 15:35:00", G, "Publishing the auditable intermediate rather than only the headline is the right instinct. It invites the reader to check us, which is how the headline earns trust."),
  ]),

I("DRG-75", "Story", "Heat pump profiles driven by temperature", "Done",
  """
Half-hourly heat pump demand per adopting household, driven by outdoor
temperature rather than a fixed profile.

* demand from heating degree hours and a configurable coefficient of
  performance
* COP varying with temperature - efficiency falls exactly when demand rises,
  which is the whole reason heat pumps matter for peak
* after-diversity maximum demand per heat pump reported per scenario
  """,
  parent="DRG-6", assignee=D, priority="High", points="8",
  components="Simulation", labels="simulation;heat-pump",
  created="2025-12-15 09:20:00", resolved="2026-01-09 15:50:00",
  comments=[
    ("2025-12-17 11:15:00", D, "Temperature-varying COP is the detail that makes this credible. A fixed COP understates the cold-snap peak, and the cold snap is the case the whole study is about."),
    ("2026-01-07 10:20:00", G, "This is also why DRG-48's lagged temperature work matters - the building thermal mass means the heat pump is still working the morning after the cold evening."),
    ("2026-01-09 15:45:00", D, "1.30 kW after-diversity per heat pump, which sits inside the range DNOs plan with. Published in every scenario summary."),
  ]),

I("DRG-76", "Task", "Year-end report and 2026 plan", "Done",
  """
Close 2025 with stakeholders and agree the 2026 shape.

Delivered in 2025: data foundations and the synthetic path, consumption
analysis, the feature set, the full model ladder, and statistical stress
detection.

2026: electrification scenarios, sensitivity, explainability, the dashboard
and API, MLOps and Azure deployment.
  """,
  parent="DRG-16", assignee=S, points="3", components="Governance",
  labels="ceremony;reporting", created="2025-12-08 09:15:00",
  resolved="2025-12-19 16:20:00",
  comments=[
    ("2025-12-19 16:10:00", S, "Twelve months in and the honest summary is that we spent the first quarter on data quality and never regretted it. Three of the year's five significant defects were leakage or data-integrity issues found by suspicion rather than by a test, and that is the pattern to fix in 2026."),
    ("2025-12-19 16:25:00", G, "Which is an argument for a dedicated QA role. Raising it as a resourcing item rather than something we absorb."),
    ("2026-01-05 09:30:00", S, "Raised. Noting here that it took until June to be filled."),
  ]),

I("DRG-77", "Story", "Deployment target options and a costed recommendation", "Done",
  """
Decide where DRG will run, with costs, before building for it.

Compared: Azure Container Apps with Azure ML, App Service, and AKS.

Recommendation: Container Apps for the API and dashboard, Azure ML for
training and the managed endpoint. Scale to zero on non-production, which
matters for a system that is used during working hours and idle at night.
  """,
  parent="DRG-13", assignee=V, points="5", components="Infrastructure",
  labels="azure;spike", created="2025-12-01 09:30:00",
  resolved="2025-12-18 15:10:00",
  comments=[
    ("2025-12-16 11:20:00", V, "AKS is rejected on operational cost rather than capability. A Kubernetes cluster for a workload this size is a full-time job nobody on this team has, and Container Apps gives us scale-to-zero without it."),
    ("2025-12-18 15:05:00", S, "Costed estimate attached to the year-end report. Non-production comes to a level finance will not query, which is the practical test."),
  ]),

I("DRG-78", "Task", "Modelling notes as a handover document", "Done",
  """
Write the modelling decisions down well enough that the other analyst can run
and defend the stage.

Covers: the split contract, why lags at 1/48/336, the leakage rules from
DRG-46, DRG-58 and DRG-69, the model ladder and why XGBoost is primary, the
stress definition and its limits, and the metrics and their caveats.

Mitigation for the knowledge concentration risk raised in DRG-50.
  """,
  parent="DRG-15", assignee=G, points="5", components="Docs",
  labels="docs;raid", created="2025-12-08 09:20:00",
  resolved="2025-12-23 14:40:00",
  comments=[
    ("2025-12-22 10:30:00", D, "Read it end to end and ran the model stage from it without asking anything. That is the actual acceptance test for this ticket."),
    ("2025-12-23 14:35:00", S, "Good. Closing the knowledge concentration risk down to watch, with the equivalent for the simulation stage due in Q1."),
  ]),

]
