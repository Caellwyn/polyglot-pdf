/**
 * devConsoleCapture (bd polyglot-pdf-2m9)
 *
 * Mirrors the browser console to the backend dev log so frontend logs land in the
 * SAME backend/logs/gemini_<date>.jsonl timeline as the Gemini I/O events -- no more
 * copy/pasting console output during local debugging. The backend endpoint
 * (POST /dev/console-log) is itself hard-gated on the .env.DEV marker (404 in prod),
 * and this client only ever POSTs to a LOCALHOST backend, so nothing is shipped off
 * the machine.
 *
 * It wraps console.log/info/warn/error/debug, keeps the original behavior (still
 * prints to the real console), buffers entries, and flushes batches on a short
 * interval and on page hide/unload.
 */

import { getBackendUrl } from "./config";

type Level = "log" | "info" | "warn" | "error" | "debug";

interface Entry { level: Level; text: string; ts: number }

let installed = false;

/** Resolve the backend HTTP origin from the WS url, ONLY when it is localhost. */
function localBackendOrigin(): string | null {
  try {
    const ws = getBackendUrl(); // e.g. ws://localhost:8000/ws/fill
    const u = new URL(ws);
    const host = u.hostname;
    if (host !== "localhost" && host !== "127.0.0.1") return null; // never POST to cloud
    const httpProto = u.protocol === "wss:" ? "https:" : "http:";
    return `${httpProto}//${u.host}`;
  } catch {
    return null;
  }
}

function stringifyArg(a: unknown): string {
  if (typeof a === "string") return a;
  if (a instanceof Error) return `${a.name}: ${a.message}`;
  try {
    return JSON.stringify(a);
  } catch {
    return String(a);
  }
}

/**
 * Install the console mirror. Safe to call once at app start; a no-op if the
 * backend is not local or if already installed.
 */
export function installDevConsoleCapture(getWsSessionId?: () => string | undefined): void {
  if (installed) return;
  const origin = localBackendOrigin();
  if (!origin) return; // not local dev -> do nothing
  installed = true;

  const endpoint = `${origin}/dev/console-log`;
  const buffer: Entry[] = [];
  const levels: Level[] = ["log", "info", "warn", "error", "debug"];
  const original: Record<Level, (...args: unknown[]) => void> = {} as any;

  const flush = (useBeacon = false) => {
    if (buffer.length === 0) return;
    const entries = buffer.splice(0, buffer.length);
    const body = JSON.stringify({
      ws_session_id: getWsSessionId?.(),
      entries,
    });
    try {
      // sendBeacon survives page unload; fetch (keepalive) for the interval path.
      if (useBeacon && navigator.sendBeacon) {
        navigator.sendBeacon(endpoint, new Blob([body], { type: "application/json" }));
      } else {
        void fetch(endpoint, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body,
          keepalive: true,
        }).catch(() => { /* dev-only; ignore transport errors */ });
      }
    } catch {
      /* never let logging break the app */
    }
  };

  for (const level of levels) {
    // eslint-disable-next-line no-console
    original[level] = console[level].bind(console);
    // eslint-disable-next-line no-console
    console[level] = (...args: unknown[]) => {
      original[level](...args); // keep real console behavior
      try {
        buffer.push({
          level,
          text: args.map(stringifyArg).join(" "),
          ts: Date.now(),
        });
        // Cap buffer so a runaway log loop can't grow memory unbounded.
        if (buffer.length > 500) buffer.splice(0, buffer.length - 500);
      } catch {
        /* ignore */
      }
    };
  }

  // Flush on a short interval and when the page is hidden/unloaded.
  setInterval(() => flush(false), 1500);
  window.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden") flush(true);
  });
  window.addEventListener("beforeunload", () => flush(true));

  original.log(`[devConsoleCapture] mirroring console -> ${endpoint}`);
}
