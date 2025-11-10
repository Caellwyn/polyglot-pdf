# Token Usage Monitor

Real-time dashboard for monitoring Gemini API token usage and costs during form filling sessions.

## Features

- **Real-time monitoring** of token usage events
- **Cost tracking** broken down by modality (text vs audio, input vs output)
- **Session aggregation** across multiple Gemini sessions per form
- **Interactive charts** showing cumulative tokens, cost breakdown, and usage over time
- **Filtering** by form type and session ID
- **Event history** with detailed token counts

## Architecture

```
Backend (Python)
  ├── Gemini API responses with usage_metadata
  ├── token_file_logger.py writes to logs/token_usage.jsonl
  └── Each event tagged with: form_id, form_session_id, gemini_session_id, part_id

Token Monitor (Node.js)
  ├── server.js watches token_usage.jsonl
  ├── Broadcasts new events via WebSocket
  └── Serves historical events to new connections

Dashboard (HTML + Chart.js)
  ├── Connects to WebSocket server
  ├── Displays real-time charts and statistics
  └── Allows filtering by form/session
```

## Usage

### Quick Start (Recommended)

**Windows:**
```bash
scripts\start-token-monitor.bat
```

**Mac/Linux:**
```bash
./scripts/start-token-monitor.sh
```

The script will:
- Install dependencies if needed
- Start the WebSocket server
- Open the dashboard in your browser

### Manual Start

**1. Start the backend**
```bash
cd backend
uvicorn main:app --reload
```

**2. Start the token monitor**
```bash
cd token-monitor
npm start
```

**3. Open the dashboard**
Open `token-monitor/dashboard.html` in your web browser.

**4. Use the voice form**
Navigate to `http://localhost:5174/schema-form-demo.html` and use voice features. Token events will appear in real-time on the dashboard.

## Dashboard Features

### Summary Cards
- **Total Tokens**: Aggregated across all sessions
- **Total Cost**: USD cost breakdown
- **Active Sessions**: Number of unique Gemini sessions
- **Events**: Total number of token usage events

### Charts
1. **Cumulative Tokens Over Time**: Line chart showing token accumulation
2. **Token Distribution by Modality**: Pie chart of text vs audio, input vs output
3. **Cost Breakdown**: Bar chart of costs by modality
4. **Tokens per Event**: Bar chart showing individual event sizes

### Filters
- **Filter by Form**: Show only events for specific forms (e.g., I-90, I-589)
- **Filter by Session**: Show only events for a specific form_session_id
- Aggregation still works correctly across Gemini session switches

### Events Table
Shows the last 20 events with:
- Timestamp
- Form ID
- Session ID (shortened)
- Part ID
- Token counts (total, text in/out, audio in/out)
- Cost in USD

## File Format

Token events are logged to `backend/logs/token_usage.jsonl` in newline-delimited JSON format:

```json
{
  "event_type": "token_usage",
  "timestamp": "2025-11-09T12:34:56.789Z",
  "form_id": "I-90",
  "form_session_id": "web_abc123",
  "gemini_session_id": "LiveAI-xyz456",
  "part_id": "part_1",
  "event": {
    "prompt_tokens": 100,
    "response_tokens": 50,
    "total_tokens": 150,
    "text_input": 80,
    "audio_input": 20,
    "text_output": 40,
    "audio_output": 10
  },
  "cost": {
    "text_input_usd": 0.0001,
    "audio_input_usd": 0.0002,
    "text_output_usd": 0.0003,
    "audio_output_usd": 0.0004,
    "total_usd": 0.001
  },
  "session_cumulative": {
    "total_tokens": 150,
    "total_cost_usd": 0.001,
    "text_input": 80,
    "audio_input": 20,
    "text_output": 40,
    "audio_output": 10
  }
}
```

## Session IDs Explained

- **form_id**: Form type (e.g., "I-90", "I-589")
- **form_session_id**: Overall form filling session (persists across Gemini session switches)
- **gemini_session_id**: Specific Gemini connection (changes when switching parts/sections)
- **part_id**: Current form part (e.g., "part_1", "part_2")

This allows tracking total token usage across multiple Gemini sessions for a single form completion.

## Development

The monitor is for local development only. Production will use BigQuery for token analytics.

### Dependencies
- `ws`: WebSocket server
- `chokidar`: File watcher

### Port
WebSocket server runs on port **8765**

## Troubleshooting

**Dashboard shows "Disconnected"**
- Make sure the monitor server is running (`npm start`)
- Check that port 8765 is not blocked

**No events appearing**
- Verify backend is logging to `backend/logs/token_usage.jsonl`
- Check that `set_session_context()` is being called with valid form_id and session_id

**Events not updating in real-time**
- The file watcher may take a moment to detect changes
- Try refreshing the dashboard to load historical events
