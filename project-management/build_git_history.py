# -*- coding: utf-8 -*-
"""Build the DRG git history: main, development and one branch per ticket.

What this does
--------------
Reconstructs the repository as it would have been built, 02 Jan 2025 - 09 Sep
2026, from the Jira backlog in this folder:

  main                        release branch - takes a merge of development
                              at the end of every sprint that delivered work
  development                 integration branch
  drg/DRG-nn-<slug>           one working branch per ticket, KEPT after merge

Every working branch is cut from development, carries one or more commits by
the ticket's assignee, takes a merge of development back in when development
has moved on underneath it, and is then merged into development with a merge
commit. No branch is deleted.

Stories that extend a file written by an earlier ticket, and bugs that fix
one, carry real diffs: the earlier ticket commits the file as it was before
the later change (REVISIONS below), and the later ticket commits the change.

How
---
Commits are written with git plumbing (hash-object / write-tree /
commit-tree) straight from the objects of the current `main` commit. Nothing
is checked out, so the working tree, line endings and Windows file locks never
come into it.

Safety
------
* Nothing is pushed. `origin` is not contacted.
* The original `main` is kept as the tag `pre-history-snapshot` the first time
  the script runs.
* The final trees of `development` and `main` are asserted identical to the
  source `main` tree, so no file is lost, added or altered.
* Every commit falls Monday-Friday 09:00-17:00 UK time, inside the project,
  and never before its author joined.

Re-running replaces `development`, every `drg/*` branch and `main`, so it
refuses unless --force is given.

Usage
-----
    python project-management/build_git_history.py --dry-run
    python project-management/build_git_history.py
    python project-management/build_git_history.py --force
"""

import argparse
import datetime as dt
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)

from backlog_common import JOINED, PEOPLE, PROJECT_START, sprint_bounds  # noqa: E402
from data_issues import ISSUES  # noqa: E402

BASE_BRANCH = "main"
DEV_BRANCH = "development"
BRANCH_PREFIX = "drg/"
SNAPSHOT_TAG = "pre-history-snapshot"
DOMAIN = "futuristictechnologies.co.uk"
RELEASE_MANAGER = "devendranath.singam"
LAST_DAY = dt.datetime(2026, 9, 9, 16, 30)          # "today" in the Jira export

ISSUE = {i["key"]: i for i in ISSUES}


# ==========================================================================
# what each ticket delivers
#
# (ticket, [(commit subject, [paths])]).  Ordered as the work was merged.
# A path appears in more than one ticket only when REVISIONS says what it
# looked like before the later ticket changed it; the build asserts that.
# ==========================================================================

PM = "project-management/"

