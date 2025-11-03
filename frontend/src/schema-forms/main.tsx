/**
 * Schema Forms Entry Point
 *
 * Renders the SchemaFormDemo component
 */

import React from "react";
import ReactDOM from "react-dom/client";
import { SchemaFormDemo } from "./SchemaFormDemo";
import "./styles/schema-form.css";

const root = document.getElementById("root");
if (!root) {
  throw new Error("Root element not found");
}

ReactDOM.createRoot(root).render(
  <React.StrictMode>
    <SchemaFormDemo />
  </React.StrictMode>
);
