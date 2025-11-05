import React from 'react';
import type { FormSchema, FormField } from '../types/schema';

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
  const [error, setError] = React.useState<string | null>(null);
  const [scale, setScale] = React.useState(1.0);

  // For now, show a placeholder until we can load PDF.js properly
  // In production, this will use PDF.js to render the PDF
  return (
    <div ref={containerRef} className="h-full relative bg-gray-100">
      <div className="absolute top-4 right-4 z-10 flex gap-2">
        <button
          className="btn-sm btn-secondary"
          onClick={() => setScale(s => Math.max(0.5, s - 0.1))}
        >
          −
        </button>
        <span className="btn-sm bg-white px-3 py-1 text-sm">
          {Math.round(scale * 100)}%
        </span>
        <button
          className="btn-sm btn-secondary"
          onClick={() => setScale(s => Math.min(2.0, s + 0.1))}
        >
          +
        </button>
      </div>

      <div className="h-full overflow-auto custom-scrollbar p-8">
        <div className="bg-white shadow-lg mx-auto" style={{ width: '8.5in' }}>
          {/* PDF Canvas will go here */}
          <div className="relative">
            <div className="p-8 text-center text-gray-500">
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
              <p className="text-lg font-medium mb-2">PDF Viewer</p>
              <p className="text-sm">Loading: {pdfPath.split('/').pop()}</p>
              <p className="text-xs text-gray-400 mt-4">
                PDF.js will render the document here with interactive field overlays
              </p>
              {error && (
                <p className="text-sm text-red-600 mt-4">Error: {error}</p>
              )}
            </div>

            {/* Field overlays (will be positioned absolutely over PDF) */}
            {schema.fields
              .filter(f => f.pdf_position)
              .map(field => {
                const pos = field.pdf_position!;
                const isSelected = field.id === selectedFieldId;

                return (
                  <div
                    key={field.id}
                    className={`field-highlight ${isSelected ? 'selected' : 'hover'}`}
                    style={{
                      position: 'absolute',
                      // These would be calculated based on PDF page dimensions
                      // For now, just show as example
                      top: `${pos.y || 0}px`,
                      left: `${pos.x || 0}px`,
                      width: `${pos.width || 100}px`,
                      height: `${pos.height || 20}px`,
                    }}
                    onClick={() => onSelectField(field.id)}
                    title={field.spoken_name || field.id}
                  />
                );
              })}
          </div>
        </div>
      </div>

      {/* Field count overlay */}
      <div className="absolute bottom-4 left-4 bg-white px-3 py-2 rounded shadow text-sm text-gray-600">
        {schema.fields.length} fields •{' '}
        {schema.fields.filter(f => f.pdf_position).length} with positions
      </div>
    </div>
  );
};