PLAN = [
 # ---- 2025 --------------------------------------------------------------
 ("DRG-19", [
    ("Add the team roster, sprint calendar and inception epics",
     [PM + "backlog_common.py", PM + "backlog_epics.py"]),
 ]),
 ("DRG-20", [
    ("Add repository scaffold, packaging and ignore rules",
     [".gitignore", "pyproject.toml", "src/drg/__init__.py"]),
    ("Add the project README", ["README.md"]),
 ]),
 ("DRG-21", [
    ("Split dependencies into core, deep, azure and dev tiers",
     ["requirements.txt", "requirements-deep.txt", "requirements-azure.txt",
      "requirements-dev.txt"]),
 ]),
 ("DRG-22", [
    ("Add the Low Carbon London chunked loader and neighbourhood aggregation",
     ["src/drg/data/lcl_loader.py"]),
 ]),
 ("DRG-24", [
    ("Add the calibrated synthetic smart-meter generator",
     ["src/drg/data/synthetic.py"]),
 ]),
 ("DRG-26", [
    ("Add the YAML configuration and the typed config loader",
     ["configs/config.yaml", "src/drg/config.py"]),
    ("Add IO and logging utilities",
     ["src/drg/utils/__init__.py", "src/drg/utils/io.py",
      "src/drg/utils/logging_utils.py"]),
 ]),
 ("DRG-27", [
    ("Drop the repeated autumn hour before regularising the half-hourly grid",
     ["src/drg/data/lcl_loader.py"]),
 ]),
 ("DRG-25", [
    ("Add the pipeline stage runner", ["src/drg/pipeline.py"]),
    ("Add the Typer CLI with run-all", ["src/drg/cli.py"]),
 ]),
 ("DRG-28", [
    ("Lay out the raw, interim, processed and external data contract",
     ["data/raw/.gitkeep", "data/interim/.gitkeep", "data/processed/.gitkeep",
      "data/external/.gitkeep"]),
 ]),
 ("DRG-30", [
    ("Add CI: lint and tests on every push", [".github/workflows/ci.yml"]),
 ]),
 ("DRG-31", [
    ("Write the architecture document, non-goals first", ["docs/ARCHITECTURE.md"]),
 ]),
 ("DRG-32", [
    ("Add daily and weekly load shape profiling", ["src/drg/analysis/eda.py"]),
 ]),
 ("DRG-35", [
    ("Add offline test fixtures built on the synthetic generator",
     ["tests/conftest.py"]),
    ("Add data generation, cleaning and column resolution checks",
     ["tests/test_data.py"]),
 ]),
 ("DRG-36", [
    ("Add the seasonal profile and winter amplification", ["src/drg/analysis/eda.py"]),
 ]),
 ("DRG-37", [
    ("Interpolate short gaps only and leave long gaps missing",
     ["src/drg/data/lcl_loader.py"]),
 ]),
 ("DRG-38", [
    ("Add container images for the pipeline, API and dashboard",
     ["docker/Dockerfile.pipeline", "docker/Dockerfile.api",
      "docker/Dockerfile.dashboard", ".dockerignore"]),
    ("Add docker-compose for the local stack", ["docker-compose.yml"]),
 ]),
 ("DRG-39", [
    ("Add the EDA run with the figure set and summary report",
     ["src/drg/analysis/eda.py", "artifacts/figures/.gitkeep",
      "artifacts/reports/.gitkeep"]),
 ]),
 ("DRG-41", [
    ("Add the key-free weather client with an offline fallback",
     ["src/drg/data/external_apis.py", ".env.example"]),
 ]),
 ("DRG-42", [
    ("Add calendar and cyclical time features",
     ["src/drg/features/engineering.py"]),
 ]),
 ("DRG-44", [
    ("Add the chronological train, validation and test split",
     ["src/drg/features/engineering.py"]),
 ]),
 ("DRG-43", [
    ("Add lag features at 1, 48 and 336 half-hours",
     ["src/drg/features/engineering.py"]),
 ]),
 ("DRG-47", [
    ("Configure ruff and black in pyproject", ["pyproject.toml"]),
 ]),
 ("DRG-45", [
    ("Add rolling mean, std, min and max features",
     ["src/drg/features/engineering.py"]),
 ]),
 ("DRG-46", [
    ("Build rolling windows from trailing values only",
     ["src/drg/features/engineering.py"]),
 ]),
 ("DRG-48", [
    ("Add temperature, degree-day and carbon features",
     ["src/drg/features/engineering.py"]),
    ("Export the feature API from the package", ["src/drg/features/__init__.py"]),
 ]),
 ("DRG-52", [
    ("Add the seasonal naive baseline", ["src/drg/models/baseline.py"]),
 ]),
 ("DRG-53", [
    ("Label the naive baseline as same half-hour yesterday",
     ["src/drg/models/baseline.py"]),
 ]),
 ("DRG-54", [
    ("Add the Linear and Ridge baselines", ["src/drg/models/baseline.py"]),
 ]),
 ("DRG-55", [
    ("Add the evaluation harness with peak and stress-alarm metrics",
     ["src/drg/models/evaluate.py"]),
 ]),
 ("DRG-56", [
    ("Guard MAPE against near-zero demand half-hours",
     ["src/drg/models/evaluate.py"]),
 ]),
 ("DRG-58", [
    ("Fit the scaler inside the pipeline, on the training window only",
     ["src/drg/models/baseline.py"]),
 ]),
 ("DRG-59", [
    ("Add the XGBoost forecaster", ["src/drg/models/gbm.py"]),
 ]),
 ("DRG-61", [
    ("Add rolling-origin cross-validation", ["src/drg/models/gbm.py"]),
 ]),
 ("DRG-62", [
    ("Train the model ladder and write the comparison report",
     ["src/drg/models/train.py"]),
 ]),
 ("DRG-63", [
    ("Persist model artefacts with their metadata",
     ["src/drg/models/registry.py", "src/drg/models/__init__.py",
      "artifacts/models/.gitkeep"]),
 ]),
 ("DRG-64", [
    ("Add the PyTorch LSTM and GRU sequence models", ["src/drg/models/deep.py"]),
 ]),
 ("DRG-65", [
    ("Fall back cleanly when torch cannot load its DLLs", ["src/drg/models/deep.py"]),
    ("Document the MSVC runtime prerequisite for the deep tier",
     ["README.md", "scripts/setup_local.ps1"]),
 ]),
 ("DRG-66", [
    ("Add the torch-free sequence MLP fallback", ["src/drg/models/deep.py"]),
 ]),
 ("DRG-68", [
    ("Add per-neighbourhood percentile stress thresholds",
     ["src/drg/stress/detection.py"]),
 ]),
 ("DRG-69", [
    ("Compute the stress threshold on the training window only",
     ["src/drg/models/train.py"]),
 ]),
 ("DRG-70", [
    ("Detect stress events with a minimum duration", ["src/drg/stress/detection.py"]),
 ]),
 ("DRG-71", [
    ("Add stress frequency, duration, seasonal and diurnal metrics",
     ["src/drg/stress/detection.py", "src/drg/stress/__init__.py"]),
 ]),
 ("DRG-73", [
    ("Add per-household EV adoption and charging simulation",
     ["src/drg/simulation/electrification.py"]),
 ]),
 ("DRG-77", [
    ("Document deployment options with a costed recommendation", ["docs/AZURE.md"]),
 ]),
 ("DRG-76", [
    ("Record the 2025 backlog for the year-end report", [PM + "backlog_year1.py"]),
 ]),
 ("DRG-75", [
    ("Add temperature-driven heat pump profiles",
     ["src/drg/simulation/electrification.py"]),
 ]),
 # ---- 2026 --------------------------------------------------------------
 ("DRG-79", [
    ("Add the combined EV and heat pump scenario engine",
     ["src/drg/simulation/electrification.py", "src/drg/simulation/__init__.py"]),
 ]),
 ("DRG-80", [
    ("Take the combined peak from the aggregated profile, not the sum of peaks",
     ["src/drg/simulation/electrification.py"]),
 ]),
 ("DRG-85", [
    ("Add the near-real-time replay engine",
     ["src/drg/streaming/replay.py", "src/drg/streaming/__init__.py"]),
 ]),
 ("DRG-86", [
    ("Add the carbon intensity client with a climatology fallback",
     ["src/drg/data/external_apis.py"]),
 ]),
 ("DRG-87", [
    ("Derive replay timestamps from event time, not the wall clock",
     ["src/drg/streaming/replay.py"]),
 ]),
 ("DRG-88", [
    ("Add the combined live context snapshot with degraded-feed reporting",
     ["src/drg/data/external_apis.py"]),
    ("Export the data clients from the package", ["src/drg/data/__init__.py"]),
 ]),
 ("DRG-89", [
    ("Add the end-to-end walkthrough notebook", ["notebooks/01_drg_walkthrough.ipynb"]),
 ]),
 ("DRG-90", [
    ("Add the adoption sensitivity sweep and elasticity curves",
     ["src/drg/analysis/sensitivity.py", "src/drg/analysis/__init__.py"]),
 ]),
 ("DRG-93", [
    ("Add SHAP global and stress-period explanations",
     ["src/drg/explain/shap_explain.py", "src/drg/explain/__init__.py"]),
 ]),
 ("DRG-96", [
    ("Add the dashboard shell and the chart theme",
     ["src/drg/dashboard/__init__.py", "src/drg/dashboard/app.py",
      "src/drg/dashboard/theme.py", ".streamlit/config.toml"]),
 ]),
 ("DRG-95", [
    ("Report SHAP attribution as a share of the total", ["src/drg/explain/shap_explain.py"]),
 ]),
 ("DRG-97", [
    ("Add the live forecast and stress profile panels", ["src/drg/dashboard/app.py"]),
 ]),
 ("DRG-98", [
    ("Add the team conversation history to the QA onboarding pack",
     [PM + "data_slack.py", PM + "data_slack_extra.py"]),
 ]),
 ("DRG-101", [
    ("Add the FastAPI service and the forecast endpoint",
     ["src/drg/api/__init__.py", "src/drg/api/main.py"]),
 ]),
 ("DRG-104", [
    ("Add the scenario studio and sensitivity panels", ["src/drg/dashboard/app.py"]),
 ]),
 ("DRG-102", [
    ("Add the stress, scenario, sensitivity and explanation endpoints",
     ["src/drg/api/main.py"]),
 ]),
 ("DRG-103", [
    ("Return the version on the health response", ["src/drg/api/main.py"]),
    ("Add replay, feed and API contract tests", ["tests/test_streaming_and_api.py"]),
 ]),
 ("DRG-105", [
    ("Generate the model spec for registry registration",
     ["pipelines/make_model_spec.py"]),
 ]),
 ("DRG-106", [
    ("Add the promotion gate", ["src/drg/mlops/gate.py", "src/drg/mlops/__init__.py"]),
    ("Add the promotion CLI used by the release workflow",
     ["pipelines/promote_model.py"]),
 ]),
 ("DRG-109", [
    ("Add the data and feature regression pack",
     ["tests/test_features_and_models.py"]),
 ]),
 ("DRG-110", [
    ("Key the site series on the selected neighbourhood", ["src/drg/dashboard/app.py"]),
    ("Add dashboard smoke tests", ["tests/test_dashboard.py"]),
 ]),
 ("DRG-108", [
    ("Add the SHAP explanation panel", ["src/drg/dashboard/app.py"]),
 ]),
 ("DRG-111", [
    ("Add the Bicep root template", ["infra/azure/main.bicep"]),
    ("Add the storage, registry, key vault and monitoring modules",
     ["infra/azure/modules/storage.bicep", "infra/azure/modules/registry.bicep",
      "infra/azure/modules/keyvault.bicep", "infra/azure/modules/monitoring.bicep"]),
    ("Add the Container Apps and Azure ML workspace modules",
     ["infra/azure/modules/containerapps.bicep",
      "infra/azure/modules/machinelearning.bicep"]),
    ("Add the deployment scripts and the infrastructure workflow",
     ["scripts/deploy_azure.sh", "scripts/deploy_azure.ps1",
      ".github/workflows/deploy-azure.yml"]),
 ]),
 ("DRG-112", [
    ("Add the Azure ML training job and environment",
     ["infra/aml/train-job.yml", "infra/aml/environment.yml",
      "pipelines/run_azureml.py"]),
 ]),
 ("DRG-116", [
    ("Add the promotion gate and endpoint regression pack", ["tests/test_mlops.py"]),
 ]),
 ("DRG-114", [
    ("Size the environment parameters for the cost pass",
     ["infra/azure/main.parameters.json"]),
 ]),
 ("DRG-113", [
    ("Add the managed online endpoint and deployment definitions",
     ["infra/aml/endpoint.yml", "infra/aml/deployment.yml",
      "infra/aml/sample-request.json"]),
    ("Add the scoring script and the endpoint smoke test",
     ["pipelines/score.py", "pipelines/verify_endpoint.py"]),
 ]),
 ("DRG-118", [
    ("Refresh the business requirements document",
     ["docs/design/DRG_Business_Requirements.html",
      "docs/design/DRG_Business_Requirements.pdf"]),
    ("Refresh the architecture design document",
     ["docs/design/DRG_Architecture_Design.html",
      "docs/design/DRG_Architecture_Design.pdf", "docs/design/README.md"]),
 ]),
 ("DRG-120", [
    ("Add the stress, simulation and sensitivity regression pack",
     ["tests/test_stress_and_simulation.py"]),
 ]),
 ("DRG-123", [
    ("Add the weekly retrain, gate and deploy workflow",
     [".github/workflows/model-deploy.yml"]),
    ("Add workflow contract tests", ["tests/test_workflows.py"]),
 ]),
 ("DRG-119", [
    ("Add the backlog, traceability and history generators",
     [PM + "README.md", PM + "backlog_year2.py", PM + "data_issues.py",
      PM + "build_jira_csv.py", PM + "build_git_history.py"]),
    ("Add the generated Jira and Slack exports",
     [PM + "drg_jira_issues.csv", PM + "drg_jira_comments.csv",
      PM + "drg_slack_messages.csv", PM + "drg_slack_import.csv",
      PM + "drg_slack_import_eng.csv", PM + "drg_slack_import_general.csv",
      PM + "drg_slack_import_modelling.csv", PM + "drg_slack_import_releases.csv",
      PM + "drg_slack_import_stakeholders.csv", PM + "drg_slack_import_standup.csv"]),
 ]),
]

