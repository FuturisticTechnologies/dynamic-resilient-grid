# -*- coding: utf-8 -*-
"""Slack transcript for DynamicResilientGrid, 02 Jan 2025 - 09 Sep 2026.

Channels
  #drg-general        project-wide decisions and announcements
  #drg-eng            platform, pipeline, infrastructure, CI
  #drg-modelling      features, models, stress, simulation, explainability
  #drg-standup        written standups and sprint ceremonies
  #drg-releases       merges, deploys, CI outcomes
  #drg-stakeholders   shared with network planning, sustainability and the
                      academic partner

`thread` carries the timestamp of the parent message for threaded replies.
Neha joins 15 Jun 2026 and Amit 24 Aug 2026; neither appears before their date.
"""

from backlog_common import G, D, V, N, A, S

GEN = "#drg-general"
ENG = "#drg-eng"
MOD = "#drg-modelling"
STD = "#drg-standup"
REL = "#drg-releases"
STK = "#drg-stakeholders"


def M(channel, ts, author, text, thread=None, issue=None, reactions=""):
    return dict(channel=channel, ts=ts, author=author, text=text,
                thread=thread or "", issue=issue or "", reactions=reactions)


SLACK = [

# ================================================================= Jan 2025
M(GEN, "2025-01-02 09:05:00", S,
  "Morning all, and welcome to day one of Dynamic Resilient Grid. Kickoff at "
  "09:30, then epic cutting. Two things I want agreed before any code: how we "
  "work, and what we are explicitly not building.", reactions=":wave: 3"),
M(GEN, "2025-01-02 09:08:00", G,
  "Ready. I have read the proposal twice - seven objectives, and the one that "
  "will decide whether anyone believes the rest is the stress definition. We "
  "have no transformer ratings, so we cannot claim a capacity breach."),
M(GEN, "2025-01-02 09:11:00", D,
  "Same read. And the dataset licence is the thing I would like resolved in "
  "week one, because if we cannot redistribute any of it then the synthetic "
  "generator stops being a nice-to-have."),
M(GEN, "2025-01-02 12:30:00", S,
  "Workshop done. Sixteen epics, DRG-1 to DRG-16. Sequencing: data first, "
  "then analysis, then features, then models, then stress, then scenarios. "
  "No forecast until Q3 and that is deliberate.", issue="DRG-19",
  reactions=":white_check_mark: 3"),
M(GEN, "2025-01-02 12:38:00", V,
  "The one I want on the record: DRG-14 runs the whole length of the project "
  "rather than being a deployment phase at the end. run-all exists in week "
  "two, not month twelve.", thread="2025-01-02 12:30:00", issue="DRG-14"),
M(GEN, "2025-01-02 12:45:00", G,
  "And DRG-31's non-goals section. No power flow, no topology, no ratings. "
  "Written on page one of the architecture doc, because someone will "
  "eventually present this as if we modelled the network.",
  thread="2025-01-02 12:30:00", issue="DRG-31", reactions=":100: 2"),
M(GEN, "2025-01-02 13:10:00", S,
  "RAID log is open with three risks: the LCL licence, PyTorch on Windows, "
  "and knowledge concentration across a team of four. I will review them at "
  "every planning session rather than when something goes wrong.",
  issue="DRG-19"),

M(ENG, "2025-01-07 10:20:00", V,
  "src layout for DRG-20 rather than a flat package. Costs one line in "
  "pyproject and it means a test can never accidentally import the working "
  "directory instead of the installed package.", issue="DRG-20"),
M(ENG, "2025-01-13 10:45:00", V,
  "Torch stays out of the base install in DRG-21. Large download, optional to "
  "the argument we are making, and on Windows it needs a system runtime we "
  "cannot assume. That is RAID risk 2 and I expect it to bite us in Q3.",
  issue="DRG-21", reactions=":eyes: 2"),

M(MOD, "2025-01-08 11:25:00", D,
  "DRG-22 design note: defining the canonical frame first and making both the "
  "LCL loader and the synthetic generator targets of it. If the real loader "
  "defines the shape and synthetic is retrofitted, synthetic is permanently "
  "second class and will be broken when we need it.", issue="DRG-22"),
M(MOD, "2025-01-08 11:40:00", G,
  "Right call. The moment the two diverge, every result becomes 'which loader "
  "produced this?'", thread="2025-01-08 11:25:00", issue="DRG-22"),

M(GEN, "2025-01-31 15:35:00", S,
  "LCL licence answer, and it is the one we expected: no redistribution, no "
  "committing extracts, nothing shipped in a container. Derived aggregate "
  "statistics are fine.", issue="DRG-23", reactions=":eyes: 3"),
M(GEN, "2025-01-31 15:50:00", D,
  "So the synthetic generator is not a convenience, it is the only way this "
  "project is demonstrable. Moving DRG-24 up.",
  thread="2025-01-31 15:35:00", issue="DRG-24"),
M(GEN, "2025-01-31 16:10:00", G,
  "Which is a better outcome than it sounds. It forces the synthetic path to "
  "be first class, so every reviewer, every CI run and every new joiner "
  "exercises the same route. If it had been optional we would have let it "
  "rot.", thread="2025-01-31 15:35:00", reactions=":100: 3"),

M(MOD, "2025-01-21 10:35:00", D,
  "Calibration targets for DRG-24: mean and spread of household daily "
  "consumption, morning to evening peak ratio, weekday to weekend difference, "
  "winter to summer amplitude. All taken from the LCL aggregates rather than "
  "invented.", issue="DRG-24"),
M(MOD, "2025-01-27 15:20:00", G,
  "Checked the output against the LCL aggregates. Load shapes overlay well "
  "and the household spread is right. It will not fool anyone into thinking "
  "it is real, and it does not need to - it needs to exercise the same code "
  "and produce conclusions of the same shape.", thread="2025-01-21 10:35:00",
  issue="DRG-24", reactions=":+1: 2"),

M(MOD, "2025-01-27 11:20:00", G,
  "Something is wrong with the daily profiles - there is a step in them on "
  "exactly two days of the year.", issue="DRG-27"),
M(MOD, "2025-01-27 11:35:00", G,
  "Last Sunday in October and last Sunday in March. It is the BST change - "
  "duplicate timestamps in autumn, missing ones in spring. Every household, "
  "every year.", thread="2025-01-27 11:20:00", issue="DRG-27",
  reactions=":face_palm: 2"),
M(MOD, "2025-01-29 10:25:00", D,
  "Confirmed. Moving to UTC for the index and deriving local hour for the "
  "calendar features. Keeping everything local means the index is not "
  "monotonic twice a year and every rolling window quietly misbehaves.",
  thread="2025-01-27 11:20:00", issue="DRG-27"),
M(MOD, "2025-01-29 10:40:00", G,
  "Worth saying out loud that this is the single most common bug in UK "
  "half-hourly energy data. It will not be the last time it costs us an "
  "afternoon.", thread="2025-01-27 11:20:00", issue="DRG-27"),

# ================================================================= Feb 2025
M(ENG, "2025-01-22 11:45:00", V,
  "Building run-all now, in week three, when there are two stages to "
  "orchestrate. Doing it at the end means every stage gets built against a "
  "slightly different idea of what the previous one produced, and the "
  "integration becomes a project of its own.", issue="DRG-25",
  reactions=":+1: 3"),
M(ENG, "2025-02-12 14:15:00", V,
  "CI runs the whole pipeline on synthetic data, not just unit tests. Four "
  "minutes, and it is the only thing that proves the stages still fit "
  "together.", issue="DRG-30"),
M(ENG, "2025-02-14 15:20:00", D,
  "First green run caught a stage that only worked because I had a stale "
  "interim file locally.", thread="2025-02-12 14:15:00", issue="DRG-30",
  reactions=":sweat_smile: 2"),

M(MOD, "2025-02-07 11:25:00", D,
  "Keeping the contributing household count alongside the neighbourhood "
  "total in DRG-29. Without it, a neighbourhood whose meters drop out for a "
  "week looks like a neighbourhood whose demand fell, and those are "
  "indistinguishable in the aggregate.", issue="DRG-29"),

M(GEN, "2025-02-24 14:30:00", G,
  "Architecture doc is up. Non-goals are section two, ahead of the "
  "architecture itself: no power flow, no topology, no ratings, stress is "
  "statistical and relative to a site's own history.", issue="DRG-31"),
M(GEN, "2025-02-25 09:45:00", S,
  "Adding that to the RAID log as a live risk with the document as its "
  "mitigation, so it stays visible rather than being considered handled.",
  thread="2025-02-24 14:30:00", issue="DRG-31"),

M(STK, "2025-02-28 14:00:00", S,
  "February report. Delivered: data foundations, the synthetic generator, "
  "run-all and CI. Next: consumption analysis. Headline numbers in the report "
  "are generated from the pipeline rather than retyped, so they cannot drift "
  "from what the code produced.", issue="DRG-34", reactions=":+1: 2"),

# ================================================================= Mar 2025
M(MOD, "2025-03-04 10:45:00", G,
  "Household heterogeneity finding for DRG-33: the top decile of households "
  "uses roughly three times the median. That matters for the EV simulation - "
  "if adoption is sampled uniformly we will understate the peak, because "
  "early adopters are not a random draw.", issue="DRG-33",
  reactions=":eyes: 2"),

M(MOD, "2025-03-05 10:25:00", D,
  "Raising a bug against my own work. Neighbourhood totals look complete for "
  "periods where the loader reported missing household reads - the resample "
  "was forward-filling by default. Gaps became flat lines.", issue="DRG-37"),
M(MOD, "2025-03-06 09:45:00", G,
  "And a forward-filled evening peak is a fabricated peak that will feed the "
  "percentile defining stress. The useful thing here is that the 48-per-day "
  "assertion and the aggregate disagreed, and both could not be true.",
  thread="2025-03-05 10:25:00", issue="DRG-37"),
M(MOD, "2025-03-06 10:00:00", G,
  "Keeping that as a habit: assert the same fact in two places and let them "
  "argue. It is how both of the data bugs so far were found.",
  thread="2025-03-05 10:25:00", issue="DRG-37", reactions=":100: 2"),

M(MOD, "2025-03-10 11:25:00", G,
  "DRG-36 result, and it is the most useful thing this quarter has produced: "
  "autocorrelation at 336 half-hours - the same half-hour last week - is "
  "stronger than at 48, the same half-hour yesterday. The weekly cycle "
  "dominates.", issue="DRG-36", reactions=":chart_with_upwards_trend: 2"),
M(MOD, "2025-03-14 15:50:00", D,
  "That predicts the whole feature set, and it predicts what SHAP will say "
  "eventually. If lag_336 does not come out on top in a year's time, one of "
  "the two analyses is wrong.", thread="2025-03-10 11:25:00", issue="DRG-36"),

M(STD, "2025-03-28 16:25:00", S,
  "Q1 review done. Question from the stakeholder session, recorded because it "
  "will come back: 'when do we see a forecast?' Answer is Q3, and the reason "
  "is that a forecast built on data with two corrupt days a year and "
  "forward-filled gaps would have been ready in March and wrong.",
  issue="DRG-40", reactions=":100: 3"),
M(STD, "2025-03-31 09:45:00", G,
  "That framing helped in the room. Worth reusing verbatim.",
  thread="2025-03-28 16:25:00", issue="DRG-40"),

# ================================================================= Apr 2025
M(MOD, "2025-04-08 09:45:00", G,
  "Writing the split contract down before the first model exists. Chronological, "
  "never shuffled, validation for early stopping, test untouched until final "
  "reporting. Random splits on a time series produce beautiful scores and "
  "worthless models, and the failure is invisible in the metrics.",
  issue="DRG-44", reactions=":pushpin: 3"),
M(MOD, "2025-04-11 11:20:00", D,
  "Dropping the first week rather than imputing lag_336. An imputed value in "
  "the strongest feature in the model, concentrated entirely at the start of "
  "the series, is not a trade worth making.", issue="DRG-43"),

M(MOD, "2025-04-28 10:35:00", G,
  "First Ridge run came back at 0.11 MAE on validation. That is roughly six "
  "times better than anything plausible for half-hourly demand, so something "
  "is wrong.", issue="DRG-46", reactions=":eyes: 2"),
M(MOD, "2025-04-28 11:10:00", D,
  "Found it - the rolling mean window is centred rather than trailing, so the "
  "feature for 18:00 includes the 18:00 value. The model is being handed a "
  "smoothed version of its own target.", thread="2025-04-28 10:35:00",
  issue="DRG-46", reactions=":face_palm: 2"),
M(MOD, "2025-04-28 11:30:00", G,
  "A result far better than the problem is hard is not a good result, it is a "
  "symptom. Worth building that reflex now, because we will see this again.",
  thread="2025-04-28 10:35:00", issue="DRG-46"),
M(MOD, "2025-05-02 14:20:00", D,
  "Fixed, plus an assertion that no feature correlates with the target above "
  "a threshold only leakage explains. Ridge is now 0.83, which is a believable "
  "number.", thread="2025-04-28 10:35:00", issue="DRG-46"),

# ============================================================= May-Jun 2025
M(MOD, "2025-05-12 10:45:00", D,
  "Lagged temperature earns its place in DRG-48. Buildings have thermal mass, "
  "so yesterday evening's cold is still in the walls this morning. The "
  "un-lagged version underfits exactly the cold snaps we care about.",
  issue="DRG-48"),

M(GEN, "2025-05-19 09:45:00", S,
  "Mid-year RAID review. LCL licence closed. PyTorch moved from watch to "
  "active - the deep model is planned for Q3 and the runtime dependency is "
  "unresolved. New risk: knowledge concentration. The simulation exists only "
  "in Divya's head and the model ladder only in Geetha's.", issue="DRG-50",
  reactions=":eyes: 2"),
M(GEN, "2025-05-23 10:35:00", G,
  "Mitigation proposal: the modelling notes have to be good enough that the "
  "other person can run the stage. That is a real deliverable rather than a "
  "promise, so it goes on the board as DRG-78.",
  thread="2025-05-19 09:45:00", issue="DRG-78", reactions=":+1: 3"),

M(MOD, "2025-06-03 10:20:00", G,
  "Starting the naive baseline. This is the model to beat and it deserves the "
  "same care as the others - a weak baseline makes every later result look "
  "better than it is, which is a comfortable mistake and a corrosive one.",
  issue="DRG-52"),
M(MOD, "2025-06-09 11:25:00", D,
  "The naive baseline docstring says 'same half-hour last week' and the code "
  "shifts 48, which is yesterday. Not a maths bug - a label bug, which is "
  "arguably worse because the number is right for a thing nobody agreed to.",
  issue="DRG-53"),
M(MOD, "2025-06-10 09:35:00", G,
  "Publishing both and naming them separately. Daily-naive is what a control "
  "room actually does, weekly-naive is the stronger statistical baseline, and "
  "nobody should have to guess which one a later comparison beat.",
  thread="2025-06-09 11:25:00", issue="DRG-53", reactions=":+1: 2"),

M(MOD, "2025-06-18 11:20:00", G,
  "One evaluation harness for DRG-55, and models only supply predictions. "
  "Every model computing its own metrics is how you get a comparison table "
  "where the numbers are not comparable.", issue="DRG-55"),
M(MOD, "2025-06-25 10:35:00", G,
  "Ridge at 0.83 MAE against daily-naive at 1.54. A regularised linear model "
  "on good features gets most of the way, which is worth knowing before "
  "anyone concludes the problem needed gradient boosting.", issue="DRG-54",
  reactions=":chart_with_upwards_trend: 2"),

M(MOD, "2025-06-24 10:25:00", G,
  "Test scores are not degrading at all relative to validation, which is "
  "unusual for a chronological split. Looking into it.", issue="DRG-58"),
M(MOD, "2025-06-24 10:50:00", G,
  "The scaler is fitted on the full series, test window included. The lags "
  "themselves are fine - standardisation has seen the future. Second leakage "
  "bug in two months and a subtler one.", thread="2025-06-24 10:25:00",
  issue="DRG-58", reactions=":eyes: 3"),
M(MOD, "2025-06-25 09:55:00", D,
  "Restructuring so the split happens before any fitted transform, and the "
  "transform is fitted inside the pipeline rather than beside it. That makes "
  "the mistake structurally hard rather than something we have to remember.",
  thread="2025-06-24 10:25:00", issue="DRG-58"),
M(MOD, "2025-06-30 11:20:00", G,
  "Which is the right lesson. We have caught two of these by being suspicious "
  "of good numbers and that will not scale - the third one slips through "
  "unless it is impossible by construction.",
  thread="2025-06-24 10:25:00", issue="DRG-58", reactions=":100: 2"),

# ============================================================= Jul-Sep 2025
M(MOD, "2025-07-14 10:35:00", G,
  "One XGBoost model across all four neighbourhoods with site as a feature, "
  "rather than four models. Not enough data per site to justify four, and the "
  "shared model can borrow strength across them. That is a testable claim so "
  "I will test it.", issue="DRG-59"),
M(MOD, "2025-07-21 11:25:00", D,
  "Tested: shared beats per-site on three of four sites and ties on the "
  "fourth. Recording it in the notes because it is a question that will be "
  "asked again.", thread="2025-07-14 10:35:00", issue="DRG-59",
  reactions=":+1: 2"),
M(MOD, "2025-07-25 16:10:00", G,
  "XGBoost: 0.70 MAE, 0.95 RMSE, R squared 0.986. Against daily-naive at 1.54 "
  "that is substantial; against Ridge at 0.83 it is real but modest. Both "
  "framings go in the write-up.", issue="DRG-59",
  reactions=":tada: 3 :chart_with_upwards_trend: 2"),
M(MOD, "2025-08-08 15:20:00", G,
  "Hyperparameter tuning bought about 0.04 MAE over sensible defaults. "
  "Recording that as a counterweight to the instinct that more search is "
  "always worth it - the features did far more than the parameters.",
  issue="DRG-60"),
M(MOD, "2025-08-22 16:00:00", G,
  "Rolling-origin CV: RMSE 0.74 to 0.95 across five folds, with the headline "
  "test at 0.95. The headline sits at the pessimistic end of the range rather "
  "than the flattering one, which is the version to publish.", issue="DRG-61",
  reactions=":100: 2"),

M(ENG, "2025-09-16 10:20:00", G,
  "Torch installs fine on this Windows box and then raises an OSError on "
  "import - a DLL load failure. Lost an hour before realising the install had "
  "succeeded and the import had not.", issue="DRG-65"),
M(ENG, "2025-09-16 11:45:00", V,
  "Known issue with the Windows wheels - they link against the MSVC "
  "redistributable, which is not installed by default and is not something "
  "pip can pull in. This is RAID risk 2 from January, so at least it is not a "
  "surprise.", thread="2025-09-16 10:20:00", issue="DRG-65",
  reactions=":eyes: 2"),
M(ENG, "2025-09-18 09:55:00", S,
  "Marking the risk realised and mitigated rather than closing it quietly. "
  "The mitigation - graceful fallback plus a documented prerequisite - is the "
  "reusable part.", thread="2025-09-16 10:20:00", issue="DRG-65"),
M(ENG, "2025-09-24 14:20:00", V,
  "Fixed. Import is guarded, the fallback to the sklearn sequence model is "
  "automatic and reported in the run log, and the README says what to "
  "install. A missing optional dependency should degrade the run, not end "
  "it.", thread="2025-09-16 10:20:00", issue="DRG-65",
  reactions=":white_check_mark: 3"),
M(MOD, "2025-09-25 10:45:00", G,
  "The torch-free fallback comes in at 0.78 MAE, between Ridge and XGBoost. "
  "Built as a fallback and it turns out to be a legitimate rung on the "
  "ladder.", issue="DRG-66", reactions=":+1: 2"),
M(MOD, "2025-09-26 15:50:00", G,
  "Deep models do not beat XGBoost on this data volume. Competitive, far more "
  "expensive to train and serve. Recording it as a finding and stopping, "
  "rather than spending a quarter tuning it into a tie.", issue="DRG-64"),

# ============================================================= Oct-Dec 2025
M(MOD, "2025-10-13 09:50:00", G,
  "Stress definition wording, which goes everywhere this number appears: this "
  "is not a capacity breach. We do not have ratings. It is the top 5% of a "
  "site's own history, and the interesting claim is how much more often that "
  "happens under electrification.", issue="DRG-68", reactions=":100: 3"),

M(MOD, "2025-10-27 10:25:00", D,
  "Stress-alarm F1 is suspiciously stable across every model including naive "
  "at 0.85, which is high for something that just repeats yesterday.",
  issue="DRG-69"),
M(MOD, "2025-10-27 10:45:00", G,
  "The P95 threshold is computed over the entire series, test window "
  "included. Every model is scored against a threshold derived partly from "
  "the data it is tested on - and it flatters all of them equally, which is "
  "why the ranking looked fine.", thread="2025-10-27 10:25:00",
  issue="DRG-69", reactions=":eyes: 3"),
M(MOD, "2025-10-28 09:35:00", G,
  "Third leakage bug this year and the pattern is consistent: never the "
  "model, always something fitted on more data than it should have seen. "
  "Scaler, rolling window, now a threshold.", thread="2025-10-27 10:25:00",
  issue="DRG-69"),
M(MOD, "2025-10-30 11:20:00", G,
  "Proposing a rule rather than another fix: anything estimated from data - a "
  "scaler, a threshold, a percentile, an encoding - is fitted on train and "
  "applied elsewhere, with a test for each. Otherwise we find the fourth in "
  "February.", thread="2025-10-27 10:25:00", issue="DRG-69",
  reactions=":100: 3"),
M(MOD, "2025-11-04 14:30:00", D,
  "Rule adopted and in the modelling notes. Thresholds are train-only now, "
  "the F1 numbers moved slightly and the ranking held.",
  thread="2025-10-27 10:25:00", issue="DRG-69"),

M(MOD, "2025-11-20 10:25:00", G,
  "Stress-alarm F1 alongside MAE for every model, per DRG-72. A model can "
  "improve MAE by getting the easy quiet half-hours slightly better while "
  "getting worse at the peaks. Without this metric we would select for the "
  "wrong thing and never know.", issue="DRG-72", reactions=":100: 2"),
M(MOD, "2025-12-05 15:40:00", D,
  "XGBoost 0.90 stress F1, daily-naive 0.85. A smaller gap than the MAE "
  "difference suggests, which is informative in itself - the peaks are the "
  "recurrent, forecastable part.", thread="2025-11-20 10:25:00",
  issue="DRG-72"),

M(MOD, "2025-12-03 10:45:00", D,
  "EV adoption sampled bottom-up per household rather than as an aggregate "
  "uplift. A uniform uplift assumes every household charges at the same time, "
  "which is the assumption that would make the whole result wrong in the "
  "alarming direction.", issue="DRG-73"),
M(MOD, "2025-12-15 10:35:00", D,
  "Reporting kWh per car per day in every scenario summary. It comes out at "
  "5.3, about 1,900 kWh a year, consistent with average UK mileage. That is "
  "the number a planner checks first to decide whether to trust the rest.",
  issue="DRG-74", reactions=":+1: 2"),

M(STK, "2025-12-19 16:15:00", S,
  "Year-end report. Delivered in 2025: data foundations and the synthetic "
  "path, consumption analysis, the feature set, the full model ladder, and "
  "statistical stress detection. 2026: scenarios, sensitivity, "
  "explainability, dashboard and API, MLOps and Azure.", issue="DRG-76",
  reactions=":tada: 4"),
M(GEN, "2025-12-19 16:30:00", S,
  "Internal version of the same summary: we spent Q1 on data quality and "
  "never regretted it. Three of the year's five significant defects were "
  "leakage or data-integrity issues found by suspicion rather than by a test. "
  "That is the pattern to fix in 2026.", issue="DRG-76"),
M(GEN, "2025-12-19 16:40:00", G,
  "Which is an argument for a dedicated QA role. Raising it as a resourcing "
  "item rather than something we absorb.", thread="2025-12-19 16:30:00",
  issue="DRG-76", reactions=":+1: 3"),
M(GEN, "2026-01-05 09:35:00", S,
  "Raised with the resourcing group. Noting it here so we can see how long it "
  "takes.", thread="2025-12-19 16:30:00"),

# ================================================================= Jan 2026
M(MOD, "2026-01-07 10:35:00", D,
  "Re-aggregating from households is the whole point of DRG-79. Two "
  "households with an EV and a heat pump do not both plug in at 18:00, and "
  "only a bottom-up model can express that.", issue="DRG-79"),

M(MOD, "2026-01-13 10:25:00", G,
  "The combined EV and heat pump scenario comes out almost exactly equal to "
  "the sum of the two applied separately. Physical systems very rarely add "
  "exactly, and when they do it usually means the model has lost the thing "
  "that would have made them not add.", issue="DRG-80", reactions=":eyes: 3"),
M(MOD, "2026-01-15 11:35:00", D,
  "Confirmed - the household profiles are being aggregated twice, and the "
  "second aggregation destroys the time offsets between households. Fixing so "
  "aggregation happens exactly once, at the end.",
  thread="2026-01-13 10:25:00", issue="DRG-80"),
M(MOD, "2026-01-19 09:50:00", G,
  "Adding an assertion that the combined peak is strictly below the sum of "
  "the individual peaks. That encodes a physical fact rather than a code "
  "expectation - if it ever fails, either the model is wrong or something "
  "genuinely surprising is happening.", thread="2026-01-13 10:25:00",
  issue="DRG-80", reactions=":100: 3"),
M(MOD, "2026-01-22 15:10:00", D,
  "Fixed. EV alone at 80% gives +154%, heat pumps alone at 70% give +113%, "
  "together +237% rather than +267%. The 29 point gap is diversity.",
  thread="2026-01-13 10:25:00", issue="DRG-80", reactions=":tada: 3"),
M(GEN, "2026-01-22 15:30:00", G,
  "And that gap is the finding, not a caveat. It is the most "
  "planning-relevant thing we have produced - the two loads peak at "
  "overlapping but not identical times, so naive addition overstates the "
  "problem by a quarter.", issue="DRG-80", reactions=":100: 3"),

M(GEN, "2026-01-16 15:15:00", S,
  "New risk on the board: we are about to spend two quarters building a "
  "dashboard for a user we have described rather than met. That pattern ends "
  "with a beautiful tool nobody opens.", issue="DRG-83", reactions=":eyes: 2"),
M(GEN, "2026-01-19 10:25:00", G,
  "Agreed. Mitigation: get a network planner in front of the scenario results "
  "before the dashboard design is fixed, even if what we show them is a "
  "notebook.", thread="2026-01-16 15:15:00", issue="DRG-83"),

# ============================================================= Feb-Mar 2026
M(MOD, "2026-02-13 15:50:00", D,
  "Stress under scenarios, thresholds held at the historical P95: base 4.4% "
  "of half-hours, rising to 46.8% at the highest adoption. Roughly ten times "
  "more often, with mean event duration going from 2.2 to 6.9 hours.",
  issue="DRG-82", reactions=":eyes: 3"),
M(MOD, "2026-02-16 09:35:00", G,
  "The duration change may matter more to an operator than the frequency. Two "
  "hours is manageable; seven covers the whole evening peak and leaves no "
  "recovery window.", thread="2026-02-13 15:50:00", issue="DRG-82"),
M(MOD, "2026-01-28 09:55:00", G,
  "Holding the threshold at the historical value is the crux of DRG-82. "
  "Recomputing P95 under each scenario would define stress away - the top 5% "
  "is always 5% - and produce the reassuring answer that nothing changes.",
  issue="DRG-82", reactions=":100: 2"),

M(ENG, "2026-02-18 10:35:00", V,
  "Replay is the only way to test the operational path without waiting for "
  "real time to pass. It has to be deterministic or it is a demo rather than "
  "a test.", issue="DRG-85"),
M(ENG, "2026-02-27 10:25:00", D,
  "Two replays of the same day disagree on when a stress event ended. One "
  "period, which is exactly the size that gets dismissed as noise.",
  issue="DRG-87"),
M(ENG, "2026-03-02 09:45:00", V,
  "Wall clock had leaked into the window logic - a slow step let a window "
  "advance further than it should have. Same lesson as the training leakage "
  "bugs in a different costume: something that should be derived from the "
  "data was derived from the environment.", thread="2026-02-27 10:25:00",
  issue="DRG-87", reactions=":100: 2"),
M(ENG, "2026-03-18 11:25:00", V,
  "Three-level fallback on external feeds with provenance recorded: live, "
  "then cache, then documented default. A cached value silently substituted "
  "for a live one is how a demo shows yesterday's weather as if it were "
  "today's.", issue="DRG-88"),

M(GEN, "2026-03-24 14:20:00", S,
  "Knowledge concentration risk closed rather than watched. Both critical "
  "stages now have handover notes, and both were acceptance-tested by the "
  "other analyst running the stage from the document without asking "
  "anything.", issue="DRG-89", reactions=":+1: 3"),

# ============================================================= Apr-May 2026
M(MOD, "2026-03-25 10:25:00", G,
  "Sweeping the stress percentile itself in DRG-90. If the entire finding "
  "changes between P90 and P95 then the finding is about our choice of "
  "percentile rather than about electrification.", issue="DRG-90"),
M(MOD, "2026-04-14 11:20:00", G,
  "Sensitivity result: adoption rate dominates everything else by a wide "
  "margin. Charger power and COP matter within plausible ranges but do not "
  "change direction or order of magnitude. The percentile shifts absolute "
  "numbers without changing the ratio between scenarios.", issue="DRG-91",
  reactions=":100: 2"),
M(MOD, "2026-04-24 14:30:00", G,
  "Which means saying plainly that we do not forecast adoption. DRG tells you "
  "what happens if adoption reaches a level; it does not tell you whether it "
  "will, and conflating those is how a scenario tool gets quoted as a "
  "prediction.", issue="DRG-92", reactions=":100: 3"),

M(MOD, "2026-05-05 10:35:00", G,
  "SHAP global drivers: lag_336 at 39%, lag_1 at 27%, lag_48 at 7.6%, time of "
  "day at 4%. That matches the autocorrelation analysis from March last year, "
  "which is a satisfying consistency check across two completely independent "
  "methods.", issue="DRG-93", reactions=":tada: 2"),
M(MOD, "2026-05-11 10:25:00", D,
  "The SHAP ranking disagrees with the XGBoost feature importances on "
  "temperature. DRG-93 said explicitly that a disagreement is worth "
  "investigating, so flagging it.", issue="DRG-95"),
M(MOD, "2026-05-11 10:50:00", G,
  "Explanations are computed on the standardised matrix and labelled with raw "
  "feature names, so contributions are not comparable across features with "
  "different original scales. Temperature looks negligible and it is not.",
  thread="2026-05-11 10:25:00", issue="DRG-95", reactions=":eyes: 2"),
M(MOD, "2026-05-20 14:40:00", G,
  "Fixed by reporting shares of total absolute attribution rather than raw "
  "contributions. Scale-free, comparable across features, and comparable "
  "between models later.", thread="2026-05-11 10:25:00", issue="DRG-95"),
M(MOD, "2026-05-13 11:25:00", G,
  "Stress-period SHAP: same drivers, but the lags take a larger share. "
  "lag_336 holds at 39%, lag_1 rises to 29%, lag_48 to 10.7%, time of day "
  "falls. High-demand half-hours are more strongly recurrent than ordinary "
  "ones.", issue="DRG-94"),
M(MOD, "2026-05-15 15:30:00", D,
  "Which gives us the useful operational sentence: the stressful periods are "
  "the predictable ones. That is what makes them manageable rather than "
  "merely alarming.", thread="2026-05-13 11:25:00", issue="DRG-94",
  reactions=":100: 3"),

M(ENG, "2026-04-29 10:20:00", D,
  "Chart theme before the first chart. Fixed colour per neighbourhood across "
  "all pages - four sites across six pages, and if the colours shuffle the "
  "reader relearns the legend every time.", issue="DRG-96"),
M(ENG, "2026-05-14 11:35:00", G,
  "The 'real or synthetic' badge on every page is not optional. Someone will "
  "screenshot a synthetic run into a planning document otherwise, and the "
  "numbers are plausible enough that nobody would catch it.",
  thread="2026-04-29 10:20:00", issue="DRG-96", reactions=":100: 3"),

# ================================================================= Jun 2026
M(GEN, "2026-06-01 09:45:00", S,
  "Neha Chauhan joins as QA analyst on Monday 15 June. Six months after we "
  "raised it at the year-end review - recording the delay because the cost is "
  "visible: five of the defects since January were silent.", issue="DRG-98",
  reactions=":wave: 4"),
M(GEN, "2026-06-12 15:20:00", V,
  "Runbook dry-run from a clean machine. run-all from a fresh clone works "
  "with no dataset and no keys, which is the DRG-23 decision paying off "
  "eighteen months later.", thread="2026-06-01 09:45:00", issue="DRG-98",
  reactions=":+1: 3"),

M(GEN, "2026-06-15 09:40:00", N,
  "Morning all - Neha, first day. Thanks for the runbook. Starting by "
  "building and running the pipeline before I form any opinions.",
  reactions=":wave: 4"),
M(GEN, "2026-06-16 11:25:00", N,
  "run-all worked first time from the runbook, on synthetic data, with no "
  "credentials. That is rarer than it should be and it made day one useful "
  "rather than administrative.", issue="DRG-99", reactions=":tada: 3"),
M(MOD, "2026-06-19 14:35:00", N,
  "Read the modelling notes. Of the eight significant defects on this "
  "project, seven produced a plausible wrong number rather than a failure. "
  "That shapes what I should test: agreement between stages, not behaviour of "
  "functions.", issue="DRG-99", reactions=":100: 3"),
M(MOD, "2026-06-26 15:55:00", N,
  "Gap analysis done. No coverage at all on the simulation, the API contract, "
  "or anything checking that a model artefact matches the feature spec it "
  "claims. The third is the quiet one - the check exists but nothing tests "
  "that it fires.", issue="DRG-99", reactions=":eyes: 3"),
M(MOD, "2026-06-26 16:15:00", G,
  "That last point is exactly the kind of thing we could not see from inside. "
  "Raising it into the gate work.", thread="2026-06-26 15:55:00",
  issue="DRG-106"),
M(MOD, "2026-06-30 10:25:00", N,
  "Turning the three leakage incidents into one standing rule with a test "
  "each: anything estimated from data is fitted on train only. It was already "
  "written in the notes as a rule - it just was not enforced anywhere.",
  issue="DRG-100", reactions=":100: 3"),
M(MOD, "2026-07-03 15:40:00", G,
  "Which is the difference between a lesson and a control. We wrote the rule "
  "down in November and still had to remember it.",
  thread="2026-06-30 10:25:00", issue="DRG-100"),

M(ENG, "2026-06-10 10:35:00", V,
  "Readiness separate from health on the API. A container that is up but has "
  "no model loaded should not receive traffic, and conflating the two is how "
  "you serve 500s to a load balancer that thinks everything is fine.",
  issue="DRG-101"),
M(ENG, "2026-06-24 11:20:00", N,
  "Reviewed the API contract before the implementation was finished, which "
  "was the right order. Asked for the error shape to be specified too - a "
  "documented success response and an undocumented failure response is half a "
  "contract.", issue="DRG-101", reactions=":+1: 2"),

# ================================================================= Jul 2026
M(ENG, "2026-07-06 11:25:00", N,
  "The forecast endpoint returns values with no model version, despite the "
  "OpenAPI schema promising one. The schema and the responses disagreeing is "
  "the actual defect.", issue="DRG-103"),
M(ENG, "2026-07-09 09:55:00", V,
  "Fair, and a contract test across every route is the right fix. Doing it "
  "endpoint by endpoint would leave the next endpoint to remember.",
  thread="2026-07-06 11:25:00", issue="DRG-103", reactions=":+1: 2"),

M(MOD, "2026-07-08 10:25:00", G,
  "Stress F1 in the promotion gate with zero tolerance, unlike MAE which gets "
  "a small one. The whole platform exists to detect stress, and trading that "
  "away for average error is precisely the trade we must not make silently.",
  issue="DRG-106", reactions=":100: 3"),
M(MOD, "2026-07-20 11:35:00", N,
  "Feature-spec check is in the gate - the artefact declares its features and "
  "the gate asserts the serving path supplies exactly those. It caught a "
  "column ordering difference on the first run.", issue="DRG-106",
  reactions=":eyes: 2"),

M(MOD, "2026-07-27 10:25:00", V,
  "The scheduled retrain produced a model at 0.68 MAE against the incumbent's "
  "0.70, and the gate blocked it. Stress F1 came in at 0.87 against 0.90.",
  issue="DRG-107", reactions=":eyes: 3"),
M(MOD, "2026-07-29 09:45:00", G,
  "That is the gate working, not failing. It improved on the quiet half-hours "
  "which are the bulk of the data, and got worse at the peaks which are the "
  "point. A single headline metric would have promoted it and nobody would "
  "have noticed until an event was missed.", thread="2026-07-27 10:25:00",
  issue="DRG-107", reactions=":100: 4"),
M(MOD, "2026-08-05 11:20:00", N,
  "Adding a regression test that constructs exactly this case - better MAE, "
  "worse F1 - and asserts the gate refuses it. Otherwise a future refactor "
  "could relax the gate and nothing would catch it.",
  thread="2026-07-27 10:25:00", issue="DRG-107", reactions=":+1: 3"),
M(MOD, "2026-08-07 15:10:00", G,
  "Retrain window reweighted toward recent peak periods and the next "
  "candidate passed both criteria. Keeping DRG-107 linked from the MLOps epic "
  "as the worked example.", thread="2026-07-27 10:25:00", issue="DRG-107"),

M(ENG, "2026-07-21 11:20:00", N,
  "Switching neighbourhood in the dashboard updates the title and the "
  "threshold line but not the demand series until you reload. Two of the four "
  "sites have similar magnitudes, so on those it is undetectable by eye.",
  issue="DRG-110", reactions=":eyes: 2"),
M(ENG, "2026-07-23 09:50:00", D,
  "Cache key was on date range only, so a neighbourhood change was a cache "
  "hit. Same class of defect as the API missing its version field - the "
  "identity of the thing was incomplete.", thread="2026-07-21 11:20:00",
  issue="DRG-110"),

M(REL, "2026-07-31 16:20:00", V,
  "CI now runs the full pipeline on synthetic data on every push, about seven "
  "minutes. Closing DRG-14 - eighteen months of engineering practice work, "
  "and the run-all decision from week three is still paying for itself.",
  issue="DRG-14", reactions=":tada: 3"),

# ============================================================= Aug-Sep 2026
M(ENG, "2026-07-30 10:35:00", V,
  "Bicep over Terraform for DRG-111, specifically because of the ML "
  "workspace. First-party templates for AML are better maintained, and this "
  "estate is entirely Azure so the portability argument does not apply.",
  issue="DRG-111"),
M(ENG, "2026-08-12 11:25:00", V,
  "Managed identity throughout rather than connection strings. No connection "
  "strings in configuration means none to leak, and it removes the rotation "
  "problem entirely.", issue="DRG-111", reactions=":+1: 2"),
M(GEN, "2026-08-14 15:40:00", S,
  "Infrastructure deploys clean into the non-production subscription. The "
  "shared environment risk from January is closed - twenty months on laptops "
  "is finally over.", issue="DRG-111", reactions=":tada: 4"),
M(ENG, "2026-08-19 10:45:00", V,
  "Same code path locally and in AML. A separate cloud training script is how "
  "the two silently diverge and the cloud model stops matching what was "
  "validated.", issue="DRG-112"),
M(ENG, "2026-08-26 11:20:00", V,
  "The scoring path shares feature construction with training rather than "
  "reimplementing it. Training-serving skew from two copies of the same logic "
  "is the classic way a deployed model quietly stops matching its "
  "evaluation.", issue="DRG-113", reactions=":100: 2"),

M(GEN, "2026-08-17 11:15:00", S,
  "Amit Shinde joins as BA on Monday 24 August. DRG-18 is cut already so "
  "there is a real backlog on day one. For twenty months Geetha and I carried "
  "the stakeholder relationship between us, and that stopped scaling once "
  "three groups wanted different cuts of the same results.", issue="DRG-18",
  reactions=":wave: 4"),

M(GEN, "2026-08-24 09:40:00", A,
  "Hello all - Amit, first day. Starting with the objectives table in the "
  "README, which maps each proposal objective to the module that answers it. "
  "That is an unusually good front door.", reactions=":wave: 5"),
M(STK, "2026-08-28 11:35:00", A,
  "Halfway through the stakeholder conversations. The theme is not doubt "
  "about the numbers - it is that different groups want different cuts. "
  "Planners want per-substation, sustainability wants carbon, the academic "
  "partner wants the method. One dashboard is currently trying to be all "
  "three.", issue="DRG-115", reactions=":eyes: 3"),
M(GEN, "2026-09-04 15:40:00", A,
  "Gap list done. Nine items: four already answered by something they had not "
  "seen, three genuine gaps, and two out of scope by design - power flow and "
  "adoption forecasting - which need saying clearly rather than being left "
  "open.", issue="DRG-115", reactions=":+1: 3"),
M(GEN, "2026-09-04 16:05:00", G,
  "Those last two are exactly the non-goals from DRG-31, twenty months ago. "
  "Good to have them confirmed as live stakeholder expectations rather than "
  "hypothetical ones.", thread="2026-09-04 15:40:00", issue="DRG-127"),

M(MOD, "2026-09-02 10:25:00", N,
  "The combined-below-additive assertion is the one I care most about in the "
  "simulation pack. It encodes a physical fact rather than a coding "
  "expectation - if it ever fails, something real has changed.",
  issue="DRG-120", reactions=":100: 2"),

M(STD, "2026-09-08 09:20:00", S,
  "Standup. Sprint 44, day seven. Reminder that the October steering agenda "
  "needs the monitoring ownership decision - DRG-124 is blocked on a rota, "
  "not on work.", issue="DRG-124"),
M(STD, "2026-09-08 09:22:00", G,
  "Yesterday: reviewing the operator runbook wording. Today: same, plus the "
  "stress explanation panel. No blockers.", issue="DRG-125"),
M(STD, "2026-09-08 09:24:00", D,
  "Yesterday: replay page polish. Today: starting the sensitivity page, which "
  "Amit's traceability work surfaced as the one requirement with a test and "
  "no view.", issue="DRG-122"),
M(STD, "2026-09-08 09:26:00", V,
  "Yesterday: endpoint scores against the sample request. Today: the "
  "verification script, then the traffic shift. Scheduled retrain is running "
  "nightly and the gate is deciding.", issue="DRG-113"),
M(STD, "2026-09-08 09:28:00", N,
  "Yesterday: sampling, determinism and threshold stability assertions all "
  "green. Today: ADMD range checks, then UAT scenarios.", issue="DRG-120"),
M(STD, "2026-09-08 09:30:00", A,
  "Yesterday: BRD refresh, two thirds through. Today: traceability - "
  "twenty-one of twenty-six traced. Blocked on nothing.", issue="DRG-119"),

M(GEN, "2026-09-08 11:30:00", S,
  "Twenty months in. 43 sprints, six people, three of whom joined mid-flight. "
  "The thing I would keep if we started again is spending the first quarter "
  "on data quality with nothing to show for it.", reactions=":100: 4"),
M(GEN, "2026-09-08 11:40:00", G,
  "And publishing the naive baseline in every table. It is the reason we can "
  "say the model is worth deploying rather than merely that it scores well.",
  thread="2026-09-08 11:30:00", reactions=":100: 3"),
M(GEN, "2026-09-08 11:48:00", N,
  "From three months in: nearly every defect here has been a plausible wrong "
  "number rather than a crash. Nine of them. That changed how I test - "
  "assertions between stages rather than more unit tests.",
  thread="2026-09-08 11:30:00", reactions=":100: 3"),
M(GEN, "2026-09-08 11:55:00", A,
  "From two weeks in: the platform's problem is no longer credibility, it is "
  "that three audiences want three different products from it. That is a much "
  "better problem than the reverse.", thread="2026-09-08 11:30:00",
  issue="DRG-118", reactions=":+1: 3"),
M(GEN, "2026-09-09 11:20:00", D,
  "One more for that list: the diversity result. Nobody asked for it, it came "
  "out of a bug that made the numbers look too round, and it is arguably the "
  "most planning-relevant thing we have produced.", issue="DRG-80",
  reactions=":100: 4"),

M(STK, "2026-09-09 14:30:00", S,
  "September report is out. Headlines: XGBoost at 0.70 MAE against an "
  "operational baseline of 1.54; peak amplification of +237% at the highest "
  "electrification scenario, which is 29 points below naive addition because "
  "the two loads do not peak together; and stress rising from 4.4% to 46.8% "
  "of half-hours with mean event duration going from 2.2 to 6.9 hours.",
  reactions=":tada: 4 :chart_with_upwards_trend: 2"),

]
