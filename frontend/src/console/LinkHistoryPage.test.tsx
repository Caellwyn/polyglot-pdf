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

import { LinkHistoryPage } from './LinkHistoryPage';

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
    return handler(String(url), init);
  });
  return { impl: impl as unknown as typeof fetch, calls };
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

  it('an employee view sends NO employee_id and hides the revoke controls', async () => {
    vi.stubEnv('VITE_ADMIN_API_BASE_URL', 'https://admin.example');
    vi.stubEnv('VITE_APP_CHANNEL', 'demo');
    const { impl, calls } = mockFetch(() => jsonResponse({ links: [SAMPLE_ROW] }));

    render(<LinkHistoryPage user={employeeUser('emp-1')} fetchImpl={impl} />);

    await screen.findByText('w7');
    expect(calls).toHaveLength(1);
    const url = new URL(calls[0].url);
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

    const revokeCalls = calls.filter((c) => c.url.includes('/revoke'));
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

  it('shows the server error message on a failed load', async () => {
    vi.stubEnv('VITE_ADMIN_API_BASE_URL', 'https://admin.example');
    vi.stubEnv('VITE_APP_CHANNEL', 'demo');
    const { impl } = mockFetch(() => jsonResponse({ detail: 'link store unavailable' }, 503));

    render(<LinkHistoryPage user={managerUser()} fetchImpl={impl} />);

    expect(await screen.findByRole('alert')).toBeTruthy();
    expect(screen.getByText(/link store unavailable/i)).toBeTruthy();
  });
});
