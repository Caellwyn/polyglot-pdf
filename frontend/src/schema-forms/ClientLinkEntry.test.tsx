/**
 * ClientLinkEntry -- the client's only entry path (bd polyglot-pdf-ugm6).
 *
 * @vitest-environment jsdom
 */
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";

import { ClientLinkEntry, readTokenFromHash } from "./ClientLinkEntry";
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
    expect(String(url)).toContain("/api/links/open");
    expect(JSON.parse(init.body).token).toBe("good.token");
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

  it("refuses immediately when the URL carries no token", async () => {
    setHash("");
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    render(<ClientLinkEntry />);

    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("does not render the form app when the network fails", async () => {
    // A thrown fetch must fail CLOSED, not fall through to the form.
    setHash("#t=good.token");
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));

    render(<ClientLinkEntry />);

    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.queryByTestId("form-app")).toBeNull();
  });

  it("renders the form ONLY with a redeemed link, never on phase alone", async () => {
    // FAIL-CLOSED, STRUCTURALLY. Found by mutation: flipping the catch block
    // to setPhase("ready") left all 11 tests green, because `link` happened
    // to stay null. That is accidental protection -- the guard now requires
    // BOTH a ready phase and a redeemed link, and this test drives the exact
    // case (a network failure that wrongly reports ready).
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
