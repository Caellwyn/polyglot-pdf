/**
 * PDFViewer -- the live Preview page stack: rendered PDF pages with
 * fill-state field overlays on top (bd polyglot-pdf-ogrt).
 *
 * Diverged from the schema editor's PDFViewer: no toolbar/selection (the
 * pane owns fit-width; snap-to camera is the P1.3 bead); overlays are the
 * fill-state FieldOverlay, driven by the wrapped FieldValue map from
 * SchemaFormState (passed down by SchemaForm, which subscribes to the
 * schemaFormStateChange channel).
 */

import React from 'react';
import type { PDFDocumentProxy, PDFPageProxy } from 'pdfjs-dist';
import type { FormField } from '../schema-forms/types/schema';
import { readFieldEntryWithAlias, unwrapFieldValue } from '../schema-forms/utils/fieldValue';
import { shouldShowField } from '../schema-forms/utils/validation';
import { pdfToScreenCoords, hasValidCoordinates } from './pdfCoordinates';
import { PDFPage } from './PDFPage';
import { FieldOverlay, type FillState } from './FieldOverlay';
import { FieldEditPopover } from './FieldEditPopover';

export interface PDFViewerProps {
  document: PDFDocumentProxy;
  numPages: number;
  scale: number;
  fields: FormField[];
  /** Wrapped FieldValue map straight from SchemaFormState. */
  fieldValues: Record<string, any>;
  currentFieldId?: string | null;
  onFirstPageLoad?: (page: PDFPageProxy) => void;
  /**
   * Click-to-edit (bd polyglot-pdf-7esr). All four arrive together from
   * PreviewPane (which owns the editing state); absent, the surface is
   * read-only exactly as before.
   */
  editingFieldId?: string | null;
  onOverlayClick?: (fieldId: string) => void;
  onCloseEditor?: () => void;
  validationErrors?: Record<string, string>;
  onFieldChange?: (fieldId: string, value: any) => void;
  onFieldBlur?: (fieldId: string) => void;
}

export function fillStateFor(
  fieldId: string,
  wrapped: any,
  raw: unknown,
  currentFieldId?: string | null
): FillState {
  if (fieldId === currentFieldId) return 'current';
  // An empty array counts as empty (a cleared checkbox_group selection) --
  // same convention as validation.ts's required-check.
  const isEmpty =
    raw === null ||
    raw === undefined ||
    raw === '' ||
    raw === false ||
    (Array.isArray(raw) && raw.length === 0);
  if (isEmpty) return 'empty';
  if (wrapped && typeof wrapped === 'object' && wrapped.confirmed) return 'confirmed';
  return 'filled';
}

export const PDFViewer: React.FC<PDFViewerProps> = ({
  document,
  numPages,
  scale,
  fields,
  fieldValues,
  currentFieldId,
  onFirstPageLoad,
  editingFieldId,
  onOverlayClick,
  onCloseEditor,
  validationErrors,
  onFieldChange,
  onFieldBlur,
}) => {
  const editable = !!(onOverlayClick && onCloseEditor && onFieldChange && onFieldBlur);
  const editingField =
    editable && editingFieldId ? fields.find((f) => f.id === editingFieldId) : undefined;
  return (
    <>
      {Array.from({ length: numPages }, (_, i) => {
        const pageNum = i + 1;
        const pageFields = fields.filter((f) => f.pdf_position?.page === pageNum);
        // The popover renders inside ITS field's page container, in the same
        // page coordinate space as the overlays (scrolls with the page).
        const editingHere =
          editingField && editingField.pdf_position?.page === pageNum &&
          hasValidCoordinates(editingField.pdf_position)
            ? editingField
            : undefined;
        return (
          <div key={pageNum} className="pdf-viewer__page" data-page-number={pageNum}>
            <div className="pdf-viewer__page-inner">
              <PDFPage
                document={document}
                pageNumber={pageNum}
                scale={scale}
                onPageLoad={pageNum === 1 ? onFirstPageLoad : undefined}
              />
              <div className="pdf-viewer__overlay-layer">
                {pageFields.map((field) => {
                  // []-alias-aware read (bd polyglot-pdf-7sdc): the overlay must
                  // resolve a value stored under the OTHER bracket variant than
                  // field.id, matching the validator projection and the backend
                  // fill. A bare fieldValues[field.id] rendered BLANK for a
                  // filled checkbox-group after the got6 dedup collapsed the
                  // duplicate key to whichever bracket variant Gemini last wrote.
                  const wrapped = readFieldEntryWithAlias(fieldValues, field.id);
                  const raw = unwrapFieldValue(wrapped);
                  return (
                    <FieldOverlay
                      key={field.id}
                      field={field}
                      rawValue={raw}
                      fillState={fillStateFor(field.id, wrapped, raw, currentFieldId)}
                      scale={scale}
                      // show_if-hidden fields DIM, never disappear -- they
                      // exist on the printed page (bd polyglot-pdf-lp5v).
                      // shouldShowField unwraps the wrapped map internally.
                      dimmed={!shouldShowField(field, fieldValues, fields)}
                      onClick={editable ? onOverlayClick : undefined}
                    />
                  );
                })}
              </div>
              {editingHere && (
                <FieldEditPopover
                  field={editingHere}
                  value={fieldValues[editingHere.id]}
                  allFieldValues={fieldValues}
                  error={validationErrors?.[editingHere.id] ?? null}
                  onChange={(value) => onFieldChange!(editingHere.id, value)}
                  onBlur={onFieldBlur!}
                  onClose={onCloseEditor!}
                  anchor={pdfToScreenCoords(editingHere.pdf_position!, scale)}
                />
              )}
            </div>
            <div className="pdf-preview-pane__page-label">
              Page {pageNum} of {numPages}
            </div>
          </div>
        );
      })}
    </>
  );
};
