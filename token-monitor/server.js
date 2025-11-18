/**
 * Token & Latency Monitor - File Watcher & WebSocket Server
 *
 * Watches:
 * - backend/logs/token_usage.jsonl (token events)
 * - backend/logs/latency/*.jsonl (latency events - latest file)
 *
 * Broadcasts events to connected dashboards via WebSocket.
 * Run: node token-monitor/server.js
 */

const fs = require('fs');
const path = require('path');
const WebSocket = require('ws');
const chokidar = require('chokidar');

const PORT = 8765;
const TOKEN_LOG_FILE = path.join(__dirname, '..', 'backend', 'logs', 'token_usage.jsonl');
const LATENCY_LOG_DIR = path.join(__dirname, '..', 'backend', 'logs', 'latency');

// Create WebSocket server
const wss = new WebSocket.Server({ port: PORT });

// Track connected clients
const clients = new Set();

// Store all events in memory for new connections
const tokenEvents = [];
const latencyEvents = [];

wss.on('connection', (ws) => {
  console.log('[Monitor] Client connected');
  clients.add(ws);

  // Send all historical events to new client
  ws.send(JSON.stringify({
    type: 'token_history',
    events: tokenEvents
  }));

  ws.send(JSON.stringify({
    type: 'latency_history',
    events: latencyEvents
  }));

  ws.on('close', () => {
    console.log('[Monitor] Client disconnected');
    clients.delete(ws);
  });

  ws.on('error', (error) => {
    console.error('[Monitor] WebSocket error:', error);
    clients.delete(ws);
  });
});

// Broadcast token event to all connected clients
function broadcastToken(event) {
  const message = JSON.stringify({
    type: 'token_event',
    event: event
  });

  clients.forEach((client) => {
    if (client.readyState === WebSocket.OPEN) {
      client.send(message);
    }
  });
}

// Broadcast latency event to all connected clients
function broadcastLatency(event) {
  const message = JSON.stringify({
    type: 'latency_event',
    event: event
  });

  clients.forEach((client) => {
    if (client.readyState === WebSocket.OPEN) {
      client.send(message);
    }
  });
}

// Get latest latency log file
function getLatestLatencyLogFile() {
  if (!fs.existsSync(LATENCY_LOG_DIR)) {
    return null;
  }

  const files = fs.readdirSync(LATENCY_LOG_DIR)
    .filter(f => f.endsWith('.jsonl'))
    .map(f => ({
      name: f,
      path: path.join(LATENCY_LOG_DIR, f),
      mtime: fs.statSync(path.join(LATENCY_LOG_DIR, f)).mtime
    }))
    .sort((a, b) => b.mtime - a.mtime);

  return files.length > 0 ? files[0].path : null;
}

// Load existing token events
function loadTokenEvents() {
  if (!fs.existsSync(TOKEN_LOG_FILE)) {
    console.log('[TokenMonitor] Token log does not exist yet:', TOKEN_LOG_FILE);
    return;
  }

  const content = fs.readFileSync(TOKEN_LOG_FILE, 'utf-8');
  const lines = content.trim().split('\n').filter(line => line.length > 0);

  lines.forEach(line => {
    try {
      const event = JSON.parse(line);
      tokenEvents.push(event);
    } catch (err) {
      console.error('[TokenMonitor] Failed to parse token line:', err);
    }
  });

  console.log(`[TokenMonitor] Loaded ${tokenEvents.length} historical token events`);
}

// Load existing latency events
function loadLatencyEvents() {
  const latencyLogFile = getLatestLatencyLogFile();

  if (!latencyLogFile) {
    console.log('[LatencyMonitor] No latency log files found yet');
    return;
  }

  console.log('[LatencyMonitor] Loading from:', path.basename(latencyLogFile));

  const content = fs.readFileSync(latencyLogFile, 'utf-8');
  const lines = content.trim().split('\n').filter(line => line.length > 0);

  lines.forEach(line => {
    try {
      const event = JSON.parse(line);
      latencyEvents.push(event);
    } catch (err) {
      console.error('[LatencyMonitor] Failed to parse latency line:', err);
    }
  });

  console.log(`[LatencyMonitor] Loaded ${latencyEvents.length} historical latency events`);
  return latencyLogFile;
}

