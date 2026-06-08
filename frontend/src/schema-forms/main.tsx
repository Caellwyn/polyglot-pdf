/**
 * Schema Forms Entry Point
 *
 * Renders the SchemaFormDemo component
 */

import React from "react";
import ReactDOM from "react-dom/client";
import { SchemaFormDemo } from "./SchemaFormDemo";
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
  <AuthProvider>
    <ProtectedRoute>
      <SchemaFormDemo />
    </ProtectedRoute>
  </AuthProvider>
  // </React.StrictMode>
);
