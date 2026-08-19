"""Promotion gate, model spec generation and endpoint verification tests.

These guard the only automated path by which a model reaches production
traffic, so the failure modes matter more than the happy path: a regressed
model must be blocked, and a broken endpoint must fail the smoke test.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from drg.mlops.gate import (
    GateThresholds,
    evaluate_gate,
    load_candidate_metrics,
    load_incumbent_metrics,
    to_registry_tags,
)

ROOT = Path(__file__).resolve().parents[1]

GOOD = {
    "model": "xgboost",
    "champion": "xgboost",
    "mae": 0.70,
    "rmse": 0.947,
    "mape": 3.37,
    "r2": 0.986,
    "stress_precision": 0.909,
    "stress_recall": 0.897,
    "stress_f1": 0.903,
    "n": 11524,
    "data_source": "low-carbon-london",
}


def _candidate(**overrides):
    return {**GOOD, **overrides}


# ===========================================================================
# absolute gates
# ===========================================================================
def test_good_model_promotes_on_first_deployment():
    decision = evaluate_gate(_candidate())
    assert decision.promote
    assert not decision.failures
    assert "no deployed model" in decision.to_markdown()


@pytest.mark.parametrize(
    "field,value,expected_check",
    [
        ("r2", 0.5, "R2 floor"),
        ("mape", 25.0, "MAPE ceiling"),
        ("stress_recall", 0.4, "Stress recall floor"),
        ("stress_f1", 0.2, "Stress F1 floor"),
        ("n", 100, "Evaluation size"),
    ],
)
def test_absolute_gates_block_bad_models(field, value, expected_check):
    decision = evaluate_gate(_candidate(**{field: value}))
    assert not decision.promote
    assert any(c.name == expected_check for c in decision.failures)


def test_missing_metric_is_treated_as_a_failure_not_a_pass():
    candidate = _candidate()
    del candidate["r2"]
    decision = evaluate_gate(candidate)
    assert not decision.promote, "an absent metric must never silently pass a gate"


def test_synthetic_provenance_warns_but_does_not_block():
    decision = evaluate_gate(_candidate(data_source="synthetic"))
    assert decision.promote, "provenance is advisory so demo pipelines still run"
    warning = next(c for c in decision.checks if c.name == "Data provenance")
    assert not warning.passed and not warning.blocking
    assert warning.icon == "WARN"


# ===========================================================================
# relative gates
# ===========================================================================
def test_rmse_regression_beyond_tolerance_blocks():
    incumbent = {"rmse": 0.85, "stress_recall": 0.90}
    decision = evaluate_gate(_candidate(), incumbent)
    assert not decision.promote
    assert any(c.name == "RMSE vs incumbent" for c in decision.failures)


def test_small_rmse_regression_inside_tolerance_promotes():
    # 0.947 vs 0.940 is +0.74%, inside the 2% tolerance for retraining noise
    decision = evaluate_gate(_candidate(), {"rmse": 0.940, "stress_recall": 0.90})
    assert decision.promote


def test_improvement_over_incumbent_promotes():
    decision = evaluate_gate(_candidate(), {"rmse": 1.40, "stress_recall": 0.81})
    assert decision.promote


def test_recall_collapse_blocks_even_when_rmse_improves():
    """The whole point of the gate: a better RMSE must not buy a worse alarm."""
    candidate = _candidate(rmse=0.60, stress_recall=0.72, stress_f1=0.70)
    decision = evaluate_gate(candidate, {"rmse": 1.00, "stress_recall": 0.92})
    assert not decision.promote
    assert any(c.name == "Stress recall vs incumbent" for c in decision.failures)


def test_thresholds_are_configurable():
    strict = GateThresholds(min_r2=0.99)
    assert not evaluate_gate(_candidate(), thresholds=strict).promote
    lenient = GateThresholds(min_r2=0.5, max_rmse_regression_pct=50.0)
    assert evaluate_gate(_candidate(), {"rmse": 0.85}, thresholds=lenient).promote


def test_thresholds_from_dict_ignores_unknown_keys():
    th = GateThresholds.from_dict({"min_r2": 0.8, "nonsense": 1})
    assert th.min_r2 == 0.8
    assert th.max_mape == GateThresholds().max_mape


# ===========================================================================
# metric loading and tag round-trip
# ===========================================================================
def test_load_candidate_from_run_report(tmp_path):
    report = {
        "data": {"rows": 151488, "source": "synthetic"},
        "model": {
            "champion": "xgboost",
            "cv_mean_rmse": 0.87,
            "test_metrics": [
                {"model": "ridge_regression", "rmse": 1.10, "r2": 0.98},
                {"model": "xgboost", "rmse": 0.947, "r2": 0.986, "mape": 3.37},
            ],
        },
    }
    path = tmp_path / "run_report.json"
    path.write_text(json.dumps(report), encoding="utf-8")

    metrics = load_candidate_metrics(path)
    assert metrics["rmse"] == 0.947, "must pick the champion, not the first row"
    assert metrics["champion"] == "xgboost"
    assert metrics["data_source"] == "synthetic"


def test_load_candidate_from_model_metrics(tmp_path):
    payload = {
        "champion": "xgboost",
        "n_features": 47,
        "test_metrics": [{"model": "xgboost", "rmse": 0.9, "r2": 0.99}],
    }
    path = tmp_path / "model_metrics.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert load_candidate_metrics(path)["rmse"] == 0.9


def test_load_candidate_rejects_unknown_artifact(tmp_path):
    path = tmp_path / "junk.json"
    path.write_text('{"hello": "world"}', encoding="utf-8")
    with pytest.raises(ValueError, match="neither a run_report"):
        load_candidate_metrics(path)


def test_incumbent_absent_or_empty_is_none(tmp_path):
    assert load_incumbent_metrics(None) is None
    assert load_incumbent_metrics(tmp_path / "missing.json") is None
    empty = tmp_path / "empty.json"
    empty.write_text("{}", encoding="utf-8")
    assert load_incumbent_metrics(empty) is None


def test_registry_tag_round_trip(tmp_path):
    """Tags written after one deployment must be readable as the next incumbent."""
    tags = to_registry_tags(GOOD, extra={"git_sha": "abc123"})
    assert all(isinstance(v, str) for v in tags.values()), "Azure ML tags must be strings"

    path = tmp_path / "tags.json"
    path.write_text(json.dumps(tags), encoding="utf-8")
    incumbent = load_incumbent_metrics(path)

    assert incumbent["rmse"] == pytest.approx(GOOD["rmse"])
    assert incumbent["stress_recall"] == pytest.approx(GOOD["stress_recall"])
    assert incumbent["git_sha"] == "abc123"

    # and the round-tripped incumbent drives the gate correctly
    assert evaluate_gate(_candidate(rmse=0.80), incumbent).promote
    assert not evaluate_gate(_candidate(rmse=1.50), incumbent).promote


def test_incumbent_accepts_az_ml_list_output(tmp_path):
    path = tmp_path / "list.json"
    path.write_text(json.dumps([{"name": "drg-champion", "tags": {"rmse": "0.9"}}]), encoding="utf-8")
    assert load_incumbent_metrics(path)["rmse"] == 0.9


# ===========================================================================
# CLI behaviour (the workflow branches on these exit codes)
# ===========================================================================
def _run_cli(script: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(ROOT / "pipelines" / script), *args],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )


def test_promote_cli_exit_codes(tmp_path):
    report = ROOT / "artifacts" / "reports" / "run_report.json"
    if not report.exists():
        pytest.skip("run the pipeline first: python -m drg.cli run-all")

    ok = _run_cli("promote_model.py", "--candidate", str(report))
    assert ok.returncode == 0, ok.stdout + ok.stderr
    assert "PROMOTE" in ok.stdout

    incumbent = tmp_path / "inc.json"
    incumbent.write_text(json.dumps({"rmse": "0.50", "stress_recall": "0.99"}), encoding="utf-8")
    blocked = _run_cli("promote_model.py", "--candidate", str(report), "--incumbent", str(incumbent))
    assert blocked.returncode == 2, "a blocked promotion must exit 2, not 0 or 1"
    assert "BLOCK" in blocked.stdout

    forced = _run_cli(
        "promote_model.py", "--candidate", str(report), "--incumbent", str(incumbent), "--force"
    )
    assert forced.returncode == 0, "--force is the dry-run path and must not fail the job"


def test_model_spec_generation(tmp_path):
    tags = tmp_path / "tags.json"
    tags.write_text(json.dumps(to_registry_tags(GOOD)), encoding="utf-8")
    out = tmp_path / "model-spec.yml"

    result = _run_cli(
        "make_model_spec.py",
        "--name",
        "drg-champion",
        "--path",
        "artifacts/models",
        "--tags",
        str(tags),
        "--out",
        str(out),
    )
    assert result.returncode == 0, result.stdout + result.stderr

    spec = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert spec["name"] == "drg-champion"
    assert spec["type"] == "custom_model"
    assert all(isinstance(v, str) and len(v) <= 250 for v in spec["tags"].values())


# ===========================================================================
# endpoint verification
# ===========================================================================
def _write(tmp_path: Path, name: str, payload: dict) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_endpoint_verification_passes_on_a_healthy_response(tmp_path):
    request = _write(tmp_path, "req.json", {"records": [{"lag_1": 20.0}]})
    response = _write(
        tmp_path,
        "resp.json",
        {"forecast_kwh": [28.0], "model": "xgboost", "missing_features": [], "is_stress": [False]},
    )
    result = _run_cli(
        "verify_endpoint.py",
        "--response",
        str(response),
        "--request",
        str(request),
        "--latency-ms",
        "500",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASSED" in result.stdout


@pytest.mark.parametrize(
    "response,latency,label",
    [
        ({"forecast_kwh": [0.0], "missing_features": []}, "500", "zero forecast"),
        ({"forecast_kwh": [9999.0], "missing_features": []}, "500", "implausible forecast"),
        ({"forecast_kwh": [28.0], "missing_features": ["lag_1", "lag_48"]}, "500", "dropped features"),
        ({"forecast_kwh": [28.0], "missing_features": []}, "60000", "latency budget"),
        ({"error": "model failed to load"}, "500", "endpoint error"),
        ({"model": "xgboost"}, "500", "no forecast at all"),
    ],
)
def test_endpoint_verification_catches_broken_deployments(tmp_path, response, latency, label):
    request = _write(tmp_path, "req.json", {"records": [{"lag_1": 20.0}]})
    resp = _write(tmp_path, "resp.json", response)
    result = _run_cli(
        "verify_endpoint.py",
        "--response",
        str(resp),
        "--request",
        str(request),
        "--latency-ms",
        latency,
    )
    assert result.returncode == 1, f"{label} should fail the smoke test: {result.stdout}"
    assert "FAILED" in result.stdout


def test_endpoint_verification_checks_record_count(tmp_path):
    request = _write(tmp_path, "req.json", {"records": [{"lag_1": 1.0}, {"lag_1": 2.0}]})
    resp = _write(tmp_path, "resp.json", {"forecast_kwh": [28.0], "missing_features": []})
    result = _run_cli("verify_endpoint.py", "--response", str(resp), "--request", str(request))
    assert result.returncode == 1
    assert "expected 2 forecasts" in result.stdout


def test_scoring_script_serves_the_committed_sample_request():
    """The payload the workflow smoke-tests with must actually score."""
    sample = ROOT / "infra" / "aml" / "sample-request.json"
    models = ROOT / "artifacts" / "models"
    if not (models / "best_model.joblib").exists():
        pytest.skip("no trained model; run python -m drg.cli train")

    code = (
        "import json,sys,os;"
        "sys.path.insert(0,'pipelines');"
        "os.environ['AZUREML_MODEL_DIR']=r'" + str(models) + "';"
        "import score;score.init();"
        "print(json.dumps(score.run(open(r'" + str(sample) + "').read())))"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=ROOT)
    assert result.returncode == 0, result.stderr

    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["missing_features"] == [], "the sample request must be feature-complete"
    assert 0 < payload["forecast_kwh"][0] < 500
