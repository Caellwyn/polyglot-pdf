/**
 * Field-highlight timing.
 *
 * The `.field-highlight` class runs the `highlight-pulse` CSS animation
 * (schema-forms/styles/schema-form.css), which is 1.5s long. The class is
 * removed after the animation completes, so the removal delay is pinned to the
 * animation duration -- a single source of truth for both highlight call sites
 * (the AI field-confirm scroll in webFormConnection.ts and the next-field hint
 * in SchemaForm.tsx). Previously these used 1500ms and 2000ms respectively;
 * 2000ms left the class on for 500ms after the pulse finished (bd polyglot-pdf-nxb).
 */
export const FIELD_HIGHLIGHT_DURATION_MS = 1500;
