// A spend-exhausted client link is TERMINAL (bd polyglot-pdf-cke6v).
//
// The backend closes 1013 with reason "budget_exhausted" when a link has spent
// its ceiling. Before this, handleClose branched on no code at all: 1013 fell
// through to the generic path, burned every backoff retry against a socket that
// refuses each time, and settled on "reconnect_failed" -- which drives a modal
// offering a Reconnect button that cannot work. A client reads that as the app
// being broken, which is exactly what the backend's 1013-not-1008 choice was
// made to avoid.
//
// THE TRAP THESE TESTS EXIST FOR: 1013 carries TWO reasons with OPPOSITE
// handling. "budget_exhausted" is permanent; "budget_unavailable" (the spend
// store was unreachable) is transient and must keep retrying. Branching on the
// code alone would silently strand a client whose only problem was a blip in
// our own datastore.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import { WebFormConnection } from './webFormConnection';

// form_metadata is REQUIRED: the state manager compares the stored session's
// form_number/version against it on init, so a fixture without it throws the
// moment a previous test has left state in sessionStorage.
const SCHEMA: any = {
  form_id: 'f',
  title: 'F',
  form_metadata: { form_number: 'TEST-1', version: '1' },
  sections: [],
};

/** Drive handleClose directly -- the socket lifecycle is not what is under test. */
function closeWith(conn: any, code: number, reason: string) {
  conn.handleClose({ code, reason, wasClean: false } as any, undefined);
}

describe('a spend-exhausted link is terminal', () => {
  let conn: any;
  let statuses: string[];

  beforeEach(() => {
    vi.useFakeTimers();
    // The state manager persists to sessionStorage and REUSES a matching
    // session on construct, so state left by an earlier test leaks into the
    // next one -- which is how the first version of this file passed test 1 and
    // threw on the rest.
    try { sessionStorage.clear(); } catch { /* not all envs provide it */ }
    statuses = [];
    conn = new WebFormConnection(SCHEMA, {
      onStatusChange: (s: string) => statuses.push(s),
    }) as any;
    // The state a live client is in when the ceiling is hit: connected, with
    // auto-reconnect armed. Without this the !enableAutoReconnect branch would
    // absorb the close and the test would pass for the wrong reason.
    conn.enableAutoReconnect = true;
    conn.status = 'connected';
  });

  afterEach(() => {
    vi.clearAllTimers();
    vi.useRealTimers();
  });

  it('does NOT retry, and reports budget_exhausted (exit criterion 1)', () => {
    closeWith(conn, 1013, 'budget_exhausted');

    expect(conn.status).toBe('budget_exhausted');
    expect(statuses).toContain('budget_exhausted');
    // The point of the bead: no backoff timer, no attempt counted. A retry here
    // is not merely wasteful -- it delays telling the client the truth.
    expect(conn.reconnectTimer).toBeFalsy();
    expect(conn.reconnectAttempts).toBe(0);
    // And emphatically not the status that offers a Reconnect button.
    expect(statuses).not.toContain('reconnect_failed');
    expect(statuses).not.toContain('reconnecting');
  });

  it('STILL retries on budget_unavailable -- transient (exit criterion 3)', () => {
    // Same close code, opposite meaning: our spend store was unreachable, which
    // says nothing about the client's allowance. Treating this as terminal
    // would strand a client over our own outage.
    closeWith(conn, 1013, 'budget_unavailable');

    expect(conn.status).not.toBe('budget_exhausted');
    expect(statuses).not.toContain('budget_exhausted');
    // It took the ordinary retry path.
    expect(conn.reconnectAttempts).toBeGreaterThan(0);
  });

  it('leaves an ordinary drop (1006, no reason) on the retry path', () => {
    // Guards the guard: if the new branch matched too broadly -- on the code,
    // or on a missing reason -- every network blip would become terminal.
    closeWith(conn, 1006, '');

    expect(conn.status).not.toBe('budget_exhausted');
    expect(conn.reconnectAttempts).toBeGreaterThan(0);
  });

  it('reports the real cause even on a FIRST connect to a spent link', () => {
    // A client returning to a used-up link never reaches "connected", so
    // enableAutoReconnect is still false. That path reports a generic
    // "disconnected" unless the budget branch is checked BEFORE it -- and this
    // is the likeliest way a real client meets this state.
    const fresh: any = new WebFormConnection(SCHEMA, {}) as any;
    fresh.enableAutoReconnect = false;

    fresh.handleClose({ code: 1013, reason: 'budget_exhausted', wasClean: false } as any, undefined);

    expect(fresh.status).toBe('budget_exhausted');
  });

  it('clears the AI-drop marker, so two modals cannot stack', () => {
    // A Gemini drop sets droppedReconnectInFlight to drive the "trouble
    // reaching the AI" modal. If the budget close does not clear it, that modal
    // renders on top of the spend-ceiling one: two explanations for one event,
    // and the wrong one in front.
    conn.droppedReconnectInFlight = true;

    closeWith(conn, 1013, 'budget_exhausted');

    expect(conn.droppedReconnectInFlight).toBe(false);
  });
});