# Files not named above are swept into a final commit rather than lost.
SWEEP = ("DRG-119", "Add remaining project files")


# ==========================================================================
# revisions: what a file looked like before a later ticket changed it
#
# ticket -> [(path, [(pattern, replacement), ...])]
#
# The rules are applied to the FINAL content, newest ticket first, so the
# ticket that introduced a file commits it as it stood before every later
# change, and each later ticket commits exactly its own diff. Every pattern
# must match, or the build stops - a pattern that silently misses would turn
# a real change into an empty diff.
# ==========================================================================

LCL = "src/drg/data/lcl_loader.py"
EDA = "src/drg/analysis/eda.py"
FEAT = "src/drg/features/engineering.py"
BASE = "src/drg/models/baseline.py"
DEEP = "src/drg/models/deep.py"
STRESS = "src/drg/stress/detection.py"
SIM = "src/drg/simulation/electrification.py"
EXT = "src/drg/data/external_apis.py"
DASH = "src/drg/dashboard/app.py"
API = "src/drg/api/main.py"

SECTION = r"\n\n\n# =+\n# [^\n]*\n# =+\n"      # a "# ====" banner and its gap

REVISIONS = {
 # --- data ---------------------------------------------------------------
 # naive local time: the repeated autumn hour broke the reindex
 "DRG-27": [(LCL, [
    (r'sub = sub\.sort_values\("timestamp"\)\.drop_duplicates\("timestamp"\)',
     'sub = sub.sort_values("timestamp")'),
 ])],
 # gaps left by the reindex were forward-filled into fabricated readings
 "DRG-37": [(LCL, [
    (r'        # interpolate short gaps only; long gaps stay NaN and are dropped\n'
     r'        series = series\.interpolate\(method="time", limit=max_gap, limit_area="inside"\)',
     '        # fill the holes left by regularising the grid\n'
     '        series = series.ffill()'),
 ])],
 "DRG-86": [(EXT, [
    (r'# =+\n# Carbon intensity\n# =+\n.*?(?=# =+\n# Weather\n# =+\n)', ''),
    (r'CARBON_ARCHIVE_START = pd\.Timestamp\("2018-01-01"\)\n', ''),
 ])],
 "DRG-88": [(EXT, [
    (SECTION + r'def fetch_context_snapshot\(.*\Z', '\n'),
 ])],

 # --- analysis -----------------------------------------------------------
 "DRG-36": [(EDA, [
    (r'def seasonal_profile\(.*?(?=def peak_pattern\()', ''),
 ])],
 "DRG-39": [(EDA, [
    (r'\n\n\ndef run_eda\(.*\Z', '\n'),
 ])],

 # --- features -----------------------------------------------------------
 "DRG-43": [(FEAT, [
    (r'def add_lag_features\(.*?\n    return df\n\n\n', ''),
    (r'    df = add_lag_features\(\n.*?\n    \)\n', ''),
 ])],
 "DRG-44": [(FEAT, [
    (r'\n\n\ndef chronological_split\(.*\Z', '\n'),
 ])],
 "DRG-45": [(FEAT, [
    (r'    by_hood = grp\n    for window in rolling_windows:\n.*?'
     r'roll_min_\{window\}"\] = [^\n]*\n\n', ''),
    (r'        base = df\.get\("roll_mean_48"\)\n        if base is not None:\n'
     r'            df\["load_factor"\] = [^\n]*\n', ''),
    (r'    rolling_windows: list\[int\],\n', ''),
    (r'        rolling_windows=list\(fcfg\.get\("rolling_windows", \[6, 48, 336\]\)\),\n', ''),
    (r'"""Lags / rolling statistics, computed strictly on past values\."""',
     '"""Lag features, computed strictly on past values."""'),
 ])],
 # the window was centred, so the feature for 18:00 contained 18:00
 "DRG-46": [(FEAT, [
    (r'    shifted = grp\.shift\(1\)  # never leak the current observation\n'
     r'    by_hood = shifted\.groupby\(df\["neighbourhood_id"\], observed=True\)\n',
     '    by_hood = grp\n'),
    (r'roll = by_hood\.rolling\(window, min_periods=max\(2, window // 4\)\)',
     'roll = by_hood.rolling(window, min_periods=max(2, window // 4), center=True)'),
 ])],
 "DRG-48": [(FEAT, [
    (r'def add_exogenous_features\(.*?\n    return df\n\n\n', ''),
    (r'    if fcfg\.get\("add_weather", True\) or fcfg\.get\("add_carbon", True\):\n'
     r'        df = add_exogenous_features\(.*?\n        \)\n', ''),
    (r'\* \*\*exogenous\*\* - temperature, heating/cooling degrees and carbon intensity\.\n', ''),
 ])],

 # --- models -------------------------------------------------------------
 # the docstring promised last week while the code read yesterday
 "DRG-53": [(BASE, [
    (r'Predict the observed demand from the same half-hour one day earlier\.\n\n'
     r'    This is the operational status quo it is fair to beat, and it needs no\n'
     r'    fitting',
     'Predict the observed demand from the same half-hour one week earlier.\n\n'
     '    It needs no\n'
     '    fitting'),
 ])],
 "DRG-54": [(BASE, [
    (r'\n\n\nclass BaselineForecaster:.*\Z', '\n'),
    (r'from sklearn\.impute import SimpleImputer\n'
     r'from sklearn\.linear_model import LinearRegression, Ridge\n'
     r'from sklearn\.pipeline import Pipeline\n'
     r'from sklearn\.preprocessing import StandardScaler\n', ''),
    (r'from typing import Any\n\n', ''),
 ])],
 # the scaler sat beside the pipeline and was fitted on the whole series
 "DRG-58": [(BASE, [
    (r'        self\.pipeline = Pipeline\(\n            \[\n'
     r'                \("impute", SimpleImputer\(strategy="median"\)\),\n'
     r'                \("scale", StandardScaler\(\)\),\n',
     '        self.scaler = StandardScaler()\n'
     '        self.pipeline = Pipeline(\n            [\n'
     '                ("impute", SimpleImputer(strategy="median")),\n'),
    (r'(    def fit\(self, X: pd\.DataFrame, y: np\.ndarray\) -> "BaselineForecaster":)',
     '    def fit_scaler(self, X_all: pd.DataFrame) -> "BaselineForecaster":\n'
     '        """Standardise against the full engineered series."""\n'
     '        self.scaler.fit(X_all)\n'
     '        return self\n\n\\1'),
    (r'self\.pipeline\.fit\(X, y\)', 'self.pipeline.fit(self.scaler.transform(X), y)'),
    (r'self\.pipeline\.predict\(X\)', 'self.pipeline.predict(self.scaler.transform(X))'),
 ])],
 "DRG-56": [("src/drg/models/evaluate.py", [
    (r'def _safe_mape\(y_true: np\.ndarray, y_pred: np\.ndarray, floor: float = 1e-6\) -> float:\n'
     r'    denom = np\.maximum\(np\.abs\(y_true\), floor\)\n'
     r'    return float\(np\.mean\(np\.abs\(\(y_true - y_pred\) / denom\)\) \* 100\.0\)',
     'def _safe_mape(y_true: np.ndarray, y_pred: np.ndarray) -> float:\n'
     '    return float(np.mean(np.abs((y_true - y_pred) / y_true)) * 100.0)'),
 ])],
 "DRG-61": [("src/drg/models/gbm.py", [
    (r'\n\n\ndef rolling_origin_validate\(.*\Z', '\n'),
 ])],
 # only ImportError was caught; a DLL load failure is an OSError
 "DRG-65": [
    (DEEP, [
        (r'except Exception:  # pragma: no cover\n    torch = None',
         'except ImportError:  # pragma: no cover\n    torch = None'),
    ]),
    ("README.md", [
        (r'pip install -r requirements-deep.txt    # PyTorch LSTM  \(Windows also needs the MSVC runtime:\n'
         r' +# https://aka\.ms/vs/17/release/vc_redist\.x64\.exe\)',
         'pip install -r requirements-deep.txt    # PyTorch LSTM'),
    ]),
 ],
 "DRG-66": [(DEEP, [
    (SECTION + r'class SequenceMLPForecaster:.*\Z', '\n'),
 ])],
 # the P95 used for stress-alarm scoring was taken over train + val + test
 "DRG-69": [("src/drg/models/train.py", [
    (r'stress_threshold = _global_stress_threshold\(\n        train,',
     'stress_threshold = _global_stress_threshold(\n        features,'),
 ])],

 # --- stress and simulation ----------------------------------------------
 "DRG-70": [(STRESS, [
    (r'\n\n\ndef stress_events\(.*\Z', '\n'),
 ])],
 "DRG-71": [(STRESS, [
    (r'\n\n\ndef _season_name\(.*\Z', '\n'),
 ])],
 "DRG-75": [(SIM, [
    (SECTION + r'def _heat_pump_shape\(.*\Z', '\n'),
    (r'@dataclass\nclass HeatPumpConfig:\n.*?\n\n\n', ''),
 ])],
 "DRG-79": [(SIM, [
    (SECTION + r'def apply_scenario\(.*\Z', '\n'),
    (r'@dataclass\nclass ScenarioResult:\n.*?\n\n\n', ''),
 ])],
 # peaks were added per technology, so the combined peak lost its diversity
 "DRG-80": [(SIM, [
    (r'    new_peak = float\(out\.groupby\("neighbourhood_id"\)\["electrified_kwh"\]\.max\(\)\.mean\(\)\)',
     '    new_peak = base_peak + sum(\n'
     '        float(out.groupby("neighbourhood_id")[col].max().mean())\n'
     '        for col in ("ev_kwh", "heat_pump_kwh")\n'
     '    )'),
 ])],

 # --- streaming, explain, dashboard, API ---------------------------------
 # the forecast timestamp came from the processing clock
 "DRG-87": [("src/drg/streaming/replay.py", [
    (r'next_ts = pd\.Timestamp\(window\["timestamp"\]\.iloc\[-1\]\) \+ pd\.Timedelta\(minutes=30\)',
     'next_ts = pd.Timestamp.now().floor("30min") + pd.Timedelta(minutes=30)'),
 ])],
 # raw SHAP magnitudes were compared across features on different scales
 "DRG-95": [("src/drg/explain/shap_explain.py", [
    (r'    total = df\["mean_abs_shap"\]\.sum\(\)\n    df\["contribution_pct"\] = [^\n]*\n', ''),
 ])],
 "DRG-97": [(DASH, [
    (r'\ntab_live, tab_stress = st\.tabs\(.*\Z', ''),
 ])],
 "DRG-104": [(DASH, [
    (r'tab_live, tab_stress, tab_scenario, tab_sens = st\.tabs\(\n'
     r'    \["Live & forecast", "Stress profile", "Scenario studio", "Sensitivity"\]\n\)',
     'tab_live, tab_stress = st.tabs(\n    ["Live & forecast", "Stress profile"]\n)'),
    (SECTION + r'with tab_scenario:.*\Z', '\n'),
 ])],
 "DRG-108": [(DASH, [
    (r'tab_live, tab_stress, tab_scenario, tab_sens, tab_explain = st\.tabs\(\n'
     r'    \["Live & forecast", "Stress profile", "Scenario studio", "Sensitivity", "Explainability"\]\n\)',
     'tab_live, tab_stress, tab_scenario, tab_sens = st.tabs(\n'
     '    ["Live & forecast", "Stress profile", "Scenario studio", "Sensitivity"]\n)'),
    (SECTION + r'with tab_explain:.*\Z', '\n'),
 ])],
 # the cached series was keyed on the window only, so a site change hit the cache
 "DRG-110": [(DASH, [
    (r'site_demand = demand\[demand\["neighbourhood_id"\] == site\]\.sort_values\("timestamp"\)\n',
     '@st.cache_data(show_spinner=False)\n'
     'def site_series(days: int) -> pd.DataFrame:\n'
     '    return demand[demand["neighbourhood_id"] == site].sort_values("timestamp")\n\n\n'
     'site_demand = site_series(window_days)\n'),
 ])],
 "DRG-102": [(API, [
    (r'\n\n\n@app\.get\("/stress"\).*?(?=\n\n\n@app\.get\("/metrics"\))', ''),
    (r'# =+\n# schemas\n# =+\n.*?(?=# =+\n# endpoints)', ''),
    (r'    GET  /stress[^\n]*\n.*?    GET  /explain[^\n]*\n', ''),
 ])],
 "DRG-103": [(API, [
    (r'        "version": __version__,\n', ''),
 ])],
 "DRG-47": [("pyproject.toml", [
    (r'\n\[tool\.ruff\]\n.*\Z', ''),
 ])],
}


