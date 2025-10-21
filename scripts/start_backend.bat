@echo off
REM Backend Launcher Script (Windows)
REM Run from project root directory

cd /d "%~dp0\.."

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
