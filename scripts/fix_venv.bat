@echo off
REM Script to fix virtual environment after folder rename

echo.
echo ==================================================
echo   Fixing Virtual Environment After Folder Rename
echo ==================================================
echo.

cd /d "%~dp0\.."

REM Remove old venv
if exist ".venv" (
    echo [1/4] Removing old virtual environment...
    rmdir /s /q .venv
    echo       Done
)

echo.
echo [2/4] Creating new virtual environment...
python -m venv .venv
echo       Done

echo.
echo [3/4] Activating virtual environment...
call .venv\Scripts\activate.bat
echo       Done

echo.
echo [4/4] Installing dependencies...
echo       (This may take a few minutes...)
python -m pip install --upgrade pip >nul 2>&1
python -m pip install -r backend\requirements-dev.txt
echo       Done

echo.
echo ==================================================
echo   Virtual Environment Fixed!
echo ==================================================
echo.
echo You can now run:
echo   scripts\start_backend.bat
echo.
echo Or double-click start_backend.bat in the scripts folder
echo.
pause
