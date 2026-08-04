// @vitest-environment jsdom
//
// Regression tests for SchemaFormDemo's authed manifest fetch (bd z2is):
//   1. The /api/form-kits fetch carries `Authorization: Bearer <idToken>`.
//   2. A 401 SURFACES as the error state -- it must NOT silently fall back to
//      the static /form-kits/index.json bundle (which would mask a broken
//      token path in prod behind stale bundled kits).
//   3. A plain network failure (backend down, local dev) still falls back to
//      the static bundle -- the pre-z2is behavior, preserved.
import { render, screen, cleanup, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { SchemaFormDemo } from './SchemaFormDemo';

// Presentational/heavy children are irrelevant here -- the assertions are all
// about the manifest fetch. Mock them shallow.
vi.mock('./components/SchemaForm', () => ({
  SchemaForm: () => <div data-testid="schema-form" />,
}));
vi.mock('./components/LanguageSelectionModal', () => ({
  LanguageSelectionModal: () => <div data-testid="onboarding-modal" />,
}));
vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({
    user: { getIdToken: async () => 'id-token-abc' },
  }),
}));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  sessionStorage.clear();
});

function stubFetch(handler: (url: string) => Promise<Partial<Response>>) {
  const calls: string[] = [];
  const fetchMock = vi.fn(async (url: any) => {
    calls.push(String(url));
    return (await handler(String(url))) as Response;
  });
  vi.stubGlobal('fetch', fetchMock);
  return calls;
}

describe('SchemaFormDemo authed manifest fetch (bd z2is)', () => {
  it('sends the Firebase ID token on the /api/form-kits fetch', async () => {
    const seenHeaders: Record<string, string>[] = [];
    const fetchMock = vi.fn(async (url: any, init?: any) => {
      if (String(url).includes('/api/form-kits')) {
        seenHeaders.push((init?.headers ?? {}) as Record<string, string>);
        return {
          ok: true,
          status: 200,
          json: async () => ({ forms: [] }),
        } as unknown as Response;
      }
      throw new Error(`unexpected fetch: ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);

    render(<SchemaFormDemo />);
    await waitFor(() => expect(seenHeaders.length).toBeGreaterThan(0));
    expect(seenHeaders[0]['Authorization']).toBe('Bearer id-token-abc');
  });

  it('surfaces a 401 as the error state and does NOT fall back to the static bundle', async () => {
    const calls = stubFetch(async (url) => {
      if (url.includes('/api/form-kits')) {
        return { ok: false, status: 401, statusText: 'Unauthorized' };
      }
      // The static fallback -- reaching this on a 401 is the regression.
      return {
        ok: true,
        status: 200,
        json: async () => ({ generatedAt: 'x', forms: [] }),
      };
    });

    render(<SchemaFormDemo />);

    await screen.findByText('Unable to load forms');
    expect(
      screen.getByText(/Not authorized to load form kits/i)
    ).toBeTruthy();
    expect(calls.some((u) => u.includes('/form-kits/index.json'))).toBe(false);
  });

  it('still falls back to the static bundle on a plain network failure', async () => {
    const calls = stubFetch(async (url) => {
      if (url.includes('/api/form-kits')) {
        throw new Error('ECONNREFUSED');
      }
      if (url.includes('/form-kits/index.json')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({ generatedAt: 'x', forms: [] }),
        };
      }
      throw new Error(`unexpected fetch: ${url}`);
    });

    render(<SchemaFormDemo />);

    await waitFor(() =>
      expect(calls.some((u) => u.includes('/form-kits/index.json'))).toBe(true)
    );
    // Fallback succeeded with zero forms -> the "no forms" state, not the
    // auth-error state.
    expect(screen.queryByText(/Not authorized/i)).toBeNull();
  });
});
