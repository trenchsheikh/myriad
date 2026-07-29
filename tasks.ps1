# Myriad task runner for Windows (PowerShell).
# Usage:  .\tasks.ps1 understat
#         .\tasks.ps1 help

param(
    [Parameter(Position = 0)]
    [string]$Task = "help"
)

# Don't treat native-command stderr (Python logging) as terminating errors.
$ErrorActionPreference = "Continue"

function Invoke-Uv {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$UvArgs)
    # Ensure repo-root imports (eval/, models/, ...) resolve when running scripts/*.py
    $env:PYTHONPATH = (Resolve-Path $PSScriptRoot).Path
    & uv @UvArgs
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

switch ($Task.ToLower()) {
    "ingest" {
        Invoke-Uv run python -m loaders.crowd_to_duck
    }
    "results" {
        Invoke-Uv run python -m collectors.results
    }
    "resolve-teams" {
        Invoke-Uv run python -m loaders.resolve_team
    }
    "understat" {
        Invoke-Uv run python -m collectors.understat
    }
    "fixtures" {
        Invoke-Uv run python -m collectors.fixtures
    }
    "check-gaps" {
        Invoke-Uv run python scripts/check_gaps.py
    }
    "load" {
        Invoke-Uv run python scripts/full_load.py --skip-download
    }
    "audit" {
        Invoke-Uv run python scripts/data_audit.py
    }
    "fit-dc" {
        Invoke-Uv run python scripts/fit_dixon_coles.py
    }
    "backtest" {
        # Smoke window by default; full season: uv run python -m backtest.walkforward --start 2015-08-01 --end 2026-05-31
        Invoke-Uv run python -m backtest.walkforward --start 2024-08-15 --end 2025-05-31 --max-matchdays 5
    }
    "score" {
        Invoke-Uv run python scripts/score_backtest.py
    }
    "tune-xi" {
        Invoke-Uv run python scripts/tune_xi.py
    }
    "full-backtest" {
        # Requires docs/xi_best.txt from tune-xi
        $hl = "182.5"
        if (Test-Path "$PSScriptRoot\docs\xi_best.txt") {
            $hl = (Get-Content "$PSScriptRoot\docs\xi_best.txt" -Raw).Trim()
        }
        Write-Host "full backtest half-life=$hl"
        Invoke-Uv run python -m backtest.walkforward --start 2015-08-01 --end 2026-05-31 --half-life $hl
    }
    "calibrate" {
        Invoke-Uv run python scripts/plot_calibration.py
    }
    "simulate" {
        Write-Host "not yet implemented (Day 20)"
    }
    "publish" {
        Write-Host "not yet implemented (Day 24)"
    }
    "help" {
        Write-Host @"
Myriad tasks (Windows):

  .\tasks.ps1 ingest         Load crowd Parquet into DuckDB
  .\tasks.ps1 results        Download football-data results
  .\tasks.ps1 resolve-teams  Canonical team IDs -> matches
  .\tasks.ps1 understat      Pull Understat xG and join
  .\tasks.ps1 fixtures       Load 2026-27 FPL fixtures + stadiums
  .\tasks.ps1 check-gaps     Assert crowd capture gaps <= 90 min
  .\tasks.ps1 load           Full rebuild of DuckDB (reuse cached downloads)
  .\tasks.ps1 audit         Run Day 8 data audit checks
  .\tasks.ps1 fit-dc        Fit Dixon-Coles baseline (Day 9)
  .\tasks.ps1 backtest      Walk-forward smoke (5 matchdays)
  .\tasks.ps1 score         Score predictions vs results + benchmarks
  .\tasks.ps1 tune-xi       Grid-search half-life on early seasons
  .\tasks.ps1 full-backtest Full walk-forward 2015-26 with best ξ
  .\tasks.ps1 calibrate     Write docs/calibration.png

Or call uv directly, e.g.:
  uv run python -m collectors.understat
"@
    }
    default {
        Write-Error "Unknown task '$Task'. Run .\tasks.ps1 help"
        exit 1
    }
}
