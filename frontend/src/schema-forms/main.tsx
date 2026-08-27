/**
 * Schema Forms Entry Point
 *
 * This file is now ONLY the createRoot call. The route table lives in
 * AppRoutes.tsx so it can be imported by a test -- while it lived here,
 * nothing could pin it, and two shape-preserving mutations that break the
 * client tier entirely passed the whole frontend suite (bd polyglot-pdf-ugm6,
 * Opus cross-surface r8).
 */

import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { AppRoutes } from "./AppRoutes";
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
    <AppRoutes />
  </BrowserRouter>
  // </React.StrictMode>
);
