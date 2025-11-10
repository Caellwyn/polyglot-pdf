@echo off
REM Start Token Usage Monitor
REM
REM This script starts the token monitor server and opens the dashboard in your browser.
REM The monitor watches backend/logs/token_usage.jsonl and broadcasts events to the dashboard.

setlocal

REM Get project root (parent of scripts folder)
set "SCRIPT_DIR=%~dp0"
set "PROJECT_ROOT=%SCRIPT_DIR%.."

echo =========================================
echo Token Usage Monitor
echo =========================================
echo.

REM Check if dependencies are installed
if not exist "%PROJECT_ROOT%\token-monitor\node_modules" (
    echo Installing dependencies...
    cd /d "%PROJECT_ROOT%\token-monitor"
    call npm install
    echo.
)

REM Clear the terminal for a clean view
cls

echo =========================================
echo Token Usage Monitor
echo =========================================
echo.
echo Starting WebSocket server on port 8765...
echo Dashboard will open in your browser.
echo.
echo Press Ctrl+C to stop the monitor
echo.
echo =========================================
echo.

REM Start the monitor server
cd /d "%PROJECT_ROOT%\token-monitor"
start "Token Monitor Server" node server.js

REM Wait a moment for server to start
timeout /t 2 /nobreak >nul

REM Open the dashboard in the default browser
start "" "%PROJECT_ROOT%\token-monitor\dashboard.html"

echo.
echo Token monitor is running!
echo.
echo Make sure the backend is also running:
echo    cd backend ^&^& uvicorn main:app --reload
echo.
echo Then use the voice form to generate token events:
echo    http://localhost:5174/schema-form-demo.html
echo.
echo Press any key to stop the monitor...
pause >nul

REM Kill the monitor server when user presses a key
taskkill /FI "WindowTitle eq Token Monitor Server*" /T /F >nul 2>&1

endlocal
