"""Post-deployment verification of a scoring response.

Run against the raw output of ``az ml online-endpoint invoke`` before any
production traffic is shifted onto a new deployment:

    az ml online-endpoint invoke -n drg-forecast --deployment-name green \
        --request-file infra/aml/sample-request.json > response.json

    python pipelines/verify_endpoint.py --response response.json \
        --request infra/aml/sample-request.json --latency-ms 812

The checks are deliberately about *behaviour*, not just HTTP success: an
endpoint that returns 200 with a zero forecast, or that silently dropped most
of the feature vector, is broken in the way that matters.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from drg.config import load_config  # noqa: E402
from drg.utils.logging_utils import get_logger, setup_logging  # noqa: E402

log = get_logger("drg.verify")


def _load(path: str | Path) -> dict:
    """Read a response file, tolerating the CLI double-encoding it as a string."""
    raw = Path(path).read_text(encoding="utf-8").strip()
    payload = json.loads(raw)
    if isinstance(payload, str):  # az ml sometimes returns a JSON string
        payload = json.loads(payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify an online-endpoint scoring response")
    parser.add_argument("--response", required=True)
    parser.add_argument("--request", default=None, help="The request that produced it")
    parser.add_argument("--latency-ms", type=float, default=None)
    parser.add_argument("--config", default=None)
    parser.add_argument(
        "--max-missing-features",
        type=int,
        default=0,
        help="How many unfilled features the response may report",
    )
    args = parser.parse_args()

    setup_logging()
    cfg = load_config(args.config)
    limits = cfg.get("mlops.smoke_test", {}) or {}
    lo = float(limits.get("min_forecast_kwh", 0.1))
    hi = float(limits.get("max_forecast_kwh", 500.0))
    max_latency = float(limits.get("max_latency_ms", 5000))

    response = _load(args.response)
    failures: list[str] = []
    notes: list[str] = []

    if "error" in response:
        failures.append(f"endpoint returned an error: {response['error']}")

    forecasts = response.get("forecast_kwh")
    if not isinstance(forecasts, list) or not forecasts:
        failures.append("response contains no 'forecast_kwh' list")
    else:
        if args.request:
            expected = len(_load(args.request).get("records", []))
            if expected and len(forecasts) != expected:
                failures.append(f"expected {expected} forecasts, got {len(forecasts)}")
        for i, value in enumerate(forecasts):
            if not isinstance(value, (int, float)):
                failures.append(f"forecast[{i}] is not numeric: {value!r}")
            elif not (lo <= float(value) <= hi):
                failures.append(f"forecast[{i}] = {value} outside the plausible range [{lo}, {hi}]")
        notes.append(f"forecasts: {[round(float(v), 3) for v in forecasts if isinstance(v, (int, float))]}")

    missing = response.get("missing_features")
    if isinstance(missing, list):
        if len(missing) > args.max_missing_features:
            failures.append(
                f"{len(missing)} features were missing from the request "
                f"(allowed {args.max_missing_features}): {missing[:8]}"
            )
        else:
            notes.append(f"missing features: {len(missing)}")

    if response.get("model"):
        notes.append(f"model: {response['model']}")
    if response.get("n_features"):
        notes.append(f"n_features: {response['n_features']}")

    if "is_stress" in response:
        flags = response["is_stress"]
        if not isinstance(flags, list) or len(flags) != len(forecasts or []):
            failures.append("'is_stress' does not align with 'forecast_kwh'")
        else:
            notes.append(f"stress flags: {flags}")

    if args.latency_ms is not None:
        if args.latency_ms > max_latency:
            failures.append(f"latency {args.latency_ms:.0f} ms exceeds the {max_latency:.0f} ms budget")
        else:
            notes.append(f"latency: {args.latency_ms:.0f} ms")

    for note in notes:
        log.info("  %s", note)

    if failures:
        for failure in failures:
            log.error("SMOKE TEST FAILED: %s", failure)
        print("ENDPOINT VERIFICATION FAILED")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    log.info("endpoint verification passed (%s checks)", len(notes))
    print("ENDPOINT VERIFICATION PASSED: " + " | ".join(notes))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
