/**
 * PreviewPane -- the Preview view-mode surface (bd polyglot-pdf-vxwj shell,
 * live surface bd polyglot-pdf-ogrt).
 *
 * Renders the blank form PDF with fill-state field overlays: the user's
 * answers paint into their printed rects live as the voice session (or a
 * manual edit) fills them. SchemaForm passes the wrapped FieldValue map down
 * on every schemaFormStateChange, so no extra subscription lives here.
 * Click a field overlay to edit it in place (FieldEditPopover, bd
 * polyglot-pdf-7esr); the snap-to camera is bd polyglot-pdf-35t0.
 *
 * Lazy-loaded from SchemaForm (React.lazy), so pdfjs stays out of the default
 * bundle while the preview flag is off.
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { PDFPageProxy } from 'pdfjs-dist';
import type { FormSchema } from '../schema-forms/types/schema';
import { usePDFDocument } from './usePDFDocument';
import { hasValidCoordinates } from './pdfCoordinates';
import { PDFViewer } from './PDFViewer';
import { useSnapToField } from './useSnapToField';
import './pdf-view.css';

export interface PreviewPaneProps {
  pdfUrl?: string;
  schema: FormSchema;
  /** Wrapped FieldValue map from SchemaFormState (fresh on every change). */
  fieldValues: Record<string, any>;
  currentFieldId?: string | null;
  /**
   * Click-to-edit (bd polyglot-pdf-7esr): SchemaForm's existing
   * handleFieldChange / handleFieldBlur / validationErrors. handleFieldChange
   * is the single place stamping {confirmed: true, confirmationMethod:
   * 'manual_edit'} and fanning out copy_to -- Preview edits get exact parity
   * with Simplified-mode edits. All optional: absent, the surface stays
   * read-only.
   */
  validationErrors?: Record<string, string>;
  onFieldChange?: (fieldId: string, value: any) => void;
  onFieldBlur?: (fieldId: string) => void;
}

const MIN_SCALE = 0.5;
const MAX_SCALE = 2.0;

export default function PreviewPane({
  pdfUrl,
  schema,
  fieldValues,
  currentFieldId,
  validationErrors,
  onFieldChange,
  onFieldBlur,
}: PreviewPaneProps) {
  const { document: pdfDoc, numPages, isLoading, error } = usePDFDocument(pdfUrl ?? null);
  const [scale, setScale] = useState(1.0);
  const paneRef = useRef<HTMLDivElement>(null);
  const fitAppliedRef = useRef(false);

  // Click-to-edit popover state (bd polyglot-pdf-7esr). Closed on voice
  // advance (a currentFieldId change snaps the camera; keeping a popover
  // anchored to a now-off-screen rect would disorient, and write-through
  // means the typed value is already committed) and on zoom (the anchor's
  // screen rect changes under it).
  const editable = !!(onFieldChange && onFieldBlur);
  const [editingFieldId, setEditingFieldId] = useState<string | null>(null);
  const closeEditor = useCallback(() => setEditingFieldId(null), []);
  useEffect(() => {
    setEditingFieldId(null);
  }, [currentFieldId, scale]);

  // QA surface: any field that cannot paint (no usable rect) is listed once
  // per pane mount. Deps are deliberately empty: `schema` gets a fresh object
  // identity on every state reload (SchemaFormStateManager.load JSON-parses),
  // so a [schema] dep would re-log per fill.
  useEffect(() => {
    const unpositioned = schema.fields.filter((f) => !hasValidCoordinates(f.pdf_position));
    if (unpositioned.length > 0) {
      console.debug(
        `[PreviewPane] ${unpositioned.length} field(s) lack a usable pdf_position and will not paint:`,
        unpositioned.map((f) => f.id)
      );
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- once per mount by design
  }, []);

  // Snap-to camera (bd 35t0): instant snap on every current-field change;
  // free wandering between advances; the button below snaps back on demand.
  // Unpositioned fields have no overlay to snap to -- short-circuit them.
  // Deps deliberately empty: the field list is static per mount, while the
  // `schema` PROP identity churns on every fill (state reload) -- keying on it
  // would give isSnappable a fresh identity per fill and re-fire the snap
  // effect, yanking a wandering user back on every fill (free-wander rule).
  const positionedIds = useMemo(
    () => new Set(schema.fields.filter((f) => hasValidCoordinates(f.pdf_position)).map((f) => f.id)),
    // eslint-disable-next-line react-hooks/exhaustive-deps -- static per mount by design
    []
  );
  const isSnappable = useCallback((fieldId: string) => positionedIds.has(fieldId), [positionedIds]);
  const { snapTo } = useSnapToField(paneRef, currentFieldId, !!pdfDoc, isSnappable);

  // Fit-width once, off the first rendered page's unscaled dimensions.
  const handleFirstPageLoad = useCallback((page: PDFPageProxy) => {
    if (fitAppliedRef.current || !paneRef.current) return;
    fitAppliedRef.current = true;
    const pageWidth = page.getViewport({ scale: 1.0 }).width;
    const available = paneRef.current.clientWidth - 32;
    if (pageWidth > 0 && available > 0) {
      const fit = Math.min(MAX_SCALE, Math.max(MIN_SCALE, available / pageWidth));
      setScale(Math.round(fit * 100) / 100);
    }
  }, []);

  if (!pdfUrl) {
    return (
      <div className="pdf-preview-pane__notice">
        Preview mode needs the form's PDF, which is not configured for this
        form. Switch back to Simplified view.
      </div>
    );
  }

  return (
    <div className="pdf-preview-pane">
      <div className="pdf-preview-pane__toolbar">
        <div className="pdf-preview-pane__banner">
          Preview mode: your answers appear on the real form as you go. Colors:
          orange = current field, blue = filled, green = confirmed. For the
          exact print output, use "Preview Filled PDF" below.
        </div>
        <button
          type="button"
          className="pdf-preview-pane__snap-button"
          onClick={() => currentFieldId && snapTo(currentFieldId)}
          disabled={!currentFieldId}
          title={
            currentFieldId
              ? 'Jump back to the field being filled'
              : 'Available while the voice assistant is on a field'
          }
        >
          Snap to current field
        </button>
      </div>
      <div className="pdf-preview-pane__pages" ref={paneRef}>
        {error && <p className="pdf-preview-pane__error">Could not load the form PDF: {error}</p>}
        {!error && isLoading && <p className="pdf-preview-pane__loading">Loading the form...</p>}
        {pdfDoc && (
          <PDFViewer
            document={pdfDoc}
            numPages={numPages}
            scale={scale}
            fields={schema.fields}
            fieldValues={fieldValues}
            currentFieldId={currentFieldId}
            onFirstPageLoad={handleFirstPageLoad}
            editingFieldId={editable ? editingFieldId : null}
            onOverlayClick={editable ? setEditingFieldId : undefined}
            onCloseEditor={editable ? closeEditor : undefined}
            validationErrors={validationErrors}
            onFieldChange={onFieldChange}
            onFieldBlur={onFieldBlur}
          />
        )}
      </div>
    </div>
  );
}