# ==========================================================================
# git plumbing
# ==========================================================================

def git(*args, data=None, env=None, binary=False):
    full = dict(os.environ)
    full.update(env or {})
    result = subprocess.run(["git"] + list(args), cwd=REPO, input=data,
                            capture_output=True, env=full)
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed:\n"
                           f"{result.stderr.decode('utf-8', 'replace')}")
    return result.stdout if binary else result.stdout.decode("utf-8", "replace").strip()


def source_tree(ref):
    """{path: (mode, blob sha)} for every file in `ref`."""
    out = {}
    for entry in git("ls-tree", "-r", "-z", ref, binary=True).split(b"\0"):
        if not entry:
            continue
        meta, path = entry.split(b"\t", 1)
        mode, kind, sha = meta.decode("ascii").split()
        if kind != "blob":
            raise RuntimeError(f"unsupported {kind} entry {path!r} in {ref}")
        out[path.decode("utf-8")] = (mode, sha)
    return out


def slug(text, words=5):
    parts = re.sub(r"[^a-z0-9 ]", "", text.lower()).split()
    return "-".join(parts[:words])


def sprint_number(ticket):
    match = re.match(r"Sprint (\d+)", ISSUE[ticket].get("sprint") or "")
    if not match:
        raise RuntimeError(f"{ticket} is not in a sprint")
    return int(match.group(1))


