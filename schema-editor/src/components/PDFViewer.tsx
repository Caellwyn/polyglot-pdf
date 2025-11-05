import React from 'react';
import type { FormSchema, FormField } from '../types/schema';
import { usePDFDocument } from '../hooks/usePDFDocument';
import { PDFPage } from './PDFPage';

interface PDFViewerProps {
  pdfPath: string;
  schema: FormSchema;
  selectedFieldId: string | null;
  onSelectField: (fieldId: string) => void;
}

export const PDFViewer: React.FC<PDFViewerProps> = ({
  pdfPath,
  schema,
  selectedFieldId,
  onSelectField,
}) => {
  const containerRef = React.useRef<HTMLDivElement>(null);
  const [scale, setScale] = React.useState(1.0);

  // Load PDF document
  const { document, numPages, isLoading, error } = usePDFDocument(pdfPath);

  // Zoom controls
  const handleZoomIn = () => setScale(s => Math.min(2.0, s + 0.25));
  const handleZoomOut = () => setScale(s => Math.max(0.5, s - 0.25));
  const handleFitWidth = () => {
    // Will implement in Phase 5
    setScale(1.0);
  };

  return (
    <div ref={containerRef} className="h-full flex flex-col bg-gray-100">
      {/* Toolbar */}
      <div className="bg-white border-b border-gray-200 px-4 py-2 flex items-center justify-between">
        <div className="flex items-center gap-2 text-sm text-gray-600">
          {numPages > 0 && (
            <span>
              {numPages} {numPages === 1 ? 'page' : 'pages'}
            </span>
          )}
          {schema.fields.filter(f => f.pdf_position).length > 0 && (
            <>
              <span>•</span>
              <span>
                {schema.fields.filter(f => f.pdf_position).length} fields with positions
              </span>
            </>
          )}
        </div>

        {/* Zoom controls */}
        <div className="flex items-center gap-2">
          <button
            className="btn-sm btn-secondary"
            onClick={handleZoomOut}
            disabled={scale <= 0.5}
            title="Zoom out"
          >
            −
          </button>
          <span className="btn-sm bg-white px-3 py-1 text-sm border border-gray-300">
            {Math.round(scale * 100)}%
          </span>
          <button
            className="btn-sm btn-secondary"
            onClick={handleZoomIn}
            disabled={scale >= 2.0}
            title="Zoom in"
          >
            +
          </button>
          <button
            className="btn-sm btn-secondary ml-2"
            onClick={handleFitWidth}
            title="Fit to width"
          >
            Fit Width
          </button>
        </div>
      </div>

      {/* PDF Content Area */}
      <div className="flex-1 overflow-auto custom-scrollbar">
        {isLoading && (
          <div className="h-full flex items-center justify-center">
            <div className="text-center">
              <div className="animate-spin w-12 h-12 border-4 border-primary-500 border-t-transparent rounded-full mx-auto mb-4" />
              <p className="text-gray-600">Loading PDF...</p>
              <p className="text-sm text-gray-500 mt-2">{pdfPath.split('/').pop()}</p>
            </div>
          </div>
        )}

        {error && (
          <div className="h-full flex items-center justify-center">
            <div className="text-center max-w-md">
              <svg
                className="w-16 h-16 text-red-500 mx-auto mb-4"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                />
              </svg>
              <h3 className="text-lg font-semibold text-gray-900 mb-2">Failed to Load PDF</h3>
              <p className="text-gray-600 mb-4">{error}</p>
              <p className="text-sm text-gray-500">{pdfPath}</p>
            </div>
          </div>
        )}

        {document && !isLoading && !error && (
          <div className="p-8">
            {/* Render first page only for Phase 1 */}
            <PDFPage
              document={document}
              pageNumber={1}
              scale={scale}
              className="mb-4"
            />
          </div>
        )}

        {!document && !isLoading && !error && (
          <div className="h-full flex items-center justify-center">
            <div className="text-center text-gray-400">
              <svg
                className="w-24 h-24 mx-auto mb-4 text-gray-300"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z"
                />
              </svg>
              <p className="text-lg">No PDF selected</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
