// @vitest-environment jsdom
//
// Link history (bd polyglot-pdf-x22hm, Epic 2 Track C bead C5).
//
// Exit criterion 1: "the employee view sends no employee_id and hides
// revoke; the manager view can filter and revoke (one call, re-read); the
// table renders only the allowlisted columns (mocked API, mutation-
// verified)." Exercises the REAL adminFetch (not a mock of adminApi.ts)
// against an injected fetchImpl, the same integration MintLinkPage.test.tsx
// and adminApi.test.ts both use -- so a change to adminFetch's own request
// shape (headers, channel param) is caught here too, not only in
// adminApi.test.ts.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { LinkHistoryPage } from './LinkHistoryPage';

// Resolve from THIS TEST FILE, never process.cwd(): a worktree vitest run is
// invoked from the MAIN checkout here (the node_modules junction workaround),
// so a cwd-relative read would audit the wrong copy entirely. Same idiom as
// frontend/src/shared/introScript.mirror.test.ts.
function repoPath(...parts: string[]): string {
  const here = expect.getState().testPath as string;
  // <repo>/frontend/src/console/<file> -> up 4 to <repo>
  return resolve(here, '../../../..', ...parts);
}

vi.mock('../firebase/config', () => ({
  auth: { __sentinel: 'auth' },
  db: { __sentinel: 'db' },
}));
vi.mock('../contexts/AuthContext', async () => {
  const actual = await vi.importActual<Record<string, unknown>>(
    '../contexts/AuthContext',
  );
  return {
    ...actual,
    useAuth: () => ({ user: null, loading: false }),
  };
});

function managerUser(uid = 'mgr-1') {
  return {
    uid,
    getIdToken: async () => 'mgr-token',
    getIdTokenResult: async () => ({ claims: { firm_id: 'firm-1', firm_role: 'manager' } }),
  };
}

function employeeUser(uid = 'emp-1') {
  return {
    uid,
    getIdToken: async () => 'emp-token',
    getIdTokenResult: async () => ({ claims: { firm_id: 'firm-1', firm_role: 'employee' } }),
  };
}

const SAMPLE_ROW = {
  jti: 'jti-1',
  kit_id: 'w7',
  employee_id: 'emp-1',
  // bd polyglot-pdf-cpsi0: the manager-only Employee column's display
  // value; employee_id (the uid) remains on the row for the title
  // tooltip.
  employee_label: 'staffer@example.com',
  status: 'minted',
  minted_at: 1000,
  open_deadline: 2000,
  opened_at: null,
  completed_at: null,
  spend_usd: null,
  turns: null,
  cap_usd: 3.0,
  credit_cost: 1,
  // Extra key a future stored doc might carry -- must NEVER render.
  internal_secret: 'do-not-show',
};

function jsonResponse(body: unknown, status = 200) {
  return { ok: status < 400, status, json: async () => body } as unknown as Response;
}

function mockFetch(handler: (url: string, init?: RequestInit) => Response) {
  const calls: Array<{ url: string; init?: RequestInit }> = [];
  const impl = vi.fn(async (url: unknown, init?: RequestInit) => {
    calls.push({ url: String(url), init });
    // FirmAlertsBanner (bd polyglot-pdf-62o4d) now fetches
    // /admin/firms/{firm_id}/alerts independently the moment this page
    // mounts. It is recorded in `calls` like any other request (so a test
    // that asserts on the FULL call list still sees it -- see the
    // "sends NO employee_id" test's own path-filtered assertion below),
    // but it must not be routed into a test's OWN link-list/revoke
    // sequencing logic, which every existing handler here was written
    // before the banner existed to expect. Answered with an empty list
    // here, once, so the banner renders nothing and every other handler
    // keeps counting only the calls IT cares about.
    if (String(url).includes('/alerts')) {
      return jsonResponse({ alerts: [] });
    }
    return handler(String(url), init);
  });
  return { impl: impl as unknown as typeof fetch, calls };
}

/** Calls this test's OWN logic cares about -- everything except
 * FirmAlertsBanner's own independent /alerts fetch. */
function nonAlertCalls(calls: Array<{ url: string; init?: RequestInit }>) {
  return calls.filter((c) => !c.url.includes('/alerts'));
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllEnvs();
});

