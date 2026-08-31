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

  it('says MINTING IS OFF rather than showing a 404', async () => {
    // The backend answers 404 when LINK_MINTING_ENABLED is false -- on purpose,
    // so a disabled endpoint does not advertise itself. "Not found" on a button
    // you just pressed tells the operator nothing about which knob to turn.
    await mounted({ ok: false, status: 404, json: async () => ({}) });

    fireEvent.click(screen.getByText('Create link'));

    await waitFor(() => expect(screen.getByRole('alert')).toBeTruthy());
    expect(screen.getByRole('alert').textContent).toContain('LINK_MINTING_ENABLED');
  });

  it('names LINK_BASE_URL when link delivery is unconfigured', async () => {
    await mounted({ ok: false, status: 503, json: async () => ({}) });

    fireEvent.click(screen.getByText('Create link'));

    await waitFor(() => expect(screen.getByRole('alert')).toBeTruthy());
    expect(screen.getByRole('alert').textContent).toContain('LINK_BASE_URL');
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
