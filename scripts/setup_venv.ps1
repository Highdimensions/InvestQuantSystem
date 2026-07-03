param(
    [switch] $WithAkshare
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$VenvDir = Join-Path $RepoRoot ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"

if (-not (Test-Path $VenvPython)) {
    python -m venv $VenvDir
}

& $VenvPython -m pip install --upgrade pip

$Requirements = if ($WithAkshare) {
    Join-Path $RepoRoot "requirements-akshare.txt"
} else {
    Join-Path $RepoRoot "requirements.txt"
}

& $VenvPython -m pip install -r $Requirements
& $VenvPython -m pip install --no-deps -e $RepoRoot

Write-Host "Virtual environment ready: $VenvDir"
Write-Host "Activate with: .\.venv\Scripts\Activate.ps1"
