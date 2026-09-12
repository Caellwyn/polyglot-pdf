import React from 'react';
import { SignInGate } from './components/SignInGate';
import { WhoAmIPage } from './components/WhoAmIPage';
import { AuditLogPage } from './components/AuditLogPage';
import { ConfigEditorPage } from './components/ConfigEditorPage';
import { UsersPage } from './pages/UsersPage';
import { KitCommercialsPage } from './pages/KitCommercialsPage';
import { FirmsPage } from './pages/FirmsPage';
import { FirmDetailPage } from './pages/FirmDetailPage';
import { MonitoringPage } from './pages/MonitoringPage';
import { UsagePage } from './pages/UsagePage';
import { CostReportsPage } from './pages/CostReportsPage';
import { AlertsPage } from './pages/AlertsPage';
import { ErrorsPage } from './pages/ErrorsPage';
import { signOutAdmin } from './utils/adminAuth';
import { AuthError, ForbiddenError, type WhoAmI } from './utils/adminApi';

type Tab = 'whoami' | 'audit' | 'config' | 'users' | 'kits' | 'firms'
  | 'monitoring' | 'usage' | 'reports' | 'alerts' | 'errors';

/**
 * Admin console shell (bd polyglot-pdf-b6943, extended by polyglot-pdf-z4y91,
 * polyglot-pdf-r8z9g, polyglot-pdf-mzblw, and polyglot-pdf-i6dlb): the sign-in
 * gate, then a simple tabbed shell over the console's pages -- who-am-I, the
 * audit log list, the per-channel runtime-config editor, staff-account
 * management (users), kit commercials (per-form credit price and USD spend
 * ceiling), firms (list/detail with ledger, grants, links and revoke), and
 * the five monitoring pages (bd polyglot-pdf-i6dlb, E3.11b): Monitoring
 * (per-channel health), Usage (a firm's month rollup), Cost & income
 * (BigQuery reports over a month range), Alerts (list + acknowledge), and
 * Errors (Cloud Error Reporting group stats per channel).
 *
 * Deliberately NO ROUTER: a handful of tabs behind a boolean "signed in"
 * state is simple enough that a router would be pure ceremony for this
 * bead's scope. A future bead can add one if the page count grows past what
 * tab state comfortably tracks.
 *
 * FIRM DETAIL IS A SUB-VIEW OF THE FIRMS TAB, not a sixth tab: `openFirmId`
 * tracks which firm (if any) is open. Switching away to another tab and
 * back to Firms always lands on the list (the tab click below clears
 * `openFirmId`), matching how a router's own list link would behave rather
 * than leaving a stale detail view mounted behind the wrong tab.
 */
