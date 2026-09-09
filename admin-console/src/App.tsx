import React from 'react';
import { SignInGate } from './components/SignInGate';
import { WhoAmIPage } from './components/WhoAmIPage';
import { AuditLogPage } from './components/AuditLogPage';
import { ConfigEditorPage } from './components/ConfigEditorPage';
import { UsersPage } from './pages/UsersPage';
import { KitCommercialsPage } from './pages/KitCommercialsPage';
import { signOutAdmin } from './utils/adminAuth';
import { AuthError, ForbiddenError, type WhoAmI } from './utils/adminApi';

type Tab = 'whoami' | 'audit' | 'config' | 'users' | 'kits';

/**
 * Admin console shell (bd polyglot-pdf-b6943, extended by polyglot-pdf-z4y91
 * and polyglot-pdf-mzblw): the sign-in gate, then a simple tabbed shell over
 * the console's pages -- who-am-I, the audit log list, the per-channel
 * runtime-config editor, staff-account management (users), and kit
 * commercials (per-form credit price and USD spend ceiling).
 *
 * Deliberately NO ROUTER: a handful of tabs behind a boolean "signed in"
 * state is simple enough that a router would be pure ceremony for this
 * bead's scope. A future bead can add one if the page count grows past what
 * tab state comfortably tracks.
 */
export const App: React.FC = () => {
  const [who, setWho] = React.useState<WhoAmI | null>(null);
  const [tab, setTab] = React.useState<Tab>('whoami');
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
            onClick={() => setTab(item.id)}
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
      </main>
    </div>
  );
};
