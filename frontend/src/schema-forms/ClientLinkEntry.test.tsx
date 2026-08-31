/**
 * ClientLinkEntry -- the client's only entry path (bd polyglot-pdf-ugm6).
 *
 * @vitest-environment jsdom
 */
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";

import { ClientLinkEntry, readTokenFromHash } from "./ClientLinkEntry";
import {
  clearClientLinkToken,
  resolveSessionToken,
  setClientLinkToken,
} from "../shared/sessionCredential";
import { ONBOARDING_FORM_KEY, ONBOARDING_LANGUAGE_KEY } from "./onboardingStorage";

// SchemaFormDemo drags in the whole voice app (WS, audio, PDF worker). This
// suite is about the GATE, so stub it: rendering the real one would test
// everything except the thing under test.
vi.mock("./SchemaFormDemo", () => ({
  SchemaFormDemo: () => <div data-testid="form-app">form app</div>,
}));

const OPENED = {
  kit_id: "firm-a-intake",
  firm_id: "firm-a",
  jti: "join-key-123",
  complete_by: 2_000_000_000,
};

function setHash(hash: string) {
  window.history.replaceState(null, "", "/f" + hash);
}

describe("ClientLinkEntry", () => {
  beforeEach(() => {
    sessionStorage.clear();
    clearClientLinkToken();   // also drops the module's in-memory mirror
    vi.restoreAllMocks();
  });

  afterEach(() => {
    // Unmount between tests: without this the rendered trees accumulate in
    // the shared jsdom document and every query matches multiple elements
    // (this suite's own first run failed exactly that way).
    cleanup();
    vi.unstubAllGlobals();
  });

  describe("readTokenFromHash", () => {
    it("reads the token from the fragment", () => {
      expect(readTokenFromHash("#t=abc.def")).toBe("abc.def");
    });

    it("tolerates a rewritten URL shape", () => {
      // Email clients and chat apps rewrite links; the token must survive a
      // `#/f?t=` shape as well as a bare `#t=`.
      expect(readTokenFromHash("#/f?t=abc.def")).toBe("abc.def");
    });

    it("returns null when there is no token", () => {
      for (const hash of ["", "#", "#other=1", "#t=", "#t=%20"]) {
        expect(readTokenFromHash(hash)).toBeNull();
      }
    });
  });

  it("redeems the link and then renders the form app", async () => {
    setHash("#t=good.token");
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => OPENED,
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<ClientLinkEntry />);

    expect(await screen.findByTestId("form-app")).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    // PARSE IT, do not substring-match. `toContain("/api/links/open")`
    // passed while the URL was
    // "wss://host/ws/fill/api/links/open" -- built from the WEBSOCKET
    // resolver -- which throws in fetch, so every valid link showed "not
    // valid" (Opus cross-surface r4). The property that matters is that a
    // browser can actually fetch it.
    const parsed = new URL(String(url));
    expect(parsed.protocol).toMatch(/^https?:$/);
    expect(parsed.pathname).toBe("/api/links/open");
    expect(JSON.parse(init.body).token).toBe("good.token");
  });

  it("STASHES the redeemed token so the app can AUTHENTICATE", async () => {
    // THE UNPROVEN HALF of r1 finding 1. That bug was "the redeemed token
    // was captured and then discarded", and the fix is one line in this
    // component -- setClientLinkToken(token). NOTHING pinned it: delete that
    // line and all 13 tests here stayed green, because they assert the form
    // renders, the form id is pinned, or the fetch shape -- none of which
    // touch the credential.
    //
    // sessionCredential.test.ts cannot cover it either: it proves the
    // MODULE round-trips, which is the one-layer-removed shape this bead
    // has now been bitten by four times.
    //
    // Mutation: drop setClientLinkToken(token) in ClientLinkEntry -- red.
    clearClientLinkToken();
    setHash("#t=good.token");
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, json: async () => OPENED }),
    );

    render(<ClientLinkEntry />);
    await screen.findByTestId("form-app");

    // The assertion that MATTERS is the second one: it proves the credential
    // is reachable through the resolver every backend-calling site actually
    // uses, not merely that some key was written to storage.
    expect(sessionStorage.getItem("vff_client_link_token")).toBe("good.token");
    expect(await resolveSessionToken(null)).toBe("good.token");
  });

  it("PINS the form so the client never sees a form picker", async () => {
    // Exit criterion: a link reaches exactly the one kit it names. If the
    // form id were not pinned before render, the client would be shown the
    // onboarding modal and could pick a DIFFERENT form.
    setHash("#t=good.token");
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, json: async () => OPENED }),
    );

    render(<ClientLinkEntry />);
    await screen.findByTestId("form-app");

    expect(sessionStorage.getItem(ONBOARDING_FORM_KEY)).toBe("firm-a-intake");
  });

  it("leaves LANGUAGE unset so the client still chooses their own", async () => {
    // Deliberate: the form is the firm's choice, the language is the
    // client's. Pinning language here would silently pick one for them.
    setHash("#t=good.token");
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, json: async () => OPENED }),
    );

    render(<ClientLinkEntry />);
    await screen.findByTestId("form-app");

    expect(sessionStorage.getItem(ONBOARDING_LANGUAGE_KEY)).toBeNull();
  });

  it("CLEARS the token from the address bar once redeemed", async () => {
    // The fragment is a working credential until the link is completed. It
    // must not linger in the URL through a screen-share or a history sync.
    setHash("#t=good.token");
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, json: async () => OPENED }),
    );

    render(<ClientLinkEntry />);
    await screen.findByTestId("form-app");

    expect(window.location.hash).toBe("");
  });

  it("shows one generic message for EVERY refusal", async () => {
    // The backend returns one indistinguishable 404 for expired / replayed /
    // forged / suspended, so the UI must not invent distinctions it does not
    // have -- and the client's action is the same in every case.
    setHash("#t=bad.token");
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: false, status: 404, json: async () => ({}) }),
    );

    render(<ClientLinkEntry />);

    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.getByText(/this link is not valid/i)).toBeTruthy();
    expect(screen.queryByTestId("form-app")).toBeNull();
  });

  it("refuses when the URL carries no token AND nothing was redeemed", async () => {
    // A stranger opening /f with no fragment. Distinct from the RELOAD case
    // below -- the difference is whether this tab ever redeemed a link.
    setHash("");
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    render(<ClientLinkEntry />);

    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("RECOVERS on reload: empty hash but a token in this tab's storage", async () => {
    // THE RELOAD CASE, and the one the storage exists for. We clear the
    // fragment after redeeming, so a refresh arrives with an empty URL and a
    // still-valid token in sessionStorage.
    //
    // The first pass shipped the storage WITHOUT this branch -- written,
    // never read -- so a reload still showed "This link is not valid" while
    // the commit and three docs claimed it was fixed (fresh-eyes r3). A test
    // that only checks the storage module cannot catch that; this one drives
    // the gate component, which is where the bug was.
    setClientLinkToken("already.redeemed.token");
    setHash("");
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    render(<ClientLinkEntry />);

    expect(await screen.findByTestId("form-app")).toBeTruthy();
    // And it must NOT re-redeem: the link is already open and the form id is
    // already pinned, so a second /open is a wasted metered call.
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("a reload does NOT resurrect a session in a tab that never redeemed", async () => {
    // The recovery must key on THIS tab's storage, not on anything ambient.
    // sessionStorage is tab-scoped, so a fresh tab has nothing and must
    // refuse -- otherwise the recovery branch becomes a way in.
    clearClientLinkToken();
    setHash("");
    vi.stubGlobal("fetch", vi.fn());

    render(<ClientLinkEntry />);

    expect(await screen.findByRole("alert")).toBeTruthy();
  });

  it("does not render the form app when the network fails", async () => {
    // A thrown fetch must fail CLOSED, not fall through to the form.
    setHash("#t=good.token");
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));

    render(<ClientLinkEntry />);

    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.queryByTestId("form-app")).toBeNull();
  });

  it("never renders the form from an ERROR path", async () => {
    // FAIL-CLOSED. Found by mutation: flipping the catch block to
    // setPhase("ready") once left every test green because `link` happened to
    // stay null -- accidental protection, not a guarantee.
    //
    // The guard is now `phase !== "ready"` alone (the reload path has no
    // `link` object, since /open is not re-fetched), so what makes it safe is
    // that ONLY TWO paths set "ready": a successful redemption, and a
    // confirmed token in this tab. No catch, timeout, or refusal does --
    // verified independently by fresh-eyes r4, which mutated the catch block
    // and watched this test and its neighbour go red.
    //
    // A malformed 200 is the real-world shape: a proxy or captive portal
    // returning HTML where JSON was expected.
    setHash("#t=good.token");
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => {
          throw new Error("not json");
        },
      }),
    );

    render(<ClientLinkEntry />);

    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.queryByTestId("form-app")).toBeNull();
    // And nothing was pinned, so a later legitimate link is not confused by
    // a half-written selection.
    expect(sessionStorage.getItem(ONBOARDING_FORM_KEY)).toBeNull();
  });

  it("redeems only ONCE across re-renders", async () => {
    setHash("#t=good.token");
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => OPENED,
    });
    vi.stubGlobal("fetch", fetchMock);

    const { rerender } = render(<ClientLinkEntry />);
    await screen.findByTestId("form-app");
    rerender(<ClientLinkEntry />);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
  });
});
