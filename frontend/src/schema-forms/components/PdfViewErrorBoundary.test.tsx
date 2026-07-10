/**
 * Unit tests for PdfViewErrorBoundary (bd polyglot-pdf-huer).
 *
 * Pins: (a) it is a pass-through when nothing throws; (b) it catches a
 * render-time throw and shows the fallback; (c) wrapped around a Suspense +
 * React.lazy() component whose import() rejects (the real-world failure mode
 * -- a lazy pdf-view chunk that fails to fetch), it still ends up showing the
 * fallback instead of crashing.
 */

import React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import { PdfViewErrorBoundary } from './PdfViewErrorBoundary';

describe('PdfViewErrorBoundary', () => {
  afterEach(() => cleanup());

  function Thrower(): React.ReactNode {
    throw new Error('boom');
  }

  it('renders children when nothing throws', () => {
    render(
      <PdfViewErrorBoundary fallback={<div>fallback</div>}>
        <div>all good</div>
      </PdfViewErrorBoundary>
    );

    expect(screen.getByText('all good')).toBeTruthy();
    expect(screen.queryByText('fallback')).toBeNull();
  });

  it('renders the fallback when a child throws during render', () => {
    // Silence the expected React error-boundary console noise (matches the
    // pattern in AuthContext.test.tsx).
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});

    render(
      <PdfViewErrorBoundary fallback={<div>fallback shown</div>}>
        <Thrower />
      </PdfViewErrorBoundary>
    );

    expect(screen.getByText('fallback shown')).toBeTruthy();
    expect(screen.queryByText('all good')).toBeNull();

    spy.mockRestore();
  });

  it('shows the fallback when a lazy component wrapped in Suspense fails to load', async () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});

    const FailingLazy = React.lazy(() =>
      Promise.reject(new Error('chunk fetch failed'))
    );

    render(
      <PdfViewErrorBoundary fallback={<div>preview unavailable</div>}>
        <React.Suspense fallback={<div>loading...</div>}>
          <FailingLazy />
        </React.Suspense>
      </PdfViewErrorBoundary>
    );

    expect(await screen.findByText('preview unavailable')).toBeTruthy();

    spy.mockRestore();
  });

  it('recovers on a fresh mount after a tripped instance is unmounted (reopen-reset)', () => {
    // The SchemaForm mounts sit inside conditionals (showPDFPreview / viewMode),
    // so closing the preview unmounts the boundary and reopening it mounts a
    // FRESH, untripped instance -- there is no explicit reset() path, recovery
    // is just React discarding the old instance's hasError state. A refactor
    // that shared ONE long-lived boundary instance across opens (e.g. hoisting
    // it above the conditional) would break this recovery, since hasError
    // would stay true forever after the first crash. This test pins the
    // mechanism (bd polyglot-pdf-dr1l).
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});

    const { unmount } = render(
      <PdfViewErrorBoundary fallback={<div>fallback shown</div>}>
        <Thrower />
      </PdfViewErrorBoundary>
    );
    expect(screen.getByText('fallback shown')).toBeTruthy();

    unmount();

    render(
      <PdfViewErrorBoundary fallback={<div>fallback shown</div>}>
        <div>all good</div>
      </PdfViewErrorBoundary>
    );
    expect(screen.getByText('all good')).toBeTruthy();
    expect(screen.queryByText('fallback shown')).toBeNull();

    spy.mockRestore();
  });
});