describe('LinkHistoryPage', () => {
  it('renders only the allowlisted columns, never an extra key', async () => {
    vi.stubEnv('VITE_ADMIN_API_BASE_URL', 'https://admin.example');
    vi.stubEnv('VITE_APP_CHANNEL', 'staging');
    const { impl } = mockFetch(() => jsonResponse({ links: [SAMPLE_ROW] }));

    render(<LinkHistoryPage user={managerUser()} fetchImpl={impl} />);

    expect(await screen.findByText('w7')).toBeTruthy();
    expect(screen.getByText('minted')).toBeTruthy();
    // The allowlist has no "internal_secret" column and no raw dump of the
    // row -- confirms the page does not spread the row onto the DOM.
    expect(screen.queryByText('do-not-show')).toBeNull();
    expect(document.body.textContent).not.toContain('internal_secret');
  });

  it('a manager sees an Employee column showing the label, uid as a tooltip', async () => {
    vi.stubEnv('VITE_ADMIN_API_BASE_URL', 'https://admin.example');
    vi.stubEnv('VITE_APP_CHANNEL', 'staging');
    const { impl } = mockFetch(() => jsonResponse({ links: [SAMPLE_ROW] }));

    render(<LinkHistoryPage user={managerUser()} fetchImpl={impl} />);

    await screen.findByText('w7');
    // bd polyglot-pdf-cpsi0 exit criterion 3: the manager view shows
    // employee_label, with the raw uid (employee_id) as a title tooltip.
    const employeeCell = screen.getByText('staffer@example.com');
    expect(employeeCell).toBeTruthy();
    expect(employeeCell.getAttribute('title')).toBe('emp-1');
    expect(screen.getByRole('columnheader', { name: 'Employee' })).toBeTruthy();
  });

  it('an employee view has NO Employee column at all', async () => {
    vi.stubEnv('VITE_ADMIN_API_BASE_URL', 'https://admin.example');
    vi.stubEnv('VITE_APP_CHANNEL', 'demo');
    const { impl } = mockFetch(() => jsonResponse({ links: [SAMPLE_ROW] }));

    render(<LinkHistoryPage user={employeeUser('emp-1')} fetchImpl={impl} />);

    await screen.findByText('w7');
    // An employee's own rows are always their own -- repeating their own
    // label on every row adds nothing, so the column is hidden entirely
    // (mirrors the existing Revoke-column hiding for this same actor).
    expect(screen.queryByRole('columnheader', { name: 'Employee' })).toBeNull();
    expect(screen.queryByText('staffer@example.com')).toBeNull();
  });

  it('an employee view sends NO employee_id and hides the revoke controls', async () => {
    vi.stubEnv('VITE_ADMIN_API_BASE_URL', 'https://admin.example');
    vi.stubEnv('VITE_APP_CHANNEL', 'demo');
    const { impl, calls } = mockFetch(() => jsonResponse({ links: [SAMPLE_ROW] }));

    render(<LinkHistoryPage user={employeeUser('emp-1')} fetchImpl={impl} />);

    await screen.findByText('w7');
    const linkCalls = nonAlertCalls(calls);
    expect(linkCalls).toHaveLength(1);
    const url = new URL(linkCalls[0].url);
    expect(url.pathname).toBe('/admin/firms/firm-1/links');
    expect(url.searchParams.has('employee_id')).toBe(false);
    // No filter controls, no Revoke column/button at all for an employee.
    expect(screen.queryByLabelText(/employee/i)).toBeNull();
    expect(screen.queryByRole('button', { name: /revoke/i })).toBeNull();
  });

  it('a manager can filter by employee and status', async () => {
    vi.stubEnv('VITE_ADMIN_API_BASE_URL', 'https://admin.example');
    vi.stubEnv('VITE_APP_CHANNEL', 'demo');
    const { impl, calls } = mockFetch(() => jsonResponse({ links: [] }));

    render(<LinkHistoryPage user={managerUser()} fetchImpl={impl} />);
    await waitFor(() => expect(calls.length).toBeGreaterThanOrEqual(1));

    const employeeInput = screen.getByLabelText(/employee/i) as HTMLInputElement;
    const statusSelect = screen.getByLabelText(/status/i) as HTMLSelectElement;
    const { fireEvent } = await import('@testing-library/react');
    fireEvent.change(employeeInput, { target: { value: 'emp-9' } });
    fireEvent.change(statusSelect, { target: { value: 'opened' } });
    fireEvent.click(screen.getByRole('button', { name: /filter/i }));

    await waitFor(() => expect(calls.length).toBeGreaterThanOrEqual(2));
    const lastUrl = new URL(calls[calls.length - 1].url);
    expect(lastUrl.searchParams.get('employee_id')).toBe('emp-9');
    expect(lastUrl.searchParams.get('status')).toBe('opened');
  });

  it('revoke fires ONE call and RE-READS the list (not a local patch)', async () => {
    vi.stubEnv('VITE_ADMIN_API_BASE_URL', 'https://admin.example');
    vi.stubEnv('VITE_APP_CHANNEL', 'demo');
    let listCallCount = 0;
    const { impl, calls } = mockFetch((url, init) => {
      // mockFetch's own alerts short-circuit already answers
      // FirmAlertsBanner's independent fetch before this handler ever
      // sees it, so `url` here is either the link list or the revoke
      // call -- listCallCount stays a pure count of the LIST route.
      if (url.includes('/revoke')) {
        expect(init?.method).toBe('POST');
        return jsonResponse({ jti: 'jti-1', status: 'revoked' });
      }
      listCallCount += 1;
      // Second read reflects the server's post-revoke state -- proves the
      // table comes from a RE-READ, not a client-side patch of the old row.
      const status = listCallCount === 1 ? 'minted' : 'revoked';
      return jsonResponse({ links: [{ ...SAMPLE_ROW, status }] });
    });

    render(<LinkHistoryPage user={managerUser()} fetchImpl={impl} />);
    const revokeButton = await screen.findByRole('button', { name: /^revoke$/i });

    const { fireEvent } = await import('@testing-library/react');
    fireEvent.click(revokeButton);

    await waitFor(() => expect(screen.getByText('revoked')).toBeTruthy());

    const revokeCalls = nonAlertCalls(calls).filter((c) => c.url.includes('/revoke'));
    expect(revokeCalls).toHaveLength(1);
    expect(listCallCount).toBe(2);
  });

  it('the revoke button never appears for a row that is not `minted`', async () => {
    vi.stubEnv('VITE_ADMIN_API_BASE_URL', 'https://admin.example');
    vi.stubEnv('VITE_APP_CHANNEL', 'demo');
    const { impl } = mockFetch(() => jsonResponse({
      links: [{ ...SAMPLE_ROW, status: 'completed' }],
    }));

    render(<LinkHistoryPage user={managerUser()} fetchImpl={impl} />);
    await screen.findByText('completed');

    expect(screen.queryByRole('button', { name: /^revoke$/i })).toBeNull();
  });

  it('a signed-in user with no firm_id claim gets an error, not a stuck spinner', async () => {
    vi.stubEnv('VITE_ADMIN_API_BASE_URL', 'https://admin.example');
    vi.stubEnv('VITE_APP_CHANNEL', 'demo');
    const { impl, calls } = mockFetch(() => jsonResponse({ links: [] }));
    const noFirmUser = {
      uid: 'dev-1',
      getIdToken: async () => 'dev-token',
      getIdTokenResult: async () => ({ claims: {} }),
    };

    render(<LinkHistoryPage user={noFirmUser} fetchImpl={impl} />);

    expect(await screen.findByRole('alert')).toBeTruthy();
    expect(screen.queryByText(/loading/i)).toBeNull();
    // No firmId means no fetch is ever attempted -- nothing to load.
    expect(calls).toHaveLength(0);
  });

  it('a getIdTokenResult() failure gets a distinct error, not a stuck spinner', async () => {
    vi.stubEnv('VITE_ADMIN_API_BASE_URL', 'https://admin.example');
    vi.stubEnv('VITE_APP_CHANNEL', 'demo');
    const { impl } = mockFetch(() => jsonResponse({ links: [] }));
    const brokenUser = {
      uid: 'flaky-1',
      getIdToken: async () => 'flaky-token',
      getIdTokenResult: async () => { throw new Error('network blip'); },
    };

    render(<LinkHistoryPage user={brokenUser} fetchImpl={impl} />);

    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toMatch(/sign in again/i);
    expect(screen.queryByText(/loading/i)).toBeNull();
  });

  it('shows the server error message on a failed load', async () => {
    vi.stubEnv('VITE_ADMIN_API_BASE_URL', 'https://admin.example');
    vi.stubEnv('VITE_APP_CHANNEL', 'demo');
    const { impl } = mockFetch(() => jsonResponse({ detail: 'link store unavailable' }, 503));

    render(<LinkHistoryPage user={managerUser()} fetchImpl={impl} />);

    expect(await screen.findByRole('alert')).toBeTruthy();
    expect(screen.getByText(/link store unavailable/i)).toBeTruthy();
  });

  it('revoke: a 401 (AuthError) says "sign in again", not "could not reach the server" (x22hm review finding 5)', async () => {
    // adminFetch THROWS AuthError on a 401 rather than returning it, so the
    // !response.ok branch never sees it -- the bare catch below it was the
    // ONLY handler, and it reported a network failure for a sign-in problem.
    // load() distinguishes this case five lines up; revoke() must too.
    vi.stubEnv('VITE_ADMIN_API_BASE_URL', 'https://admin.example');
    vi.stubEnv('VITE_APP_CHANNEL', 'demo');
    const { impl } = mockFetch((url) => {
      if (url.includes('/revoke')) return jsonResponse({ detail: 'expired' }, 401);
      return jsonResponse({ links: [SAMPLE_ROW] });
    });

    render(<LinkHistoryPage user={managerUser()} fetchImpl={impl} />);
    const revokeButton = await screen.findByRole('button', { name: /^revoke$/i });

    const { fireEvent } = await import('@testing-library/react');
    fireEvent.click(revokeButton);

    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toMatch(/sign in again/i);
    expect(alert.textContent).not.toMatch(/could not reach the server/i);
  });

  it('revoke: a 403 (ForbiddenError) surfaces the server detail, not "could not reach the server" (x22hm review finding 5)', async () => {
    // Same asymmetry as the 401 case above: adminFetch throws ForbiddenError
    // on a 403, so only the catch handles it.
    vi.stubEnv('VITE_ADMIN_API_BASE_URL', 'https://admin.example');
    vi.stubEnv('VITE_APP_CHANNEL', 'demo');
    const { impl } = mockFetch((url) => {
      if (url.includes('/revoke')) {
        return jsonResponse({ detail: 'not your firm' }, 403);
      }
      return jsonResponse({ links: [SAMPLE_ROW] });
    });

    render(<LinkHistoryPage user={managerUser()} fetchImpl={impl} />);
    const revokeButton = await screen.findByRole('button', { name: /^revoke$/i });

    const { fireEvent } = await import('@testing-library/react');
    fireEvent.click(revokeButton);

    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toMatch(/not your firm/i);
    expect(alert.textContent).not.toMatch(/could not reach the server/i);
  });
});

