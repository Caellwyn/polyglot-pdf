/**
 * Token Usage Monitor - File Watcher & WebSocket Server
 *
 * Tails backend/logs/token_usage.jsonl and broadcasts events to connected dashboards.
 * Run: node token-monitor/server.js
 */

const fs = require('fs');
const path = require('path');
const WebSocket = require('ws');
const chokidar = require('chokidar');

const PORT = 8765;
const LOG_FILE = path.join(__dirname, '..', 'backend', 'logs', 'token_usage.jsonl');

// Create WebSocket server
const wss = new WebSocket.Server({ port: PORT });

// Track connected clients
const clients = new Set();

// Store all events in memory for new connections
const allEvents = [];

wss.on('connection', (ws) => {
  console.log('[TokenMonitor] Client connected');
  clients.add(ws);

  // Send all historical events to new client
  ws.send(JSON.stringify({
    type: 'history',
    events: allEvents
  }));

  ws.on('close', () => {
    console.log('[TokenMonitor] Client disconnected');
    clients.delete(ws);
  });

  ws.on('error', (error) => {
    console.error('[TokenMonitor] WebSocket error:', error);
    clients.delete(ws);
  });
});

// Broadcast event to all connected clients
function broadcast(event) {
  const message = JSON.stringify({
    type: 'event',
    event: event
  });

  clients.forEach((client) => {
    if (client.readyState === WebSocket.OPEN) {
      client.send(message);
    }
  });
}

// Load existing events from file
function loadExistingEvents() {
  if (!fs.existsSync(LOG_FILE)) {
    console.log('[TokenMonitor] Log file does not exist yet:', LOG_FILE);
    return;
  }

  const content = fs.readFileSync(LOG_FILE, 'utf-8');
  const lines = content.trim().split('\n').filter(line => line.length > 0);

  lines.forEach(line => {
    try {
      const event = JSON.parse(line);
      allEvents.push(event);
    } catch (err) {
      console.error('[TokenMonitor] Failed to parse line:', err);
    }
  });

  console.log(`[TokenMonitor] Loaded ${allEvents.length} historical events`);
}

// Watch for new lines in the log file
function watchLogFile() {
  // Ensure directory exists
  const logDir = path.dirname(LOG_FILE);
  if (!fs.existsSync(logDir)) {
    fs.mkdirSync(logDir, { recursive: true });
  }

  // Create file if it doesn't exist
  if (!fs.existsSync(LOG_FILE)) {
    fs.writeFileSync(LOG_FILE, '');
  }

  let fileSize = fs.statSync(LOG_FILE).size;

  const watcher = chokidar.watch(LOG_FILE, {
    persistent: true,
    ignoreInitial: false
  });

  watcher.on('change', () => {
    const newSize = fs.statSync(LOG_FILE).size;

    if (newSize > fileSize) {
      // Read only the new content
      const stream = fs.createReadStream(LOG_FILE, {
        start: fileSize,
        end: newSize,
        encoding: 'utf-8'
      });

      let buffer = '';
      stream.on('data', (chunk) => {
        buffer += chunk;
        const lines = buffer.split('\n');

        // Process all complete lines
        for (let i = 0; i < lines.length - 1; i++) {
          const line = lines[i].trim();
          if (line.length > 0) {
            try {
              const event = JSON.parse(line);
              allEvents.push(event);
              broadcast(event);
              console.log('[TokenMonitor] New event:', event.event_type,
                          'Tokens:', event.event.total_tokens,
                          'Cost: $' + event.cost.total_usd.toFixed(6));
            } catch (err) {
              // Skip invalid JSON - likely a partial write, will get complete line next time
              console.log('[TokenMonitor] Skipping incomplete line (will retry on next update)');
            }
          }
        }

        // Keep the incomplete line in buffer
        buffer = lines[lines.length - 1];
      });

      stream.on('end', () => {
        // Process any remaining data in buffer
        if (buffer.trim().length > 0) {
          try {
            const event = JSON.parse(buffer.trim());
            allEvents.push(event);
            broadcast(event);
            console.log('[TokenMonitor] New event:', event.event_type,
                        'Tokens:', event.event.total_tokens,
                        'Cost: $' + event.cost.total_usd.toFixed(6));
          } catch (err) {
            // Ignore - partial write
          }
        }
      });

      fileSize = newSize;
    }
  });

  console.log('[TokenMonitor] Watching log file:', LOG_FILE);
}

// Start server
console.log('[TokenMonitor] Starting WebSocket server on port', PORT);
loadExistingEvents();
watchLogFile();

console.log('');
console.log('Token Monitor Server Running');
console.log('=============================');
console.log('WebSocket: ws://localhost:' + PORT);
console.log('Dashboard: Open token-monitor/dashboard.html in browser');
console.log('');
