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
	# Limit reload to backend dir and exclude the virtual env to avoid noisy reloads on pip site-packages
	# Run in the foreground to ensure the correct code is executed and the process is clearly visible.
	$uvCmd = ".\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload --reload-dir backend --reload-exclude .venv --port 8000"
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

