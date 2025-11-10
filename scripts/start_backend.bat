@echo off
REM Backend Launcher Script (Windows)
REM Run from project root directory

cd /d "%~dp0\.."

REM Check for gcloud application default credentials
REM Note: Credentials may need to be refreshed periodically for security
echo Checking gcloud authentication...
gcloud auth application-default print-access-token >nul 2>&1

if %ERRORLEVEL% NEQ 0 (
    echo ==========================================
    echo  GCloud Authentication Required
    echo ==========================================
    echo.
    echo Application Default Credentials are required for Gemini API access.
    echo This needs to be refreshed periodically for security.
    echo.
    echo Running: gcloud auth application-default login
    echo.
    gcloud auth application-default login
    
    if %ERRORLEVEL% NEQ 0 (
        echo ERROR: Failed to authenticate with gcloud
        pause
        exit /b 1
    )
    echo.
    echo [32m√ Authentication successful![0m
    echo.
) else (
    echo [32m√ GCloud credentials are valid[0m
)
echo.

REM Check if virtual environment exists
if not exist ".venv\Scripts\activate.bat" (
    echo ERROR: Virtual environment not found!
    echo Please create one first: python -m venv .venv
    pause
    exit /b 1
)

REM Activate virtual environment
call .venv\Scripts\activate.bat

REM Check if requirements are installed
python -c "import fastapi" >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo Installing dependencies...
    pip install -r backend\requirements.txt
)

REM Start backend server
echo.
echo ========================================
echo  Starting Backend Server
echo ========================================
echo.
echo  URL: http://localhost:8000
echo  Docs: http://localhost:8000/docs
echo.
echo  Press Ctrl+C to stop
echo ========================================
echo.

uvicorn backend.main:app --reload --port 8000
