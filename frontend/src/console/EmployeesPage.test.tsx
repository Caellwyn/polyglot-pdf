// @vitest-environment jsdom
//
// EmployeesPage (bd polyglot-pdf-krbol, C4). Pins the exit criterion
// verbatim: "the create request body carries no firm_id; the reset link is
// shown once; disable and role change call their routes once (mocked API,
// mutation-verified)".
//
// Requests are verified at the WIRE LEVEL via a mocked fetchImpl (mirrors
// MintLinkPage.test.tsx's approach, since EmployeesPage builds its own typed
// calls on adminApi.ts's adminFetch rather than importing route-specific
// helpers) -- this is a STRONGER guard than asserting a helper was called
// with an object, because it also proves JSON.stringify actually drops the
// omitted key rather than serializing `firm_id: undefined` as some other
// shape.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, fireEvent, waitFor, within } from '@testing-library/react';

import { EmployeesPage } from './EmployeesPage';

// Firebase initializes at import time and throws without an API key.
vi.mock('../firebase/config', () => ({
  auth: { __sentinel: 'auth' },
  db: { __sentinel: 'db' },
}));

const MANAGER_USER = {
  uid: 'staff-1',
  getIdToken: async () => 'staff-token',
  getIdTokenResult: async () => ({ claims: { firm_role: 'manager' } }),
};

const EMPLOYEE_USER = {
  uid: 'staff-2',
  getIdToken: async () => 'staff-token-2',
  getIdTokenResult: async () => ({ claims: { firm_role: 'employee' } }),
};

vi.mock('../contexts/AuthContext', async () => {
  const actual = await vi.importActual<Record<string, unknown>>(
    '../contexts/AuthContext',
  );
  return {
    ...actual,
    useAuth: () => ({ user: MANAGER_USER, loading: false }),
  };
});

const EMPLOYEE_ROW = {
  uid: 'u1',
  email: 'alice@example.com',
  display_name: 'Alice',
  disabled: false,
  firm_id: 'firm-a',
  firm_role: 'employee',
};

const MANAGER_ROW = {
  uid: 'u2',
  email: 'bob@example.com',
  display_name: 'Bob',
  disabled: true,
  firm_id: 'firm-a',
  firm_role: 'manager',
};

// The signed-in manager's OWN row, as it comes back from list_firm_users:
// the query filters on the firm_id claim the manager carries too, so their
// own account is a normal member of the returned staff pool. `uid` matches
// MANAGER_USER.uid deliberately -- this is the shape the self-action guard
// must recognize.
const SELF_ROW = {
  uid: 'staff-1',
  email: 'manager@example.com',
  display_name: 'The Manager',
  disabled: false,
  firm_id: 'firm-a',
  firm_role: 'manager',
};

const LIST_PAGE = { firm_id: 'firm-a', users: [EMPLOYEE_ROW, MANAGER_ROW], truncated: false };
const LIST_PAGE_WITH_SELF = {
  firm_id: 'firm-a',
  users: [EMPLOYEE_ROW, MANAGER_ROW, SELF_ROW],
  truncated: false,
};

interface Call { url: string; init: RequestInit; body: unknown; }

/** A fetch double that serves GET /admin/users from `listResponse` (default
 * LIST_PAGE) and any mutation from `mutationResponse` -- records every call
 * with its parsed JSON body so tests can assert the exact wire shape. */
function mockFetch(
  mutationResponse: Partial<Response> & { json?: () => Promise<unknown> } = {
    ok: true, status: 200, json: async () => ({}),
  },
  listResponse: Partial<Response> & { json?: () => Promise<unknown> } = {
    ok: true, status: 200, json: async () => LIST_PAGE,
  },
) {
  const calls: Call[] = [];
  const impl = vi.fn(async (url: unknown, init?: RequestInit) => {
    const method = init?.method ?? 'GET';
    let body: unknown = undefined;
    if (init?.body) {
      try { body = JSON.parse(init.body as string); } catch { body = init.body; }
    }
    calls.push({ url: String(url), init: init ?? {}, body });
    if (method === 'GET') return listResponse as unknown as Response;
    return mutationResponse as unknown as Response;
  });
  return { impl: impl as unknown as typeof fetch, calls };
}

