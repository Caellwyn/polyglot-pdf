<#
.SYNOPSIS
  Spin up the polyglot-pdf frontend + backend LOCALLY for development and
  full-fidelity Gemini I/O logging.

.DESCRIPTION
  Starts:
    - Backend  : uvicorn backend.main:app on http://localhost:8000
                 (port 8000 is what the frontend's dev WS URL defaults to:
                 ws://localhost:8000/ws/fill -- see frontend/src/shared/config.ts)
    - Frontend : vite dev server on http://localhost:5173, started with
                 `--mode demo` + a process-env VITE_WS_URL pointing at the LOCAL
                 backend. Both are load-bearing: without --mode demo the
                 Firebase config is undefined and the SPA renders a BLANK WHITE
                 SCREEN; without the WS override it would silently talk to the
                 DEPLOYED backend instead of the one this script just started.

  Local dev runs on VERTEX by default (ADC + GOOGLE_CLOUD_PROJECT), so ALL local
  spend lands on the ONE Vertex billing account -- never AI Studio (bd
  polyglot-pdf-6les). The premium (3.1) arm is the sole exception: 3.1 is
  AI-Studio-only for now, so -Model premium uses VERTEXAI=false + GEMINI_API_KEY
  and bills to the AI Studio account.

  It also ensures backend/.env.DEV exists so the dev file logger captures FULL
  message bodies (tool-call args, tool responses, hints) to
  backend/logs/gemini_YYYY-MM-DD.jsonl. That marker file + that logs dir are
  gitignored and never ship to Cloud Run, so production logs stay PII-free.

  This is a DEV-ONLY convenience runner. It does NOT deploy anything.

.PARAMETER Model
  Which native-audio Live model to run, for A/B testing tool-call reliability:
    standard -> gemini-2.5-flash-native-audio-preview-12-2025 (default; mirrors
                the deployed demo/prod default since bd polyglot-pdf-5oq)
    premium  -> gemini-3.1-flash-live-preview            (opt-in; unreliable
                tool-calling in audio mode)
  Maps to USE_PREMIUM_MODEL. To pin an exact id instead, set $env:MODEL_NATIVE
  before launching (non-empty MODEL_NATIVE wins over this flag).

.PARAMETER BackendOnly
  Start only the backend (skip the frontend vite server).

.PARAMETER NoDevLog
  Do NOT create backend/.env.DEV. Use when you explicitly want production-style
  (redacted) logging locally. Full message bodies will NOT be captured.

.PARAMETER Temperature
  Sampling temperature for the Live session (bd polyglot-pdf-0rpu). Omit to
  send nothing and keep Google's default (1.0). NOT local-dev-only any more:
  LIVE_TEMPERATURE is honored in deployed services too as of 2026-08-10 (the
  demo deploys at 0.4), so this switch is the local equivalent of that env
  var, not a dev-only escape hatch.

  Why you would set it: at the default 1.0 the model sometimes prefers a
  conversationally-plausible continuation over the literal tool response. A
  logged session shows it handed "Stored value: name_1b_last = 'Smith'" and
  telling the user "You said Jose" -- a value from two fields earlier. Lower
  temperature biases toward literal instruction-following.

  SWEEP 0.3-0.6. Do NOT pass 0: googleapis/js-genai#1578 reports runaway /
  no-audio output and a 1011 session close at temperature 0 on native audio.
  Values <=0 or >2 are rejected by the adapter and ignored.

  This knob is DOUBLE-GATED on backend/.env.DEV, so it does nothing in a
  deployed service even if the env var is set -- deliberately.

.PARAMETER Transcripts
  LOCAL-DEV-ONLY: capture what was SAID (both sides) into
  backend/logs/gemini_YYYY-MM-DD.jsonl as `transcript` records.

  Without it, the log proves what was STORED but not what reached the user's
  ears -- which is why bd 0rpu took three rounds to diagnose. Turn this on when
  chasing any "she said the wrong thing" report.

  PRIVACY: transcripts are PHI. Gated on backend/.env.DEV (gitignored, never
  deployed) AND this opt-in, so it cannot turn on in production.

.EXAMPLE
  ./scripts/dev-local.ps1
  Start both servers on the 2.5 model (the deployed default) with full dev logging.

.EXAMPLE
  ./scripts/dev-local.ps1 -Model premium
  Same, but on the 3.1 model (A/B comparison).

.EXAMPLE
  ./scripts/dev-local.ps1 -Temperature 0.4 -Transcripts
  The bd 0rpu prototyping loop: lower the sampling temperature AND record what
  was said, so a wrong read-back can be read straight out of the log instead of
  inferred. Sweep 0.6 -> 0.4 -> 0.3, restarting between values, and grep the log:

    Select-String -Path backend/logs/gemini_*.jsonl -Pattern '"transcript"'

  Each hit carries {heard_from_user, spoken_by_model}; compare spoken_by_model
  against the `stored_values` in the neighbouring tool_response to see whether
  the model read back the value it was actually handed.

.NOTES
  Stop everything with Ctrl-C in this window; the script tears down both child
  processes on exit. Logs to tail: backend/logs/gemini_*.jsonl
#>
[CmdletBinding()]
param(
    [ValidateSet('premium', 'standard')]
    [string]$Model = 'standard',
    [switch]$BackendOnly,
    [switch]$NoDevLog,
    # 0 is rejected on purpose: it is a KNOWN native-audio session killer
    # (googleapis/js-genai#1578 -- runaway/no-audio output + a 1011 close), so
    # the runner refuses it up front rather than letting the adapter silently
    # drop it. Leave unset to send no temperature at all (Google default 1.0).
    [ValidateRange(0.1, 2.0)]
    [double]$Temperature = 0,
    [switch]$Transcripts
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
    Write-Host "backend/.venv/Scripts/pip install -r backend/requirements-dev.txt"
    exit 1
}

# Credential preflight (bd polyglot-pdf-6les). The DEFAULT (standard) arm runs on
# Vertex, which authenticates via Application Default Credentials (ADC) +
# GOOGLE_CLOUD_PROJECT -- NOT an API key. The premium (3.1) arm runs on AI Studio
# and DOES need GEMINI_API_KEY. Warn per the arm actually selected.
if ($Model -eq 'premium') {
    if (-not $env:GEMINI_API_KEY) {
        # backend/.env is auto-loaded by load_dotenv() at backend/main.py, so the
        # key may live there even if it's not in this shell. Only warn -- do not block.
        $BackendEnv = Join-Path $RepoRoot 'backend\.env'
        if (Test-Path $BackendEnv) {
            Write-Host "NOTE: GEMINI_API_KEY not in this shell; relying on backend/.env (load_dotenv)." -ForegroundColor Yellow
        } else {
            Write-Host "WARNING: premium arm uses AI Studio (VERTEXAI=false), which REQUIRES GEMINI_API_KEY," -ForegroundColor Yellow
            Write-Host "  but it is not set and backend/.env does not exist." -ForegroundColor Yellow
            Write-Host "  Set it: \$env:GEMINI_API_KEY = '<your-key>'  (or add it to backend/.env)" -ForegroundColor Yellow
        }
    }
} else {
    # Vertex ADC lives at the well-known gcloud path; if it is absent, Vertex calls
    # will fail auth. Warn (do not block) -- the user may have ADC via a
    # service-account key env instead. Guard the base path: under
    # $ErrorActionPreference='Stop', Join-Path with a null base (a stripped
    # %APPDATA%) would THROW and abort the runner; fall back to $HOME\AppData\Roaming
    # (or CLOUDSDK_CONFIG if the user relocated the gcloud config dir).
    $GcloudDir = if ($env:CLOUDSDK_CONFIG) { $env:CLOUDSDK_CONFIG }
                 elseif ($env:APPDATA)     { Join-Path $env:APPDATA 'gcloud' }
                 else                      { Join-Path $HOME 'AppData\Roaming\gcloud' }
    $Adc = Join-Path $GcloudDir 'application_default_credentials.json'
    if (-not (Test-Path $Adc) -and -not $env:GOOGLE_APPLICATION_CREDENTIALS) {
        Write-Host "WARNING: Vertex (default) needs Application Default Credentials, but none found." -ForegroundColor Yellow
        Write-Host "  Run 'gcloud auth application-default login', or set GOOGLE_APPLICATION_CREDENTIALS." -ForegroundColor Yellow
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

# --- Model + backend selection ------------------------------------------------
# ALL sessions run on VERTEX by default so spend lands on ONE billing account
# (bd polyglot-pdf-6les; maintainer directive 2026-07-15). The premium (3.1) arm
# is the sole exception: 3.1 is AI-Studio-only for now, so it MUST use
# VERTEXAI=false + GEMINI_API_KEY -- a model-availability constraint, not a
# billing choice -- and therefore bills to the AI Studio account (warned below).
if ($Model -eq 'premium') {
    $UsePremium = 'true'
    $VertexAi = 'false'
    Write-Host "WARNING: premium (3.1) arm runs on AI STUDIO (VERTEXAI=false) -- 3.1 is not on Vertex yet." -ForegroundColor Yellow
    Write-Host "  This arm bills to the AI Studio account, NOT the Vertex project. Use the default (standard) arm for Vertex." -ForegroundColor Yellow
} else {
    $UsePremium = 'false'
    $VertexAi = 'true'
}

# --- Launch backend -----------------------------------------------------------
# Run uvicorn on port 8000 to match the frontend's default WS URL. Run with
# backend/ as the working directory (reload-watch scoping -- see $BackendArgs)
# using the main repo's venv interpreter; PYTHONPATH=$RepoRoot keeps
# backend.main importing THIS checkout's code.
#
# Set the backend's env vars on THIS process before launching. Start-Process
# inherits the parent environment, and -NoNewWindow keeps it in this console.
# (We avoid Start-Process -Environment: that parameter only exists on
# PowerShell 7.4+, and this repo targets Windows PowerShell 5.1 too.) We snapshot
# and restore the prior values so a re-run in the same shell stays clean.
$BackendArgs = @(
    '-m', 'uvicorn', 'backend.main:app',
    '--host', '127.0.0.1', '--port', '8000', '--reload',
    # Scope the reload watcher to backend/. The scoping is done by launching
    # uvicorn with backend/ as its WORKING DIRECTORY (see Start-Process below):
    # uvicorn's WatchFiles supervisor DROPS any reload dir that is a child of
    # the process cwd and watches the cwd instead (uvicorn 0.24, unchanged
    # upstream), so with cwd at the repo root every --reload-dir form collapsed
    # to watching the WHOLE root -- including .claude/worktrees/ with its ~130
    # sibling checkouts, so an agent editing any .py in ANY of them restarted
    # this backend. With cwd == the reload dir the supervisor keeps exactly
    # that dir; the absolute --reload-dir is kept because newer uvicorns honor
    # it directly. Safe to move the cwd: PYTHONPATH (set below) pins imports
    # to the repo root, and backend runtime paths anchor on __file__, not cwd.
    # backend/ imports no other top-level package (shared/ is one JSON file,
    # no Python).
    '--reload-dir', (Join-Path $RepoRoot 'backend')
)
# GOOGLE_CLOUD_PROJECT is used by the Vertex path (google-genai + ADC); harmless
# on the Studio (premium) path, which uses GEMINI_API_KEY. Respect an already-set
# value so a different project can be used per run.
$VertexProject = if ($env:GOOGLE_CLOUD_PROJECT) { $env:GOOGLE_CLOUD_PROJECT } else { 'polyglot-demo-aa709' }
# VFF_DISABLE_AUTH=true bypasses Firebase token verification, matching
# scripts/dev-local.sh (bd polyglot-pdf-zeqt -- this script never set it, so the
# POSIX and PowerShell dev paths diverged). Locally, firebase_admin uses ADC and
# verify_id_token() validates against the ADC project + fetches Google's signing
# keys, which times out / mismatches the demo project's token: the WS handshake
# silently times out and the SPA falls back to Cloud Run, so your local backend
# never sees the session. Since bd polyglot-pdf-z2is the same verification also
# gates /api/fill-pdf and /api/form-kits*, so WITHOUT this the local form
# CATALOGUE 401s and the app shows "Unable to load forms" -- a wider break than
# the original WS-only symptom. Override per run: $env:VFF_DISABLE_AUTH='false'
$DisableAuth = if ($env:VFF_DISABLE_AUTH) { $env:VFF_DISABLE_AUTH } else { 'true' }
# SEND_TRANSCRIPT (bd polyglot-pdf-cgeh): dev-local.sh sets it; without it a
# Windows dev-local run had NO audio transcription in the dev log -- the
# decisive datapoint for diagnosing "audio reaches Gemini but it stays silent".
# An explicit $env:SEND_TRANSCRIPT still wins, matching the .sh precedence.
# (DISABLE_GEMINI_VAD is gone -- bd polyglot-pdf-v1m8g made PTT the only
# input mode, so there is no VAD mode to select.)
$SendTranscript = if ($env:SEND_TRANSCRIPT) { $env:SEND_TRANSCRIPT } else { 'true' }
$BackendEnvVars = @{
    'VERTEXAI'             = $VertexAi
    'USE_PREMIUM_MODEL'    = $UsePremium
    'GOOGLE_CLOUD_PROJECT' = $VertexProject
    'VFF_DISABLE_AUTH'     = $DisableAuth
    'SEND_TRANSCRIPT'      = $SendTranscript
    'PYTHONPATH'           = $RepoRoot
    'PYTHONUNBUFFERED'     = '1'
    # Empty string = "do not send" (Google's default stands).
    # TEMPERATURE is a normal setting: honored here AND in deployed services
    # since 2026-08-10 (the demo runs 0.4). TRANSCRIPTS is the PHI knob and is
    # still additionally gated backend-side on backend/.env.DEV, so setting it
    # here can never affect a deployed service.
    'LIVE_TEMPERATURE'     = $(if ($Temperature -gt 0) { "$Temperature" } else { '' })
    'LIVE_DEV_TRANSCRIPTS' = $(if ($Transcripts) { 'true' } else { 'false' })
}
if ($Transcripts -and $NoDevLog) {
    Write-Host "WARNING: -Transcripts is ignored with -NoDevLog (the backend gates it on backend/.env.DEV)." -ForegroundColor Yellow
}
$PriorEnv = @{}
foreach ($k in $BackendEnvVars.Keys) {
    $PriorEnv[$k] = [Environment]::GetEnvironmentVariable($k, 'Process')
    Set-Item -Path "Env:$k" -Value $BackendEnvVars[$k]
}

Write-Host ""
$TempLabel = if ($Temperature -gt 0) { "$Temperature" } else { 'default(1.0)' }
$TxLabel = if ($Transcripts) { 'ON' } else { 'off' }
Write-Host "Starting backend (uvicorn :8000, VERTEXAI=$VertexAi, USE_PREMIUM_MODEL=$UsePremium, VFF_DISABLE_AUTH=$DisableAuth)..." -ForegroundColor Cyan
Write-Host "  temperature=$TempLabel   transcripts=$TxLabel (LOCAL-DEV ONLY)   SEND_TRANSCRIPT=$SendTranscript" -ForegroundColor DarkGray

try {
    $BackendProc = Start-Process -FilePath $VenvPython -ArgumentList $BackendArgs `
        -WorkingDirectory (Join-Path $RepoRoot 'backend') -PassThru -NoNewWindow
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
    # --mode demo is LOAD-BEARING, not a preference: plain `npm run dev` loads
    # only .env/.env.local/.env.development, NONE of which exist here, so every
    # VITE_FIREBASE_* var is undefined and the SPA dies on
    # "auth/invalid-api-key" -- a BLANK WHITE SCREEN with no server-side clue.
    # `--mode demo` makes vite read the committed frontend/.env.demo, which
    # carries the Firebase web config. dev-local.sh has always done this; this
    # script did not, which is why it rendered nothing (maintainer 2026-08-05).
    #
    # VITE_WS_URL must be a PROCESS env var, not a .env entry: vite's precedence
    # is `.env.[mode]` > `.env.local`, so under --mode demo a .env.local CANNOT
    # override .env.demo's CLOUD RUN WS url. Without this override the SPA would
    # come up looking fine while talking to the DEPLOYED backend -- so a local
    # backend change (or a temperature sweep) would appear to do nothing.
    #
    # build:worklet first: plain `vite` has no worklet build hook, and the audio
    # worklet is required for the mic path.
    $LocalWsUrl = 'ws://127.0.0.1:8000/ws/fill'
    Write-Host "Starting frontend (vite :5173, --mode demo, WS -> $LocalWsUrl)..." -ForegroundColor Cyan
    $FrontendDir = Join-Path $RepoRoot 'frontend'
    $PriorWsUrl = [Environment]::GetEnvironmentVariable('VITE_WS_URL', 'Process')
    Set-Item -Path 'Env:VITE_WS_URL' -Value $LocalWsUrl
    try {
        # Worklet build is a prerequisite, so run it to completion first.
        & 'npm.cmd' 'run' 'build:worklet' --prefix $FrontendDir 2>&1 | Out-Host
        $FrontendProc = Start-Process -FilePath 'npm.cmd' `
            -ArgumentList @('run', 'dev', '--', '--mode', 'demo') `
            -WorkingDirectory $FrontendDir -PassThru -NoNewWindow
    } finally {
        # The child already inherited VITE_WS_URL; restore this shell.
        if ($null -eq $PriorWsUrl) {
            Remove-Item -Path 'Env:VITE_WS_URL' -ErrorAction SilentlyContinue
        } else {
            Set-Item -Path 'Env:VITE_WS_URL' -Value $PriorWsUrl
        }
    }
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
            # taskkill /T kills the WHOLE process tree. uvicorn --reload spawns a
            # reloader child and npm spawns vite as a child; Stop-Process on the
            # top-level PID alone would orphan those and leave port 8000/5173
            # bound for the next run. /F forces, /T includes descendants.
            try { & taskkill.exe /F /T /PID $p.Id 2>$null | Out-Null } catch {}
            if (-not $p.HasExited) {
                try { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue } catch {}
            }
        }
    }
    Write-Host "Stopped." -ForegroundColor Cyan
}
