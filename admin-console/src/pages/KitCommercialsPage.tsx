import React from 'react';
import {
  listKits, getKitCommercial, setKitCommercial, type KitCommercial,
} from '../utils/adminApi';

interface KitCommercialsPageProps {
  /** Called first on every catch. Returns true when `err` was an
   * AuthError/ForbiddenError that App has already routed back to the
   * sign-in gate -- in that case this page must NOT also set its own
   * generic error banner (the gate is about to replace this page entirely).
   * Returns false for anything else, so this page's normal error handling
   * still applies. See App.tsx's handleAuthExpired docstring for why this
   * is the console's single mid-session-eviction predicate. */
  onAuthExpired: (err: unknown) => boolean;
}

/** Which edited field a server 422 belongs to, or null when the message
 * does not name one (a store-level 500/503, or the future "kit_id not
 * found" case) -- shown next to that field's input instead of as a generic
 * banner. Classified by an ALLOWLIST prefix match against
 * admin_backend/routes/kit_routes.py's own detail strings ("credit_cost
 * must be..." / "burn_cap_usd must be...") rather than a blacklist, so a
 * future unrelated failure message can never be misrouted onto a field by
 * accident. */
function fieldFromDetail(message: string): 'creditCost' | 'burnCapUsd' | null {
  if (message.startsWith('credit_cost ')) return 'creditCost';
  if (message.startsWith('burn_cap_usd ')) return 'burnCapUsd';
  return null;
}

/** Client-side mirror of kit_routes.py's own validation (module docstring:
 * credit_cost a positive int, burn_cap_usd a positive finite float, bool
 * excluded from both since bool is an int subclass) -- ahead of the PUT so
 * an obviously bad value never round-trips to the server only to bounce
 * back as a 422 for something a number input could catch immediately. This
 * is a CONVENIENCE gate, not the source of truth: the server's own 422
 * (surfaced via fieldFromDetail above) is still what ultimately decides a
 * value's validity, since this page must never accept a value the route
 * would refuse. */
function validateCreditCost(raw: string): string | null {
  if (raw.trim() === '') return 'credit_cost must be a positive integer';
  const n = Number(raw);
  if (!Number.isInteger(n) || n <= 0) {
    return 'credit_cost must be a positive integer';
  }
  return null;
}

function validateBurnCapUsd(raw: string): string | null {
  if (raw.trim() === '') return 'burn_cap_usd must be a positive finite number';
  const n = Number(raw);
  if (!Number.isFinite(n) || n <= 0) {
    return 'burn_cap_usd must be a positive finite number';
  }
  return null;
}

/**
 * Kit commercials page (bd polyglot-pdf-mzblw, Epic 2 Track C bead C1): the
 * FIRST admin-console page over admin_backend/routes/kit_routes.py's three
 * routes -- list every kit (GET /admin/kits), then edit ONE kit's pricing at
 * a time with a whole-body PUT and a post-save re-read.
 *
 * LIST SHOWS `credit_cost`, `cap_usd` (the route's own field name -- see
 * adminApi.ts's KitCommercial docstring for why this is not called
 * "burn_cap_usd" here) and `source` ("kit" when a commercial doc exists,
 * "default" when the kit rides the global fallback). It does NOT show
 * `updated_by`: neither GET route's response carries it (only the raw
 * Firestore doc does), and adding it would need a kit_routes.py wire
 * change outside this bead's Surfaces (adminApi.ts + this page + the shell
 * tab only) -- noted in the merge report as a discrepancy from the bead's
 * prose rather than silently dropped.
 *
 * EDIT ONE KIT AT A TIME: clicking "Edit" on a row loads that kit's fresh
 * commercial via GET /admin/kits/{kit_id}/commercial (not the list row's
 * already-rendered values -- the whole point of a fresh read before editing
 * is that the list could be stale if another operator just saved), and one
 * Save PUTs the WHOLE body (credit_cost, burn_cap_usd, display) -- never a
 * partial patch, matching the route's own "a PUT replaces the whole
 * commercial doc" contract.
 *
 * KNOWN GAP, NOT INTRODUCED HERE: this page always sends `display: {}` on
 * Save (never omitted -- kit_routes.py treats a missing/null `display` the
 * same way, defaulting it to `{}` server-side) because NEITHER GET route
 * this page reads (`resolve_commercial`'s own docstring: "display: dict
 * console label etc.; not read here") ever returns a kit's existing
 * `display` value -- there is nothing here to preserve. CONCRETELY: a kit
 * seeded with a `display.label` by `scripts/seed_kit_commercials.py` LOSES
 * that label the first time ANY console operator edits its price through
 * this page, PUT's own whole-doc-replace contract being what it is. This
 * is a pre-existing gap in the read side of bead A3/B3's `kit_routes.py`
 * (Surfaces here are `adminApi.ts` + this page + the shell tab only, not
 * `kit_routes.py`) -- flagged rather than silently worked around; filed as
 * bd `polyglot-pdf-zcbm1` (add `display` to
 * `kit_commercials.resolve_commercial`'s return value so both GET routes
 * surface it, then this page can preserve it on save).
 *
 * EXACTLY ONE PUT PER SAVE. Client-side validation (mirroring the route's
 * own rules: credit_cost a positive int, burn_cap_usd a positive finite
 * number) runs BEFORE the network call, so an obviously bad value never
 * reaches the server -- but the server's 422 is still what this page trusts
 * for anything its own check does not catch, surfaced next to the field it
 * names (fieldFromDetail's allowlist) rather than as a generic banner.
 *
 * POST-SAVE RE-READ: a successful PUT re-fetches the kit's commercial (GET)
 * so the editor reflects what the server actually stored, then reloads the
 * list too, mirroring ConfigEditorPage/UsersPage's round-trip pattern.
 */
