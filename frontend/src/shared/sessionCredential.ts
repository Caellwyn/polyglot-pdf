/**
 * The ONE place a session credential is resolved (bd polyglot-pdf-ugm6).
 *
 * Two kinds of caller reach the backend, and they hold different credentials:
 *
 *   - FIRM STAFF: a Firebase account -> `user.getIdToken()`.
 *   - A FIRM'S CLIENT: no account at all, ever. They hold a signed magic-link
 *     token, redeemed by ClientLinkEntry and stashed here.
 *
 * WHY A MODULE AND NOT A PROP: `user ? await user.getIdToken() : undefined`
 * appears at SIX call sites across SchemaFormDemo and SchemaForm (the WS
 * connect, reconnects, the manifest fetch, the PDF fetch, and both TTS
 * paths). Threading a prop through all six would leave the client tier
 * working on whichever sites got updated and silently unauthenticated on the
 * rest -- and the next new call site would default to broken. Resolving it in
 * one function means a client session works everywhere or nowhere, which is a
 * failure mode you can actually see.
 *
 * The link token is held IN MEMORY ONLY. Persisting it to sessionStorage
 * would leave a working credential on disk for anything that can read storage
 * -- and the whole reason the token rides the URL fragment is to keep it out
 * of durable places.
 */

let linkToken: string | null = null;

/** Stash the redeemed client link token for this tab's session. */
export function setClientLinkToken(token: string): void {
  linkToken = token;
}

/** True when this session is a client-link session rather than a staff one. */
export function hasClientLinkToken(): boolean {
  return linkToken !== null;
}

/** Forget the token (used by tests; also correct on an explicit sign-out). */
export function clearClientLinkToken(): void {
  linkToken = null;
}

/**
 * Resolve the credential for a backend call.
 *
 * The CLIENT LINK WINS when present. A client-link session has no Firebase
 * user, so the two are mutually exclusive in practice -- but the explicit
 * ordering matters: if a staff member ever opened a client link in their own
 * signed-in browser, sending their STAFF token would start a session
 * attributed to the staff account rather than to the link, quietly breaking
 * both the telemetry attribution and the link's one-time-use accounting.
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
  if (linkToken) return linkToken;
  return user ? user.getIdToken() : undefined;
}
