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
import { clearClientLinkToken, setClientLinkToken } from '../shared/sessionCredential';

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
  // The client-link token is module state AND sessionStorage, so a leak from
  // the so88g test would silently change what every later test authenticates
  // with -- passing or failing for a reason unrelated to its own subject.
  clearClientLinkToken();
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

  it('uses the STAFF token even when this tab has opened a client link', async () => {
    // bd polyglot-pdf-so88g. The console shares an origin and a tab with /f,
    // and the mint-test-mint-again loop is the first thing anyone does with
    // this page: mint a link, open it to check it, come back and mint another.
    // Step 2 stashes a client-link token in sessionStorage, and the
    // FORM-FILLING resolver prefers it by design -- so the second mint went
    // out with the client's credential and was refused, reported to the
    // operator as "not attached to a firm".
    //
    // Not fixed by flipping that precedence: link-wins is load-bearing on the
    // fill path (it keeps a session attributed to the link, which the
    // one-time-use accounting depends on). The console asks a different
    // question, so it calls a different resolver.
    setClientLinkToken('client.link.token');

    const { calls } = await mounted({
      ok: true, status: 200,
      json: async () => ({ url: 'https://demo.example/f#t=tok' }),
    });
    fireEvent.click(screen.getByText('Create link'));
    await waitFor(() => expect(screen.getByLabelText('Client link')).toBeTruthy());

    const mint = calls.find((c) => c.url.includes('/api/links/mint'));
    const headers = (mint!.init!.headers ?? {}) as Record<string, string>;
    expect(headers.Authorization).toBe('Bearer staff-token');
    expect(headers.Authorization).not.toContain('client.link.token');
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

  it('shows insufficient-credits on a 402', async () => {
    // bd polyglot-pdf-jecrl (A3): the firm's balance does not cover this
    // kit's credit_cost. Distinct wording from every other refusal so an
    // operator does not read it as "no firm claim" or "minting is off".
    await mounted({
      ok: false, status: 402,
      json: async () => ({ detail: 'This firm does not have enough credits to mint a link.' }),
    });

    fireEvent.click(screen.getByText('Create link'));

    await waitFor(() => expect(screen.getByRole('alert')).toBeTruthy());
    const text = screen.getByRole('alert').textContent ?? '';
    expect(text).toContain('credits');
    expect(text).not.toContain('firm claim');
  });

  it('shows the balance in the 402 message when the body carries one', async () => {
    await mounted({
      ok: false, status: 402,
      json: async () => ({
        detail: 'This firm does not have enough credits to mint a link.',
        balance: 3,
      }),
    });

    fireEvent.click(screen.getByText('Create link'));

    await waitFor(() => expect(screen.getByRole('alert')).toBeTruthy());
    expect(screen.getByRole('alert').textContent).toContain('3');
  });

  it('distinguishes "live firm, wrong deployment" from "no firm claim" -- both are 403', async () => {
    // bd polyglot-pdf-jecrl (A3): a REAL firm account, refused only because
    // THIS deployment may not mint for a live firm. Needs the opposite
    // remedy from the original "not attached to a firm" 403 -- an app admin
    // cannot fix this by attaching a firm, and a signed-in staffer cannot
    // fix it at all (it is a deployment choice, not an account problem).
    await mounted({
      ok: false, status: 403,
      json: async () => ({ detail: 'This deployment cannot mint links for a live firm.' }),
    });

    fireEvent.click(screen.getByText('Create link'));

    await waitFor(() => expect(screen.getByRole('alert')).toBeTruthy());
    const text = screen.getByRole('alert').textContent ?? '';
    expect(text).toContain('live firm');
    // Emphatically NOT the "not attached to a firm" message -- that sends an
    // operator to the wrong fix (attaching a firm claim helps nothing here).
    expect(text).not.toContain('not attached to a firm');
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
