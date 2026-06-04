# Token & Latency Monitor

Real-time dashboard for monitoring Gemini API token usage, costs, and pipeline latency during form filling sessions.

## Features

### Token Usage Tab
- **Real-time monitoring** of token usage events
- **Cost tracking** broken down by modality (text vs audio, input vs output)
- **Session aggregation** across multiple Gemini sessions per form
- **Interactive charts** showing cumulative tokens, cost breakdown, and usage over time
- **Filtering** by form type and session ID
- **Event history** with detailed token counts

### Latency Metrics Tab
- **Pipeline latency tracking** from audio input to TTS output
- **Performance metrics** including average and P95 latency
- **Event timeline** showing latency over time
- **Event type distribution** across the pipeline
- **Filtering** by form type and session ID
- **Real-time updates** for live latency monitoring

## Architecture

```
Backend (Python) - Gemini Live API
  ├── live_ai_gemini.py extracts usage_metadata from Gemini responses
  ├── token_file_logger.py writes to logs/token_usage.jsonl
  ├── latency_logger.py writes to logs/latency/*.jsonl (if enabled)
  └── Each event tagged with: form_id, form_session_id, gemini_session_id, section_id

Monitor Server (Node.js)
  ├── server.js watches token_usage.jsonl and latest latency log
  ├── Broadcasts token_event and latency_event via WebSocket
  └── Serves historical events to new connections

Dashboard (HTML + Chart.js)
  ├── Tabbed interface (Token Usage | Latency Metrics)
  ├── Connects to WebSocket server
  ├── Displays real-time charts and statistics
  └── Allows filtering by form/session on both tabs
```

**Current Architecture** (November 2025):
- Uses Gemini Live 2.5 Flash Preview with native audio I/O
- Token logging integrated in `backend/adapters/live_ai_gemini.py`
- Tracks tokens across multiple Gemini sessions (session switching when changing form parts)
- Aggregates costs across text and audio modalities (input/output)

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

### Token Usage Tab

**Summary Cards:**
- **Total Tokens**: Aggregated across all sessions
- **Total Cost**: USD cost breakdown
- **Active Sessions**: Number of unique Gemini sessions
- **Events**: Total number of token usage events

**Charts:**
1. **Cumulative Tokens Over Time**: Line chart showing token accumulation
2. **Token Distribution by Modality**: Pie chart of text vs audio, input vs output
3. **Cost Breakdown**: Bar chart of costs by modality
4. **Tokens per Event**: Bar chart showing individual event sizes

**Filters:**
- **Filter by Form**: Show only events for specific forms (e.g., I-90, I-589)
- **Filter by Form Session**: Show only events for a specific form_session_id
- **Filter by Gemini Session**: Show only events for a specific gemini_session_id
- Aggregation works correctly across session switches

**Events Table:**
Shows the last 20 token events with:
- Timestamp
- Form ID
- Session ID (shortened)
- Part ID
- Token counts (total, text in/out, audio in/out)
- Cost in USD

### Latency Metrics Tab

**Summary Cards:**
- **Total Events**: Number of latency events logged
- **Avg Latency**: Average pipeline completion time
- **Sessions**: Number of tracked sessions
- **P95 Latency**: 95th percentile latency

**Charts:**
1. **Pipeline Latency Over Time**: Line chart showing latency trends
2. **Event Type Distribution**: Doughnut chart of event types

**Filters:**
- **Filter by Form**: Show latency for specific forms
- **Filter by Form Session**: Track latency for a specific session

**Events Table:**
Shows the last 50 latency events with:
- Timestamp
- Event name (e.g., pipeline_processing_started)
- Source (frontend/backend)
- Form ID
- Session ID
- Delta from previous event (ms)

## File Formats

### Token Events

Token events are logged to `backend/logs/token_usage.jsonl` in newline-delimited JSON format:

