import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { WebFormConnection } from './webFormConnection';

// Sprint 23 C2 (bd polyglot-pdf-bwevj): the backend's policy refusals -- 1008
// (authentication, origin, link/kit scope) and 1009 (frame cap) -- now arrive
// AFTER accept(), so they reach handleClose instead of failing connect().
// They are terminal: retrying sends the same thing to the same gate. The wire
// reason is kept for the UI.

const SCHEMA: any = {
  form_id: 'f',
  title: 'F',
  form_metadata: { form_number: 'TEST-1', version: '1' },
  sections: [],
};

function closeWith(conn: any, code: number, reason: string) {
  conn.handleClose({ code, reason, wasClean: false } as any, undefined);
}

describe('a policy refusal (1008/1009) is terminal', () => {
  let conn: any;
  let statuses: string[];

  beforeEach(() => {
    vi.useFakeTimers();
    try { sessionStorage.clear(); } catch { /* not all envs provide it */ }
    statuses = [];
    conn = new WebFormConnection(SCHEMA, {
      onStatusChange: (s: string) => statuses.push(s),
    }) as any;
    conn.enableAutoReconnect = true;
    conn.status = 'connected';
  });

  afterEach(() => {
    vi.clearAllTimers();
    vi.useRealTimers();
  });

  it.each([
    [1008, 'Authentication failed'],
    [1008, 'This account is not enrolled for the voice application'],
    [1008, 'Origin not allowed'],
    [1008, 'Kit not available'],
    [1009, 'Frame too large'],
  ])('does NOT retry on %i "%s" and keeps the wire reason', (code, reason) => {
    closeWith(conn, code as number, reason as string);
    expect(conn.status).toBe('policy_refused');
    expect(conn.reconnectTimer).toBeFalsy();
    expect(conn.reconnectAttempts).toBe(0);
    expect(conn.lastPolicyRefusal).toBe(reason);
  });

  it('a non-policy close (1006 abnormal) still schedules the bounded reconnect', () => {
    closeWith(conn, 1006, '');
    expect(conn.lastPolicyRefusal).toBeNull();
    expect(conn.reconnectTimer).toBeTruthy();
  });
});
