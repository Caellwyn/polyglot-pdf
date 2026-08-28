# Dev convenience script: set up env, run backend and frontend

param(
	[switch]$BackendOnly,
	[switch]$FrontendOnly
)

Set-Location "$PSScriptRoot\.."

if (-not (Test-Path .venv)) {
	Write-Host "Creating Python venv..."
	py -3.11 -m venv .venv
}

. .\.venv\Scripts\Activate.ps1
& .\.venv\Scripts\python.exe -m pip install --upgrade pip | Out-Null
& .\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt | Out-Null

$env:VITE_API_URL = "http://localhost:8000"

if (-not $FrontendOnly) {
	# Limit reload to backend dir. The scoping comes from RUNNING IN backend/,
	# not from --reload-dir alone: uvicorn's WatchFiles supervisor drops any
	# reload dir that is a child of the process cwd and watches the cwd instead,
	# so from the repo root this watched the whole tree including
	# .claude/worktrees/ (bd polyglot-pdf-b5nmq). PYTHONPATH keeps backend.main
	# importable from the repo root.
	#
	# No --reload-exclude for .venv: the watch is now scoped to backend/, which
	# does not contain it, and uvicorn's exclude resolver takes RELATIVE patterns
	# only -- an absolute one raises NotImplementedError before the port binds.
	# Run in the foreground to ensure the correct code is executed and the process is clearly visible.
	$RepoRoot = (Resolve-Path .).Path
	$uvCmd = "`$env:PYTHONPATH='$RepoRoot'; Set-Location '$RepoRoot\backend'; & '$RepoRoot\.venv\Scripts\python.exe' -m uvicorn backend.main:app --reload --reload-dir '$RepoRoot\backend' --port 8000"
	Write-Host "Starting backend server in the foreground..."
	Start-Job -ScriptBlock { param($cmd) Invoke-Expression $cmd } -ArgumentList $uvCmd
}

if (-not $BackendOnly) {
	Push-Location frontend
	if (-not (Test-Path node_modules)) {
		npm install
	}
	npm run dev
	Pop-Location
}