def seed_of(ticket):
    return sum(ord(c) * (i + 1) for i, c in enumerate(ticket))


# ==========================================================================
# plan validation and file versions
# ==========================================================================

def validate_plan(files):
    errors, first, planned = [], {}, {}
    revision_keys = {(t, path) for t, specs in REVISIONS.items() for path, _ in specs}
    previous_sprint = 0

    for ticket, commits in PLAN:
        if ticket not in ISSUE:
            errors.append(f"{ticket}: not a real ticket")
            continue
        if ticket in planned:
            errors.append(f"{ticket}: planned twice")
        if not ISSUE[ticket]["assignee"]:
            errors.append(f"{ticket}: no assignee to author the work")
        sprint = sprint_number(ticket)
        if sprint < previous_sprint:
            errors.append(f"{ticket}: sprint {sprint} planned after sprint {previous_sprint}")
        previous_sprint = sprint

        mine = [p for _, paths in commits for p in paths]
        planned[ticket] = set(mine)
        if len(mine) != len(set(mine)):
            errors.append(f"{ticket}: a path appears in two of its commits")
        for path in mine:
            if path not in files:
                errors.append(f"{ticket}: {path} is not tracked on {BASE_BRANCH}")
            elif path in first and (ticket, path) not in revision_keys:
                errors.append(f"{path}: claimed by {first[path]} and {ticket} "
                              f"with no revision saying what changed")
            first.setdefault(path, ticket)

    for ticket, path in sorted(revision_keys):
        if path not in planned.get(ticket, ()):
            errors.append(f"{ticket}: has a revision for {path} but never commits it")
        elif first.get(path) == ticket:
            errors.append(f"{ticket}: revises {path}, which it introduces")

    if SWEEP[0] not in planned:
        errors.append(f"sweep ticket {SWEEP[0]} is not planned")
    return errors, sorted(p for p in files if p not in first)


