# VAD Tuning Dashboard

A real-time dashboard for tuning Voice Activity Detection (VAD) parameters for the Voice Form Filler project.

## Features

### 📊 Real-Time Energy Graph
- Streaming line chart showing microphone energy levels
- Visual threshold overlays (attack/release lines)
- Event markers for speech start/end/misfires
- 10-second rolling window

### 🎛️ Live Parameter Controls
- **Positive Speech Threshold** (0.5 - 1.0): Confidence needed to START speech detection
- **Negative Speech Threshold** (0.3 - 0.95): Confidence needed to END speech detection (hysteresis)
- **Min Speech Duration** (50 - 1000ms): Minimum sustained speech before triggering
- **Redemption Period** (100 - 1000ms): Grace period before ending speech
- **Frontend Min Duration** (100 - 1000ms): Frontend-level duration threshold

### 📈 Live Metrics
- Current/baseline/peak energy levels
- Total speech events and misfires
- False positive rate
- Average speech duration
- Real-time event log with timestamps

### 💾 Configuration Management
- Preset configurations (Default, Sensitive, Conservative, Fast Response)
- Export config to file for copying to source code
- Persistent storage in localStorage
- Visual indicators for unsaved changes

## Usage

### Starting the Dashboard

```bash
cd frontend
npm run dev:vad
```

Then open http://localhost:5175/ in your browser.

### Tuning Workflow

1. **Click "Start Recording"** - Grants microphone access and begins monitoring
2. **Speak into your microphone** - Watch the energy graph and VAD behavior
3. **Adjust sliders** - Tune parameters in real-time
4. **Observe the impact** - See event markers and metrics update
5. **Export configuration** - Click "Export Config" to download settings
6. **Stop and restart** - Apply new configuration requires restarting recording
7. **Update source files** - Copy exported values to `useDemoVAD.ts` and `frontend.config.ts`

### Understanding the Graph

- **Blue line**: Real-time microphone energy (0-100)
- **Gray dashed line**: Baseline energy (calibrated at start)
- **Green dashed line**: Attack threshold (triggers speech start)
- **Red dashed line**: Release threshold (triggers speech end)
- **Green vertical markers**: Speech start events
- **Red vertical markers**: Speech end events
- **Yellow vertical markers**: VAD misfires (false positives)

### Preset Configurations

- **Default**: Balanced settings (current production values)
- **Sensitive**: Catches quiet speech, may have false positives
- **Conservative**: Reduces false positives, may miss quiet speech
- **Fast Response**: Quick barge-in detection, may be choppy

## Architecture

### Components

- **VADTuningDashboard.tsx** - Main container component
- **EnergyGraph.tsx** - Real-time Chart.js visualization
- **VADControlPanel.tsx** - Parameter sliders and presets
- **MetricsPanel.tsx** - Live metrics and event log

### Hooks

- **useVADConfig** - Configuration management with localStorage
- **useEnergyMonitor** - Connects to audioManager for energy data
- **useDemoVAD** - VAD engine from @ricky0123/vad-react

### Data Flow

```
Microphone → audioManager → useEnergyMonitor → EnergyGraph
                         → VAD → events → MetricsPanel
                                      → event markers
```

## Building for Production

```bash
npm run build:vad
```

Output: `dist/vad-tuning/`

## Configuration Files

The dashboard tunes parameters in two files:

### `useDemoVAD.ts`
- `positiveSpeechThreshold`
- `negativeSpeechThreshold`
- `minSpeechMs`
- `redemptionMs`

### `frontend.config.ts`
- `MIN_SPEECH_DURATION_MS`

After tuning, copy the exported values to these files and restart the application.

## Tips

### Reducing False Positives (Echo/Background Noise)
- Increase `positiveSpeechThreshold` (0.95 → 0.98)
- Increase `minSpeechMs` (250ms → 400ms)
- Use "Conservative" preset

### Improving Responsiveness (Faster Barge-In)
- Decrease `minSpeechMs` (250ms → 150ms)
- Decrease `redemptionMs` (400ms → 300ms)
- Use "Fast Response" preset

### Catching Quiet Speech
- Decrease `positiveSpeechThreshold` (0.95 → 0.85)
- Use "Sensitive" preset
- Note: May increase false positives

## Troubleshooting

### No microphone access
- Check browser permissions
- Ensure HTTPS or localhost
- Try different browser

### Graph not updating
- Check browser console for errors
- Ensure microphone is not being used by another application
- Restart recording

### Configuration not applying
- Stop recording first
- Change sliders
- Restart recording (config applies at start)

## Technical Notes

- Uses Silero VAD model via @ricky0123/vad-react
- Chart.js with annotation plugin for visualizations
- Shared MediaStream between audioManager and VAD (prevents echo issues)
- 16kHz audio sampling rate
- Rolling buffer of 500 data points (~10 seconds)

## Related Documentation

- `planning_documents/VAD_ENHANCEMENT_PLAN.md` - VAD optimization plans
- `frontend/src/demo/useDemoVAD.ts` - VAD implementation
- `frontend/frontend.config.ts` - Frontend configuration
