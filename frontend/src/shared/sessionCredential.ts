/**
 * The ONE place a session credential is resolved (bd polyglot-pdf-ugm6).
 *
 * Two kinds of caller reach the backend, and they hold different credentials:
 *
 *   - FIRM STAFF: a Firebase account -> `user.getIdToken()`.
 *   - A FIRM'S CLIENT: no account at all, ever. They hold a signed magic-link
 *     token, redeemed by ClientLinkEntry and stashed here.
 *
 * WHY A MODULE AND NOT A PROP: the inline
 * `user ? await user.getIdToken() : undefined` appeared at NINE call sites
 * across FIVE files -- SchemaFormDemo, SchemaForm, ArchivedVersionsLink,
 * usePDFDocument, and FilledPreviewModal. (A review named six across two;
 * grepping the SET found nine, and the three it missed -- the PDF fetch, the
 * filled-preview fetch, the archive read -- are ones a client link needs.
 * That is why this file counts by grep, not from memory, and why
 * sessionCredential.test.ts derives the set from the shipped sources so a NEW
 * site fails CI -- the guard asserts the offender list is EMPTY at any
 * ordinal, so it keeps working as sites are added rather than pinning a
 * count. The mint page at /console/links was the tenth and passes, because it
 * routes through here.) Threading a prop through all of them would leave the
 * client tier
 * working on whichever sites got updated and silently unauthenticated on the
 * rest -- and the next new call site would default to broken. Resolving it in
 * one function means a client session works everywhere or nowhere, which is a
 * failure mode you can actually see.
 *
 * STORAGE: sessionStorage, scoped to the TAB (maintainer decision,
 * 2026-08-24). Memory-only stranded a client on any RELOAD -- not just a
 * closed tab, but a refresh, a back/forward, or a phone reclaiming a
 * backgrounded tab -- because the entry gate clears the token from the URL
 * once redeemed. On a 40-minute immigration form that is a likely event, and
 * the cost was losing the session.
 *
 * sessionStorage survives a reload and dies with the tab. It is never shared
 * with another tab and never reaches localStorage or disk in a form that
 * outlives the browser session. The tradeoff accepted: anything that can run
 * script on this page can read it -- but such an attacker already holds the
 * live session, so this widens no meaningful surface.
 *
 * If the tab DOES close (or a phone evicts it), the client is not stranded
 * either: the link stays valid for SEVEN DAYS after first opening, so they
 * reopen the original message and continue. That is the deliberate fallback
 * -- see DEFAULT_COMPLETE_WINDOW_S in backend/services/link_tokens.py.
 */

const STORAGE_KEY = "vff_client_link_token";

// Mirrored in memory so a resolve never depends on storage being readable
// (private-mode quirks, a disabled-storage browser). Storage is the DURABLE
// copy; this is the fast, always-available one.
let linkToken: string | null = null;

/** Stash the redeemed client link token for this tab's session. */
export function setClientLinkToken(token: string): void {
  linkToken = token;
  try {
    sessionStorage.setItem(STORAGE_KEY, token);
  } catch {
    // Storage disabled or full: the in-memory copy still carries this
    // page-load, so the client can finish unless they reload. Failing the
    // session here would be strictly worse.
  }
}

/** True when this session is a client-link session rather than a staff one. */
export function hasClientLinkToken(): boolean {
  return readToken() !== null;
}

/** In-memory first, then the tab's storage (the post-reload case). */
function readToken(): string | null {
  if (linkToken) return linkToken;
  try {
    const stored = sessionStorage.getItem(STORAGE_KEY);
    if (stored) {
      linkToken = stored;   // rehydrate so later reads skip storage
      return stored;
    }
  } catch {
    // Unreadable storage is not an error here -- it just means no token.
  }
  return null;
}

/** Forget the token (used by tests; also correct on an explicit sign-out). */
export function clearClientLinkToken(): void {
  linkToken = null;
  try {
    sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    // Nothing to do; the in-memory copy is already cleared.
  }
}

/**
 * Resolve the credential for a backend call ON THE FORM-FILLING PATH.
 *
 * The CLIENT LINK WINS when present. A client-link session has no Firebase
 * user, so the two are mutually exclusive in practice -- but the explicit
 * ordering matters: if a staff member ever opened a client link in their own
 * signed-in browser, sending their STAFF token would start a session
 * attributed to the staff account rather than to the link, quietly breaking
 * both the telemetry attribution and the link's one-time-use accounting.
 *
 * NOT FOR STAFF-ONLY CONSOLE ACTIONS -- use resolveStaffToken for those (bd
 * polyglot-pdf-so88g). Minting a link is a firm-staff act, and the link-wins
 * rule sends the wrong credential the moment a staffer has tried one of their
 * own links in that tab.
 */
export function resolveSessionToken(
  user: { getIdToken: () => Promise<string> } | null | undefined,
): string | undefined | Promise<string | undefined> {
  // NOT `async`, deliberately. An async function always yields a microtask
  // even on a path that never awaits, and at least one caller races cleanup
  // against its fetch: usePDFDocument unmounts while the fetch is pending,
  // and an extra microtask hop let cleanup win so the fetch never started
  // (a real regression, caught by usePDFDocument.cancelledFetch.test.tsx).
  //
  // Returning a UNION keeps the synchronous case synchronous while callers
  // can still `await` it -- awaiting a non-promise is a no-op. Both kinds of
  // caller therefore work unchanged.
  const token = readToken();
  if (token) return token;
  return user ? user.getIdToken() : undefined;
}

/**
 * Resolve the credential for a STAFF-ONLY action (bd polyglot-pdf-so88g).
 *
 * The mirror image of resolveSessionToken: the FIREBASE USER WINS, and a
 * stashed client-link token is ignored outright rather than preferred.
 *
 * WHY A SECOND FUNCTION RATHER THAN A FLAG ON THE FIRST. The link-wins rule
 * is load-bearing on the form-filling path -- it keeps a session attributed
 * to the link rather than to a staffer who happened to open it, which the
 * one-time-use accounting and the telemetry both depend on. Flipping that
 * globally to fix minting would break the thing it exists to protect. The two
 * paths genuinely want opposite precedence, so they get one function each,
 * named for the tier they serve.
 *
 * The bug this fixes: a staffer mints a link, opens it in the same tab to try
 * it, and every later mint from that tab sends the CLIENT token. The backend
 * resolves it to a caller with no uid and refuses with 403 -- reported to the
 * operator as "your account is not attached to a firm", which is both wrong
 * and unfixable by them. Fails closed (no unauthorized mint), but the
 * mint-test-mint-again loop is exactly the console's first workflow.
 *
 * The return type mirrors resolveSessionToken's union for SYMMETRY -- so the
 * two are interchangeable at a call site -- and NOT for its microtask reason.
 * That reason is real but specific to the other function: its readToken()
 * early return hands back a stored string synchronously. This one has no such
 * branch; getIdToken() is always a Promise, so it can never return
 * synchronously with a token.
 */
export function resolveStaffToken(
  user: { getIdToken: () => Promise<string> } | null | undefined,
): string | undefined | Promise<string | undefined> {
  return user ? user.getIdToken() : undefined;
}

/**
 * TEST ONLY: drop the in-memory copy without touching storage, simulating
 * what a page reload does to this module. Exported because the alternative
 * -- asserting that setItem was called -- would pass even if nothing ever
 * read the value back, which is the half that actually matters.
 */
export function clearInMemoryOnly(): void {
  linkToken = null;
}
