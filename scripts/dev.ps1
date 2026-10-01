<#
.SYNOPSIS
  Developer entry points for Windows PowerShell — same targets as the Makefile.
.EXAMPLE
  .\scripts\dev.ps1 test
  .\scripts\dev.ps1 up
#>
param(
    [Parameter(Position = 0)]
    [ValidateSet("help", "install", "lock", "upgrade", "upgrade-agent", "up", "down", "test", "test-backend", "test-agent", "test-legacy", "lint", "lint-py", "hooks", "ci", "typecheck", "migrate", "cli")]
    [string]$Task = "help",
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$CliArgs
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Py = Join-Path $Root ".venv\Scripts\python.exe"

function Invoke-Step([string]$Description, [scriptblock]$Block) {
    Write-Host ">> $Description" -ForegroundColor Cyan
    & $Block
    if ($LASTEXITCODE -ne 0) { throw "$Description failed (exit $LASTEXITCODE)" }
}

function Start-TestDb {
    Invoke-Step "start postgres-test" { docker compose up -d --wait postgres-test }
}

Push-Location $Root
try {
    switch ($Task) {
        "help" {
            Write-Host "install    install backend + agent runtime deps and dev tooling into .venv, npm ci"
            Write-Host "lock       recompile backend/ and agent/ requirements.txt from requirements.in"
            Write-Host "up         start the whole stack in Docker (migrate, backend, agent, frontend)"
            Write-Host "down       stop it"
            Write-Host "test       start postgres-test, run every pytest suite and the frontend tests"
            Write-Host "lint       oxlint (frontend)"
            Write-Host "typecheck  tsc -b (frontend)"
            Write-Host "migrate    alembic upgrade head against DATABASE_URL"
            Write-Host "cli        python -m backend.cli <args>   e.g. .\scripts\dev.ps1 cli finalize-stuck-sessions --dry-run"
        }
        "install" {
            Invoke-Step "pip install" { & $Py -m pip install -r backend/requirements.txt -r agent/requirements.txt -r requirements-dev.txt }
            Invoke-Step "npm ci" { Push-Location frontend; npm ci; Pop-Location }
        }
        "lock" {
            # Agent first: both locks install into one environment, so the
            # backend is compiled against the agent's result as a constraint.
            # See the Makefile's `lock` target for why.
            # NOTE: this RE-RESOLVES; pip-compile keeps versions already
            # pinned in the output. It does not pull newer releases -- that
            # is `upgrade`.
            Invoke-Step "compile agent lock" { & $Py -m piptools compile --strip-extras --no-header -o agent/requirements.txt agent/requirements.in }
            Invoke-Step "compile backend lock" { & $Py -m piptools compile --strip-extras --no-header -c agent/requirements.txt -o backend/requirements.txt backend/requirements.in }
            Invoke-Step "check they coexist" { & $Py -m pytest -q backend/tests/test_requirements.py }
        }
        "upgrade" {
            # Pulls the newest releases the .in files allow. Backend only:
            # the agent lock carries livekit-agents and `av`, which no test
            # here can verify (the agent suite runs against fakes, with no
            # LiveKit server), so bumping those needs a real spoken
            # interview afterwards -- use `upgrade-agent` deliberately.
            Invoke-Step "upgrade backend lock" { & $Py -m piptools compile --upgrade --strip-extras --no-header -c agent/requirements.txt -o backend/requirements.txt backend/requirements.in }
            Invoke-Step "check they coexist" { & $Py -m pytest -q backend/tests/test_requirements.py }
        }
        "upgrade-agent" {
            Invoke-Step "upgrade agent lock" { & $Py -m piptools compile --upgrade --strip-extras --no-header -o agent/requirements.txt agent/requirements.in }
            Invoke-Step "recompile backend against it" { & $Py -m piptools compile --strip-extras --no-header -c agent/requirements.txt -o backend/requirements.txt backend/requirements.in }
            Invoke-Step "check they coexist" { & $Py -m pytest -q backend/tests/test_requirements.py }
        }
        "up"   { Invoke-Step "docker compose up" { docker compose --profile app up --build } }
        "down" { Invoke-Step "docker compose down" { docker compose --profile app down } }
        "test" {
            Start-TestDb
            Invoke-Step "pytest (backend, agent, legacy)" { & $Py -m pytest -q }
            Invoke-Step "vitest" { Push-Location frontend; npm test; Pop-Location }
        }
        "test-backend" { Start-TestDb; Invoke-Step "pytest backend/tests" { & $Py -m pytest -q backend/tests } }
        "test-agent"   { Invoke-Step "pytest agent" { & $Py -m pytest -q agent } }
        "test-legacy"  { Start-TestDb; Invoke-Step "pytest tests/legacy" { & $Py -m pytest -q tests/legacy } }
        "lint"      { Invoke-Step "oxlint" { Push-Location frontend; npx oxlint src; Pop-Location } }
        "lint-py"   { Invoke-Step "ruff check" { & $Py -m ruff check . } }
        "hooks"     { Invoke-Step "pre-commit install" { & $Py -m pre_commit install } }
        "ci"        {
            # The same gates as .github/workflows/ci.yml, in the same order.
            Invoke-Step "ruff check" { & $Py -m ruff check . }
            Start-TestDb
            Invoke-Step "pytest" { & $Py -m pytest -q --cov=backend/backend --cov=agent/agent --cov-report=term-missing:skip-covered }
            Invoke-Step "frontend" { Push-Location frontend; npm run typecheck; npm run lint; npm test; npm run build:only; Pop-Location }
        }
        "typecheck" { Invoke-Step "tsc -b" { Push-Location frontend; npm run typecheck; Pop-Location } }
        "migrate"   { Invoke-Step "alembic upgrade head" { Push-Location backend; & $Py -m alembic upgrade head; Pop-Location } }
        "cli"       { Invoke-Step "backend.cli" { $env:PYTHONPATH = "backend"; & $Py -m backend.cli @CliArgs } }
    }
}
finally {
    Pop-Location
}
