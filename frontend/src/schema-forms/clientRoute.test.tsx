/**
 * The route the client actually walks through (bd polyglot-pdf-ugm6).
 *
 * Opus cross-surface r8: no test imported the route table, so two mutations
 * that keep the code shape perfectly intact and destroy the feature both
 * passed all 1589 frontend tests -- wrapping the client route in
 * ProtectedRoute, and renaming its path. ClientLinkEntry has 15 tests of its
 * own; the COMPONENT was never the risk. The door it is mounted behind was.
 *
 * These assert BEHAVIOR (what a signed-out client sees at /f), not shape.
 *
 * @vitest-environment jsdom
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { AppRoutes, CLIENT_LINK_PATH } from "./AppRoutes";

// Firebase initializes at IMPORT time and throws without an API key, so the
// config must be stubbed before anything in the auth chain loads (the same
// pattern AuthContext.test.tsx uses).
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

// The client tier is signed out BY DEFINITION -- they have no account and
// never will. This is the state every real client is in.
vi.mock("../contexts/AuthContext", async () => {
  const actual = await vi.importActual<Record<string, unknown>>(
    "../contexts/AuthContext",
  );
  return {
    ...actual,
    AuthProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
    useAuth: () => ({ user: null, loading: false }),
  };
});

// The voice app drags in WS/audio/PDF workers; the route is what is under
// test, not what it renders once mounted.
vi.mock("./SchemaFormDemo", () => ({
  SchemaFormDemo: () => <div data-testid="staff-app">staff app</div>,
}));

describe("the client link route", () => {
  afterEach(() => cleanup());

  it("renders the CLIENT entry at /f for a signed-out visitor", async () => {
    // Mutation A (r8): wrap this route in ProtectedRoute -- red. Every client
    // would be bounced to a sign-in they can never pass, which the route
    // table's own comment warns against in capitals.
    render(
      <MemoryRouter initialEntries={[CLIENT_LINK_PATH]}>
        <AppRoutes />
      </MemoryRouter>,
    );

    // ClientLinkEntry's own output -- it refuses (no token in a MemoryRouter
    // hash), which is correct and is still PROOF the client route rendered.
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.getByText(/this link is not valid/i)).toBeTruthy();
    // And emphatically NOT the staff app or a sign-in wall.
    expect(screen.queryByTestId("staff-app")).toBeNull();
  });

  it("still gates every OTHER path behind sign-in", async () => {
    // The client route must not have opened the staff app to anonymous
    // users. ProtectedRoute renders its own sign-in UI for a null user.
    render(
      <MemoryRouter initialEntries={["/"]}>
        <AppRoutes />
      </MemoryRouter>,
    );

    expect(screen.queryByTestId("staff-app")).toBeNull();
  });

  it("pins the path the BACKEND builds links against", () => {
    // Mutation B (r8): rename the path -- red. This is a CROSS-LANGUAGE
    // contract: backend/routes/link_routes.py builds every minted URL as
    // `<base>/f#t=<token>`. Changing either side alone silently breaks every
    // link a firm has already sent -- no error, the client just lands on a
    // sign-in screen.
    //
    // Precisely: EACH SIDE is independently pinned to the same literal --
    // this constant here, and test_link_routes.py'''s fragment assertions
    // there. Not a single shared source of truth (the languages cannot share
    // one), but a unilateral change on EITHER side goes red, which is the
    // property that matters.
    expect(CLIENT_LINK_PATH).toBe("/f");
  });
});
