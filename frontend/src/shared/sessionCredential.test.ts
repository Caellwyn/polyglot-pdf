/**
 * The session credential resolver (bd polyglot-pdf-ugm6).
 *
 * @vitest-environment jsdom
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import {
  clearClientLinkToken,
  clearInMemoryOnly,
  hasClientLinkToken,
  resolveSessionToken,
  setClientLinkToken,
} from "./sessionCredential";

const staffUser = { getIdToken: async () => "firebase-id-token" };

describe("resolveSessionToken", () => {
  afterEach(() => clearClientLinkToken());

  it("returns the Firebase token for a signed-in staff user", async () => {
    expect(await resolveSessionToken(staffUser)).toBe("firebase-id-token");
  });

  it("returns undefined when there is neither a user nor a link", async () => {
    expect(await resolveSessionToken(null)).toBeUndefined();
  });

  it("returns the LINK token for a client with no account", async () => {
    // The client tier's whole premise: no Firebase user exists, so without
    // this the backend call goes out with no credential at all and /ws/fill
    // (token is a REQUIRED query param) rejects it before it is even handled.
    setClientLinkToken("payload.signature");

    expect(await resolveSessionToken(null)).toBe("payload.signature");
  });

  it("prefers the LINK token over a staff token when both exist", async () => {
    // Mutually exclusive in practice, but the ordering is deliberate: a staff
    // member who opened a client link in their own signed-in browser would
    // otherwise start a session attributed to THEIR account rather than the
    // link -- quietly breaking both telemetry attribution and the link's
    // one-time-use accounting.
    setClientLinkToken("link-token");

    expect(await resolveSessionToken(staffUser)).toBe("link-token");
  });

  it("SURVIVES a reload but never reaches localStorage", () => {
    // Maintainer decision 2026-08-24. Memory-only stranded a client on any
    // RELOAD (the entry gate clears the token from the URL once redeemed),
    // which on a 40-minute form is a likely event with an expensive cost.
    //
    // sessionStorage is scoped to the TAB: it survives a reload, dies when
    // the tab closes, and is never shared with another tab. localStorage
    // would outlive the browser session entirely and is the line we hold.
    setClientLinkToken("secret.token");

    expect(sessionStorage.getItem("vff_client_link_token")).toBe("secret.token");
    expect(JSON.stringify({ ...localStorage })).not.toContain("secret.token");
  });

  it("recovers the token from storage after a reload drops memory", async () => {
    // THE RELOAD CASE, simulated the only honest way: wipe the module's
    // in-memory copy the way a page load does, and require the token to come
    // back from the tab's storage. Asserting only setItem would pass even if
    // nothing ever READ it back.
    setClientLinkToken("reload.token");
    clearInMemoryOnly();

    expect(await resolveSessionToken(null)).toBe("reload.token");
  });

  it("a closed tab leaves nothing behind (clear removes storage too)", () => {
    setClientLinkToken("gone.token");
    clearClientLinkToken();

    expect(sessionStorage.getItem("vff_client_link_token")).toBeNull();
    expect(hasClientLinkToken()).toBe(false);
  });
});

describe("the credential resolver is the ONLY token source", () => {
  it("no component derives a backend token directly from the Firebase user", () => {
    // PIN THE SET, not an instance (CLAUDE.md scar #7). The fresh-eyes
    // reviewer named SIX sites deriving `user.getIdToken()` inline; grepping
    // for the whole set found NINE -- including the PDF fetch, which a client
    // link session needs as much as the socket. Fixing the six named ones
    // would have left the client tier working on some surfaces and silently
    // unauthenticated on others.
    //
    // Derived from the shipped sources so a TENTH site fails CI rather than
    // shipping broken for clients only. If you are adding a backend call:
    // use resolveSessionToken(user), not user.getIdToken().
    const root = join(__dirname, "..");
    const offenders: string[] = [];

    const walk = (dir: string) => {
      for (const entry of readdirSync(dir)) {
        const full = join(dir, entry);
        if (statSync(full).isDirectory()) {
          if (entry !== "node_modules" && entry !== "__tests__") walk(full);
          continue;
        }
        if (!/\.tsx?$/.test(entry) || /\.test\.tsx?$/.test(entry)) continue;
        if (full.includes("sessionCredential")) continue;   // the resolver itself
        const src = readFileSync(full, "utf8");
        // The inline pattern this module replaced. A bare getIdToken() call
        // elsewhere (AuthContext's own plumbing) is fine -- what must not
        // recur is deriving a BACKEND CALL's token inline.
        if (src.includes("await user.getIdToken() : undefined")) {
          offenders.push(full.slice(root.length + 1).replace(/\\/g, "/"));
        }
      }
    };
    walk(root);

    expect(offenders).toEqual([]);
  });
});
