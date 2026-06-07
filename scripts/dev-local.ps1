<#
.SYNOPSIS
  Spin up the polyglot-pdf frontend + backend LOCALLY for development and
  full-fidelity Gemini I/O logging.

.DESCRIPTION
  Starts:
    - Backend  : uvicorn backend.main:app on http://localhost:8000
                 (port 8000 is what the frontend's dev WS URL defaults to:
                 ws://localhost:8000/ws/fill -- see frontend/src/shared/config.ts)
    - Frontend : vite dev server on http://localhost:5173 (npm run dev)

  Local dev runs against the Gemini Developer API (AI Studio), which has the
  3.1 model, so it forces VERTEXAI=false and requires GEMINI_API_KEY.

  It also ensures backend/.env.DEV exists so the dev file logger captures FULL
  message bodies (tool-call args, tool responses, hints) to
  backend/logs/gemini_YYYY-MM-DD.jsonl. That marker file + that logs dir are
  gitignored and never ship to Cloud Run, so production logs stay PII-free.

  This is a DEV-ONLY convenience runner. It does NOT deploy anything.

.PARAMETER Model
  Which native-audio Live model to run, for A/B testing tool-call reliability:
    premium  -> gemini-3.1-flash-live-preview            (default)
    standard -> gemini-2.5-flash-native-audio-preview-12-2025
  Maps to USE_PREMIUM_MODEL. To pin an exact id instead, set $env:MODEL_NATIVE
  before launching (non-empty MODEL_NATIVE wins over this flag).

.PARAMETER BackendOnly
  Start only the backend (skip the frontend vite server).

.PARAMETER NoDevLog
  Do NOT create backend/.env.DEV. Use when you explicitly want production-style
  (redacted) logging locally. Full message bodies will NOT be captured.

.EXAMPLE
  ./scripts/dev-local.ps1
  Start both servers on the 3.1 model with full dev logging.

.EXAMPLE
  ./scripts/dev-local.ps1 -Model standard
  Same, but on the 2.5 model (A/B comparison).

.NOTES
  Stop everything with Ctrl-C in this window; the script tears down both child
  processes on exit. Logs to tail: backend/logs/gemini_*.jsonl
#>
[CmdletBinding()]
param(
    [ValidateSet('premium', 'standard')]
    [string]$Model = 'premium',
    [switch]$BackendOnly,
    [switch]$NoDevLog
)

$ErrorActionPreference = 'Stop'

# Resolve repo root from this script's location (scripts/ is at repo root).
# Use the git common dir so this works from a worktree too: the venv lives only
# in the MAIN repo, but the frontend/backend SOURCE is in whichever checkout
# this script sits in -- so source paths are relative to the script, while the
# python interpreter comes from the main repo.
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptDir

Push-Location $RepoRoot
try {
    $CommonDir = (& git rev-parse --path-format=absolute --git-common-dir 2>$null)
    if ($LASTEXITCODE -eq 0 -and $CommonDir) {
        $MainRepo = Split-Path -Parent $CommonDir
    } else {
        $MainRepo = $RepoRoot
    }
} finally {
    Pop-Location
}

$VenvPython = Join-Path $MainRepo 'backend\.venv\Scripts\python.exe'
$BackendLogDir = Join-Path $RepoRoot 'backend\logs'
$EnvDevMarker = Join-Path $RepoRoot 'backend\.env.DEV'

Write-Host "=== polyglot-pdf local dev runner ===" -ForegroundColor Cyan
Write-Host "Repo (source) : $RepoRoot"
Write-Host "Main repo venv: $MainRepo"
Write-Host "Model         : $Model"

# --- Preflight checks ---------------------------------------------------------
if (-not (Test-Path $VenvPython)) {
    Write-Host "ERROR: backend venv not found at $VenvPython" -ForegroundColor Red
    Write-Host "Create it in the MAIN repo: python -m venv backend/.venv; " -NoNewline
    Write-Host "backend/.venv/Scripts/pip install -r backend/requirements.txt"
    exit 1
}

if (-not $env:GEMINI_API_KEY) {
    # backend/.env is auto-loaded by load_dotenv() at backend/main.py, so the key
    # may live there even if it's not in this shell. Only warn -- do not block.
    $BackendEnv = Join-Path $RepoRoot 'backend\.env'
    if (Test-Path $BackendEnv) {
        Write-Host "NOTE: GEMINI_API_KEY not in this shell; relying on backend/.env (load_dotenv)." -ForegroundColor Yellow
    } else {
        Write-Host "WARNING: GEMINI_API_KEY is not set and backend/.env does not exist." -ForegroundColor Yellow
        Write-Host "  Local dev uses AI Studio (VERTEXAI=false), which REQUIRES an API key." -ForegroundColor Yellow
        Write-Host "  Set it: \$env:GEMINI_API_KEY = '<your-key>'  (or add it to backend/.env)" -ForegroundColor Yellow
    }
}

if (-not $BackendOnly) {
    $NodeModules = Join-Path $RepoRoot 'frontend\node_modules'
    if (-not (Test-Path $NodeModules)) {
        Write-Host "ERROR: frontend/node_modules missing. Run 'npm install' in frontend/ first." -ForegroundColor Red
        exit 1
    }
}

# --- Dev logging marker -------------------------------------------------------
if (-not $NoDevLog) {
    if (-not (Test-Path $EnvDevMarker)) {
        # The dev file logger keys ONLY on the existence of this file, not its
        # contents (backend/utils/dev_file_logger.py). It is gitignored.
        Set-Content -Path $EnvDevMarker -Value "# Presence of this file enables local full-body Gemini logging (dev only). Gitignored." -Encoding ascii
        Write-Host "Created $EnvDevMarker (full-body dev logging ON)." -ForegroundColor Green
    } else {
        Write-Host "Dev logging marker present: $EnvDevMarker (full-body logging ON)." -ForegroundColor Green
    }
    Write-Host "Captured Gemini I/O -> $BackendLogDir\gemini_<date>.jsonl" -ForegroundColor Green
} else {
    Write-Host "NoDevLog set: NOT creating .env.DEV (production-style redacted logging)." -ForegroundColor Yellow
}

# --- Model selection ----------------------------------------------------------
if ($Model -eq 'premium') {
    $UsePremium = 'true'
} else {
    $UsePremium = 'false'
}

# --- Launch backend -----------------------------------------------------------
# Run uvicorn on port 8000 to match the frontend's default WS URL. Run from the
# SOURCE repo root (so backend.main imports this checkout's code) using the main
# repo's venv interpreter.
#
# Set the backend's env vars on THIS process before launching. Start-Process
# inherits the parent environment, and -NoNewWindow keeps it in this console.
# (We avoid Start-Process -Environment: that parameter only exists on
# PowerShell 7.4+, and this repo targets Windows PowerShell 5.1 too.) We snapshot
# and restore the prior values so a re-run in the same shell stays clean.
$BackendArgs = @(
    '-m', 'uvicorn', 'backend.main:app',
    '--host', '127.0.0.1', '--port', '8000', '--reload'
)
$BackendEnvVars = @{
    'VERTEXAI'          = 'false'
    'USE_PREMIUM_MODEL' = $UsePremium
    'PYTHONPATH'        = $RepoRoot
    'PYTHONUNBUFFERED'  = '1'
}
$PriorEnv = @{}
foreach ($k in $BackendEnvVars.Keys) {
    $PriorEnv[$k] = [Environment]::GetEnvironmentVariable($k, 'Process')
    Set-Item -Path "Env:$k" -Value $BackendEnvVars[$k]
}

Write-Host ""
Write-Host "Starting backend (uvicorn :8000, VERTEXAI=false, USE_PREMIUM_MODEL=$UsePremium)..." -ForegroundColor Cyan

try {
    $BackendProc = Start-Process -FilePath $VenvPython -ArgumentList $BackendArgs `
        -WorkingDirectory $RepoRoot -PassThru -NoNewWindow
} finally {
    # Restore this shell's env immediately; the child already inherited the values.
    foreach ($k in $BackendEnvVars.Keys) {
        if ($null -eq $PriorEnv[$k]) {
            Remove-Item -Path "Env:$k" -ErrorAction SilentlyContinue
        } else {
            Set-Item -Path "Env:$k" -Value $PriorEnv[$k]
        }
    }
}

$FrontendProc = $null
if (-not $BackendOnly) {
    Write-Host "Starting frontend (vite dev :5173)..." -ForegroundColor Cyan
    $FrontendDir = Join-Path $RepoRoot 'frontend'
    # npm is resolved from PATH; run 'npm run dev' (the schema-forms voice SPA).
    $FrontendProc = Start-Process -FilePath 'npm.cmd' -ArgumentList @('run', 'dev') `
        -WorkingDirectory $FrontendDir -PassThru -NoNewWindow
}

Write-Host ""
Write-Host "=== Local stack up ===" -ForegroundColor Green
Write-Host "  Backend : http://localhost:8000  (health: /health)"
if (-not $BackendOnly) { Write-Host "  Frontend: http://localhost:5173" }
Write-Host "  Logs    : $BackendLogDir\gemini_<date>.jsonl"
Write-Host ""
Write-Host "Press Ctrl-C to stop both." -ForegroundColor Yellow

# --- Wait + teardown ----------------------------------------------------------
try {
    while ($true) {
        if ($BackendProc.HasExited) {
            Write-Host "Backend exited (code $($BackendProc.ExitCode))." -ForegroundColor Red
            break
        }
        if ($FrontendProc -and $FrontendProc.HasExited) {
            Write-Host "Frontend exited (code $($FrontendProc.ExitCode))." -ForegroundColor Red
            break
        }
        Start-Sleep -Milliseconds 500
    }
} finally {
    Write-Host ""
    Write-Host "Shutting down..." -ForegroundColor Cyan
    foreach ($p in @($BackendProc, $FrontendProc)) {
        if ($p -and -not $p.HasExited) {
            try { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue } catch {}
        }
    }
    Write-Host "Stopped." -ForegroundColor Cyan
}
