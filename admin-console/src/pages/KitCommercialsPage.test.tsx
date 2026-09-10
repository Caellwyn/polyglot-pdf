/**
 * KitCommercialsPage (bd polyglot-pdf-mzblw). Pins the exit criterion
 * verbatim: "list, edit-save-reread round trip (exactly one PUT), and a 422
 * surfaced as a field error, against a mocked API (mutation-verified)".
 *
 * Mirrors UsersPage.test.tsx / ConfigEditorPage.test.tsx's mocking
 * approach: keep the real AuthError/ForbiddenError classes (onAuthExpired
 * branches on instanceof), mock only the network calls.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { KitCommercialsPage } from './KitCommercialsPage';
import {
  AuthError, ForbiddenError,
  listKits, getKitCommercial, setKitCommercial,
} from '../utils/adminApi';

vi.mock('../utils/adminApi', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../utils/adminApi')>();
  return {
    ...actual,
    listKits: vi.fn(),
    getKitCommercial: vi.fn(),
    setKitCommercial: vi.fn(),
  };
});

const noAuthExpired = () => false;

const W7 = {
  kit_id: 'w-7', credit_cost: 3, cap_usd: 5, source: 'kit' as const,
  display: { label: 'Form W-7' },
};
const I90 = {
  kit_id: 'i-90', credit_cost: 1, cap_usd: 2, source: 'default' as const,
  display: {},
};

const KITS_PAGE = { kits: [W7, I90] };

async function openEditor(kitId: string) {
  const row = screen.getByText(kitId).closest('tr')!;
  fireEvent.click(within(row).getByRole('button', { name: 'Edit' }));
  await waitFor(() => expect(getKitCommercial).toHaveBeenCalledWith(kitId));
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(listKits).mockResolvedValue(KITS_PAGE);
  vi.mocked(getKitCommercial).mockResolvedValue(W7);
});

describe('KitCommercialsPage', () => {
  it('lists every kit with its credit cost, USD cap, and source', async () => {
    render(<KitCommercialsPage onAuthExpired={noAuthExpired} />);

    expect(await screen.findByText('w-7')).toBeInTheDocument();
    expect(screen.getByText('i-90')).toBeInTheDocument();

    const w7Row = screen.getByText('w-7').closest('tr')!;
    expect(within(w7Row).getByText('3')).toBeInTheDocument();
    expect(within(w7Row).getByText('5')).toBeInTheDocument();
    expect(within(w7Row).getByText('kit')).toBeInTheDocument();

    const i90Row = screen.getByText('i-90').closest('tr')!;
    expect(within(i90Row).getByText('default')).toBeInTheDocument();

    expect(listKits).toHaveBeenCalledTimes(1);
  });

  it('does not show the edit form until a row is opened', async () => {
    render(<KitCommercialsPage onAuthExpired={noAuthExpired} />);
    await screen.findByText('w-7');

    expect(screen.queryByLabelText('Credit cost')).not.toBeInTheDocument();
    expect(getKitCommercial).not.toHaveBeenCalled();
  });

  it('Edit loads a FRESH read of that kit, not the list row\'s values', async () => {
    // The list says credit_cost 3, but a fresh GET says 4 (another operator
    // just saved) -- the editor must show the fresh value, proving it does
    // not just copy the row it already had.
    vi.mocked(getKitCommercial).mockResolvedValue({ ...W7, credit_cost: 4 });
    render(<KitCommercialsPage onAuthExpired={noAuthExpired} />);
    await screen.findByText('w-7');

    await openEditor('w-7');

    expect(await screen.findByDisplayValue('4')).toBeInTheDocument();
    expect(getKitCommercial).toHaveBeenCalledTimes(1);
  });

  it('edit-save-reread round trip calls PUT exactly once and reflects the reread value', async () => {
    vi.mocked(setKitCommercial).mockResolvedValue({
      kit_id: 'w-7', credit_cost: 5, burn_cap_usd: 9, cap_usd: 9,
      display: {}, before: null, request_id: 'req-1',
    });
    render(<KitCommercialsPage onAuthExpired={noAuthExpired} />);
    await screen.findByText('w-7');
    await openEditor('w-7');
    await screen.findByDisplayValue('3');

    // The re-read after save returns yet another value (9.5, not the 9 the
    // PUT echoed) so the test can tell the editor is showing the RE-READ,
    // not merely the PUT response.
    vi.mocked(getKitCommercial).mockResolvedValueOnce(
      { kit_id: 'w-7', credit_cost: 5, cap_usd: 9.5, source: 'kit', display: { label: 'Form W-7' } },
    );

    fireEvent.change(screen.getByLabelText('Credit cost'), { target: { value: '5' } });
    fireEvent.change(screen.getByLabelText('Burn cap (USD)'), { target: { value: '9' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(setKitCommercial).toHaveBeenCalledTimes(1));
    expect(setKitCommercial).toHaveBeenCalledWith('w-7', {
      creditCost: 5, burnCapUsd: 9, display: { label: 'Form W-7' },
    });

    // Exactly one PUT -- a second click, a re-render, or a retry must never
    // fire a second one for the same save.
    expect(setKitCommercial).toHaveBeenCalledTimes(1);

    // The re-read landed: the cap field shows 9.5 (the GET's number), not
    // the PUT response's 9.
    await waitFor(() => expect(screen.getByDisplayValue('9.5')).toBeInTheDocument());
    expect(getKitCommercial).toHaveBeenCalledTimes(2);

    // The list behind the editor is refreshed too.
    await waitFor(() => expect(listKits).toHaveBeenCalledTimes(2));
  });

  it('Save echoes back the display map read on Edit, never a hardcoded {} (bd polyglot-pdf-zcbm1)', async () => {
    // W7's fixture carries a seeded display label. This is the regression
    // this bead fixes: before resolve_commercial returned `display`, this
    // page had nothing to read it from and always sent display: {} on
    // every save, silently wiping any label a kit had been seeded with.
    vi.mocked(setKitCommercial).mockResolvedValue({
      kit_id: 'w-7', credit_cost: 5, burn_cap_usd: 9, cap_usd: 9,
      display: { label: 'Form W-7' }, before: null, request_id: 'req-1',
    });
    render(<KitCommercialsPage onAuthExpired={noAuthExpired} />);
    await screen.findByText('w-7');
    await openEditor('w-7');
    await screen.findByDisplayValue('3');

    fireEvent.change(screen.getByLabelText('Credit cost'), { target: { value: '5' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(setKitCommercial).toHaveBeenCalledTimes(1));
    expect(setKitCommercial).toHaveBeenCalledWith('w-7', expect.objectContaining({
      display: { label: 'Form W-7' },
    }));
  });

  it('Save on a kit with no existing display echoes back {}, not a stale label from a previous edit', async () => {
    // I90's fixture has no display label. Opening I90 must not leak w-7's
    // label from a prior edit in the same session -- each Edit captures
    // its OWN kit's display fresh.
    vi.mocked(getKitCommercial).mockResolvedValue(I90);
    vi.mocked(setKitCommercial).mockResolvedValue({
      kit_id: 'i-90', credit_cost: 2, burn_cap_usd: 3, cap_usd: 3,
      display: {}, before: null, request_id: 'req-2',
    });
    render(<KitCommercialsPage onAuthExpired={noAuthExpired} />);
    await screen.findByText('i-90');
    await openEditor('i-90');
    await screen.findByDisplayValue('1');

    fireEvent.change(screen.getByLabelText('Credit cost'), { target: { value: '2' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(setKitCommercial).toHaveBeenCalledTimes(1));
    expect(setKitCommercial).toHaveBeenCalledWith('i-90', expect.objectContaining({
      display: {},
    }));
  });

  it('a 422 naming credit_cost surfaces as that field\'s error, not a generic banner', async () => {
    vi.mocked(setKitCommercial).mockRejectedValueOnce(
      new Error('credit_cost must be a positive integer, got 0'),
    );
    render(<KitCommercialsPage onAuthExpired={noAuthExpired} />);
    await screen.findByText('w-7');
    await openEditor('w-7');
    await screen.findByDisplayValue('3');

    fireEvent.change(screen.getByLabelText('Credit cost'), { target: { value: '5' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(setKitCommercial).toHaveBeenCalledTimes(1));
    const fieldError = await screen.findByText(
      'credit_cost must be a positive integer, got 0',
    );
    // It renders next to the credit-cost input, inside that field's own
    // block, not as a page-level banner.
    const creditCostInput = screen.getByLabelText('Credit cost');
    expect(creditCostInput.parentElement).toContainElement(fieldError);

    // No re-read happened -- a failed save must not fire the round trip.
    expect(getKitCommercial).toHaveBeenCalledTimes(1);
    expect(listKits).toHaveBeenCalledTimes(1);
  });

  it('a 422 naming burn_cap_usd surfaces as that field\'s error', async () => {
    vi.mocked(setKitCommercial).mockRejectedValueOnce(
      new Error('burn_cap_usd must be a positive finite number, got -1.0'),
    );
    render(<KitCommercialsPage onAuthExpired={noAuthExpired} />);
    await screen.findByText('w-7');
    await openEditor('w-7');
    await screen.findByDisplayValue('3');

    fireEvent.change(screen.getByLabelText('Burn cap (USD)'), { target: { value: '10' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(setKitCommercial).toHaveBeenCalledTimes(1));
    const fieldError = await screen.findByText(
      'burn_cap_usd must be a positive finite number, got -1.0',
    );
    const capInput = screen.getByLabelText('Burn cap (USD)');
    expect(capInput.parentElement).toContainElement(fieldError);
  });

  it('an unrelated save failure (no field named) shows the generic editor error, not a field error', async () => {
    vi.mocked(setKitCommercial).mockRejectedValueOnce(new Error('kit store unavailable'));
    render(<KitCommercialsPage onAuthExpired={noAuthExpired} />);
    await screen.findByText('w-7');
    await openEditor('w-7');
    await screen.findByDisplayValue('3');

    fireEvent.change(screen.getByLabelText('Credit cost'), { target: { value: '5' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    expect(await screen.findByText('kit store unavailable')).toBeInTheDocument();
  });

  it('client-side validation refuses a non-positive credit cost before any PUT', async () => {
    render(<KitCommercialsPage onAuthExpired={noAuthExpired} />);
    await screen.findByText('w-7');
    await openEditor('w-7');
    await screen.findByDisplayValue('3');

    fireEvent.change(screen.getByLabelText('Credit cost'), { target: { value: '0' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    expect(await screen.findByText(/credit_cost must be a positive integer/)).toBeInTheDocument();
    expect(setKitCommercial).not.toHaveBeenCalled();
  });

  it('client-side validation refuses a non-positive burn cap before any PUT', async () => {
    render(<KitCommercialsPage onAuthExpired={noAuthExpired} />);
    await screen.findByText('w-7');
    await openEditor('w-7');
    await screen.findByDisplayValue('3');

    fireEvent.change(screen.getByLabelText('Burn cap (USD)'), { target: { value: '-1' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    expect(await screen.findByText(/burn_cap_usd must be a positive finite number/)).toBeInTheDocument();
    expect(setKitCommercial).not.toHaveBeenCalled();
  });

  it('Cancel closes the editor without saving', async () => {
    render(<KitCommercialsPage onAuthExpired={noAuthExpired} />);
    await screen.findByText('w-7');
    await openEditor('w-7');
    await screen.findByDisplayValue('3');

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));

    expect(screen.queryByLabelText('Credit cost')).not.toBeInTheDocument();
    expect(setKitCommercial).not.toHaveBeenCalled();
  });

  it('routes a 403 on list load to onAuthExpired instead of the generic error banner', async () => {
    vi.mocked(listKits).mockRejectedValueOnce(new ForbiddenError('Access was revoked'));
    const onAuthExpired = vi.fn((_err: unknown) => true);
    render(<KitCommercialsPage onAuthExpired={onAuthExpired} />);

    await waitFor(() => expect(onAuthExpired).toHaveBeenCalledTimes(1));
    const [[passedErr]] = onAuthExpired.mock.calls;
    expect(passedErr).toBeInstanceOf(ForbiddenError);
    expect(screen.queryByText('Access was revoked')).not.toBeInTheDocument();
  });

  it('routes a 401 on save to onAuthExpired instead of a field or generic error', async () => {
    vi.mocked(setKitCommercial).mockRejectedValueOnce(new AuthError('Sign-in required'));
    const onAuthExpired = vi.fn((_err: unknown) => true);
    render(<KitCommercialsPage onAuthExpired={onAuthExpired} />);
    await screen.findByText('w-7');
    await openEditor('w-7');
    await screen.findByDisplayValue('3');

    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(onAuthExpired).toHaveBeenCalledTimes(1));
    const [[passedErr]] = onAuthExpired.mock.calls;
    expect(passedErr).toBeInstanceOf(AuthError);
    expect(screen.queryByText(/Could not save/)).not.toBeInTheDocument();
  });
});