```json
{
  "event_type": "token_usage",
  "timestamp": "2025-11-09T12:34:56.789Z",
  "form_id": "I-90",
  "form_session_id": "web_abc123",
  "gemini_session_id": "LiveAI-xyz456",
  "section_id": "part_1_2_addresses",
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

### Latency Events

Latency events are logged to `backend/logs/latency/*.jsonl` (rotating files) in newline-delimited JSON format:

```json
{
  "timestamp": "2025-11-17T06:13:08.826797+00:00",
  "timestamp_ms": 1763359988826,
  "event": "pipeline_processing_started",
  "source": "backend",
  "session_id": "web__XWKR86XeDs",
  "form_id": "I-90",
  "form_session_id": "form_session_abc123",
  "metadata": {
    "audio_bytes": 52736
  }
}
```

## Session IDs Explained

- **form_id**: Form type (e.g., "I-90", "I-589")
- **form_session_id**: Overall form filling session (persists across Gemini session switches)
- **session_id** (in latency): Ephemeral session ID for this connection
- **gemini_session_id** (in tokens): Specific Gemini connection (changes when switching parts/sections)
- **section_id**: Current form section (e.g., "part_1_2_addresses"); older log
  lines may still carry the legacy `part_id` key (the dashboard reads either)

This allows tracking both token usage and latency across multiple sessions for a single form completion.

## Monitoring JIT Token Reduction

The dashboard is particularly useful for tracking the JIT (Just-In-Time) schema loading optimization:

**Before JIT** (Full Schema):
- Initial handshake: ~7,400 tokens
- Each turn adds minimal tokens

**After JIT** (Manifest Mode):
- Initial handshake: ~456 tokens (94% reduction)
- Tokens accumulate gradually as schemas load on-demand
- Part switching adds previous part manifests

**How to Monitor JIT Impact**:
1. Start the dashboard: `scripts/start-token-monitor.bat` (Windows) or `./scripts/start-token-monitor.sh` (Mac/Linux)
2. Enable JIT mode in backend: Set `USE_JIT_SCHEMA=true` in `backend/.env`
3. Use the form at `http://localhost:5174/schema-form-demo.html`
4. Watch token usage in real-time on the dashboard
5. Compare "Cumulative Tokens Over Time" chart between JIT and non-JIT sessions

The dashboard filters let you compare sessions:
- Filter by Gemini Session to see individual session progression
- Compare token accumulation across multiple form parts
- Track cost differences between JIT and non-JIT modes

## Development

The monitor is for local development only. Production will use BigQuery for analytics.

### Dependencies
- `ws`: WebSocket server
- `chokidar`: File watcher
- `chart.js`: Charting library (loaded via CDN)

### Port
WebSocket server runs on port **8765**

### Key Events Tracked

**Latency Events:**
- `pipeline_processing_started` / `pipeline_processing_completed` - Full pipeline timing
- `tts_enqueue_started` / `tts_enqueue_completed` - TTS queue timing
- `asr_response_received` - ASR completion
- `tts_first_chunk_sent` / `tts_stream_complete` - Audio streaming
- Plus frontend events: `ptt_press`, `ptt_release`, `activity_start`, etc.

## Troubleshooting

**Dashboard shows "Disconnected"**
- Make sure the monitor server is running (`npm start`)
- Check that port 8765 is not blocked

**No token events appearing**
- Verify backend is logging to `backend/logs/token_usage.jsonl`
- Check that `live_ai_gemini.py` has form_id and form_session_id set
- Ensure backend is running with Gemini Live API enabled
- Token logging only occurs when `usage_metadata` is present in Gemini responses

**No latency events appearing**
- Verify backend is logging to `backend/logs/latency/*.jsonl`
- Check that latest log file is being detected by server

**Events not updating in real-time**
- The file watcher may take a moment to detect changes
- Try refreshing the dashboard to load historical events

**Latency tab shows 0ms**
- Need both `pipeline_processing_started` and `pipeline_processing_completed` events
- Make sure you're completing full voice interactions
