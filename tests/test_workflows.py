"""CI/CD workflow contract tests.

These workflows cannot be executed locally (no Azure subscription), so the
suite verifies what *can* be checked offline: that they parse, that every
expression reference resolves, that the shell in each `run:` block is
syntactically valid, and that the safety properties of the model deployment
pipeline (gate before deploy, rollback on failure) are actually wired up.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = ROOT / ".github" / "workflows"
WORKFLOWS = sorted(WORKFLOW_DIR.glob("*.yml"))

# `on:` is parsed by PyYAML 1.1 rules as the boolean True
ON_KEY = True


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def workflows() -> dict[str, dict]:
    return {p.name: _load(p) for p in WORKFLOWS}


def test_expected_workflows_exist(workflows):
    assert {"ci.yml", "deploy-azure.yml", "model-deploy.yml"} <= set(workflows)


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_workflow_parses_and_has_jobs(path):
    doc = _load(path)
    assert doc.get("name"), f"{path.name} has no name"
    assert ON_KEY in doc or "on" in doc, f"{path.name} has no trigger"
    assert doc.get("jobs"), f"{path.name} has no jobs"


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_every_expression_reference_resolves(path):
    """No `steps.x.outputs` or `needs.y.outputs` pointing at something absent."""
    doc = _load(path)
    jobs = doc["jobs"]
    problems: list[str] = []

    for job_name, job in jobs.items():
        step_ids = {s["id"] for s in job.get("steps", []) if s.get("id")}
        blob = yaml.safe_dump(job)

        for ref in set(re.findall(r"steps\.([A-Za-z0-9_-]+)\.outputs", blob)):
            if ref not in step_ids:
                problems.append(f"{job_name}: steps.{ref} has no matching step id")

        needs = job.get("needs", [])
        needs = [needs] if isinstance(needs, str) else needs
        for dep in needs:
            if dep not in jobs:
                problems.append(f"{job_name}: needs '{dep}' which is not a job")

        for dep, out in set(re.findall(r"needs\.([A-Za-z0-9_-]+)\.outputs\.([A-Za-z0-9_-]+)", blob)):
            if dep not in needs:
                problems.append(f"{job_name}: uses needs.{dep} without declaring it")
            elif out not in (jobs[dep].get("outputs") or {}):
                problems.append(f"{job_name}: needs.{dep}.outputs.{out} is not declared by '{dep}'")

        for out_name, expr in (job.get("outputs") or {}).items():
            for ref in re.findall(r"steps\.([A-Za-z0-9_-]+)\.outputs", str(expr)):
                if ref not in step_ids:
                    problems.append(f"{job_name}: output '{out_name}' reads missing step id '{ref}'")

    assert not problems, "\n".join(problems)


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_run_blocks_are_valid_shell(path, tmp_path):
    if not shutil.which("bash"):
        pytest.skip("bash not available")

    doc = _load(path)
    errors: list[str] = []
    for job_name, job in doc["jobs"].items():
        for i, step in enumerate(job.get("steps", [])):
            script = step.get("run")
            if not script or step.get("shell") in {"pwsh", "powershell", "python"}:
                continue
            # GitHub expressions are substituted before bash ever sees them
            neutral = re.sub(r"\$\{\{[^}]*\}\}", "PLACEHOLDER", script)
            candidate = tmp_path / f"{job_name}_{i}.sh"
            candidate.write_text("#!/usr/bin/env bash\n" + neutral, encoding="utf-8")
            result = subprocess.run(["bash", "-n", str(candidate)], capture_output=True, text=True)
            if result.returncode != 0:
                errors.append(f"{job_name} step {i} ({step.get('name', '')}): {result.stderr.strip()}")
    assert not errors, "\n".join(errors)


# ===========================================================================
# safety properties of the model deployment pipeline
# ===========================================================================
@pytest.fixture(scope="module")
def model_deploy() -> dict:
    return _load(WORKFLOW_DIR / "model-deploy.yml")


def test_deploy_is_gated_on_the_promotion_decision(model_deploy):
    deploy = model_deploy["jobs"]["deploy"]
    assert "gate" in deploy["needs"], "deploy must depend on the gate job"
    condition = deploy["if"]
    assert "needs.gate.outputs.promote == 'true'" in condition, "deploy must run only when the gate promotes"
    assert "dryRun" in condition, "a dry run must not deploy"


def test_gate_runs_before_any_registration(model_deploy):
    """Registration lives in deploy, which is gated - never in the gate job."""
    gate_blob = yaml.safe_dump(model_deploy["jobs"]["gate"])
    assert "az ml model create" not in gate_blob
    assert "online-deployment create" not in gate_blob


def test_new_deployment_is_created_with_zero_traffic(model_deploy):
    steps = model_deploy["jobs"]["deploy"]["steps"]
    names = [s.get("name", "") for s in steps]
    create = next(i for i, n in enumerate(names) if "Create the new deployment" in n)
    smoke = next(i for i, n in enumerate(names) if "Smoke-test" in n)
    shift = next(i for i, n in enumerate(names) if "Shift 100%" in n)
    assert create < smoke < shift, "must be: create -> smoke test -> shift traffic"


def test_rollback_step_exists_and_triggers_on_failure(model_deploy):
    steps = model_deploy["jobs"]["deploy"]["steps"]
    rollback = next((s for s in steps if "Roll back" in s.get("name", "")), None)
    assert rollback is not None, "there must be a rollback step"
    assert "failure()" in rollback["if"]
    assert "online-deployment delete" in rollback["run"], "rollback must remove the bad slot"


def test_old_deployment_is_only_retired_on_success(model_deploy):
    steps = model_deploy["jobs"]["deploy"]["steps"]
    retire = next(s for s in steps if "Retire the previous" in s.get("name", ""))
    assert "success()" in retire["if"], "never delete the incumbent unless the new slot is live"


def test_blocked_promotion_is_reported(model_deploy):
    blocked = model_deploy["jobs"]["blocked"]
    assert "needs.gate.outputs.promote != 'true'" in blocked["if"]


def test_concurrency_prevents_interrupted_traffic_shifts(model_deploy):
    assert model_deploy["concurrency"]["cancel-in-progress"] is False


def test_deployment_uses_oidc_not_stored_credentials(workflows):
    for name in ("deploy-azure.yml", "model-deploy.yml"):
        doc = workflows[name]
        assert doc["permissions"]["id-token"] == "write", f"{name} needs OIDC permission"
        blob = yaml.safe_dump(doc)
        assert "creds:" not in blob, f"{name} must not use a stored service-principal secret"


def test_prod_deployment_can_require_approval(model_deploy):
    """`environment:` on the deploy job is what enables a protection rule."""
    assert "environment" in model_deploy["jobs"]["deploy"]


def test_sample_request_is_committed_for_the_smoke_test():
    sample = ROOT / "infra" / "aml" / "sample-request.json"
    assert sample.exists(), "the smoke test invokes the endpoint with this file"
    payload = yaml.safe_load(sample.read_text(encoding="utf-8"))
    assert payload["records"], "sample request must contain at least one record"
