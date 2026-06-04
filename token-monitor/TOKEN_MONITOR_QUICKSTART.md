# Token Monitor - Quick Start Guide

Monitor real-time token usage and costs during Gemini API calls.

## Start the Monitor

**Windows:**
```bash
scripts\start-token-monitor.bat
```

**Mac/Linux:**
```bash
./scripts/start-token-monitor.sh
```

This will:
1. Install dependencies (first time only)
2. Start the WebSocket server on port 8765
3. Open the dashboard in your browser

## What You'll See

- **Total Tokens**: Cumulative across all sessions
- **Total Cost**: USD breakdown by modality (text/audio input/output)
- **Active Sessions**: Number of Gemini sessions
- **Real-time Charts**: Token usage, cost breakdown, distribution

## How It Works

1. Backend logs token events to `backend/logs/token_usage.jsonl`
2. Monitor server watches the file and broadcasts via WebSocket
3. Dashboard displays real-time updates

## Session Tracking

- **form_session_id**: Entire form completion (persists across section switches)
- **gemini_session_id**: Individual Gemini connection
- **section_id**: Current form section (older logs may carry the legacy `part_id` key)

This allows tracking total cost even when switching Gemini sessions between form sections.

## Full Documentation

See `token-monitor/README.md` for detailed documentation.
