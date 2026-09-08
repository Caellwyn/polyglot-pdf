import React from 'react';
import type { WhoAmI } from '../utils/adminApi';

interface WhoAmIPageProps {
  who: WhoAmI;
}

/**
 * "Who am I" skeleton page (bd polyglot-pdf-b6943): renders the identity the
 * server already confirmed via GET /admin/whoami during sign-in (App.tsx
 * holds that result and passes it down -- this page makes no call of its
 * own, since the gate already made the call this page would otherwise
 * repeat).
 *
 * Also shows the git commit this CONSOLE build was made from
 * (__ADMIN_CONSOLE_GIT_SHA__, a Vite build-time define -- see
 * vite.config.ts) alongside a placeholder for the ADMIN SERVICE's own
 * `GET /version`, which is a separate deploy this page does not yet call
 * (a future bead's scope; the skeleton here is what the "what is live" view
 * will build on).
 */
export const WhoAmIPage: React.FC<WhoAmIPageProps> = ({ who }) => {
  return (
    <div data-testid="whoami-page" className="max-w-xl">
      <h2 className="text-lg font-semibold text-gray-900">Who am I</h2>
      <dl className="mt-4 grid grid-cols-[auto,1fr] gap-x-4 gap-y-2 text-sm">
        <dt className="text-gray-500">Signed in as</dt>
        <dd className="text-gray-900">{who.email ?? '(no email on this account)'}</dd>
        <dt className="text-gray-500">UID</dt>
        <dd className="text-gray-900 font-mono">{who.uid}</dd>
        <dt className="text-gray-500">Console build</dt>
        <dd className="text-gray-900 font-mono">{__ADMIN_CONSOLE_GIT_SHA__}</dd>
      </dl>
    </div>
  );
};
