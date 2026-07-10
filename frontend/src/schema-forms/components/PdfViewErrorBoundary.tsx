/**
 * PdfViewErrorBoundary -- catches render-time failures from the lazy pdf-view
 * chunks (pdfjs).
 *
 * The pdf-view chunk (PreviewPane, FilledPreviewModal) is loaded via
 * React.lazy() so the pdfjs-dist bundle only fetches when the user actually
 * opens a preview (epic js7q). If that fetch fails -- a network blip, or a
 * stale deploy hash after a redeploy invalidates the old chunk URL --
 * React.lazy's import() rejection is thrown during render, and with no error
 * boundary anywhere in the app that throw crashes the WHOLE SchemaForm render,
 * including the live voice-session UI (bd polyglot-pdf-huer). This boundary is
 * generic (not tied to a specific pdf-view surface) so future pdf-view mounts
 * can reuse it (epic js7q).
 *
 * Error boundaries must be class components -- there is no hook equivalent.
 */

import React from "react";

export interface PdfViewErrorBoundaryProps {
  children: React.ReactNode;
  fallback: React.ReactNode;
}

interface PdfViewErrorBoundaryState {
  hasError: boolean;
}

export class PdfViewErrorBoundary extends React.Component<
  PdfViewErrorBoundaryProps,
  PdfViewErrorBoundaryState
> {
  constructor(props: PdfViewErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(): PdfViewErrorBoundaryState {
    return { hasError: true };
  }

  componentDidCatch(error: unknown): void {
    console.error("[PdfViewErrorBoundary] pdf-view chunk failed to load or render:", error);
  }

  render(): React.ReactNode {
    if (this.state.hasError) {
      return this.props.fallback;
    }
    return this.props.children;
  }
}
