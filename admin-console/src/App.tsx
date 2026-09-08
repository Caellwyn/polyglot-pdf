import React from 'react';
import { SignInGate } from './components/SignInGate';
import { WhoAmIPage } from './components/WhoAmIPage';
import { AuditLogPage } from './components/AuditLogPage';
import { ConfigEditorPage } from './components/ConfigEditorPage';
import { signOutAdmin } from './utils/adminAuth';
import type { WhoAmI } from './utils/adminApi';

type Tab = 'whoami' | 'audit' | 'config';

/**
 * Admin console shell (bd polyglot-pdf-b6943): the sign-in gate, then a
 * simple tabbed shell over the three skeleton pages this bead ships --
 * who-am-I, the audit log list, and the per-channel runtime-config editor.
 *
 * Deliberately NO ROUTER: three tabs behind a boolean "signed in" state is
 * simple enough that a router would be pure ceremony for this bead's scope.
 * A future bead can add one if the page count grows past what tab state
 * comfortably tracks.
 */
export const App: React.FC = () => {
  const [who, setWho] = React.useState<WhoAmI | null>(null);
  const [tab, setTab] = React.useState<Tab>('whoami');

  if (!who) {
    return <SignInGate onReady={setWho} />;
  }

  const handleSignOut = () => {
    void signOutAdmin();
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
        {tab === 'audit' && <AuditLogPage />}
        {tab === 'config' && <ConfigEditorPage />}
      </main>
    </div>
  );
};
