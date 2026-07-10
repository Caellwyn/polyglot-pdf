/**
 * PdfPreviewFallback -- error-boundary fallback for the FilledPreviewModal
 * mount (bd polyglot-pdf-dr1l, deferred from bd polyglot-pdf-huer).
 *
 * It must be dismissible and labeled like the real modal (Escape key,
 * backdrop click, role="dialog"/aria-modal/aria-label) because it appears
 * exactly where the user expects the modal (FilledPreviewModal.tsx:97-115) --
 * a silent, undismissable notice in its place would trap the user behind an
 * overlay with no way out.
 *
 * Styles are INLINE and self-contained on purpose: the real modal's CSS
 * (pdf-view/pdf-view.css) is imported only by the lazy pdf-view chunk, so it
 * is exactly unavailable when this fallback needs to render (the chunk
 * failed to load). Relying on those classes here would show an unstyled
 * notice at the worst possible time.
 */

import React, { useEffect } from "react";

export interface PdfPreviewFallbackProps {
  onClose: () => void;
}

const backdropStyle: React.CSSProperties = {
  position: "fixed",
  inset: 0,
  zIndex: 10500,
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  background: "rgba(0, 0, 0, 0.6)",
};

const cardStyle: React.CSSProperties = {
  background: "#ffffff",
  color: "#1f2937",
  borderRadius: "8px",
  padding: "1.5rem",
  maxWidth: "28rem",
  width: "calc(100% - 2rem)",
  boxShadow: "0 10px 30px rgba(0, 0, 0, 0.3)",
  textAlign: "center",
};

const messageStyle: React.CSSProperties = {
  margin: "0 0 1rem 0",
  lineHeight: 1.5,
};

const buttonStyle: React.CSSProperties = {
  background: "#374151",
  color: "#ffffff",
  border: "none",
  borderRadius: "4px",
  padding: "0.5rem 1.25rem",
  fontSize: "1rem",
  cursor: "pointer",
};

export function PdfPreviewFallback({ onClose }: PdfPreviewFallbackProps): React.ReactElement {
  // Escape closes the fallback, matching the real modal (FilledPreviewModal.tsx:98-104).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      className="pdf-preview-modal__backdrop"
      style={backdropStyle}
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label="Filled PDF preview"
    >
      <div
        className="pdf-preview-modal"
        style={cardStyle}
        onClick={(e) => e.stopPropagation()}
      >
        <p style={messageStyle}>
          The PDF preview could not be loaded. Check your connection and reload the page to
          try again.
        </p>
        <button type="button" style={buttonStyle} onClick={onClose}>
          Close
        </button>
      </div>
    </div>
  );
}
