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

  it("does not persist the token to storage", () => {
    // The token rides the URL fragment precisely to stay out of durable
    // places. Writing it to sessionStorage would undo that.
    setClientLinkToken("secret.token");

    const dump = JSON.stringify({ ...sessionStorage, ...localStorage });
    expect(dump).not.toContain("secret.token");
    expect(hasClientLinkToken()).toBe(true);
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
