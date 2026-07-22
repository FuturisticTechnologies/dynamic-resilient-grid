"""Model promotion gate.

A retrained model is only allowed to reach the serving endpoint if it clears
two kinds of check:

**Absolute gates** - floors the model must meet whatever the incumbent does.
A model that cannot forecast (low R2, high MAPE) or that misses stress periods
(low recall) is rejected even if it happens to beat a worse incumbent.

**Relative gates** - a comparison against the model currently in production.
A candidate is allowed to be marginally worse on RMSE (``max_rmse_regression_pct``)
so that ordinary retraining noise does not block a refresh, but a real
regression stops the deployment.

Stress *recall* is deliberately gated harder than precision: for a network
planner a missed stress period is a missed reinforcement signal, while a false
alarm costs an unnecessary look at a dashboard.

The decision logic lives here (importable and unit-tested);
``pipelines/promote_model.py`` is the thin CLI the CI workflow calls.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from drg.utils.logging_utils import get_logger

log = get_logger(__name__)


# ===========================================================================
# thresholds
# ===========================================================================
@dataclass
class GateThresholds:
    """Promotion criteria. Overridable from config or the workflow inputs."""

    # absolute floors / ceilings
    min_r2: float = 0.90
    max_mape: float = 8.0
    min_stress_recall: float = 0.70
    min_stress_f1: float = 0.65
    min_train_rows: int = 5000

    # relative to the incumbent
    max_rmse_regression_pct: float = 2.0
    max_recall_regression_pp: float = 5.0

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "GateThresholds":
        if not payload:
            return cls()
        known = set(cls.__dataclass_fields__)  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in payload.items() if k in known})


# ===========================================================================
# results
# ===========================================================================
@dataclass
class Check:
    name: str
    passed: bool
    detail: str
    blocking: bool = True

    @property
    def icon(self) -> str:
        if self.passed:
            return "PASS"
        return "FAIL" if self.blocking else "WARN"


@dataclass
class GateDecision:
    promote: bool
    reason: str
    checks: list[Check] = field(default_factory=list)
    candidate: dict[str, Any] = field(default_factory=dict)
    incumbent: dict[str, Any] | None = None

    @property
    def failures(self) -> list[Check]:
        return [c for c in self.checks if not c.passed and c.blocking]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    # ------------------------------------------------------------- rendering
    def to_markdown(self) -> str:
        """GitHub step-summary table."""
        verdict = "PROMOTE" if self.promote else "BLOCK"
        lines = [
            f"### Model promotion gate: **{verdict}**",
            "",
            f"_{self.reason}_",
            "",
            "| Check | Result | Detail |",
            "|---|---|---|",
        ]
        lines.extend(f"| {c.name} | {c.icon} | {c.detail} |" for c in self.checks)

        if self.candidate:
            lines += ["", "| Metric | Candidate | Incumbent |", "|---|---|---|"]
            keys = ["rmse", "mae", "mape", "r2", "stress_recall", "stress_precision", "stress_f1"]
            for key in keys:
                cand = self.candidate.get(key)
                inc = (self.incumbent or {}).get(key)
                if cand is None and inc is None:
                    continue
                lines.append(
                    f"| {key} | {_fmt(cand)} | {_fmt(inc) if inc is not None else 'n/a (first deployment)'} |"
                )
        return "\n".join(lines)


def _fmt(value: Any) -> str:
    if value is None:
        return "n/a"
    try:
        return f"{float(value):.4f}"
    except (TypeError, ValueError):
        return str(value)


# ===========================================================================
# metric loading
# ===========================================================================
def load_candidate_metrics(path: str | Path) -> dict[str, Any]:
    """Extract the champion's test metrics from a pipeline artifact.

    Accepts either ``run_report.json`` (produced by ``run_all``) or
    ``model_metrics.json`` (produced by the training stage).
    """
    payload = json.loads(Path(path).read_text(encoding="utf-8"))

    if "model" in payload and "test_metrics" in payload.get("model", {}):
        champion = payload["model"]["champion"]
        rows = payload["model"]["test_metrics"]
        extra = {
            "champion": champion,
            "cv_mean_rmse": payload["model"].get("cv_mean_rmse"),
            "data_rows": payload.get("data", {}).get("rows"),
            "data_source": payload.get("data", {}).get("source"),
        }
    elif "test_metrics" in payload:
        champion = payload.get("champion")
        rows = payload["test_metrics"]
        extra = {"champion": champion, "n_features": payload.get("n_features")}
    else:
        raise ValueError(f"{path} is neither a run_report.json nor a model_metrics.json artifact")

    metrics = next((r for r in rows if r.get("model") == champion), None)
    if metrics is None:
        raise ValueError(f"No metrics found for champion model {champion!r} in {path}")

    out = {k: v for k, v in metrics.items() if not isinstance(v, (list, dict))}
    out.update({k: v for k, v in extra.items() if v is not None})
    return out


def load_incumbent_metrics(path: str | Path | None) -> dict[str, Any] | None:
    """Read the deployed model's metrics, as stored in its registry tags.

    Returns ``None`` when there is no incumbent (first ever deployment) or the
    tag payload is empty, which the gate treats as "absolute checks only".
    """
    if path is None:
        return None
    p = Path(path)
    if not p.exists():
        log.info("no incumbent metrics at %s; treating as first deployment", p)
        return None

    raw = p.read_text(encoding="utf-8").strip()
    if not raw or raw in {"{}", "null", "[]"}:
        return None

    payload = json.loads(raw)
    if isinstance(payload, list):  # `az ml model list` output
        if not payload:
            return None
        payload = payload[0].get("tags", payload[0])
    elif "tags" in payload and isinstance(payload["tags"], dict):
        payload = payload["tags"]

    # registry tags are always strings; coerce the numeric ones back
    out: dict[str, Any] = {}
    for key, value in payload.items():
        try:
            out[key] = float(value)
        except (TypeError, ValueError):
            out[key] = value
    return out or None


def to_registry_tags(metrics: dict[str, Any], extra: dict[str, Any] | None = None) -> dict[str, str]:
    """Flatten metrics into Azure ML model tags (string values only)."""
    keep = [
        "champion",
        "mae",
        "rmse",
        "mape",
        "r2",
        "stress_precision",
        "stress_recall",
        "stress_f1",
        "stress_threshold",
        "cv_mean_rmse",
        "n",
        "data_source",
    ]
    tags = {k: str(metrics[k]) for k in keep if metrics.get(k) is not None}
    for key, value in (extra or {}).items():
        if value is not None:
            tags[key] = str(value)
    return tags


# ===========================================================================
# the gate
# ===========================================================================
def evaluate_gate(
    candidate: dict[str, Any],
    incumbent: dict[str, Any] | None = None,
    thresholds: GateThresholds | None = None,
) -> GateDecision:
    """Decide whether ``candidate`` may replace ``incumbent`` in production."""
    th = thresholds or GateThresholds()
    checks: list[Check] = []

    def _get(source: dict[str, Any] | None, key: str) -> float | None:
        if not source or source.get(key) is None:
            return None
        try:
            return float(source[key])
        except (TypeError, ValueError):
            return None

    # ---------------------------------------------------------- absolute ---
    r2 = _get(candidate, "r2")
    checks.append(
        Check(
            "R2 floor",
            r2 is not None and r2 >= th.min_r2,
            f"{_fmt(r2)} (needs >= {th.min_r2})",
        )
    )

    mape = _get(candidate, "mape")
    checks.append(
        Check(
            "MAPE ceiling",
            mape is not None and mape <= th.max_mape,
            f"{_fmt(mape)}% (needs <= {th.max_mape}%)",
        )
    )

    recall = _get(candidate, "stress_recall")
    checks.append(
        Check(
            "Stress recall floor",
            recall is not None and recall >= th.min_stress_recall,
            f"{_fmt(recall)} (needs >= {th.min_stress_recall}) "
            "- a missed stress period is a missed reinforcement signal",
        )
    )

    f1 = _get(candidate, "stress_f1")
    checks.append(
        Check(
            "Stress F1 floor",
            f1 is not None and f1 >= th.min_stress_f1,
            f"{_fmt(f1)} (needs >= {th.min_stress_f1})",
        )
    )

    rows = candidate.get("n") or candidate.get("data_rows")
    rows = int(rows) if rows is not None else None
    checks.append(
        Check(
            "Evaluation size",
            rows is not None and rows >= th.min_train_rows,
            (
                f"{rows:,} test rows (needs >= {th.min_train_rows:,})"
                if rows is not None
                else "no row count reported"
            ),
        )
    )

    # a model trained on the synthetic fallback must never reach production
    source = str(candidate.get("data_source", "")).lower()
    if source:
        checks.append(
            Check(
                "Data provenance",
                source != "synthetic",
                f"trained on '{source}'"
                + (" - the synthetic fallback is not production data" if source == "synthetic" else ""),
                blocking=False,
            )
        )

    # ---------------------------------------------------------- relative ---
    if incumbent:
        cand_rmse, inc_rmse = _get(candidate, "rmse"), _get(incumbent, "rmse")
        if cand_rmse is not None and inc_rmse is not None and inc_rmse > 0:
            change = 100.0 * (cand_rmse / inc_rmse - 1.0)
            checks.append(
                Check(
                    "RMSE vs incumbent",
                    change <= th.max_rmse_regression_pct,
                    f"{change:+.2f}% ({_fmt(cand_rmse)} vs {_fmt(inc_rmse)}; "
                    f"tolerance +{th.max_rmse_regression_pct}%)",
                )
            )

        cand_rec, inc_rec = recall, _get(incumbent, "stress_recall")
        if cand_rec is not None and inc_rec is not None:
            drop_pp = 100.0 * (inc_rec - cand_rec)
            checks.append(
                Check(
                    "Stress recall vs incumbent",
                    drop_pp <= th.max_recall_regression_pp,
                    f"{-drop_pp:+.2f} pp ({_fmt(cand_rec)} vs {_fmt(inc_rec)}; "
                    f"tolerance -{th.max_recall_regression_pp} pp)",
                )
            )
    else:
        checks.append(
            Check("Incumbent comparison", True, "no deployed model - absolute gates only", blocking=False)
        )

    failures = [c for c in checks if not c.passed and c.blocking]
    warnings = [c for c in checks if not c.passed and not c.blocking]

    if failures:
        reason = "Blocked by " + "; ".join(f"{c.name} ({c.detail})" for c in failures)
        promote = False
    else:
        reason = f"All {len(checks) - len(warnings)} blocking checks passed"
        if warnings:
            reason += f"; {len(warnings)} warning(s): " + "; ".join(c.name for c in warnings)
        promote = True

    decision = GateDecision(
        promote=promote, reason=reason, checks=checks, candidate=candidate, incumbent=incumbent
    )
    log.info("promotion gate -> %s: %s", "PROMOTE" if promote else "BLOCK", reason)
    return decision
