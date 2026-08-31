// @vitest-environment jsdom
//
// The mint page (bd polyglot-pdf-gob8l, first console slice).
//
// What matters here is what the MAINTAINER sees when something is off. Minting
// is disabled by default, LINK_BASE_URL may be unset, and an account without a
// firm claim cannot mint -- each of those is a different fix, and a page that
// says "something went wrong" for all three sends you hunting.
import { describe, it, expect, vi, afterEach } from 'vitest';
import { cleanup, render, screen, fireEvent, waitFor } from '@testing-library/react';

import { MintLinkPage } from './MintLinkPage';

// The page reads its user from context, not from a prop -- the route element
// passes no props. Firebase initializes at import time and throws without an
// API key, so the whole auth chain is stubbed (same pattern as
// clientRoute.test.tsx).
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
    useAuth: () => ({
      user: { uid: 'staff-1', getIdToken: async () => 'staff-token' },
      loading: false,
    }),
  };
});

const CATALOGUE = {
  ok: true,
  status: 200,
  json: async () => ({ forms: [{ id: 'w7', label: 'W-7' }, { id: 'i-90', label: 'I-90' }] }),
} as unknown as Response;

function mockFetch(mintResponse: Partial<Response> & { json?: () => Promise<unknown> }) {
  const calls: Array<{ url: string; init?: RequestInit }> = [];
  const impl = vi.fn(async (url: unknown, init?: RequestInit) => {
    calls.push({ url: String(url), init });
    if (String(url).includes('/api/form-kits')) return CATALOGUE;
    return mintResponse as unknown as Response;
  });
  return { impl: impl as unknown as typeof fetch, calls };
}

async function mounted(mintResponse: Partial<Response> & { json?: () => Promise<unknown> }) {
  const { impl, calls } = mockFetch(mintResponse);
  render(<MintLinkPage fetchImpl={impl} />);
  // Wait for the catalogue so the picker has a selection.
  await waitFor(() => expect(screen.getByRole('combobox')).toBeTruthy());
  await waitFor(() =>
    expect((screen.getByRole('combobox') as HTMLSelectElement).value).toBe('w7'),
  );
  return { calls };
}

afterEach(() => {
  // This project configures no auto-cleanup; a stale render otherwise wins
  // every subsequent query.
  cleanup();
  vi.restoreAllMocks();
});