export const KitCommercialsPage: React.FC<KitCommercialsPageProps> = ({ onAuthExpired }) => {
  const [kits, setKits] = React.useState<KitCommercial[]>([]);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const [editingKitId, setEditingKitId] = React.useState<string | null>(null);
  const [editLoading, setEditLoading] = React.useState(false);
  const [editError, setEditError] = React.useState<string | null>(null);
  const [creditCostInput, setCreditCostInput] = React.useState('');
  const [burnCapUsdInput, setBurnCapUsdInput] = React.useState('');
  const [creditCostFieldError, setCreditCostFieldError] = React.useState<string | null>(null);
  const [burnCapUsdFieldError, setBurnCapUsdFieldError] = React.useState<string | null>(null);
  const [saving, setSaving] = React.useState(false);
  const [savedMessage, setSavedMessage] = React.useState<string | null>(null);

  const loadKits = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const page = await listKits();
      setKits(page.kits);
    } catch (err) {
      if (onAuthExpired(err)) return;
      setError(err instanceof Error ? err.message : 'Could not load the kit list');
    } finally {
      setLoading(false);
    }
  }, [onAuthExpired]);

  React.useEffect(() => {
    void loadKits();
  }, [loadKits]);

  const closeEditor = React.useCallback(() => {
    setEditingKitId(null);
    setEditError(null);
    setCreditCostFieldError(null);
    setBurnCapUsdFieldError(null);
    setSavedMessage(null);
  }, []);

  const startEdit = React.useCallback(async (kitId: string) => {
    setEditingKitId(kitId);
    setEditError(null);
    setCreditCostFieldError(null);
    setBurnCapUsdFieldError(null);
    setSavedMessage(null);
    setEditLoading(true);
    try {
      // A fresh read, not the list row's already-rendered values -- the
      // list can be stale if another operator just saved this same kit.
      const commercial = await getKitCommercial(kitId);
      setCreditCostInput(String(commercial.credit_cost));
      setBurnCapUsdInput(String(commercial.cap_usd));
    } catch (err) {
      if (onAuthExpired(err)) { setEditingKitId(null); return; }
      setEditError(err instanceof Error ? err.message : 'Could not load this kit\'s pricing');
    } finally {
      setEditLoading(false);
    }
  }, [onAuthExpired]);

  const handleSave = React.useCallback(async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingKitId) return;

    const creditCostError = validateCreditCost(creditCostInput);
    const burnCapUsdError = validateBurnCapUsd(burnCapUsdInput);
    setCreditCostFieldError(creditCostError);
    setBurnCapUsdFieldError(burnCapUsdError);
    if (creditCostError || burnCapUsdError) return;

    setSaving(true);
    setEditError(null);
    setSavedMessage(null);
    try {
      // EXACTLY ONE PUT: the whole commercial body, never a partial patch.
      await setKitCommercial(editingKitId, {
        creditCost: Number(creditCostInput),
        burnCapUsd: Number(burnCapUsdInput),
      });
      // Re-read so the editor reflects what the server actually stored,
      // not merely the form's draft (the round trip the exit criterion
      // asks for), then refresh the list behind it.
      const reread = await getKitCommercial(editingKitId);
      setCreditCostInput(String(reread.credit_cost));
      setBurnCapUsdInput(String(reread.cap_usd));
      setSavedMessage(`Saved ${editingKitId}.`);
      await loadKits();
    } catch (err) {
      if (onAuthExpired(err)) return;
      const message = err instanceof Error ? err.message : 'Could not save this kit\'s pricing';
      const field = fieldFromDetail(message);
      if (field === 'creditCost') setCreditCostFieldError(message);
      else if (field === 'burnCapUsd') setBurnCapUsdFieldError(message);
      else setEditError(message);
    } finally {
      setSaving(false);
    }
  }, [editingKitId, creditCostInput, burnCapUsdInput, loadKits, onAuthExpired]);

  return (
    <div data-testid="kit-commercials-page" className="max-w-3xl">
      <h2 className="text-lg font-semibold text-gray-900">Kit commercials</h2>

      {error && <div className="mt-3 text-sm text-red-600">{error}</div>}
      {loading && <p className="mt-3 text-sm text-gray-500">Loading...</p>}

      <div className="mt-4 overflow-x-auto">
        <table className="min-w-full text-sm text-left" data-testid="kits-table">
          <thead>
            <tr className="border-b border-gray-200 text-gray-500">
              <th className="py-1 pr-4">Kit</th>
              <th className="py-1 pr-4">Credit cost</th>
              <th className="py-1 pr-4">Burn cap (USD)</th>
              <th className="py-1 pr-4">Source</th>
              <th className="py-1 pr-4">Actions</th>
            </tr>
          </thead>
          <tbody>
            {kits.map((kit) => (
              <tr key={kit.kit_id} className="border-b border-gray-100">
                <td className="py-1 pr-4 font-mono">{kit.kit_id}</td>
                <td className="py-1 pr-4">{kit.credit_cost}</td>
                <td className="py-1 pr-4">{kit.cap_usd}</td>
                <td className="py-1 pr-4">{kit.source}</td>
                <td className="py-1 pr-4">
                  <button
                    type="button"
                    className="btn border border-gray-300"
                    onClick={() => void startEdit(kit.kit_id)}
                  >
                    Edit
                  </button>
                </td>
              </tr>
            ))}
            {kits.length === 0 && !loading && (
              <tr>
                <td colSpan={5} className="py-4 text-gray-500">No kits found.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {editingKitId && (
        <div className="mt-6 border border-gray-200 rounded p-4 max-w-md">
          <h3 className="text-sm font-medium text-gray-900">
            Edit pricing -- {editingKitId}
          </h3>

          {editLoading && <p className="mt-2 text-sm text-gray-500">Loading...</p>}
          {editError && <div className="mt-2 text-sm text-red-600">{editError}</div>}
          {savedMessage && <div className="mt-2 text-sm text-green-700">{savedMessage}</div>}

          <form onSubmit={(e) => void handleSave(e)} className="mt-3 space-y-3 text-sm">
            <div>
              <label className="block text-gray-700" htmlFor="kit-credit-cost">
                Credit cost
              </label>
              <input
                id="kit-credit-cost"
                type="number"
                step="1"
                className="mt-1 w-full border border-gray-300 rounded px-2 py-1"
                value={creditCostInput}
                disabled={editLoading || saving}
                onChange={(e) => {
                  setCreditCostInput(e.target.value);
                  setCreditCostFieldError(null);
                }}
              />
              {creditCostFieldError && (
                <p className="mt-1 text-xs text-red-600">{creditCostFieldError}</p>
              )}
            </div>

            <div>
              <label className="block text-gray-700" htmlFor="kit-burn-cap-usd">
                Burn cap (USD)
              </label>
              <input
                id="kit-burn-cap-usd"
                type="number"
                step="0.01"
                className="mt-1 w-full border border-gray-300 rounded px-2 py-1"
                value={burnCapUsdInput}
                disabled={editLoading || saving}
                onChange={(e) => {
                  setBurnCapUsdInput(e.target.value);
                  setBurnCapUsdFieldError(null);
                }}
              />
              {burnCapUsdFieldError && (
                <p className="mt-1 text-xs text-red-600">{burnCapUsdFieldError}</p>
              )}
            </div>

            <div className="flex items-center gap-2">
              <button
                type="submit"
                className="btn btn-primary"
                disabled={editLoading || saving}
              >
                {saving ? 'Saving...' : 'Save'}
              </button>
              <button
                type="button"
                className="btn border border-gray-300"
                onClick={closeEditor}
                disabled={saving}
              >
                Cancel
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
};
