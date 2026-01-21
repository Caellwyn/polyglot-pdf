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
import "./styles/schema-form.css";

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
