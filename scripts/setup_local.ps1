<#
.SYNOPSIS
    One-shot local setup: virtual environment, dependencies, and a full
    pipeline run so the dashboard and API have something to serve.

.EXAMPLE
    ./scripts/setup_local.ps1
    ./scripts/setup_local.ps1 -WithDeep      # also install PyTorch (needs MSVC runtime)
#>
[CmdletBinding()]
param(
    [switch]$WithDeep,
    [switch]$SkipPipeline,
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "==> Creating virtual environment" -ForegroundColor Cyan
& $Python -m venv .venv

$venvPython = Join-Path $root ".venv/Scripts/python.exe"
if (-not (Test-Path $venvPython)) { $venvPython = Join-Path $root ".venv/bin/python" }

Write-Host "==> Installing dependencies" -ForegroundColor Cyan
& $venvPython -m pip install --upgrade pip --quiet
& $venvPython -m pip install -r requirements.txt -r requirements-dev.txt --quiet
& $venvPython -m pip install -e . --no-deps --quiet
if ($WithDeep) {
    & $venvPython -m pip install -r requirements-deep.txt --quiet
}

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "    created .env from .env.example"
}

Write-Host "==> Running the test suite" -ForegroundColor Cyan
& $venvPython -m pytest tests -q

if (-not $SkipPipeline) {
    Write-Host "==> Running the full pipeline (this takes a few minutes)" -ForegroundColor Cyan
    & $venvPython -m drg.cli run-all
}

Write-Host ""
Write-Host "Ready." -ForegroundColor Green
Write-Host "  Dashboard : .venv/Scripts/python -m drg.cli dashboard"
Write-Host "  API       : .venv/Scripts/python -m drg.cli serve"