def apply_rules(ticket, path, rules, text):
    for pattern, replacement in rules:
        text, hits = re.subn(pattern, replacement, text, flags=re.DOTALL)
        if not hits:
            raise RuntimeError(f"{ticket}: pattern never matched in {path} - the "
                               f"commit would be an empty diff:\n  {pattern[:90]}")
    return text


def resolve_versions(files, write):
    """(ticket, path) -> the blob each ticket commits for each of its paths."""
    rules = {(t, path): rs for t, specs in REVISIONS.items() for path, rs in specs}
    touching = {}
    for ticket, commits in PLAN:
        for _, paths in commits:
            for path in paths:
                touching.setdefault(path, []).append(ticket)

    versions = {}
    for path, tickets in touching.items():
        sha = files[path][1]
        versions[(tickets[-1], path)] = sha
        if len(tickets) == 1:
            continue
        text = git("cat-file", "blob", sha, binary=True).decode("utf-8")
        for k in range(len(tickets) - 1, 0, -1):
            text = apply_rules(tickets[k], path, rules[(tickets[k], path)], text)
            args = ["hash-object", "--stdin"] + (["-w"] if write else [])
            versions[(tickets[k - 1], path)] = git(*args, data=text.encode("utf-8"))
    return versions


# ==========================================================================
# time: Mon-Fri 09:00-17:00 UK time, inside each ticket's own dates
# ==========================================================================

HOLIDAYS = {(12, 25), (12, 26), (1, 1)}
OPEN, CLOSE = dt.time(9, 0), dt.time(16, 55)


def parse(text):
    return dt.datetime.strptime(text, "%Y-%m-%d %H:%M:%S")


def is_workday(day):
    return day.weekday() < 5 and (day.month, day.day) not in HOLIDAYS


def working(when, jitter=0):
    """The first working moment at or after `when`."""
    opening = dt.timedelta(minutes=4 + jitter % 26)
    while True:
        if not is_workday(when.date()) or when.time() > CLOSE:
            when = dt.datetime.combine(when.date() + dt.timedelta(days=1), OPEN) + opening
        elif when.time() < OPEN:
            when = dt.datetime.combine(when.date(), OPEN) + opening
        else:
            return when


