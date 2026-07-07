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
import { unwrapFieldValue } from '../schema-forms/utils/fieldValue';
import { PDFPage } from './PDFPage';
import { FieldOverlay, type FillState } from './FieldOverlay';

export interface PDFViewerProps {
  document: PDFDocumentProxy;
  numPages: number;
  scale: number;
  fields: FormField[];
  /** Wrapped FieldValue map straight from SchemaFormState. */
  fieldValues: Record<string, any>;
  currentFieldId?: string | null;
  onFirstPageLoad?: (page: PDFPageProxy) => void;
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
}) => {
  return (
    <>
      {Array.from({ length: numPages }, (_, i) => {
        const pageNum = i + 1;
        const pageFields = fields.filter((f) => f.pdf_position?.page === pageNum);
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
                  const wrapped = fieldValues[field.id];
                  const raw = unwrapFieldValue(wrapped);
                  return (
                    <FieldOverlay
                      key={field.id}
                      field={field}
                      rawValue={raw}
                      fillState={fillStateFor(field.id, wrapped, raw, currentFieldId)}
                      scale={scale}
                    />
                  );
                })}
              </div>
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
