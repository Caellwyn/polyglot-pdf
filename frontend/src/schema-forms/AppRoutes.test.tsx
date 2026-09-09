/**
 * The link-history route (bd polyglot-pdf-x22hm, Epic 2 Track C bead C5),
 * exit criterion 2: "the route table test pins the new path behind
 * ProtectedRoute."
 *
 * Mirrors clientRoute.test.tsx's mint-route tests exactly (same mocking
 * shape, same "signed out shows nothing, signed in mounts the real page, not
 * the staff catch-all" pair) -- that file already owns CLIENT_LINK_PATH and
 * MINT_PATH's own route-table coverage; this NEW file (named in the bead's
 * own surfaces list) is where LINK_HISTORY_PATH's gets pinned, rather than
 * appended to a file about a different route with its own header comment.
 *
 * @vitest-environment jsdom
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { AppRoutes, LINK_HISTORY_PATH } from "./AppRoutes";

// Firebase initializes at IMPORT time and throws without an API key --
// same stub clientRoute.test.tsx uses.
vi.mock("../firebase/config", () => ({
  auth: { __sentinel: "auth" },
  db: { __sentinel: "db" },
}));
vi.mock("firebase/auth", () => ({
  GoogleAuthProvider: class {},
  onAuthStateChanged: () => () => {},
  signInWithPopup: vi.fn(),
  signInWithEmailAndPassword: vi.fn(),
  createUserWithEmailAndPassword: vi.fn(),
  signOut: vi.fn(),
  sendPasswordResetEmail: vi.fn(),
}));

let signedIn = false;

vi.mock("../contexts/AuthContext", async () => {
  const actual = await vi.importActual<Record<string, unknown>>(
    "../contexts/AuthContext",
  );
  return {
    ...actual,
    AuthProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
    useAuth: () => ({
      user: signedIn ? { uid: "staff-1", email: "staff@example.com" } : null,
      loading: false,
    }),
  };
});

// The route table is what is under test -- LinkHistoryPage's own behavior
// (manager vs. employee, filters, revoke) is covered by
// console/LinkHistoryPage.test.tsx.
vi.mock("../console/LinkHistoryPage", () => ({
  LinkHistoryPage: () => <div data-testid="link-history-page">link history</div>,
}));

vi.mock("./SchemaFormDemo", () => ({
  SchemaFormDemo: () => <div data-testid="staff-app">staff app</div>,
}));

describe("the link-history route", () => {
  afterEach(() => {
    cleanup();
    signedIn = false;
  });

  it("does NOT show link history to a signed-out visitor", () => {
    // The real regression this guards against: dropping ProtectedRoute from
    // this route. Link history shows a firm's spend and revoke controls --
    // exactly the kind of page that must never be reachable anonymously.
    render(
      <MemoryRouter initialEntries={[LINK_HISTORY_PATH]}>
        <AppRoutes />
      </MemoryRouter>,
    );

    expect(screen.queryByTestId("link-history-page")).toBeNull();
  });

  it("MOUNTS link history for a signed-in user, not the staff app", async () => {
    // Without ProtectedRoute (or with the <Route> deleted entirely) the
    // catch-all "*" route swallows this path and renders the voice app --
    // a working page that is simply the WRONG one. This is the only test
    // that would catch that: from outside, a gated link-history page and a
    // gated staff app look identical.
    signedIn = true;
    render(
      <MemoryRouter initialEntries={[LINK_HISTORY_PATH]}>
        <AppRoutes />
      </MemoryRouter>,
    );

    expect(await screen.findByTestId("link-history-page")).toBeTruthy();
    expect(screen.queryByTestId("staff-app")).toBeNull();
  });

  it("pins the link-history path", () => {
    expect(LINK_HISTORY_PATH).toBe("/console/links/history");
  });
});