export const App: React.FC = () => {
  const [who, setWho] = React.useState<WhoAmI | null>(null);
  const [tab, setTab] = React.useState<Tab>('whoami');
  const [openFirmId, setOpenFirmId] = React.useState<string | null>(null);
  // Set when a call from AuditLogPage/ConfigEditorPage fails with a 401 or
  // 403 MID-SESSION (an operator revoked this person's app_admin claim, or
  // their ID token simply expired, while the tab stayed open). Routes back
  // to SignInGate's explicit refused/sign-in-again screen instead of the
  // generic in-page error string those pages show for every other failure
  // -- see handleAuthExpired below. Mirrors schema-editor/src/App.tsx's
  // refusedMidSession + handleAuthExpired.
  const [refusedMidSession, setRefusedMidSession] = React.useState<string | null>(null);

  // Every route this console calls gates on the SAME single check
  // (admin_backend/services/admin_auth.py's require_app_admin) -- unlike the
  // schema editor, there is no "author-only" partial-permission 403 to
  // distinguish from a full eviction, so ANY AuthError/ForbiddenError caught
  // here means "this person no longer has a working session" and must drop
  // back to the gate. Passed down to each page so their catch blocks can
  // route auth failures here instead of stringifying them into the page's
  // own generic error banner (bd polyglot-pdf-b6943 fresh-eyes finding: this
  // routing did not exist, leaving refusedReason permanently unreachable).
  const handleAuthExpired = React.useCallback((err: unknown) => {
    if (err instanceof AuthError || err instanceof ForbiddenError) {
      setRefusedMidSession(err instanceof ForbiddenError ? err.message : null);
      setWho(null);
      return true;
    }
    return false;
  }, []);

  if (!who) {
    return <SignInGate onReady={setWho} refusedReason={refusedMidSession} />;
  }

  const handleSignOut = () => {
    void signOutAdmin();
    setRefusedMidSession(null);
    setWho(null);
  };

  const handleSelectTab = (id: Tab) => {
    setTab(id);
    // A tab click is always "go to the top of this tab" -- clearing
    // openFirmId here means re-clicking Firms (even while a detail view is
    // open) returns to the list, and switching to another tab and back
    // does the same rather than leaving a stale firm_id mounted.
    setOpenFirmId(null);
  };

  return (
    <div className="min-h-screen">
      <header className="bg-white border-b border-gray-200 px-6 py-3 flex items-center justify-between">
        <h1 className="text-base font-semibold text-gray-900">Polyglot Admin Console</h1>
        <div className="flex items-center gap-4 text-sm">
          <span className="text-gray-500">{who.email ?? who.uid}</span>
          <button type="button" className="text-blue-600 hover:underline" onClick={handleSignOut}>
            Sign out
          </button>
        </div>
      </header>

      <nav className="bg-white border-b border-gray-200 px-6 flex gap-4 text-sm">
        {(
          [
            { id: 'whoami', label: 'Who am I' },
            { id: 'audit', label: 'Audit log' },
            { id: 'config', label: 'Runtime config' },
            { id: 'users', label: 'Users' },
            { id: 'kits', label: 'Kit commercials' },
            { id: 'firms', label: 'Firms' },
            { id: 'monitoring', label: 'Monitoring' },
            { id: 'usage', label: 'Usage' },
            { id: 'reports', label: 'Cost & income' },
            { id: 'alerts', label: 'Alerts' },
            { id: 'errors', label: 'Errors' },
          ] as const
        ).map((item) => (
          <button
            key={item.id}
            type="button"
            className={
              'py-2 border-b-2 ' +
              (tab === item.id
                ? 'border-primary-600 text-primary-700 font-medium'
                : 'border-transparent text-gray-500 hover:text-gray-800')
            }
            onClick={() => handleSelectTab(item.id)}
          >
            {item.label}
          </button>
        ))}
      </nav>

      <main className="p-6">
        {tab === 'whoami' && <WhoAmIPage who={who} />}
        {tab === 'audit' && <AuditLogPage onAuthExpired={handleAuthExpired} />}
        {tab === 'config' && <ConfigEditorPage onAuthExpired={handleAuthExpired} />}
        {tab === 'users' && <UsersPage onAuthExpired={handleAuthExpired} />}
        {tab === 'kits' && <KitCommercialsPage onAuthExpired={handleAuthExpired} />}
        {tab === 'firms' && (
          openFirmId ? (
            <FirmDetailPage
              firmId={openFirmId}
              onAuthExpired={handleAuthExpired}
              onBack={() => setOpenFirmId(null)}
            />
          ) : (
            <FirmsPage onAuthExpired={handleAuthExpired} onOpenFirm={setOpenFirmId} />
          )
        )}
        {tab === 'monitoring' && <MonitoringPage onAuthExpired={handleAuthExpired} />}
        {tab === 'usage' && <UsagePage onAuthExpired={handleAuthExpired} />}
        {tab === 'reports' && <CostReportsPage onAuthExpired={handleAuthExpired} />}
        {tab === 'alerts' && <AlertsPage onAuthExpired={handleAuthExpired} />}
        {tab === 'errors' && <ErrorsPage onAuthExpired={handleAuthExpired} />}
      </main>
    </div>
  );
};
