/**
 * ClientLinkEntry -- the firm CLIENT's entry point (bd polyglot-pdf-ugm6).
 *
 * THE ONLY WAY A CLIENT REACHES A FORM. They never sign in, and never use a
 * staff-signed-in machine (maintainer, 2026-08-17): they open a one-time link
 * that names one form, inside a time window.
 *
 * This component sits OUTSIDE ProtectedRoute -- deliberately, and it is the
 * whole point of adding routing. Everything else in this app requires a
 * Firebase account; a client has none and must never have one.
 *
 * THE TOKEN LIVES IN THE URL FRAGMENT (/f#t=...), which the browser never
 * sends to a server -- so the credential stays out of access logs, referrer
 * headers, and proxy logs. Two consequences this component has to honor:
 *   1. Read it from `location.hash`, never from a query string.
 *   2. CLEAR IT from the address bar once redeemed, so a screen-share, a
 *      shoulder-surfer, or a browser-history sync does not carry a working
 *      credential around after it has been used.
 */
import React, { useEffect, useRef, useState } from "react";

import { SchemaFormDemo } from "./SchemaFormDemo";
import { saveOnboardingState } from "./onboardingStorage";
import { getBackendUrl } from "../shared/config";
import {
  hasClientLinkToken,
  setClientLinkToken,
} from "../shared/sessionCredential";

/** What the backend tells us about a redeemed link. Deliberately NOT the
 *  firm's kit list -- the client sees exactly the one form they were sent. */
interface OpenedLink {
  kit_id: string;
  firm_id: string;
  jti: string;
  complete_by: number;
}

type Phase = "checking" | "ready" | "invalid";

/** Read the token out of the fragment. Accepts `#t=...` and `#/f?t=...`-ish
 *  shapes defensively, because an email client or chat app may rewrite a URL
 *  on the way to the client. */
export function readTokenFromHash(hash: string): string | null {
  const raw = hash.startsWith("#") ? hash.slice(1) : hash;
  if (!raw) return null;
  const params = new URLSearchParams(raw.includes("?") ? raw.split("?")[1] : raw);
  const token = params.get("t");
  return token && token.trim() ? token.trim() : null;
}

export function ClientLinkEntry() {
  const [phase, setPhase] = useState<Phase>("checking");
  const [link, setLink] = useState<OpenedLink | null>(null);
  // StrictMode and re-renders must not redeem twice: the open call is
  // idempotent server-side for an unfinished link, but a duplicate request is
  // still noise on a metered path.
  const redeemed = useRef(false);

  useEffect(() => {
    if (redeemed.current) return;
    redeemed.current = true;

    const token = readTokenFromHash(window.location.hash);
    if (!token) {
      // RELOAD RECOVERY. An empty hash is not necessarily an invalid link:
      // we deliberately clear the fragment after redeeming, so a refresh --
      // or back/forward, or a phone returning to a backgrounded tab --
      // arrives here with nothing in the URL but a perfectly good token
      // still in this tab's storage.
      //
      // Storing the token was pointless without this branch, and that is
      // exactly what shipped in the first pass: the storage was written and
      // never read, so a reload still showed "This link is not valid"
      // (fresh-eyes r3). The fix is only real when BOTH halves exist.
      //
      // Do NOT re-POST /open here: the link is already redeemed and the form
      // id is already pinned in onboardingStorage from the first open. Going
      // straight to ready is both correct and one fewer metered call.
      if (hasClientLinkToken()) {
        setPhase("ready");
        return;
      }
      setPhase("invalid");
      return;
    }

    let cancelled = false;
    (async () => {
      try {
        const resp = await fetch(`${getBackendUrl()}/api/links/open`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ token }),
        });
        if (cancelled) return;
        if (!resp.ok) {
          // The backend returns ONE indistinguishable refusal for every
          // failure (expired, replayed, forged, firm suspended) so the
          // endpoint is not an oracle. We show one message for the same
          // reason -- and because "which of these went wrong" is not
          // actionable for the client either way: they call the firm.
          setPhase("invalid");
          return;
        }
        const opened: OpenedLink = await resp.json();

        // STASH THE CREDENTIAL before rendering. The client has no Firebase
        // account, so this token is what authenticates their WebSocket, PDF
        // fetch, and every other backend call -- without it the app renders
        // and then silently fails to connect (fresh-eyes r1 finding 1: the
        // redeemed token was captured and then discarded).
        setClientLinkToken(token);

        // Pin the form BEFORE rendering the app, so the client is never shown
        // a form picker. Language is deliberately left unset -- the client
        // still chooses their own, which is the one onboarding step that is
        // genuinely theirs.
        saveOnboardingState({ formId: opened.kit_id });

        // Drop the credential from the address bar now that it is redeemed.
        window.history.replaceState(null, "", window.location.pathname);

        setLink(opened);
        setPhase("ready");
      } catch {
        if (!cancelled) setPhase("invalid");
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  if (phase === "checking") {
    return (
      <div className="client-link-entry" role="status" aria-live="polite">
        <p>Opening your form...</p>
      </div>
    );
  }

  // On the RELOAD path `link` is null -- the /open response was consumed on
  // the first load and is not re-fetched -- so readiness alone is the right
  // gate here. Fail-closed still holds: `phase` reaches "ready" only after a
  // successful redemption OR a confirmed token in this tab's storage, never
  // from an error path (pinned by "never renders the form from an ERROR
  // path"; fresh-eyes r4 verified it by mutating the catch block).
  if (phase !== "ready") {
    return (
      <div className="client-link-entry client-link-entry--invalid" role="alert">
        <h1>This link is not valid</h1>
        <p>
          It may have expired, or it may already have been used. Links are good
          for one form, one time.
        </p>
        <p>Please contact the office that sent it to you for a new link.</p>
      </div>
    );
  }

  return <SchemaFormDemo />;
}
