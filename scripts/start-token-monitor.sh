#!/bin/bash
#
# Start Token Usage Monitor
#
# This script starts the token monitor server and opens the dashboard in your browser.
# The monitor watches backend/logs/token_usage.jsonl and broadcasts events to the dashboard.
#

set -e  # Exit on error

# Get script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "========================================="
echo "Token Usage Monitor"
echo "========================================="
echo ""

# Check if dependencies are installed
if [ ! -d "$PROJECT_ROOT/token-monitor/node_modules" ]; then
    echo "📦 Installing dependencies..."
    cd "$PROJECT_ROOT/token-monitor"
    npm install
    echo ""
fi

# Clear the terminal for a clean view
clear

echo "========================================="
echo "🔥 Token Usage Monitor"
echo "========================================="
echo ""
echo "Starting WebSocket server on port 8765..."
echo "Dashboard will open in your browser."
echo ""
echo "Press Ctrl+C to stop the monitor"
echo ""
echo "========================================="
echo ""

# Start the monitor server
cd "$PROJECT_ROOT/token-monitor"
node server.js &
SERVER_PID=$!

# Wait a moment for server to start
sleep 2

# Open the dashboard in the default browser
DASHBOARD_PATH="$PROJECT_ROOT/token-monitor/dashboard.html"

# Try to open in browser (cross-platform)
if command -v xdg-open > /dev/null; then
    # Linux
    xdg-open "file://$DASHBOARD_PATH"
elif command -v open > /dev/null; then
    # macOS
    open "file://$DASHBOARD_PATH"
elif command -v start > /dev/null; then
    # Windows (Git Bash)
    start "" "$DASHBOARD_PATH"
else
    echo "📊 Dashboard: file://$DASHBOARD_PATH"
    echo "   (Please open this file in your browser manually)"
fi

echo ""
echo "✅ Token monitor is running!"
echo ""
echo "Make sure the backend is also running:"
echo "   cd backend && uvicorn main:app --reload"
echo ""
echo "Then use the voice form to generate token events:"
echo "   http://localhost:5174/schema-form-demo.html"
echo ""

# Wait for server process
wait $SERVER_PID
