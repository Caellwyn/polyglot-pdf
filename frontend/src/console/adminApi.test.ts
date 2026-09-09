// @vitest-environment jsdom
//
// adminApi.ts (bd polyglot-pdf-z4ljj, C0): the generic authenticated-fetch
// helper C4/C5 build their own calls on. What matters here is the SAME thing
// that matters for MintLinkPage's auth tests -- every request carries the
// staff token and the build's channel, and a 401/403 is classified rather
// than left as an opaque failed response.
import { afterEach, describe, expect, it, vi } from 'vitest';

import { AuthError, ForbiddenError, adminFetch, forbiddenFromDetail, withChannel } from './adminApi';

afterEach(() => {
  vi.unstubAllEnvs();
});

const STAFF_USER = { getIdToken: async () => 'staff-token' };

describe('withChannel', () => {
  it('appends the build channel to a bare path', () => {
    vi.stubEnv('VITE_APP_CHANNEL', 'staging');
    expect(withChannel('/admin/users')).toBe('/admin/users?channel=staging');
  });

  it('preserves an existing query string', () => {
    vi.stubEnv('VITE_APP_CHANNEL', 'demo');
    expect(withChannel('/admin/users?firm_id=f1')).toBe(
      '/admin/users?firm_id=f1&channel=demo',
    );
  });

  it('defaults to demo when the channel env is unset', () => {
    vi.stubEnv('VITE_APP_CHANNEL', undefined);
    expect(withChannel('/admin/users')).toBe('/admin/users?channel=demo');
  });
});

describe('adminFetch', () => {
  it('sends the staff Bearer token and the channel param', async () => {
    vi.stubEnv('VITE_APP_CHANNEL', 'staging');
    vi.stubEnv('VITE_ADMIN_API_BASE_URL', 'https://admin.example');
    const calls: Array<{ url: string; init: RequestInit }> = [];
    const impl = vi.fn(async (url: unknown, init?: RequestInit) => {
      calls.push({ url: String(url), init: init ?? {} });
      return { ok: true, status: 200, json: async () => ({}) } as unknown as Response;
    });

    await adminFetch('/admin/users?firm_id=f1', STAFF_USER, {}, impl as unknown as typeof fetch);

    expect(calls).toHaveLength(1);
    expect(calls[0].url).toBe('https://admin.example/admin/users?firm_id=f1&channel=staging');
    const headers = calls[0].init.headers as Record<string, string>;
    expect(headers.Authorization).toBe('Bearer staff-token');
  });

  it('sends no Authorization header when no user is signed in', async () => {
    const impl = vi.fn(async (_url: unknown, init?: RequestInit) => (
      { ok: true, status: 200, json: async () => ({}) } as unknown as Response
    ));
    await adminFetch('/admin/whoami', null, {}, impl as unknown as typeof fetch);
    const init = impl.mock.calls[0][1];
    expect((init?.headers as Record<string, string>).Authorization).toBeUndefined();
  });

  it('throws AuthError on a 401', async () => {
    const impl = vi.fn(async () => (
      { ok: false, status: 401, json: async () => ({}) } as unknown as Response
    ));
    await expect(
      adminFetch('/admin/whoami', STAFF_USER, {}, impl as unknown as typeof fetch),
    ).rejects.toBeInstanceOf(AuthError);
  });

  it('throws ForbiddenError on a 403, carrying the server detail', async () => {
    const impl = vi.fn(async () => (
      {
        ok: false, status: 403,
        json: async () => ({ detail: 'Not a firm account' }),
      } as unknown as Response
    ));
    await expect(
      adminFetch('/admin/users', STAFF_USER, {}, impl as unknown as typeof fetch),
    ).rejects.toMatchObject({
      name: 'ForbiddenError', message: 'Not a firm account', noAdminAccess: false,
    });
  });

  it('strips the NO_ADMIN_ACCESS wire marker and sets noAdminAccess on a 403 that carries it', async () => {
    // Cross-surface review finding 1 (bd polyglot-pdf-z4ljj): the server
    // marks the "no admin access at all" 403 with admin_auth's
    // NO_ADMIN_ACCESS_PREFIX (see require_app_admin_or_owning_manager,
    // admin_auth.py:303). Every other adminFetch-style client strips it and
    // routes the eviction on the flag; this client must too, or a raw
    // protocol token reaches the caller's UI.
    const impl = vi.fn(async () => (
      {
        ok: false, status: 403,
        json: async () => ({
          detail: 'NO_ADMIN_ACCESS: This account is neither an admin nor a firm manager',
        }),
      } as unknown as Response
    ));
    await expect(
      adminFetch('/admin/users', STAFF_USER, {}, impl as unknown as typeof fetch),
    ).rejects.toMatchObject({
      name: 'ForbiddenError',
      message: 'This account is neither an admin nor a firm manager',
      noAdminAccess: true,
    });
  });

  it('returns the response unchanged for any other status', async () => {
    const impl = vi.fn(async () => (
      { ok: false, status: 404, json: async () => ({}) } as unknown as Response
    ));
    const res = await adminFetch('/admin/users', STAFF_USER, {}, impl as unknown as typeof fetch);
    expect(res.status).toBe(404);
  });
});

describe('forbiddenFromDetail', () => {
  it('leaves an ordinary 403 detail unchanged with noAdminAccess false', () => {
    const err = forbiddenFromDetail('Not a firm account');
    expect(err.message).toBe('Not a firm account');
    expect(err.noAdminAccess).toBe(false);
  });

  it('strips the NO_ADMIN_ACCESS prefix and sets noAdminAccess true', () => {
    const err = forbiddenFromDetail('NO_ADMIN_ACCESS: no admin claim on this account');
    expect(err.message).toBe('no admin claim on this account');
    expect(err.noAdminAccess).toBe(true);
  });
});
