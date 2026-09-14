// @vitest-environment jsdom
//
// FirmAlertsBanner (bd polyglot-pdf-62o4d).
//
// Exit criterion 2: "renders one row per unacknowledged alert with the
// mapped text and never a raw context field value; Acknowledge appears
// for a manager only and calls the route once then re-fetches; a fetch
// error renders nothing." This component takes `user` as a plain prop (no
// useAuth() of its own), so it needs no AuthContext/firebase mocking --
// unlike MintLinkPage.test.tsx / LinkHistoryPage.test.tsx, which render
// the real page and so must stub the auth chain those pages import.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';

import { FirmAlertsBanner } from './FirmAlertsBanner';

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

const CREDIT_LOW_ALERT = {
  id: 'a1', kind: 'credit_low', level: 'warning', ts: 1000,
  context: { balance: 3, threshold: 10 }, acknowledged_at: null,
};
const CREDIT_EXHAUSTED_ALERT = {
  id: 'a2', kind: 'credit_exhausted', level: 'critical', ts: 2000,
  context: { balance: 0, threshold: 10 }, acknowledged_at: null,
};
const LINK_EXHAUSTED_ALERT = {
  id: 'a3', kind: 'link_exhausted', level: 'critical', ts: 3000,
  // A context field that is NOT named in the message map -- confirms the
  // banner never dumps raw context, even a value present on the row.
  context: { jti: 'jti-secret-value', spend_usd: 5.0, ceiling_usd: 5.0 },
  acknowledged_at: null,
};

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllEnvs();
});

describe('FirmAlertsBanner', () => {
  it('renders nothing with no user', () => {
    const { impl } = mockFetch(() => jsonResponse({ alerts: [] }));
    render(<FirmAlertsBanner user={null} fetchImpl={impl} />);
    expect(document.body.textContent).toBe('');
  });

  it('renders nothing when there are no unacknowledged alerts', async () => {
    const { impl } = mockFetch(() => jsonResponse({ alerts: [] }));
    render(<FirmAlertsBanner user={managerUser()} fetchImpl={impl} />);
    await waitFor(() => expect(impl).toHaveBeenCalled());
    expect(document.body.textContent).toBe('');
  });

  it('renders nothing on a fetch error (never a raw error message)', async () => {
    const { impl } = mockFetch(() => jsonResponse({ detail: 'boom' }, 503));
    render(<FirmAlertsBanner user={managerUser()} fetchImpl={impl} />);
    await waitFor(() => expect(impl).toHaveBeenCalled());
    expect(document.body.textContent).toBe('');
  });

  it('renders nothing when the fetch throws', async () => {
    const impl = vi.fn(async () => { throw new Error('network down'); });
    render(<FirmAlertsBanner user={managerUser()} fetchImpl={impl as unknown as typeof fetch} />);
    await waitFor(() => expect(impl).toHaveBeenCalled());
    expect(document.body.textContent).toBe('');
  });
});

describe('FirmAlertsBanner rows', () => {
  it('renders one row per alert with the mapped plain-language text', async () => {
    const { impl } = mockFetch(() => jsonResponse({
      alerts: [CREDIT_LOW_ALERT, CREDIT_EXHAUSTED_ALERT, LINK_EXHAUSTED_ALERT],
    }));
    render(<FirmAlertsBanner user={employeeUser()} fetchImpl={impl} />);

    expect(await screen.findByText('This firm has 3 credits left')).toBeTruthy();
    expect(screen.getByText('This firm is out of credits; new links cannot be minted'))
      .toBeTruthy();
    expect(screen.getByText('A client link hit its spend cap')).toBeTruthy();
  });

  it('never renders a raw context field value', async () => {
    const { impl } = mockFetch(() => jsonResponse({ alerts: [LINK_EXHAUSTED_ALERT] }));
    render(<FirmAlertsBanner user={employeeUser()} fetchImpl={impl} />);

    await screen.findByText('A client link hit its spend cap');
    // The mapped sentence names no context field; the raw jti/spend/ceiling
    // values must appear NOWHERE in the rendered output.
    expect(document.body.textContent).not.toContain('jti-secret-value');
    expect(document.body.textContent).not.toContain('5.0');
  });

  it('falls back to a generic message for an unrecognized kind, with no context interpolation', async () => {
    const { impl } = mockFetch(() => jsonResponse({
      alerts: [{
        id: 'a9', kind: 'something_new', level: 'warning', ts: 1,
        context: { mystery: 'value' }, acknowledged_at: null,
      }],
    }));
    render(<FirmAlertsBanner user={employeeUser()} fetchImpl={impl} />);

    expect(await screen.findByText('This firm has an alert that needs attention'))
      .toBeTruthy();
    expect(document.body.textContent).not.toContain('mystery');
  });

  it('fetches acknowledged=false for the given firm', async () => {
    const { impl, calls } = mockFetch(() => jsonResponse({ alerts: [] }));
    render(<FirmAlertsBanner user={managerUser('mgr-1')} fetchImpl={impl} />);
    await waitFor(() => expect(calls.length).toBe(1));
    // base is a dummy origin -- adminApiBaseUrl() resolves to '' in this
    // test env (no VITE_ADMIN_API_BASE_URL stubbed), so the recorded URL
    // is path-relative; URL() needs SOME base to parse it.
    const url = new URL(calls[0].url, 'https://admin.example');
    expect(url.pathname).toBe('/admin/firms/firm-1/alerts');
    expect(url.searchParams.get('acknowledged')).toBe('false');
  });
});

