param(
    [ValidateSet("all", "contract", "replay-golden", "evaluation-recovery")]
    [string] $Target = "all"
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$Python = if (Test-Path $VenvPython) { $VenvPython } else { "python" }
$env:PYTHONPATH = Join-Path $RepoRoot "src"

switch ($Target) {
    "all" {
        & $Python -m pytest
    }
    "contract" {
        & $Python -m pytest tests/contract
    }
    "replay-golden" {
        & $Python -m pytest tests/unit/test_market_data_repository_reconciliation.py tests/integration/test_research_pipeline.py
    }
    "evaluation-recovery" {
        & $Python -m pytest tests/integration/test_research_pipeline.py
    }
}
