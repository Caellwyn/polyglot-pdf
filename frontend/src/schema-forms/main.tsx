/**
 * Schema Forms Entry Point
 *
 * ROUTING (bd polyglot-pdf-ugm6). Two entry points with DIFFERENT auth
 * postures, which is the entire reason a router exists here:
 *
 *   /f   -- the firm CLIENT's one-time link. OUTSIDE ProtectedRoute: a client
 *           has no Firebase account and must never have one. The signed link
 *           in the URL fragment IS the credential.
 *   /*   -- everything else: staff, behind ProtectedRoute exactly as before.
 *
 * The client route MUST stay outside the auth gate. Moving it inside would
 * bounce every client to a sign-in screen they can never pass -- and the
 * maintainer explicitly rejected the alternative of clients working on
 * staff-signed-in machines (2026-08-17).
 */

import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { SchemaFormDemo } from "./SchemaFormDemo";
import { ClientLinkEntry } from "./ClientLinkEntry";
import { AuthProvider } from "../contexts/AuthContext";
import { ProtectedRoute } from "../components/layout/ProtectedRoute";
import { installDevConsoleCapture } from "../shared/devConsoleCapture";
import "./styles/schema-form.css";

// Mirror the browser console to the backend dev log when running against a LOCAL
// backend (bd polyglot-pdf-2m9). No-op against cloud/prod. Install before render so
// startup logs are captured too. ws_session_id is read live from sessionStorage so
// frontend lines correlate with the backend's ws_session_id in scripts/logs.py.
installDevConsoleCapture(() => {
  try {
    const raw = sessionStorage.getItem("schema_form_state");
    return raw ? JSON.parse(raw).formSessionId : undefined;
  } catch {
    return undefined;
  }
});

const root = document.getElementById("root");
if (!root) {
  throw new Error("Root element not found");
}



ReactDOM.createRoot(root).render(
  // Temporarily disabled StrictMode - it was causing double renders
  // and creating duplicate state objects
  // <React.StrictMode>
  <BrowserRouter>
    <Routes>
      {/* CLIENT ENTRY -- deliberately NOT wrapped in ProtectedRoute.
          AuthProvider still wraps it because downstream components read the
          auth context (and get a signed-out state, which is correct here). */}
      <Route
        path="/f"
        element={
          <AuthProvider>
            <ClientLinkEntry />
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
  </BrowserRouter>
  // </React.StrictMode>
);
