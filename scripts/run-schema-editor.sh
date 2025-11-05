#!/bin/bash

# PDF Schema Editor - Quick Launch Script
#
# This script:
# 1. Checks if dependencies are installed
# 2. Installs if needed
# 3. Launches the editor in dev mode
#
# Usage: ./scripts/run-schema-editor.sh

set -e  # Exit on error

EDITOR_DIR="schema-editor"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "======================================"
echo " PDF Schema Editor - Launch Script"
echo "======================================"
echo ""

cd "$ROOT_DIR/$EDITOR_DIR"

# Check if node_modules exists
if [ ! -d "node_modules" ]; then
    echo "📦 Installing dependencies..."
    echo ""
    npm install
    echo ""
    echo "✅ Dependencies installed!"
    echo ""
else
    echo "✅ Dependencies already installed"
    echo ""
fi

echo "🚀 Starting schema editor..."
echo ""
echo "   The editor will open at: http://localhost:3001"
echo ""
echo "   To stop: Press Ctrl+C"
echo ""
echo "======================================"
echo ""

# Start the dev server
npm run dev
