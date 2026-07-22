"""Promotion-gate CLI used by the model deployment workflow.

    python pipelines/promote_model.py \
        --candidate outputs/run_report.json \
        --incumbent incumbent_tags.json \
        --tags-out model_tags.json \
        --summary-out gate_summary.md

Exit codes: ``0`` promote, ``2`` blocked. Anything else is an error in the
gate itself. When ``GITHUB_OUTPUT`` is set the decision is also written there
so later workflow steps can branch on ``steps.gate.outputs.promote``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from drg.config import load_config  # noqa: E402
from drg.mlops.gate import (  # noqa: E402
    GateThresholds,
    evaluate_gate,
    load_candidate_metrics,
    load_incumbent_metrics,
    to_registry_tags,
)
from drg.utils.logging_utils import get_logger, setup_logging  # noqa: E402

log = get_logger("drg.promote")


def _write_github_output(decision, candidate) -> None:
    target = os.getenv("GITHUB_OUTPUT")
    if not target:
        return
    with open(target, "a", encoding="utf-8") as fh:
        fh.write(f"promote={'true' if decision.promote else 'false'}\n")
        fh.write(f"reason={decision.reason}\n")
        for key in ("rmse", "mae", "mape", "r2", "stress_recall", "stress_f1"):
            if candidate.get(key) is not None:
                fh.write(f"{key}={candidate[key]}\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Decide whether a retrained model may be promoted")
    parser.add_argument("--candidate", required=True, help="run_report.json or model_metrics.json")
    parser.add_argument("--incumbent", default=None, help="Registry tags of the deployed model")
    parser.add_argument("--config", default=None)
    parser.add_argument("--tags-out", default=None, help="Write Azure ML model tags here")
    parser.add_argument("--summary-out", default=None, help="Write a markdown summary here")
    parser.add_argument("--decision-out", default=None, help="Write the full decision as JSON here")
    parser.add_argument("--model-version", default=None, help="Recorded in the tags")
    parser.add_argument("--git-sha", default=os.getenv("GITHUB_SHA"), help="Recorded in the tags")
    parser.add_argument(
        "--allow-synthetic",
        action="store_true",
        help="Permit promoting a model trained on the synthetic fallback (demo environments)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Report the gate result but always exit 0 (dry run)",
    )
    args = parser.parse_args()

    setup_logging()
    cfg = load_config(args.config)
    thresholds = GateThresholds.from_dict(cfg.get("mlops.promotion_gate"))

    candidate = load_candidate_metrics(args.candidate)
    incumbent = load_incumbent_metrics(args.incumbent)
    log.info("candidate: %s", json.dumps(candidate, default=str))
    log.info("incumbent: %s", json.dumps(incumbent, default=str) if incumbent else "none")

    decision = evaluate_gate(candidate, incumbent, thresholds)

    # In a demo environment the synthetic-provenance warning is expected; the
    # flag only relaxes that one non-blocking check, never a blocking gate.
    if args.allow_synthetic:
        for check in decision.checks:
            if check.name == "Data provenance" and not check.passed:
                check.detail += " [accepted: --allow-synthetic]"

    summary = decision.to_markdown()
    print(summary)

    if args.summary_out:
        Path(args.summary_out).write_text(summary, encoding="utf-8")
    if step_summary := os.getenv("GITHUB_STEP_SUMMARY"):
        with open(step_summary, "a", encoding="utf-8") as fh:
            fh.write(summary + "\n")
    if args.decision_out:
        Path(args.decision_out).write_text(
            json.dumps(decision.to_dict(), indent=2, default=str), encoding="utf-8"
        )
    if args.tags_out:
        tags = to_registry_tags(
            candidate,
            extra={
                "promoted": str(decision.promote).lower(),
                "model_version": args.model_version,
                "git_sha": args.git_sha,
                "gate_reason": decision.reason[:250],
            },
        )
        Path(args.tags_out).write_text(json.dumps(tags, indent=2), encoding="utf-8")

    _write_github_output(decision, candidate)

    if decision.promote or args.force:
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
