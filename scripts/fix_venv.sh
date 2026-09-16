#!/bin/bash
# Script to fix virtual environment after folder rename

echo "=================================================="
echo "  Fixing Virtual Environment After Folder Rename"
echo "=================================================="
echo ""

cd "$(dirname "$0")/.." || exit 1

# Backup old venv name if it exists
if [ -d ".venv" ]; then
    echo "[1/4] Removing old virtual environment..."
    rm -rf .venv
    echo "      ✓ Removed"
fi

echo ""
echo "[2/4] Creating new virtual environment..."
python -m venv .venv
echo "      ✓ Created"

echo ""
echo "[3/4] Activating virtual environment..."
source .venv/Scripts/activate
echo "      ✓ Activated"

echo ""
echo "[4/4] Installing dependencies..."
pip install --upgrade pip > /dev/null 2>&1
pip install -r backend/requirements-dev.txt
echo "      ✓ Installed"

echo ""
echo "=================================================="
echo "  ✓ Virtual Environment Fixed!"
echo "=================================================="
echo ""
echo "You can now run:"
echo "  bash scripts/start_backend.sh"
echo ""
