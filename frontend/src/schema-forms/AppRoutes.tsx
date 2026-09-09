/**
 * The app's route table (bd polyglot-pdf-ugm6).
 *
 * EXTRACTED FROM main.tsx SO IT CAN BE TESTED. While the routes lived beside
 * the `createRoot` call, no test could import them, and Opus cross-surface r8
 * showed what that cost: two mutations that keep the code shape perfectly
 * intact and destroy the feature both passed all 1589 frontend tests --
 *
 *   - wrapping the client route in ProtectedRoute (the route still exists,
 *     ClientLinkEntry is still its element) bounces every client to a
 *     Firebase sign-in they can never pass;
 *   - renaming the path from "/f" to anything else sends every minted link
 *     to the staff catch-all and the same sign-in wall.
 *
 * ClientLinkEntry itself has 15 tests. The COMPONENT was never the risk --
 * the door it is mounted behind was, and nothing pinned that.
 */
import React from "react";
import { Route, Routes } from "react-router-dom";

import { SchemaFormDemo } from "./SchemaFormDemo";
import { ClientLinkEntry } from "./ClientLinkEntry";
import { MintLinkPage } from "../console/MintLinkPage";
import { EmployeesPage } from "../console/EmployeesPage";
import { AuthProvider } from "../contexts/AuthContext";
import { ProtectedRoute } from "../components/layout/ProtectedRoute";

/**
 * THE CLIENT ENTRY PATH, and one half of a CROSS-LANGUAGE CONTRACT: the
 * backend builds every minted link as `<base>${CLIENT_LINK_PATH}#t=<token>`
 * (backend/routes/link_routes.py). Changing either side alone silently
 * breaks every link a firm has already sent, with no error anywhere -- the
 * client just lands on a sign-in screen. The pairing is asserted by
 * clientRoute.test.tsx against the backend's own constant.
 */
export const CLIENT_LINK_PATH = "/f";

/** Where staff mint a client link (bd polyglot-pdf-gob8l, first console slice). */
export const MINT_PATH = "/console/links";

/** Where a firm manager runs their own staff account management (bd
 * polyglot-pdf-krbol, Epic 2 Track C bead C4). Any signed-in staffer can
 * REACH this route (ProtectedRoute gates on sign-in only, same as MINT_PATH
 * above) -- EmployeesPage itself hides its content unless the token's
 * firm_role claim is "manager", and the admin service enforces the same
 * rule independently on every request the page sends. See EmployeesPage.tsx's
 * module docstring for why the route-level gate is deliberately no
 * stricter than sign-in. */
export const EMPLOYEES_PATH = "/console/employees";

export function AppRoutes() {
  return (
    <Routes>
      {/* CLIENT ENTRY -- deliberately NOT wrapped in ProtectedRoute. A
          client has no Firebase account and must never have one, so the
          signed link in the URL fragment IS the credential. AuthProvider
          still wraps it because downstream components read the auth context
          (and correctly get a signed-out state here). */}
      <Route
        path={CLIENT_LINK_PATH}
        element={
          <AuthProvider>
            <ClientLinkEntry />
          </AuthProvider>
        }
      />
      {/* CONSOLE -- staff only, and auth-gated exactly like the app itself.
          The backend gates independently on a firm claim, so this route being
          reachable does not by itself let anyone mint. */}
      <Route
        path={MINT_PATH}
        element={
          <AuthProvider>
            <ProtectedRoute>
              <MintLinkPage />
            </ProtectedRoute>
          </AuthProvider>
        }
      />
      {/* CONSOLE -- firm-console employee management (bd polyglot-pdf-krbol).
          Same auth-gate shape as MINT_PATH: any signed-in staffer reaches
          the route, EmployeesPage's own manager-only check (UX) and the
          admin service's gate (enforcement) are what actually restrict it. */}
      <Route
        path={EMPLOYEES_PATH}
        element={
          <AuthProvider>
            <ProtectedRoute>
              <EmployeesPage />
            </ProtectedRoute>
          </AuthProvider>
        }
      />
      {/* STAFF -- unchanged: auth required. */}
      <Route
        path="*"
        element={
          <AuthProvider>
            <ProtectedRoute>
              <SchemaFormDemo />
            </ProtectedRoute>
          </AuthProvider>
        }
      />
    </Routes>
  );
}