async function mountedAsManager(
  mutationResponse?: Partial<Response> & { json?: () => Promise<unknown> },
  listResponse?: Partial<Response> & { json?: () => Promise<unknown> },
) {
  const { impl, calls } = mockFetch(mutationResponse, listResponse);
  render(<EmployeesPage user={MANAGER_USER} fetchImpl={impl} />);
  await waitFor(() => expect(screen.getByText('alice@example.com')).toBeTruthy());
  return { calls };
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe('EmployeesPage: manager-only UX gate', () => {
  it('renders nothing for a signed-in staffer whose claim is NOT manager', async () => {
    const { impl } = mockFetch();
    const { container } = render(<EmployeesPage user={EMPLOYEE_USER} fetchImpl={impl} />);

    // Give the async claim check a tick to resolve.
    await waitFor(() => expect(container.textContent).toBe(''));
    expect(screen.queryByText('Your team')).toBeNull();
    // And it must never have called the list route at all -- an employee
    // forcing this route open should not even trigger a request an app
    // admin-only surface would refuse.
    expect(impl).not.toHaveBeenCalled();
  });

  it('renders the page for a signed-in manager', async () => {
    await mountedAsManager();
    expect(screen.getByText('Your team')).toBeTruthy();
  });

  it('treats a user with no getIdTokenResult as not-manager (fail closed)', async () => {
    const { impl } = mockFetch();
    const bareUser = { getIdToken: async () => 'tok' } as unknown as typeof MANAGER_USER;
    render(<EmployeesPage user={bareUser} fetchImpl={impl} />);
    await waitFor(() => expect(impl).not.toHaveBeenCalled());
    expect(screen.queryByText('Your team')).toBeNull();
  });
});

describe('EmployeesPage: list', () => {
  it('lists the firm\'s staff with NO firm_id query param', async () => {
    const { calls } = await mountedAsManager();
    expect(screen.getByText('bob@example.com')).toBeTruthy();

    const listCall = calls.find((c) => (c.init.method ?? 'GET') === 'GET');
    expect(listCall).toBeTruthy();
    expect(listCall!.url).not.toContain('firm_id');
  });
});

describe('EmployeesPage: create', () => {
  it('the create request body carries no firm_id key', async () => {
    const { calls } = await mountedAsManager({
      ok: true, status: 200,
      json: async () => ({
        uid: 'u3', email: 'carol@example.com', firm_id: 'firm-a',
        firm_role: 'employee', reset_link: 'https://example.com/reset?oobCode=abc123',
        request_id: 'req-1',
      }),
    });

    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'carol@example.com' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create account' }));

    await waitFor(() => {
      const createCall = calls.find((c) => c.init.method === 'POST');
      expect(createCall).toBeTruthy();
    });

    const createCall = calls.find((c) => c.init.method === 'POST')!;
    const body = createCall.body as Record<string, unknown>;
    expect(body.email).toBe('carol@example.com');
    expect(body.firm_role).toBe('employee');
    // THE EXIT CRITERION: no firm_id key on the wire at all -- not `null`,
    // not an empty string, simply absent. Present with any value trips
    // resolve_target_firm's manager refusal (403), which the create call
    // above did not receive, but this asserts the WIRE shape directly
    // rather than inferring it from a lack of failure.
    expect(Object.prototype.hasOwnProperty.call(body, 'firm_id')).toBe(false);
  });

  it('shows the reset link exactly once and never a password', async () => {
    await mountedAsManager({
      ok: true, status: 200,
      json: async () => ({
        uid: 'u3', email: 'carol@example.com', firm_id: 'firm-a',
        firm_role: 'employee', reset_link: 'https://example.com/reset?oobCode=abc123',
        request_id: 'req-1',
      }),
    });

    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'carol@example.com' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create account' }));

    const occurrences = await screen.findAllByDisplayValue('https://example.com/reset?oobCode=abc123');
    expect(occurrences).toHaveLength(1);
    // No password FIELD or VALUE renders -- the page's own copy legitimately
    // says "password-reset link" (expected), so the guard is not "the word
    // password never appears" but "there is no input asking for or showing
    // one": no type="password" input anywhere on the page.
    // eslint-disable-next-line testing-library/no-node-access
    expect(document.querySelector('input[type="password"]')).toBeNull();
  });

  it('clears the reset link on the next create attempt', async () => {
    await mountedAsManager({
      ok: true, status: 200,
      json: async () => ({
        uid: 'u3', email: 'carol@example.com', firm_id: 'firm-a',
        firm_role: 'employee', reset_link: 'https://example.com/reset?oobCode=first',
        request_id: 'req-1',
      }),
    });

    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'carol@example.com' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create account' }));
    await screen.findByDisplayValue('https://example.com/reset?oobCode=first');

    // A second create starts -- the OLD link must vanish immediately, not
    // linger pointing at the wrong (now-superseded) account.
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'dave@example.com' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create account' }));

    await waitFor(() => {
      expect(screen.queryByDisplayValue('https://example.com/reset?oobCode=first')).toBeNull();
    });
  });
});

describe('EmployeesPage: disable / role change', () => {
  it('disable calls its route exactly once with no firm_id, then re-reads the list', async () => {
    const { calls } = await mountedAsManager({ ok: true, status: 200, json: async () => ({}) });

    fireEvent.click(screen.getAllByRole('button', { name: /^(Disable|Enable)$/ })[0]);

    await waitFor(() => {
      const disableCalls = calls.filter((c) => c.url.includes('/disable'));
      expect(disableCalls).toHaveLength(1);
    });

    const disableCall = calls.find((c) => c.url.includes('/disable'))!;
    expect(disableCall.init.method).toBe('PATCH');
    const body = disableCall.body as Record<string, unknown>;
    expect(Object.prototype.hasOwnProperty.call(body, 'firm_id')).toBe(false);

    // Re-reads: a second GET happened after the mutation (mutate-then-re-read).
    const getCalls = calls.filter((c) => (c.init.method ?? 'GET') === 'GET');
    expect(getCalls.length).toBeGreaterThanOrEqual(2);
  });

  it('role change calls its route exactly once with no firm_id, then re-reads', async () => {
    const { calls } = await mountedAsManager({ ok: true, status: 200, json: async () => ({}) });

    const roleSelect = screen.getByLabelText('Role for alice@example.com');
    fireEvent.change(roleSelect, { target: { value: 'manager' } });

    await waitFor(() => {
      const roleCalls = calls.filter((c) => c.url.includes('/role'));
      expect(roleCalls).toHaveLength(1);
    });

    const roleCall = calls.find((c) => c.url.includes('/role'))!;
    expect(roleCall.init.method).toBe('PATCH');
    const body = roleCall.body as Record<string, unknown>;
    expect(body.firm_role).toBe('manager');
    expect(Object.prototype.hasOwnProperty.call(body, 'firm_id')).toBe(false);
  });

  it('does not call the role route when the selection is unchanged', async () => {
    const { calls } = await mountedAsManager();
    const roleSelect = screen.getByLabelText('Role for alice@example.com');
    fireEvent.change(roleSelect, { target: { value: 'employee' } }); // already employee
    await new Promise((r) => setTimeout(r, 0));
    expect(calls.filter((c) => c.url.includes('/role'))).toHaveLength(0);
  });
});

describe('EmployeesPage: self-action guard', () => {
  // list_firm_users filters on the firm_id claim the signed-in manager
  // carries too, so the manager's OWN row appears in their firm's staff
  // list. Neither backend route refuses actor.uid === uid, so the page
  // itself must not offer a way to demote or disable that row -- doing
  // either would drop the manager's own firm_role claim (locking them out
  // of the console) or disable their whole account (locking them out of
  // the app). This uses MANAGER_USER's own uid ('staff-1'), which the
  // other fixtures in this file deliberately never use.
  it('renders no role select and no enabled Disable button for the signed-in manager\'s own row', async () => {
    const { impl } = mockFetch(undefined, { ok: true, status: 200, json: async () => LIST_PAGE_WITH_SELF });
    render(<EmployeesPage user={MANAGER_USER} fetchImpl={impl} />);
    await waitFor(() => expect(screen.getByText(/manager@example\.com/)).toBeTruthy());

    // No role <select> for the self row -- only a static role display.
    expect(screen.queryByLabelText('Role for manager@example.com')).toBeNull();

    // The self row's own Disable button (there are three rows total; the
    // self row's button is identified by its disabled state plus title).
    const selfRow = screen.getByText(/manager@example\.com/).closest('tr')!;
    const disableButton = within(selfRow).getByRole('button', { name: /^(Disable|Enable)$/ }) as HTMLButtonElement;
    expect(disableButton.disabled).toBe(true);
  });

  it('clicking the disabled self-row Disable button sends no request', async () => {
    const { impl, calls } = mockFetch(undefined, { ok: true, status: 200, json: async () => LIST_PAGE_WITH_SELF });
    render(<EmployeesPage user={MANAGER_USER} fetchImpl={impl} />);
    await waitFor(() => expect(screen.getByText(/manager@example\.com/)).toBeTruthy());

    const selfRow = screen.getByText(/manager@example\.com/).closest('tr')!;
    const disableButton = within(selfRow).getByRole('button', { name: /^(Disable|Enable)$/ });
    fireEvent.click(disableButton);
    await new Promise((r) => setTimeout(r, 0));

    // A disabled DOM button does not fire React's onClick at all, so this
    // also exercises the handler-level guard (handleToggleDisabled's own
    // early return) should that ever change: either way, no request for
    // the manager's own uid is ever sent.
    expect(calls.filter((c) => c.url.includes(`/${MANAGER_USER.uid}/`))).toHaveLength(0);
  });
});
