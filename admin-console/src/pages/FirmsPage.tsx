import React from 'react';
import {
  listFirms, createFirm, FIRM_KINDS,
  type FirmRow, type FirmKind, type FirmStatus,
} from '../utils/adminApi';
import { PageIntro } from '../components/PageIntro';

interface FirmsPageProps {
  /** Called first on every catch. Returns true when `err` was an
   * AuthError/ForbiddenError that App has already routed back to the
   * sign-in gate -- in that case this page must NOT also set its own
   * generic error banner. See UsersPage.tsx's identical prop for the full
   * rationale, and App.tsx's handleAuthExpired docstring. */
  onAuthExpired: (err: unknown) => boolean;
  /** Open a firm's detail page. App.tsx owns navigation (no router in this
   * console -- see App.tsx's module docstring), so this page only reports
   * the selected firm_id upward. */
  onOpenFirm: (firmId: string) => void;
}

/**
 * Firms list page (bd polyglot-pdf-r8z9g, Epic 2 Track C bead C2), driving
 * admin_backend/routes/firm_routes.py's GET/POST /admin/firms.
 *
 * KIND IS REQUIRED ON CREATE, client-side, mirroring the route's own
 * required (no-default) field: the create form's kind <select> has no
 * blank option and defaults to 'live'... except that is deliberately
 * DISALLOWED here -- exit criterion 1 says "create refuses without kind",
 * so this page starts the select on an explicit placeholder value the
 * button's disabled-until-chosen guard treats as "not yet chosen", forcing
 * an operator to make an active choice between mock and live rather than
 * silently inheriting whichever option happens to render first. This
 * matters because a mis-defaulted LIVE firm can mint for real money (plan:
 * "a mis-defaulted mock firm merely blocks staging while a mis-defaulted
 * live firm mints for free") -- so a client-side default here would be the
 * more dangerous direction to get wrong.
 *
 * LOADS ON MOUNT (unlike UsersPage, which waits for a firm_id): there is no
 * per-row filter to wait for -- GET /admin/firms is deliberately
 * unfiltered (firm_routes.py's own docstring) -- so the list can load
 * immediately.
 */