// Watch token log file
function watchTokenLog() {
  // Ensure directory exists
  const logDir = path.dirname(TOKEN_LOG_FILE);
  if (!fs.existsSync(logDir)) {
    fs.mkdirSync(logDir, { recursive: true });
  }

  // Create file if it doesn't exist
  if (!fs.existsSync(TOKEN_LOG_FILE)) {
    fs.writeFileSync(TOKEN_LOG_FILE, '');
  }

  let fileSize = fs.statSync(TOKEN_LOG_FILE).size;

  const watcher = chokidar.watch(TOKEN_LOG_FILE, {
    persistent: true,
    ignoreInitial: false
  });

  watcher.on('change', () => {
    const newSize = fs.statSync(TOKEN_LOG_FILE).size;

    if (newSize > fileSize) {
      const stream = fs.createReadStream(TOKEN_LOG_FILE, {
        start: fileSize,
        end: newSize,
        encoding: 'utf-8'
      });

      let buffer = '';
      stream.on('data', (chunk) => {
        buffer += chunk;
        const lines = buffer.split('\n');

        for (let i = 0; i < lines.length - 1; i++) {
          const line = lines[i].trim();
          if (line.length > 0) {
            try {
              const event = JSON.parse(line);
              tokenEvents.push(event);
              broadcastToken(event);
              console.log('[TokenMonitor]', event.event_type,
                          'Tokens:', event.event.total_tokens,
                          'Cost: $' + event.cost.total_usd.toFixed(6));
            } catch (err) {
              console.log('[TokenMonitor] Skipping incomplete line');
            }
          }
        }
        buffer = lines[lines.length - 1];
      });

      stream.on('end', () => {
        if (buffer.trim().length > 0) {
          try {
            const event = JSON.parse(buffer.trim());
            tokenEvents.push(event);
            broadcastToken(event);
          } catch (err) {
            // Ignore - partial write
          }
        }
      });

      fileSize = newSize;
    }
  });

  console.log('[TokenMonitor] Watching:', TOKEN_LOG_FILE);
}

// Watch latency log directory (watches latest file)
function watchLatencyLog() {
  const latencyLogFile = getLatestLatencyLogFile();

  if (!latencyLogFile) {
    console.log('[LatencyMonitor] No latency log file to watch yet');
    return;
  }

  let fileSize = fs.statSync(latencyLogFile).size;

  const watcher = chokidar.watch(latencyLogFile, {
    persistent: true,
    ignoreInitial: false
  });

  watcher.on('change', () => {
    const newSize = fs.statSync(latencyLogFile).size;

    if (newSize > fileSize) {
      const stream = fs.createReadStream(latencyLogFile, {
        start: fileSize,
        end: newSize,
        encoding: 'utf-8'
      });

      let buffer = '';
      stream.on('data', (chunk) => {
        buffer += chunk;
        const lines = buffer.split('\n');

        for (let i = 0; i < lines.length - 1; i++) {
          const line = lines[i].trim();
          if (line.length > 0) {
            try {
              const event = JSON.parse(line);
              latencyEvents.push(event);
              broadcastLatency(event);
              console.log('[LatencyMonitor]', event.event, 'Source:', event.source);
            } catch (err) {
              console.log('[LatencyMonitor] Skipping incomplete line');
            }
          }
        }
        buffer = lines[lines.length - 1];
      });

      stream.on('end', () => {
        if (buffer.trim().length > 0) {
          try {
            const event = JSON.parse(buffer.trim());
            latencyEvents.push(event);
            broadcastLatency(event);
          } catch (err) {
            // Ignore - partial write
          }
        }
      });

      fileSize = newSize;
    }
  });

  console.log('[LatencyMonitor] Watching:', path.basename(latencyLogFile));
}

// Start server
console.log('');
console.log('Token & Latency Monitor Server');
console.log('===============================');
console.log('Starting WebSocket server on port', PORT);
console.log('');

loadTokenEvents();
loadLatencyEvents();
watchTokenLog();
watchLatencyLog();

console.log('');
console.log('Monitor Server Running');
console.log('======================');
console.log('WebSocket: ws://localhost:' + PORT);
console.log('Dashboard: Open token-monitor/dashboard.html in browser');
console.log('');
