#!/bin/bash
# Backend Launcher Script
# Run from project root directory

# Navigate to project root
cd "$(dirname "$0")/.." || exit 1

# Activate virtual environment
if [ -f ".venv/Scripts/activate" ]; then
    source .venv/Scripts/activate
elif [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
else
    echo "ERROR: Virtual environment not found!"
    echo "Please create one first: python -m venv .venv"
    exit 1
fi

# Check if requirements are installed
if ! python -c "import fastapi" 2>/dev/null; then
    echo "Installing dependencies..."
    pip install -r backend/requirements.txt
fi

# Start backend server
echo "Starting backend server on http://localhost:8000"
echo "Press Ctrl+C to stop"
echo ""

uvicorn backend.main:app --reload --port 8000
