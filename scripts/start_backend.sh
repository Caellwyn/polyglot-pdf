#!/bin/bash
# Backend Launcher Script
# Run from project root directory

# Navigate to project root
cd "$(dirname "$0")/.." || exit 1

# Check for gcloud application default credentials
# Note: Credentials may need to be refreshed periodically for security
echo "Checking gcloud authentication..."
gcloud auth application-default print-access-token &>/dev/null

if [ $? -ne 0 ]; then
    echo "=========================================="
    echo " GCloud Authentication Required"
    echo "=========================================="
    echo ""
    echo "Application Default Credentials are required for Gemini API access."
    echo "This needs to be refreshed periodically for security."
    echo ""
    echo "Running: gcloud auth application-default login"
    echo ""
    gcloud auth application-default login
    
    # Check if login was successful
    if [ $? -ne 0 ]; then
        echo "ERROR: Failed to authenticate with gcloud"
        exit 1
    fi
    echo ""
    echo "✓ Authentication successful!"
    echo ""
else
    echo "✓ GCloud credentials are valid"
fi
echo ""

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

# In your script, instead of cd backend:
python -m uvicorn backend.main:app