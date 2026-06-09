# -*- coding: utf-8 -*-
"""Second Slack batch for DRG: ceremonies, releases and monthly reporting.

Split from data_slack.py because it is a different register - shorter, more
routine, and spread evenly across all 43 sprints rather than clustered on the
moments where something was decided or went wrong.
"""

from data_slack import M, GEN, ENG, MOD, STD, REL, STK
from backlog_common import G, D, V, N, A, S

EXTRA = [

# ================================================== sprint ceremonies, 2025
M(STD, "2025-01-06 09:30:00", S,
  "Sprint 1 planning at 10:00. Focus: repository, dependencies, the LCL "
  "loader. Standups here in writing by 09:45 each day, no meeting.",
  issue="DRG-19"),
M(STD, "2025-01-17 15:30:00", S,
  "Sprint 1 review. Scaffold, dependency tiers and the loader are done; the "
  "licence question is still open and blocks how we plan the synthetic work.",
  issue="DRG-22"),
M(STD, "2025-01-17 16:00:00", S,
  "Retro. Kept: agreeing the definition of done before writing code. Changed: "
  "the RAID log gets reviewed in planning rather than when something breaks. "
  "Tried: written standups, which everyone prefers to a call.",
  reactions=":+1: 3"),
M(STD, "2025-01-20 09:30:00", G,
  "Standup. Yesterday: LCL aggregate statistics for the calibration targets. "
  "Today: same, handing them to Divya. No blockers.", issue="DRG-24"),
M(STD, "2025-01-20 09:32:00", D,
  "Yesterday: canonical frame. Today: synthetic generator shape. Blocked on "
  "the calibration targets, unblocked this morning.", issue="DRG-24"),
M(STD, "2025-01-20 09:34:00", V,
  "Yesterday: dependency tiers merged. Today: config and logging utilities.",
  issue="DRG-26"),
M(STD, "2025-01-31 16:20:00", S,
  "Sprint 2 review. Synthetic generator, CLI skeleton and config are in. The "
  "licence answer landed today and it reshapes the plan rather than blocking "
  "it.", issue="DRG-23"),

M(STD, "2025-02-03 09:30:00", S,
  "Sprint 3 planning. Data contract, neighbourhood aggregation, CI and the "
  "architecture document."),
M(STD, "2025-02-14 15:40:00", S,
  "Sprint 3 review. CI is live and already caught a stale-file dependency. "
  "Architecture document is drafted with the non-goals in section two.",
  issue="DRG-30"),
M(STD, "2025-02-17 09:30:00", G,
  "Standup. Yesterday: profiling setup. Today: daily and weekly load shapes "
  "for all four sites. No blockers.", issue="DRG-32"),
M(STD, "2025-02-28 15:50:00", S,
  "Sprint 4 review. Load shape profiling and household heterogeneity done. "
  "The heterogeneity finding is going straight into the simulation design "
  "assumptions.", issue="DRG-33"),

M(STD, "2025-03-14 16:10:00", S,
  "Sprint 5 review. Seasonal decomposition, the forward-fill bug fixed, and "
  "container images. Data foundations epic closes here.", issue="DRG-1"),
M(STD, "2025-03-28 16:00:00", S,
  "Sprint 6 review and Q1 close. Six sprints, no forecast, and that was the "
  "plan.", issue="DRG-40", reactions=":+1: 3"),

M(STD, "2025-04-07 09:30:00", S,
  "Sprint 7 planning. Feature engineering starts: calendar, cyclical, lags. "
  "The split contract is in this sprint too and I want it merged before any "
  "model exists.", issue="DRG-44"),
M(STD, "2025-04-18 15:40:00", S,
  "Sprint 7 review. Calendar features, lags at 1/48/336 and the split "
  "contract are in."),
M(STD, "2025-05-02 15:50:00", S,
  "Sprint 8 review. Rolling statistics landed and immediately produced our "
  "first leakage bug, caught before anything was published.", issue="DRG-46"),
M(STD, "2025-05-02 16:10:00", S,
  "Retro. The useful item: Geetha was suspicious of a good number and that is "
  "what caught it. We cannot rely on that indefinitely - action is to turn it "
  "into an assertion, which is now in.", issue="DRG-46",
  reactions=":100: 3"),

M(STD, "2025-05-16 15:40:00", S,
  "Sprint 9 review. Weather features and lagged temperature in. RAID reviewed "
  "- PyTorch moved to active.", issue="DRG-50"),
M(STD, "2025-05-30 15:30:00", S,
  "Sprint 10 review. Feature sanity pass and the processed dataset "
  "materialisation. Feature engineering is effectively complete."),
M(STD, "2025-06-02 09:30:00", S,
  "Sprint 11 planning. The model ladder starts. Order is deliberate: naive, "
  "then linear, then trees.", issue="DRG-52"),
M(STD, "2025-06-13 15:40:00", S,
  "Sprint 11 review. Both naive baselines published and named separately "
  "after the label bug.", issue="DRG-53"),
M(STD, "2025-06-27 15:50:00", S,
  "Sprint 12 review. Ridge at 0.83 against naive at 1.54, and the evaluation "
  "harness is the thing that makes those comparable.", issue="DRG-55"),
M(STD, "2025-07-04 15:40:00", S,
  "Sprint 13 review. Second leakage bug found and fixed. Two in three months, "
  "both caught by suspicion rather than by a test.", issue="DRG-58"),
M(STD, "2025-07-04 16:00:00", S,
  "Retro. Action carried from May, now with more urgency: the leakage class "
  "needs to be structurally impossible, not merely watched for. Divya has "
  "restructured so transforms fit inside the pipeline.", issue="DRG-58"),

M(STD, "2025-07-25 16:20:00", S,
  "Sprint 14 review. XGBoost at 0.70 MAE. The headline number of the project "
  "so far, and it is more than twice as good as the operational baseline.",
  issue="DRG-59", reactions=":tada: 4"),
M(STD, "2025-08-08 15:30:00", S,
  "Sprint 15 review. Hyperparameter search done, and the finding that it "
  "bought very little is worth as much as the tuning."),
M(STD, "2025-08-22 16:10:00", S,
  "Sprint 16 review. Rolling-origin CV confirms the headline sits at the "
  "pessimistic end of the fold range.", issue="DRG-61"),
M(STD, "2025-09-05 15:50:00", S,
  "Sprint 17 review. Model artefacts now carry their provenance, which is the "
  "groundwork for next year's MLOps epic.", issue="DRG-63"),
M(STD, "2025-09-19 16:00:00", S,
  "Sprint 18 review. Deep models evaluated and not adopted, PyTorch risk "
  "realised and mitigated, torch-free fallback in. Model ladder epic closes.",
  issue="DRG-4", reactions=":+1: 3"),
M(STD, "2025-10-10 15:30:00", S,
  "Sprint 19 review. Ladder written up. Stress detection starts next sprint."),
M(STD, "2025-10-24 15:50:00", S,
  "Sprint 20 review. Per-site percentile thresholds in, with the wording "
  "about what stress does and does not mean carried into every artefact.",
  issue="DRG-68"),
M(STD, "2025-11-07 15:40:00", S,
  "Sprint 21 review. Third leakage bug, this one in the stress threshold. The "
  "team has proposed a standing rule rather than a third individual fix.",
  issue="DRG-69"),
M(STD, "2025-11-07 16:10:00", S,
  "Retro, and the honest version: three leakage defects this year, all caught "
  "by a person being suspicious. That is a resourcing signal as much as a "
  "process one and I am taking it to the year-end review.",
  issue="DRG-69", reactions=":100: 3"),
M(STD, "2025-11-21 15:40:00", S,
  "Sprint 22 review. Stress events, frequency and duration metrics in."),
M(STD, "2025-12-05 15:50:00", S,
  "Sprint 23 review. Stress-alarm F1 published for every model. Stress "
  "detection epic closes.", issue="DRG-5"),
M(STD, "2025-12-19 16:00:00", S,
  "Sprint 24 review and year close. EV adoption sampling and charging "
  "profiles landed; heat pumps carry into January.", issue="DRG-74"),

# ================================================== sprint ceremonies, 2026
M(STD, "2026-01-05 09:30:00", S,
  "Sprint 27 planning, first of 2026. Scenario engine and the combined EV and "
  "heat pump case. RAID review after."),
M(STD, "2026-01-23 15:50:00", S,
  "Sprint 28 review. The scenario engine landed and immediately produced a "
  "result that looked wrong, which turned into the diversity finding.",
  issue="DRG-80", reactions=":tada: 3"),
M(STD, "2026-02-06 15:40:00", S,
  "Sprint 29 review. Scenario sweep and peak amplification metrics, with ADMD "
  "printed per scenario for auditability.", issue="DRG-81"),
M(STD, "2026-02-20 15:30:00", S,
  "Sprint 30 review. Stress under scenarios, and the reporting artefacts that "
  "carry the finding. Electrification epic closes.", issue="DRG-6"),
M(STD, "2026-03-06 16:00:00", S,
  "Sprint 31 review. Replay engine and the carbon intensity feed."),
M(STD, "2026-03-20 15:40:00", S,
  "Sprint 32 review. Replay determinism bug fixed, feed degradation handled. "
  "External dependency risk moves from delivery risk to documented "
  "behaviour.", issue="DRG-88"),
M(STD, "2026-04-03 16:00:00", S,
  "Sprint 33 review. Simulation handover notes signed off by acceptance test "
  "- Geetha ran the sweep from the document. Knowledge concentration risk "
  "closed.", issue="DRG-89", reactions=":+1: 3"),
M(STD, "2026-04-17 15:40:00", S,
  "Sprint 34 review. Sensitivity framework and the stress sensitivity "
  "results.", issue="DRG-91"),
M(STD, "2026-05-01 15:30:00", S,
  "Sprint 35 review. Sensitivity written up. The headline is that the "
  "conclusion is robust to everything except adoption rate, which we do not "
  "forecast and say so.", issue="DRG-92"),
M(STD, "2026-05-15 16:00:00", S,
  "Sprint 36 review. SHAP global drivers, and the dashboard shell with its "
  "chart theme.", issue="DRG-93"),
M(STD, "2026-05-29 15:50:00", S,
  "Sprint 37 review. Stress-period SHAP, the scaling bug fixed, and the "
  "demand and forecast page.", issue="DRG-97"),
M(STD, "2026-06-12 15:40:00", S,
  "Sprint 38 review. API forecast endpoint in. Neha starts Monday and the "
  "onboarding is ready.", issue="DRG-98"),
M(STD, "2026-06-26 16:00:00", S,
  "Sprint 39 review. Neha's first sprint, and her gap analysis is the most "
  "useful document produced this quarter.", issue="DRG-99",
  reactions=":+1: 4"),
M(STD, "2026-06-26 16:20:00", S,
  "Retro. Kept: giving the new joiner a narrow first-week goal and asking for "
  "a written finding rather than agreement. Changed: QA reviews contracts "
  "before implementation, which already happened on the API and worked.",
  reactions=":100: 3"),
M(STD, "2026-07-17 15:50:00", S,
  "Sprint 40 review. Stress, scenario and explanation endpoints, model "
  "registry, and the scenario comparison page - which is the page that "
  "carries the whole project finding.", issue="DRG-104"),
M(STD, "2026-07-31 16:00:00", S,
  "Sprint 41 review. Promotion gate live, SHAP page, and the data and feature "
  "regression pack. Engineering practice epic closes.", issue="DRG-14"),
M(STD, "2026-08-14 15:40:00", S,
  "Sprint 42 review. Azure infrastructure deploys clean. The gate blocked its "
  "first promotion, which everyone agrees is a success rather than an "
  "incident.", issue="DRG-107", reactions=":100: 3"),
M(STD, "2026-08-28 16:00:00", S,
  "Sprint 43 review. AML training job, cost pass, the replay page, and Amit's "
  "first week. Three joiners in fifteen months and the onboarding pattern is "
  "now settled.", issue="DRG-115"),
M(STD, "2026-08-31 09:30:00", S,
  "Sprint 44 planning. Managed endpoint, scheduled retrain, simulation "
  "regression pack, BRD refresh and traceability. Monitoring stays blocked on "
  "the ownership decision.", issue="DRG-124"),

# ================================================================ standups
M(STD, "2025-06-24 09:30:00", G,
  "Standup. Yesterday: Ridge results. Today: looking at why test scores are "
  "not degrading relative to validation, which they should be.",
  issue="DRG-58"),
M(STD, "2025-06-24 09:32:00", D,
  "Yesterday: processed dataset materialisation. Today: same, plus whatever "
  "Geetha finds.", issue="DRG-58"),
M(STD, "2025-09-16 09:30:00", G,
  "Standup. Yesterday: LSTM training loop. Today: blocked - torch will not "
  "import on this machine despite installing cleanly.", issue="DRG-65"),
M(STD, "2025-09-16 09:32:00", V,
  "Picking that up. It is the MSVC runtime, which is RAID risk 2 arriving on "
  "schedule.", issue="DRG-65"),
M(STD, "2025-10-27 09:30:00", D,
  "Standup. Yesterday: stress event detection. Today: stress-alarm F1 numbers "
  "look wrong across the board - the naive baseline is scoring too well.",
  issue="DRG-69"),
M(STD, "2026-01-13 09:30:00", G,
  "Standup. Yesterday: scenario engine review. Today: the combined scenario "
  "peak equals the sum of the parts, which should not happen physically.",
  issue="DRG-80"),
M(STD, "2026-01-13 09:32:00", D,
  "On it. If the loads are adding exactly then something in the aggregation "
  "has lost the time offsets.", issue="DRG-80"),
M(STD, "2026-06-16 09:30:00", N,
  "Standup, day two. Yesterday: environment and a full pipeline run. Today: "
  "reading the modelling notes and starting the gap analysis.",
  issue="DRG-99"),
M(STD, "2026-07-21 09:30:00", N,
  "Standup. Yesterday: dashboard smoke tests. Today: found that switching "
  "neighbourhood does not change the series - raising it now.",
  issue="DRG-110"),
M(STD, "2026-07-27 09:30:00", V,
  "Standup. Yesterday: gate wired into the retrain. Today: the overnight "
  "retrain produced a better-MAE model and the gate refused it, which needs a "
  "decision rather than a fix.", issue="DRG-107"),
M(STD, "2026-08-25 09:30:00", A,
  "Standup, day two. Yesterday: objectives table and the architecture "
  "document. Today: stakeholder conversations with network planning.",
  issue="DRG-115"),
M(STD, "2026-09-07 09:30:00", G,
  "Standup. Yesterday: runbook wording with the planning group. Today: same. "
  "The 'what it does not mean' section is taking longer than the rest, which "
  "is probably correct.", issue="DRG-125"),
M(STD, "2026-09-09 09:30:00", S,
  "Standup. Sprint 44 day eight. Reminder: October steering needs the "
  "monitoring ownership decision and the probabilistic forecast question that "
  "Amit has had raised twice.", issue="DRG-126"),
M(STD, "2026-09-09 09:32:00", D,
  "Yesterday: started the sensitivity page. Today: same. No blockers.",
  issue="DRG-122"),
M(STD, "2026-09-09 09:34:00", N,
  "Yesterday: ADMD range checks. Today: finishing those, then UAT scenario "
  "scripts.", issue="DRG-121"),
M(STD, "2026-09-09 09:36:00", A,
  "Yesterday: traceability to 21 of 26. Today: the remaining five and the BRD "
  "refresh.", issue="DRG-119"),
M(STD, "2026-09-09 09:38:00", V,
  "Yesterday: endpoint verification script. Today: traffic shift, then the "
  "retrain schedule review.", issue="DRG-113"),

# ================================================================ releases
M(REL, "2025-01-17 15:00:00", V,
  "Tag v0.1.0. Repository scaffold, dependency tiers, LCL loader. No CI yet - "
  "that is sprint 3.", issue="DRG-22"),
M(REL, "2025-01-31 16:00:00", V,
  "Tag v0.2.0. Synthetic generator, CLI with run-all, config and logging. A "
  "clean clone now produces a full run with no dataset.", issue="DRG-24",
  reactions=":tada: 3"),
M(REL, "2025-02-14 15:00:00", V,
  "CI is green and merging is now gated on it. Full pipeline on synthetic "
  "data, four minutes.", issue="DRG-30", reactions=":white_check_mark: 3"),
M(REL, "2025-03-14 16:00:00", V,
  "Tag v0.3.0. Data contract, neighbourhood aggregation, quality checks, "
  "container images. Data foundations complete.", issue="DRG-1"),
M(REL, "2025-04-25 15:30:00", V,
  "Tag v0.4.0. Consumption analysis and the figure set. Every figure in the "
  "design document now regenerates from run-all.", issue="DRG-39"),
M(REL, "2025-06-06 16:00:00", V,
  "Tag v0.5.0. Feature engineering complete: calendar, cyclical, lags, "
  "rolling, weather, and the split contract.", issue="DRG-3"),
M(REL, "2025-06-30 15:30:00", V,
  "Tag v0.6.0. Baselines and the evaluation harness. Naive at 1.54 MAE is the "
  "bar everything else is measured against.", issue="DRG-55"),
M(REL, "2025-07-25 16:00:00", V,
  "Tag v0.7.0. XGBoost at 0.70 MAE, 0.986 R squared. Primary model selected.",
  issue="DRG-59", reactions=":tada: 4"),
M(REL, "2025-09-30 15:30:00", V,
  "Tag v0.8.0. Model ladder complete including the deep models and the "
  "torch-free fallback. The fallback is automatic and reported.",
  issue="DRG-66"),
M(REL, "2025-12-05 16:00:00", V,
  "Tag v0.9.0. Stress detection: per-site thresholds, event detection, "
  "frequency and duration, alarm F1.", issue="DRG-5"),
M(REL, "2026-02-13 16:00:00", V,
  "Tag v1.0.0. Electrification scenarios complete, including the diversity "
  "result. First release that answers all four of the analytical proposal "
  "objectives.", issue="DRG-6", reactions=":tada: 4 :rocket: 2"),
M(REL, "2026-03-27 16:00:00", V,
  "Tag v1.1.0. Replay engine and external feeds, both deterministic and both "
  "degrading gracefully.", issue="DRG-9"),
M(REL, "2026-04-24 15:00:00", V,
  "Tag v1.2.0. Sensitivity analysis. Objective 5 answered.", issue="DRG-7"),
M(REL, "2026-05-22 16:00:00", V,
  "Tag v1.3.0. SHAP explanations, global and stress-specific. Objective 6 "
  "answered.", issue="DRG-8"),
M(REL, "2026-06-19 15:30:00", V,
  "Tag v1.4.0. REST API with forecast, stress, scenario and explanation "
  "endpoints, all versioned.", issue="DRG-10"),
M(REL, "2026-07-24 16:00:00", V,
  "Tag v1.5.0. Model registry and promotion gate. From here, a model reaches "
  "the API by passing the gate rather than by being the most recent thing "
  "trained.", issue="DRG-106", reactions=":+1: 3"),
M(REL, "2026-08-14 15:00:00", V,
  "Tag v1.6.0. Azure infrastructure as Bicep, deployed to non-production. "
  "Twenty months on laptops is over.", issue="DRG-111",
  reactions=":rocket: 4"),
M(REL, "2026-08-28 15:30:00", V,
  "Tag v1.7.0. AML training job and the replay page. Managed endpoint is "
  "behind it.", issue="DRG-112"),
M(REL, "2026-07-14 14:00:00", V,
  "Hotfix: model version now on every API response, with a contract test "
  "across all routes.", issue="DRG-103"),
M(REL, "2026-07-29 14:30:00", D,
  "Hotfix: dashboard cache key includes the full selection. The neighbourhood "
  "switch bug is fixed and covered.", issue="DRG-110"),

# ============================================================ stakeholders
M(STK, "2025-01-31 14:00:00", S,
  "January report. Data foundations underway. The dataset licence question is "
  "resolved and the answer shapes our approach: everything will run on a "
  "calibrated synthetic dataset, so the system is demonstrable to anyone "
  "without a licence.", issue="DRG-23"),
M(STK, "2025-03-31 14:00:00", S,
  "March report and Q1 close. Data foundations complete, consumption analysis "
  "underway. No forecast yet - deliberately. The quarter went on making the "
  "data trustworthy, and we found and fixed two defects that would have "
  "silently distorted every model built on it.", issue="DRG-40",
  reactions=":+1: 2"),
M(STK, "2025-04-30 14:00:00", S,
  "April report. Consumption analysis complete. The headline finding is that "
  "weekly seasonality dominates - the same half-hour last week predicts "
  "demand better than the same half-hour yesterday. That shapes the whole "
  "modelling approach.", issue="DRG-36"),
M(STK, "2025-06-30 14:00:00", S,
  "June report. Baselines are in. The number to anchor on is 1.54 MAE for the "
  "operational status quo - what a control room effectively does today. Every "
  "model we build will be reported against it rather than in isolation.",
  issue="DRG-52", reactions=":+1: 3"),
M(STK, "2025-07-31 14:00:00", S,
  "July report. XGBoost achieves 0.70 MAE against the 1.54 baseline - less "
  "than half the error. Cross-validation over five time windows puts the "
  "range at 0.74 to 0.95 RMSE, so this is not a lucky split.",
  issue="DRG-59", reactions=":tada: 3"),
M(STK, "2025-09-30 14:00:00", S,
  "September report. Model ladder complete. We evaluated deep sequence models "
  "and are not adopting them - competitive but not better, and considerably "
  "more expensive to run. Recording that as a finding rather than a gap.",
  issue="DRG-64"),
M(STK, "2025-11-28 14:00:00", S,
  "November report. Stress detection is in. To be precise about what it "
  "claims: stress is a half-hour in the top 5% of a neighbourhood's own "
  "history. It is not a capacity breach - we have no transformer ratings and "
  "do not model the network.", issue="DRG-68", reactions=":+1: 2"),
M(STK, "2026-01-30 14:00:00", S,
  "January report. First combined electrification results. A correction "
  "worth flagging: our initial figures overstated the combined peak because "
  "the model was adding EV and heat pump peaks as though they coincided. They "
  "do not, and the corrected result is materially lower.", issue="DRG-80"),
M(STK, "2026-02-27 14:00:00", S,
  "February report and the headline result. At 80% EV and 70% heat pump "
  "adoption, peak demand rises 237% - not the 267% you would get by adding "
  "the technologies separately. The 29 point gap is diversity between the two "
  "loads, and it is a planning-relevant finding in its own right.",
  issue="DRG-81", reactions=":tada: 3 :eyes: 2"),
M(STK, "2026-04-30 14:00:00", S,
  "April report. Sensitivity analysis complete. The conclusions hold across "
  "plausible ranges of charging behaviour and heat pump efficiency. They "
  "depend heavily on the adoption rate itself - which DRG does not forecast, "
  "and we would rather say that plainly than imply otherwise.",
  issue="DRG-92", reactions=":100: 2"),
M(STK, "2026-05-29 14:00:00", S,
  "May report. Explainability is in. The most useful operational point: the "
  "drivers of demand during stress periods are the same as at other times, "
  "only more so. Stressful half-hours are strongly recurrent, which is what "
  "makes them forecastable and therefore manageable.", issue="DRG-94"),
M(STK, "2026-06-30 14:00:00", S,
  "June report. The API is live for integration, every response carrying the "
  "model version so any forecast can be traced back to the artefact that "
  "produced it. A QA analyst has joined the team.", issue="DRG-101"),
M(STK, "2026-07-31 14:00:00", S,
  "July report. Model governance is now enforced: a retrained model must beat "
  "the incumbent on stress detection, not only on average error, before it "
  "can be promoted. It blocked its first candidate this month, which is the "
  "control working as intended.", issue="DRG-107", reactions=":+1: 3"),
M(STK, "2026-08-31 14:00:00", S,
  "August report. Cloud infrastructure is deployed and training now runs "
  "there rather than on laptops. A business analyst has joined and is "
  "refreshing the requirements against what has actually been built.",
  issue="DRG-111"),

# ============================================== engineering and modelling
M(ENG, "2025-02-05 10:35:00", D,
  "Config hash on every processed artefact. It is what stops the classic "
  "research failure - a figure in a report nobody can regenerate because the "
  "parameters have moved since.", issue="DRG-28", reactions=":100: 2"),
M(ENG, "2025-03-11 15:25:00", V,
  "Three container images rather than one that does everything. The dashboard "
  "does not need XGBoost and the pipeline does not need Streamlit.",
  issue="DRG-38"),
M(ENG, "2025-03-20 11:35:00", V,
  "Key-free weather API is a hard requirement, not a preference. The moment a "
  "demo needs a credential it needs a person with the credential, and the "
  "project stops being self-service.", issue="DRG-41", reactions=":+1: 3"),
M(ENG, "2025-04-25 11:40:00", V,
  "ruff and black in CI so formatting stops being decided in review. Review "
  "time is better spent on whether the rolling window is left-closed.",
  issue="DRG-47"),
M(ENG, "2025-12-16 11:25:00", V,
  "AKS rejected for the deployment target on operational cost rather than "
  "capability. A Kubernetes cluster for a workload this size is a full-time "
  "job nobody here has. Container Apps gives us scale-to-zero without it.",
  issue="DRG-77"),
M(ENG, "2026-08-20 10:25:00", V,
  "The compute that was going to cost most is AML idling. Low-priority with "
  "aggressive deallocation brings training down to rounding error for a "
  "nightly job.", issue="DRG-114"),
M(ENG, "2026-09-04 11:25:00", V,
  "Retrain is scheduled, promotion is gated. Automating the retrain is safe; "
  "automating the promotion would mean the DRG-107 model shipped itself at "
  "3am.", issue="DRG-123", reactions=":100: 3"),

M(MOD, "2025-04-30 15:10:00", D,
  "Left-closed rolling windows, asserted in a test. The default in most "
  "libraries includes the current observation and that is a leak that will "
  "not show up as an error.", issue="DRG-45"),
M(MOD, "2025-05-14 11:25:00", G,
  "The 'knowable at prediction time' note per feature is the useful artefact "
  "from the sanity pass. It turns an assumption everyone holds loosely into "
  "something a reviewer can check line by line.", issue="DRG-49",
  reactions=":+1: 2"),
M(MOD, "2025-06-30 12:20:00", G,
  "Reporting the excluded fraction next to MAPE. A percentage error that "
  "quietly drops its most difficult observations is a flattering statistic, "
  "and stakeholders will quote it.", issue="DRG-56"),
M(MOD, "2025-08-29 15:10:00", G,
  "The baseline row stays in the comparison table permanently. The moment it "
  "is dropped for being uninteresting, the table stops answering the only "
  "question that matters.", issue="DRG-62", reactions=":100: 3"),
M(MOD, "2025-09-02 10:25:00", V,
  "The feature-list check on model load will save someone. Feeding columns in "
  "a different order to a tree model produces predictions rather than an "
  "error, and they will look approximately reasonable.", issue="DRG-63",
  reactions=":eyes: 2"),
M(MOD, "2025-11-07 10:35:00", G,
  "The gap-bridging rule in stress event detection matters more than it "
  "sounds. Demand oscillating around a threshold produces dozens of "
  "one-period events, which is noise dressed as a finding.", issue="DRG-70"),
M(MOD, "2025-12-17 11:20:00", D,
  "Temperature-varying COP is what makes the heat pump model credible. A "
  "fixed COP understates the cold-snap peak, and the cold snap is the case "
  "the whole study is about.", issue="DRG-75", reactions=":100: 2"),
M(MOD, "2026-02-03 10:25:00", D,
  "ADMD printed in every scenario summary rather than in an appendix. It is "
  "the number a DNO planner checks against their own assumptions to decide "
  "whether to believe the rest of the table.", issue="DRG-81"),
M(MOD, "2026-02-18 11:20:00", D,
  "The load shape overlay is the most persuasive figure we have. It shows the "
  "evening peak growing and widening rather than just a bigger number, which "
  "is what makes the duration finding land.", issue="DRG-84"),
M(MOD, "2026-07-01 10:25:00", D,
  "Putting the diversity number on the scenario page rather than in a "
  "tooltip. It is the most defensible thing we have found and the thing most "
  "likely to be lost if the page only shows the scary total.",
  issue="DRG-104", reactions=":+1: 3"),
M(MOD, "2026-07-29 10:45:00", D,
  "The attribution-not-causation note goes on the SHAP page itself. Someone "
  "will otherwise read 'lag_336 drives 39% of demand' as a statement about "
  "the world instead of about the model.", issue="DRG-108"),
M(MOD, "2026-07-14 10:25:00", N,
  "The clock-change test fixture spans both October and March, so the "
  "assertion is exercised rather than theoretical. Cheap, and it covers the "
  "defect that started this project's data quality work.", issue="DRG-109",
  reactions=":100: 2"),
M(MOD, "2026-08-14 10:35:00", N,
  "Asserting the naive baseline is present in the comparison, not just that "
  "it scores well. The failure mode is someone dropping it for looking bad, "
  "and then no result is anchored to anything.", issue="DRG-116"),
M(MOD, "2026-08-11 11:25:00", N,
  "Raising drift detection now so the run history is retained in a shape that "
  "makes it possible later. Discovering in six months that we discarded the "
  "baseline would be annoying.", issue="DRG-129"),
M(MOD, "2026-09-08 10:45:00", A,
  "Probabilistic forecasts have come up twice in my stakeholder "
  "conversations. Moving DRG-126 up for October planning - people want to "
  "know how confident the forecast is, and a point estimate does not say.",
  issue="DRG-126", reactions=":+1: 2"),
M(MOD, "2026-06-08 10:20:00", G,
  "The shared-model finding was tested on four sites. It is not safe to "
  "assume it holds at a hundred, and that is the first thing to check if we "
  "ever scale rather than the last.", issue="DRG-128"),

]