describe('LinkHistoryPage status dropdown vs backend links_store (x22hm review finding 4)', () => {
  // The dropdown hand-lists all six links_store status values. Correct
  // today, but nothing reddened when a status was added, renamed, or
  // removed on either side -- a drifted option silently sends a `status=`
  // the backend equality-filters to zero rows: a working page returning an
  // empty table, the failure mode no behavioral test sees. Parses the
  // backend source directly (same idiom as
  // frontend/src/shared/introScript.mirror.test.ts) so a rename on either
  // side fails HERE instead of shipping silently.
  it('lists exactly the STATUS_* values links_store.py defines', () => {
    const source = readFileSync(
      repoPath('backend', 'services', 'links_store.py'),
      'utf-8',
    );
    const backendStatuses = new Set<string>();
    for (const match of source.matchAll(/^STATUS_[A-Z_]+ = "([a-z_]+)"$/gm)) {
      backendStatuses.add(match[1]);
    }
    // Guard the guard: if the pattern stops matching links_store.py's actual
    // constant style, this must fail loudly rather than compare against an
    // empty set.
    expect(backendStatuses.size).toBeGreaterThan(0);

    const pageSource = readFileSync(
      repoPath('frontend', 'src', 'console', 'LinkHistoryPage.tsx'),
      'utf-8',
    );
    // Only the <option value="..."> entries inside the status <select> --
    // excludes the "All" option's value="", which is the page's own filter
    // sentinel and not a links_store status.
    const optionValues = new Set<string>();
    for (const match of pageSource.matchAll(/<option value="([a-z_]+)">/g)) {
      optionValues.add(match[1]);
    }
    expect(optionValues.size).toBeGreaterThan(0);

    expect(optionValues).toEqual(backendStatuses);
  });
});