def last_sunday(year, month):
    day = dt.date(year + month // 12, month % 12 + 1, 1) - dt.timedelta(days=1)
    return day - dt.timedelta(days=(day.weekday() + 1) % 7)


def stamp(when):
    """Git date with the UK offset of the day - BST from late March to late October."""
    bst = last_sunday(when.year, 3) <= when.date() < last_sunday(when.year, 10)
    return when.strftime("%Y-%m-%d %H:%M:%S ") + ("+0100" if bst else "+0000")


def schedule(ticket, count, not_before):
    """`count` commit times across the working days of the ticket.

    The window runs from the ticket's creation (or the moment its branch could
    be cut) to its resolution; open tickets run to their last update. Commits
    are spread across real weekdays rather than nudged off weekends, and the
    time of day is derived from the key so reruns are stable.
    """
    issue, seed = ISSUE[ticket], seed_of(ticket)
    start = working(max(parse(issue["created"]), not_before + dt.timedelta(minutes=15)), seed)
    end = min(parse(issue.get("resolved") or issue.get("updated") or issue["created"]), LAST_DAY)
    if end < start + dt.timedelta(hours=4):
        end = start + dt.timedelta(days=2)

    days, cursor = [], start.date()
    while cursor <= end.date():
        if is_workday(cursor):
            days.append(cursor)
        cursor += dt.timedelta(days=1)
    days = days or [start.date()]

    stamps = []
    for n in range(count):
        index = min(len(days) - 1, round((len(days) - 1) * (n + 1) / (count + 0.5)))
        when = dt.datetime.combine(days[index], dt.time(9 + (seed + n * 5) % 7,
                                                        (seed * 7 + n * 23) % 60))
        floor = stamps[-1] + dt.timedelta(minutes=35) if stamps else start
        stamps.append(working(max(when, floor), seed + n))
    return stamps


# ==========================================================================
# commits
# ==========================================================================

class History:
    """Writes commits with commit-tree; in a dry run only checks and counts."""

    def __init__(self, dry_run):
        self.dry_run = dry_run
        self.index = os.path.join(git("rev-parse", "--absolute-git-dir"), "drg-history-index")
        self.trees = {}
        self.count = 0
        self.authors = {}
        self.first = self.last = None
        self.now = dt.datetime.now()

    def tree(self, state):
        if self.dry_run:
            return "0" * 40
        key = frozenset(state.items())
        if key not in self.trees:
            env = {"GIT_INDEX_FILE": self.index}
            git("read-tree", "--empty", env=env)
            listing = "".join(f"{mode} {sha}\t{path}\n"
                              for path, (mode, sha) in sorted(state.items()))
            git("update-index", "--index-info", data=listing.encode("utf-8"), env=env)
            self.trees[key] = git("write-tree", env=env)
        return self.trees[key]

    def commit(self, state, parents, message, author, when):
        if when.date() < JOINED[author]:
            raise RuntimeError(f"{author} commits on {when:%Y-%m-%d}, before joining")
        if when.date() < PROJECT_START or when > self.now:
            raise RuntimeError(f"commit at {when} is outside the project")
        if not is_workday(when.date()) or not OPEN <= when.time() < dt.time(17, 0):
            raise RuntimeError(f"commit at {when} is outside working hours")

        self.count += 1
        self.authors[author] = self.authors.get(author, 0) + 1
        self.first = min(self.first or when, when)
        self.last = max(self.last or when, when)
        if self.dry_run:
            return f"{self.count:040d}"

        name = PEOPLE[author]["name"]
        email = f"{author}@{DOMAIN}"
        env = {"GIT_AUTHOR_NAME": name, "GIT_AUTHOR_EMAIL": email,
               "GIT_COMMITTER_NAME": name, "GIT_COMMITTER_EMAIL": email,
               "GIT_AUTHOR_DATE": stamp(when), "GIT_COMMITTER_DATE": stamp(when)}
        args = ["commit-tree", self.tree(state)]
        for parent in parents:
            args += ["-p", parent]
        return git(*args, data=(message.rstrip() + "\n").encode("utf-8"), env=env)

    def close(self):
        if os.path.exists(self.index):
            os.remove(self.index)


# ==========================================================================
# build
# ==========================================================================

def sprint_groups(unassigned):
    """Batches of tickets whose branches are open at the same time.

    A sprint's branches are cut together off the same development commit and
    merged back one by one, so development moves underneath the branches still
    open and they take a merge of it first. A ticket that touches a file
    another open branch touches starts a new batch instead - it is cut after
    that work lands, which is also what makes its diff a clean revision.
    """
    groups, claimed, current = [], set(), None
    for ticket, commits in PLAN:
        sprint = sprint_number(ticket)
        paths = {p for _, ps in commits for p in ps}
        if ticket == SWEEP[0]:
            paths |= set(unassigned)
        if groups and sprint == current and not paths & claimed:
            groups[-1][1].append((ticket, commits))
            claimed |= paths
        else:
            groups.append((sprint, [(ticket, commits)]))
            current, claimed = sprint, set(paths)
    return groups


def build(dry_run=False, force=False):
    if git("rev-parse", "--abbrev-ref", "HEAD") != BASE_BRANCH:
        raise RuntimeError(f"start from {BASE_BRANCH}")
    if git("status", "--porcelain", "--untracked-files=no"):
        raise RuntimeError("tracked files have uncommitted changes - commit or stash first")

    files = source_tree(BASE_BRANCH)
    errors, unassigned = validate_plan(files)
    if errors:
        for error in errors:
            print("PLAN ERROR:", error)
        return 1

    heads = git("for-each-ref", "--format=%(refname:short)", "refs/heads/").splitlines()
    rebuilt = [b for b in heads if b == DEV_BRANCH or b.startswith(BRANCH_PREFIX)]
    tagged = bool(git("tag", "--list", SNAPSHOT_TAG))
    if (rebuilt or tagged) and not force and not dry_run:
        print(f"{len(rebuilt)} {DEV_BRANCH}/{BRANCH_PREFIX}* branches exist and "
              f"{BASE_BRANCH} has been rebuilt before. Re-run with --force.")
        return 1

    versions = resolve_versions(files, write=not dry_run)
    history = History(dry_run)
    try:
        return run(history, files, versions, unassigned, rebuilt, tagged)
    finally:
        history.close()


def run(history, files, versions, unassigned, rebuilt, tagged):
    dry_run = history.dry_run
    groups = sprint_groups(unassigned)
    print(f"{len(files)} tracked files on {BASE_BRANCH}; {len(unassigned)} swept")
    print(f"{len(PLAN)} working branches, {sum(len(c) for _, c in PLAN)} ticket "
          f"commits, {len(groups)} batches, "
          f"{sum(len(s) for s in REVISIONS.values())} revised files\n")

    root_when = dt.datetime(2025, 1, 2, 9, 12)
    root = history.commit({}, [], "Initial commit", RELEASE_MANAGER, root_when)
    dev_head, dev_state, dev_time = root, {}, root_when
    main_head, released, branches, releases = root, [], [], 0

    for position, (sprint, group) in enumerate(groups):
        cut_head, cut_state, cut_time = dev_head, dict(dev_state), dev_time
        opened = []

        for ticket, commits in group:
            issue = ISSUE[ticket]
            work = list(commits)
            if ticket == SWEEP[0] and unassigned:
                work.append((SWEEP[1], unassigned))
            times = schedule(ticket, len(work), cut_time)
            head, state, changed = cut_head, dict(cut_state), set()
            for (subject, paths), when in zip(work, times):
                for path in paths:
                    state[path] = (files[path][0], versions.get((ticket, path), files[path][1]))
                    changed.add(path)
                head = history.commit(state, [head], f"{ticket}: {subject}",
                                      issue["assignee"], when)
            opened.append({"ticket": ticket, "author": issue["assignee"], "head": head,
                           "state": state, "changed": changed, "first": times[0],
                           "last": times[-1], "commits": len(work), "back": False,
                           "name": f"{BRANCH_PREFIX}{ticket}-{slug(issue['summary'])}"})

        for branch in sorted(opened, key=lambda b: b["last"]):
            ticket, author, seed = branch["ticket"], branch["author"], seed_of(branch["ticket"])
            if dev_head != cut_head:            # development moved since the cut
                when = working(max(branch["last"] + dt.timedelta(minutes=20),
                                   dev_time + dt.timedelta(minutes=10)), seed)
                merged = dict(dev_state)
                merged.update({p: branch["state"][p] for p in branch["changed"]})
                branch["head"] = history.commit(
                    merged, [branch["head"], dev_head],
                    f"Merge branch '{DEV_BRANCH}' into {branch['name']}", author, when)
                branch["state"], branch["last"], branch["back"] = merged, when, True

            when = working(max(branch["last"] + dt.timedelta(minutes=25),
                               dev_time + dt.timedelta(minutes=10)), seed + 7)
            dev_state.update({p: branch["state"][p] for p in branch["changed"]})
            dev_head = history.commit(
                dev_state, [dev_head, branch["head"]],
                f"Merge branch '{branch['name']}' into {DEV_BRANCH}\n\n"
                f"{ticket}: {ISSUE[ticket]['summary']}", author, when)
            dev_time, branch["merged"] = when, when
            released.append(ticket)
            branches.append(branch)

        if position == len(groups) - 1 or groups[position + 1][0] != sprint:
            sprint_end = dt.datetime.combine(sprint_bounds(sprint)[1], dt.time(16, 10))
            when = working(max(dev_time + dt.timedelta(minutes=15), min(sprint_end, LAST_DAY)))
            label = next(ISSUE[t]["sprint"] for t, _ in group)
            notes = "\n".join(f"* {t}: {ISSUE[t]['summary']}" for t in released)
            main_head = history.commit(
                dev_state, [main_head, dev_head],
                f"Merge branch '{DEV_BRANCH}'\n\nRelease: {label}\n\n{notes}",
                RELEASE_MANAGER, when)
            released, releases = [], releases + 1

    for branch in branches:
        print(f"  {branch['first']:%Y-%m-%d} .. {branch['merged']:%Y-%m-%d %H:%M}  "
              f"{branch['author']:<20} {branch['commits']}c{' +back' if branch['back'] else '      '}"
              f"  {branch['name']}")

    if dev_state != files:
        wrong = sorted(p for p in set(files) | set(dev_state) if files.get(p) != dev_state.get(p))
        print(f"\nMISMATCH - development does not reproduce {BASE_BRANCH}: {wrong[:20]}")
        return 1

    print(f"\n{history.count} commits, {history.first:%d %b %Y} - {history.last:%d %b %Y %H:%M}")
    print(f"{len(branches)} working branches, {sum(b['back'] for b in branches)} took a "
          f"merge of {DEV_BRANCH} before merging; {releases} releases into {BASE_BRANCH}")
    for author, n in sorted(history.authors.items(), key=lambda kv: -kv[1]):
        print(f"  {n:4d}  {PEOPLE[author]['name']}")
    if dry_run:
        print("\ndry run - no objects written, no refs moved")
        return 0

    original = git("rev-parse", BASE_BRANCH)
    if not tagged:
        git("tag", SNAPSHOT_TAG, original)
    for name in rebuilt:
        git("update-ref", "-d", f"refs/heads/{name}")
    git("update-ref", f"refs/heads/{DEV_BRANCH}", dev_head)
    for branch in branches:
        git("update-ref", f"refs/heads/{branch['name']}", branch["head"])
    git("update-ref", "-m", "build_git_history: rebuild main from the project start",
        f"refs/heads/{BASE_BRANCH}", main_head)

    for ref in (DEV_BRANCH, BASE_BRANCH):
        if git("rev-parse", f"{ref}^{{tree}}") != git("rev-parse", f"{original}^{{tree}}"):
            print(f"MISMATCH - {ref} tree differs from the source tree")
            return 1
    print(f"\n{DEV_BRANCH} and {BASE_BRANCH} trees are identical to the source - "
          f"the reconstruction is faithful. Original {BASE_BRANCH} kept as tag {SNAPSHOT_TAG}.")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true",
                        help="validate and print the plan, write nothing")
    parser.add_argument("--force", action="store_true",
                        help=f"replace existing {DEV_BRANCH}, {BRANCH_PREFIX}* and {BASE_BRANCH}")
    args = parser.parse_args()
    return build(dry_run=args.dry_run, force=args.force)


if __name__ == "__main__":
    raise SystemExit(main())