describe('MintLinkPage', () => {
  it('shows the forms the caller may actually see', async () => {
    await mounted({ ok: true, status: 200, json: async () => ({}) });
    expect(screen.getByText('W-7')).toBeTruthy();
    expect(screen.getByText('I-90')).toBeTruthy();
  });

  it('reads the catalogue from `forms`, not `parts`', async () => {
    // The WS handshake manifest uses `parts` and this route does not. Getting
    // it wrong shows an EMPTY picker with no error anywhere -- caught before
    // shipping by checking the response model rather than recalling it.
    const impl = vi.fn(async (url: unknown) => {
      if (String(url).includes('/api/form-kits')) {
        return { ok: true, status: 200,
          json: async () => ({ parts: [{ id: 'wrong', label: 'Wrong Key' }] }) } as unknown as Response;
      }
      return { ok: true, status: 200, json: async () => ({}) } as unknown as Response;
    });
    render(<MintLinkPage fetchImpl={impl as unknown as typeof fetch} />);

    await waitFor(() => expect(impl).toHaveBeenCalled());
    expect(screen.queryByText('Wrong Key')).toBeNull();
  });

  it('mints a link and shows it', async () => {
    const { calls } = await mounted({
      ok: true, status: 200,
      json: async () => ({ url: 'https://demo.example/f#t=tok', jti: 'j1', expires_at: 1 }),
    });

    fireEvent.click(screen.getByText('Create link'));

    await waitFor(() =>
      expect((screen.getByLabelText('Client link') as HTMLInputElement).value)
        .toBe('https://demo.example/f#t=tok'),
    );
    const mint = calls.find((c) => c.url.includes('/api/links/mint'));
    expect(mint).toBeTruthy();
    expect(JSON.parse(String(mint!.init!.body)).kit_id).toBe('w7');
  });

  it('AUTHENTICATES both calls with the signed-in staff token', async () => {
    // Cross-surface review r1: the page was mounted with no `user` prop and
    // read one, so resolveSessionToken(undefined) returned undefined and BOTH
    // requests went out with no Authorization header -- an empty form picker
    // and a 401 on every mint, in production only. The other tests inject
    // fetchImpl and assert on rendered output, so all 9 stayed green.
    // VFF_DISABLE_AUTH masks it locally; Cloud Run does not.
    const { calls } = await mounted({
      ok: true, status: 200,
      json: async () => ({ url: 'https://demo.example/f#t=tok' }),
    });
    fireEvent.click(screen.getByText('Create link'));
    await waitFor(() => expect(screen.getByLabelText('Client link')).toBeTruthy());

    const catalogue = calls.find((c) => c.url.includes('/api/form-kits'));
    const mint = calls.find((c) => c.url.includes('/api/links/mint'));
    for (const call of [catalogue, mint]) {
      const headers = (call!.init!.headers ?? {}) as Record<string, string>;
      expect(headers.Authorization).toBe('Bearer staff-token');
    }
  });

  it('says MINTING IS OFF rather than showing a 404', async () => {
    // The backend answers 404 when LINK_MINTING_ENABLED is false -- on purpose,
    // so a disabled endpoint does not advertise itself. "Not found" on a button
    // you just pressed tells the operator nothing about which knob to turn.
    await mounted({ ok: false, status: 404, json: async () => ({}) });

    fireEvent.click(screen.getByText('Create link'));

    await waitFor(() => expect(screen.getByRole('alert')).toBeTruthy());
    expect(screen.getByRole('alert').textContent).toContain('LINK_MINTING_ENABLED');
  });

  it('distinguishes "kit not allowed" from "minting is off" -- both are 404', async () => {
    // Cross-surface review r2: the catalogue lists every PUBLIC kit to any
    // signed-in staffer, but mint requires the kit to be in the firm's
    // explicit allowlist -- so the picker can offer a form that minting
    // refuses, with the SAME status as "minting is disabled". Telling the
    // operator to set LINK_MINTING_ENABLED (already on) is the wrong fix.
    await mounted({
      ok: false, status: 404,
      json: async () => ({ detail: 'Kit not available' }),
    });

    fireEvent.click(screen.getByText('Create link'));

    await waitFor(() => expect(screen.getByRole('alert')).toBeTruthy());
    const text = screen.getByRole('alert').textContent ?? '';
    expect(text).toContain('allowed list');
    // Emphatically NOT the disabled-minting advice.
    expect(text).not.toContain('LINK_MINTING_ENABLED');
  });

  it('names BOTH settings that cause a 503', async () => {
    // The route 503s for a missing LINK_BASE_URL *or* a missing
    // LINK_TOKEN_SECRET, so naming only one sends the operator to check a
    // setting that is already right (cross-surface review r2).
    await mounted({ ok: false, status: 503, json: async () => ({}) });

    fireEvent.click(screen.getByText('Create link'));

    await waitFor(() => expect(screen.getByRole('alert')).toBeTruthy());
    const text = screen.getByRole('alert').textContent ?? '';
    expect(text).toContain('LINK_BASE_URL');
    expect(text).toContain('LINK_TOKEN_SECRET');
  });

  it('explains a missing firm claim rather than blaming the server', async () => {
    await mounted({ ok: false, status: 403, json: async () => ({}) });

    fireEvent.click(screen.getByText('Create link'));

    await waitFor(() => expect(screen.getByRole('alert')).toBeTruthy());
    expect(screen.getByRole('alert').textContent).toContain('firm');
  });

  it('shows no link when the mint is refused', async () => {
    await mounted({ ok: false, status: 500, json: async () => ({}) });

    fireEvent.click(screen.getByText('Create link'));

    await waitFor(() => expect(screen.getByRole('alert')).toBeTruthy());
    expect(screen.queryByLabelText('Client link')).toBeNull();
  });

  it('survives the server being unreachable', async () => {
    const impl = vi.fn(async (url: unknown) => {
      if (String(url).includes('/api/form-kits')) return CATALOGUE;
      throw new Error('offline');
    });
    render(<MintLinkPage fetchImpl={impl as unknown as typeof fetch} />);
    await waitFor(() =>
      expect((screen.getByRole('combobox') as HTMLSelectElement).value).toBe('w7'),
    );

    fireEvent.click(screen.getByText('Create link'));

    await waitFor(() => expect(screen.getByRole('alert')).toBeTruthy());
    expect(screen.queryByLabelText('Client link')).toBeNull();
  });

  it('keeps the link SELECTABLE so copy is not the only way out', async () => {
    // Clipboard access is refused in plenty of contexts. A disabled input
    // cannot be selected, which would leave the operator stuck.
    await mounted({
      ok: true, status: 200,
      json: async () => ({ url: 'https://demo.example/f#t=tok' }),
    });
    fireEvent.click(screen.getByText('Create link'));

    const field = await screen.findByLabelText('Client link') as HTMLInputElement;
    expect(field.readOnly).toBe(true);
    expect(field.disabled).toBe(false);
  });
});