export const FirmsPage: React.FC<FirmsPageProps> = ({ onAuthExpired, onOpenFirm }) => {
  const [firms, setFirms] = React.useState<FirmRow[]>([]);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  // Create-firm form state.
  const [newFirmId, setNewFirmId] = React.useState('');
  const [newName, setNewName] = React.useState('');
  const [newContactEmail, setNewContactEmail] = React.useState('');
  // '' is the deliberate "not yet chosen" placeholder -- see module
  // docstring. Never a member of FIRM_KINDS, so the create button's
  // disabled check (`!newKind`) and the request's runtime type both treat
  // it as "no kind selected" rather than a fourth valid value.
  const [newKind, setNewKind] = React.useState<FirmKind | ''>('');
  const [creating, setCreating] = React.useState(false);
  const [createError, setCreateError] = React.useState<string | null>(null);

  const loadFirms = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const rows = await listFirms();
      setFirms(rows);
    } catch (err) {
      if (onAuthExpired(err)) return;
      setError(err instanceof Error ? err.message : 'Could not load the firm list');
    } finally {
      setLoading(false);
    }
  }, [onAuthExpired]);

  React.useEffect(() => {
    void loadFirms();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleCreate = React.useCallback(async (e: React.FormEvent) => {
    e.preventDefault();
    // Client-side backstop mirroring the route's own required-kind 422 --
    // exit criterion 1's "create refuses without kind". The button is
    // already disabled while newKind is '', so this is reached only via a
    // programmatic submit (e.g. pressing Enter in another field); it must
    // still refuse rather than send an empty string.
    if (!newKind) {
      setCreateError('Kind is required.');
      return;
    }
    setCreating(true);
    setCreateError(null);
    try {
      await createFirm({
        firmId: newFirmId.trim(),
        name: newName.trim(),
        contactEmail: newContactEmail.trim(),
        kind: newKind,
      });
      setNewFirmId('');
      setNewName('');
      setNewContactEmail('');
      setNewKind('');
      await loadFirms();
    } catch (err) {
      if (onAuthExpired(err)) return;
      setCreateError(err instanceof Error ? err.message : 'Could not create the firm');
    } finally {
      setCreating(false);
    }
  }, [newFirmId, newName, newContactEmail, newKind, loadFirms, onAuthExpired]);

  const statusLabel = (status: FirmStatus | null) => status ?? 'unknown';

  return (
    <div data-testid="firms-page" className="max-w-4xl">
      <h2 className="text-lg font-semibold text-gray-900">Firms</h2>
      <PageIntro>
        Create and look up law firms, and open one to manage its plan,
        credit ledger, and links.
      </PageIntro>

      <form
        onSubmit={(e) => void handleCreate(e)}
        className="mt-4 border border-gray-200 rounded p-4 flex flex-wrap items-end gap-2 text-sm"
      >
        <div>
          <label className="block text-gray-700" htmlFor="firms-new-id">
            Firm ID
          </label>
          <input
            id="firms-new-id"
            required
            className="mt-1 border border-gray-300 rounded px-2 py-1"
            value={newFirmId}
            onChange={(e) => setNewFirmId(e.target.value)}
          />
        </div>
        <div>
          <label className="block text-gray-700" htmlFor="firms-new-name">
            Name
          </label>
          <input
            id="firms-new-name"
            required
            className="mt-1 border border-gray-300 rounded px-2 py-1"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
          />
        </div>
        <div>
          <label className="block text-gray-700" htmlFor="firms-new-contact-email">
            Contact email
          </label>
          <input
            id="firms-new-contact-email"
            type="email"
            required
            className="mt-1 border border-gray-300 rounded px-2 py-1"
            value={newContactEmail}
            onChange={(e) => setNewContactEmail(e.target.value)}
          />
        </div>
        <div>
          <label className="block text-gray-700" htmlFor="firms-new-kind">
            Kind
          </label>
          <select
            id="firms-new-kind"
            required
            className="mt-1 border border-gray-300 rounded px-2 py-1"
            value={newKind}
            onChange={(e) => setNewKind(e.target.value as FirmKind | '')}
          >
            <option value="" disabled>
              Choose kind...
            </option>
            {FIRM_KINDS.map((kind) => (
              <option key={kind} value={kind}>{kind}</option>
            ))}
          </select>
        </div>
        <button type="submit" className="btn btn-primary" disabled={creating || !newKind}>
          {creating ? 'Creating...' : 'Create firm'}
        </button>
      </form>

      {createError && <div className="mt-2 text-sm text-red-600">{createError}</div>}
      {error && <div className="mt-3 text-sm text-red-600">{error}</div>}

      <div className="mt-6 overflow-x-auto">
        <table className="min-w-full text-sm text-left" data-testid="firms-table">
          <thead>
            <tr className="border-b border-gray-200 text-gray-500">
              <th className="py-1 pr-4">Firm</th>
              <th className="py-1 pr-4">Kind</th>
              <th className="py-1 pr-4">Balance</th>
              <th className="py-1 pr-4">Status</th>
            </tr>
          </thead>
          <tbody>
            {firms.map((firm) => (
              <tr key={firm.firm_id} className="border-b border-gray-100">
                <td className="py-1 pr-4">
                  <button
                    type="button"
                    className="text-blue-600 hover:underline"
                    onClick={() => onOpenFirm(firm.firm_id)}
                  >
                    {firm.name || firm.firm_id}
                  </button>
                  <div className="text-xs text-gray-500">{firm.firm_id}</div>
                </td>
                <td className="py-1 pr-4">
                  <span
                    className={
                      'inline-block rounded px-2 py-0.5 text-xs font-medium ' +
                      (firm.kind === 'live'
                        ? 'bg-green-100 text-green-800'
                        : 'bg-amber-100 text-amber-800')
                    }
                  >
                    {firm.kind}
                  </span>
                </td>
                <td className="py-1 pr-4">{firm.balance_credits}</td>
                <td className="py-1 pr-4">{statusLabel(firm.status)}</td>
              </tr>
            ))}
            {firms.length === 0 && !loading && (
              <tr>
                <td colSpan={4} className="py-4 text-gray-500">No firms yet.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};
