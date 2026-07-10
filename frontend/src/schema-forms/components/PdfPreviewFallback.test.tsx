/**
 * Unit tests for PdfPreviewFallback (bd polyglot-pdf-dr1l).
 *
 * Pins a11y/dismiss parity with the real FilledPreviewModal
 * (FilledPreviewModal.tsx:97-115): Escape closes it, backdrop click closes
 * it, clicking the inner card does NOT close it, and role/aria-modal/
 * aria-label match the real modal exactly.
 */

import React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { PdfPreviewFallback } from './PdfPreviewFallback';

describe('PdfPreviewFallback', () => {
  afterEach(() => cleanup());

  it('renders the notice with dialog a11y attributes matching the real modal', () => {
    render(<PdfPreviewFallback onClose={vi.fn()} />);

    expect(
      screen.getByText(
        'The PDF preview could not be loaded. Check your connection and reload the page to try again.'
      )
    ).toBeTruthy();

    const dialog = screen.getByRole('dialog');
    expect(dialog.getAttribute('aria-modal')).toBe('true');
    // Same aria-label as FilledPreviewModal.tsx so screen readers hear the
    // same dialog name whether the real modal or this fallback is showing.
    expect(dialog.getAttribute('aria-label')).toBe('Filled PDF preview');
  });

  it('calls onClose when the Close button is clicked', () => {
    const onClose = vi.fn();
    render(<PdfPreviewFallback onClose={onClose} />);

    fireEvent.click(screen.getByText('Close'));

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('calls onClose when Escape is pressed', () => {
    const onClose = vi.fn();
    render(<PdfPreviewFallback onClose={onClose} />);

    fireEvent.keyDown(window, { key: 'Escape' });

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('calls onClose when the backdrop is clicked', () => {
    const onClose = vi.fn();
    render(<PdfPreviewFallback onClose={onClose} />);

    fireEvent.click(screen.getByRole('dialog'));

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('does NOT call onClose when the inner card is clicked', () => {
    const onClose = vi.fn();
    render(<PdfPreviewFallback onClose={onClose} />);

    // The message text lives inside the inner card, not the backdrop.
    fireEvent.click(
      screen.getByText(
        'The PDF preview could not be loaded. Check your connection and reload the page to try again.'
      )
    );

    expect(onClose).not.toHaveBeenCalled();
  });
});