describe('FirmAlertsBanner acknowledge', () => {
  it('shows Acknowledge for a manager only, never for an employee', async () => {
    const { impl: managerImpl } = mockFetch(() => jsonResponse({ alerts: [CREDIT_LOW_ALERT] }));
    render(<FirmAlertsBanner user={managerUser()} fetchImpl={managerImpl} />);
    await screen.findByText('This firm has 3 credits left');
    expect(screen.getByRole('button', { name: /acknowledge/i })).toBeTruthy();
    cleanup();

    const { impl: employeeImpl } = mockFetch(() => jsonResponse({ alerts: [CREDIT_LOW_ALERT] }));
    render(<FirmAlertsBanner user={employeeUser()} fetchImpl={employeeImpl} />);
    await screen.findByText('This firm has 3 credits left');
    expect(screen.queryByRole('button', { name: /acknowledge/i })).toBeNull();
  });

  it('calls acknowledge ONCE then re-fetches (not a local patch)', async () => {
    let listCallCount = 0;
    const { impl, calls } = mockFetch((url, init) => {
      if (url.includes('/acknowledge')) {
        expect(init?.method).toBe('PATCH');
        return jsonResponse({ id: 'a1', acknowledged_by: 'mgr-1', acknowledged_at: 999 });
      }
      listCallCount += 1;
      // First read shows the alert; the SERVER'S second read (post-
      // acknowledge) shows it gone -- proves the banner re-fetches rather
      // than removing the row itself.
      const alerts = listCallCount === 1 ? [CREDIT_LOW_ALERT] : [];
      return jsonResponse({ alerts });
    });

    render(<FirmAlertsBanner user={managerUser()} fetchImpl={impl} />);
    const button = await screen.findByRole('button', { name: /acknowledge/i });

    const { fireEvent } = await import('@testing-library/react');
    fireEvent.click(button);

    await waitFor(() =>
      expect(screen.queryByText('This firm has 3 credits left')).toBeNull());

    const ackCalls = calls.filter((c) => c.url.includes('/acknowledge'));
    expect(ackCalls).toHaveLength(1);
    expect(listCallCount).toBe(2);
  });

  it('a failed acknowledge does not remove the row (no optimistic update)', async () => {
    const { impl } = mockFetch((url) => {
      if (url.includes('/acknowledge')) {
        return jsonResponse({ detail: 'already acknowledged by someone else' }, 409);
      }
      return jsonResponse({ alerts: [CREDIT_LOW_ALERT] });
    });

    render(<FirmAlertsBanner user={managerUser()} fetchImpl={impl} />);
    const button = await screen.findByRole('button', { name: /acknowledge/i });

    const { fireEvent } = await import('@testing-library/react');
    fireEvent.click(button);

    // The row must still be present -- a 409 must not have been treated as
    // success and hidden the row locally.
    await waitFor(() => expect(screen.getByRole('button', { name: /acknowledge/i })).toBeTruthy());
    expect(screen.getByText('This firm has 3 credits left')).toBeTruthy();
  });
});

describe('FirmAlertsBanner refreshSignal', () => {
  it('re-fetches when refreshSignal changes (mint page 402 hook)', async () => {
    const { impl, calls } = mockFetch(() => jsonResponse({ alerts: [] }));
    const { rerender } = render(
      <FirmAlertsBanner user={managerUser()} fetchImpl={impl} refreshSignal={0} />,
    );
    await waitFor(() => expect(calls.length).toBe(1));

    rerender(<FirmAlertsBanner user={managerUser()} fetchImpl={impl} refreshSignal={1} />);
    await waitFor(() => expect(calls.length).toBe(2));
  });
});
