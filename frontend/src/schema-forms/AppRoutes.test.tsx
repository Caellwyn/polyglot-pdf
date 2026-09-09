/**
 * The app's route table (bd polyglot-pdf-ugm6; renamed from
 * clientRoute.test.tsx and extended to every console route by bd
 * polyglot-pdf-krbol, C4).
 *
 * Opus cross-surface r8: no test imported the route table, so two mutations
 * that keep the code shape perfectly intact and destroy the feature both
 * passed all 1589 frontend tests -- wrapping the client route in
 * ProtectedRoute, and renaming its path. ClientLinkEntry has 15 tests of its
 * own; the COMPONENT was never the risk. The door it is mounted behind was.
 * Every console page added since (the mint route, now the employees route)
 * pins the SAME class of failure: which door it sits behind, not what it
 * renders once mounted -- each page's own tests cover its content.
 *
 * These assert BEHAVIOR (what a signed-out visitor sees at each path), not
 * shape.
 *
 * @vitest-environment jsdom
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { AppRoutes, CLIENT_LINK_PATH, MINT_PATH, EMPLOYEES_PATH } from "./AppRoutes";

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
// never will. Signed out is therefore the DEFAULT here, and every client-route
// test below depends on it; only the staff-console cases flip it.
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

// The voice app drags in WS/audio/PDF workers; the route is what is under
// test, not what it renders once mounted.
vi.mock("../console/MintLinkPage", () => ({
  MintLinkPage: () => <div data-testid="mint-page">mint page</div>,
}));

// EmployeesPage itself talks to the admin service and does its own
// manager-claim check; neither matters to the route table, which only cares
// whether the component MOUNTS behind the right door.
vi.mock("../console/EmployeesPage", () => ({
  EmployeesPage: () => <div data-testid="employees-page">employees page</div>,
}));

vi.mock("./SchemaFormDemo", () => ({
  SchemaFormDemo: () => <div data-testid="staff-app">staff app</div>,
}));

describe("the client link route", () => {
  afterEach(() => {
    cleanup();
    // Reset to the client default. A leaked `true` would quietly turn the
    // signed-out assertions into tests of a signed-in app -- passing for the
    // wrong reason, and order-dependent.
    signedIn = false;
  });

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

  // --- The mint route (bd polyglot-pdf-gob8l) -------------------------------
  // Same failure mode as the client route above, opposite polarity: /f must be
  // reachable SIGNED OUT, /console/links must NOT be. The page's own tests
  // say nothing about which door it sits behind -- and an unmounted page is
  // the exact way the previous bead shipped ten tested modules a user could
  // not reach.

  it("does NOT show the mint page to a signed-out visitor", async () => {
    // The real regression this pins: dropping ProtectedRoute while "fixing" a
    // redirect. Minting is the one action that spends money on behalf of a
    // firm, so an anonymous mint page is the worst case in this feature.
    render(
      <MemoryRouter initialEntries={[MINT_PATH]}>
        <AppRoutes />
      </MemoryRouter>,
    );

    expect(screen.queryByTestId("mint-page")).toBeNull();
  });

  it("MOUNTS the mint page for a signed-in user, not the staff app", async () => {
    // Without this, deleting the whole <Route> stays GREEN: the catch-all `*`
    // route swallows /console/links and renders the voice app, so a signed-in
    // maintainer sees a working page that is simply the WRONG one. The
    // signed-out test above cannot catch that -- both a gated mint page and a
    // gated staff app look identical from outside the door.
    //
    // Behavioral, not source-shaped: this renders the route and looks at what
    // came out. Reading AppRoutes.tsx as text would pin the code SHAPE, which
    // is what this file's header warns against.
    signedIn = true;
    render(
      <MemoryRouter initialEntries={[MINT_PATH]}>
        <AppRoutes />
      </MemoryRouter>,
    );

    expect(await screen.findByTestId("mint-page")).toBeTruthy();
    expect(screen.queryByTestId("staff-app")).toBeNull();
  });

  it("pins the mint path so a rename cannot silently orphan the console", () => {
    expect(MINT_PATH).toBe("/console/links");
  });

  // --- The employees route (bd polyglot-pdf-krbol, C4) ----------------------
  // Same failure mode as the mint route above: /console/employees must NOT be
  // reachable signed out, and deleting the whole <Route> must not stay green
  // because the catch-all silently swallows the path.

  it("does NOT show the employees page to a signed-out visitor", async () => {
    render(
      <MemoryRouter initialEntries={[EMPLOYEES_PATH]}>
        <AppRoutes />
      </MemoryRouter>,
    );

    expect(screen.queryByTestId("employees-page")).toBeNull();
  });

  it("MOUNTS the employees page for a signed-in user, not the staff app", async () => {
    // Without this, deleting the whole <Route> stays GREEN: the catch-all `*`
    // route swallows /console/employees and renders the voice app, so a
    // signed-in maintainer sees a working page that is simply the WRONG one.
    signedIn = true;
    render(
      <MemoryRouter initialEntries={[EMPLOYEES_PATH]}>
        <AppRoutes />
      </MemoryRouter>,
    );

    expect(await screen.findByTestId("employees-page")).toBeTruthy();
    expect(screen.queryByTestId("staff-app")).toBeNull();
  });

  it("pins the employees path so a rename cannot silently orphan the console", () => {
    expect(EMPLOYEES_PATH).toBe("/console/employees");
  });
});
