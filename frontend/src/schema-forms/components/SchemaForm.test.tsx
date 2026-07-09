// @vitest-environment jsdom
//
// SchemaForm structural invariants (bd polyglot-pdf-fdz8).
//
// This pins the JSX invariant that the voice overlay (VoiceOverlay /
// VoiceOverlayMobile) and its ConnectionManager live OUTSIDE the switched
// view container -- they are siblings of the Simplified/Preview ternary, not
// children of either branch. If a future refactor nested the overlay inside
// the `viewMode === 'preview' ? <PreviewPane/> : <form/>` ternary, toggling
// the view would UNMOUNT and remount the overlay, which restarts the Gemini
// session (the overlay's mount-time connect). No existing test caught that:
// the whole suite would stay green while the session silently reset on every
// toggle. The identity assertion below is the one that goes red.
//
// The heavy children (both overlays, the lazy PreviewPane/FilledPreviewModal,
// auth, the connection manager, the mic stream) are mocked to stubs so the
// test exercises only SchemaForm's own render structure.

import { render, screen, fireEvent, cleanup, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import type { FormSchema } from '../types/schema';

// --- Mocks for SchemaForm's heavy dependencies -----------------------------

// The preview-UI flag: default ON for these tests (the toggle + Preview branch
// only exist flag-on). Overridable per-test via the mocked fn.
const isPreviewUiEnabled = vi.fn(() => true);
vi.mock('../../pdf-view/featureFlag', () => ({
  isPreviewUiEnabled: () => isPreviewUiEnabled(),
}));

// Report the test-harness path ON so SchemaForm SKIPS its mount-time
// getUserMedia (jsdom has no navigator.mediaDevices) and marks the stream ready
// immediately -- the connection manager then gets created and the overlay
// renders, with no mic touched. (This flag ONLY gates the mic-skip in
// SchemaForm; it does not change the view-mode structure under test.)
vi.mock('../../shared/config', () => ({
  isTestHarnessEnabled: () => true,
}));

// A no-op connection manager so SchemaForm's stream-ready effect can create one
// and render the overlay. Only the methods SchemaForm calls need to exist.
vi.mock('../../shared/connection', () => ({
  createConnectionManager: vi.fn(() => ({
    connect: vi.fn(),
    disconnect: vi.fn(),
  })),
}));

vi.mock('../../shared/audioConstraints', () => ({
  MIC_AUDIO_CONSTRAINTS: {},
}));

// Auth: a logged-out user is fine (getToken path is never exercised by the stub
// connection manager).
vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => ({ user: null }),
}));

// The overlays -- stub each to a single identifiable node. The desktop overlay
// carries a data-testid we can grab and compare across a toggle.
vi.mock('../../demo/VoiceOverlay', () => ({
  VoiceOverlay: () => <div data-testid="voice-overlay">overlay</div>,
}));
vi.mock('../../demo/VoiceOverlayMobile', () => ({
  VoiceOverlayMobile: () => <div data-testid="voice-overlay-mobile">overlay-mobile</div>,
}));

// The lazy Preview surfaces -- stub so the Preview branch renders synchronously
// (no pdfjs, no Suspense fallback churn).
vi.mock('../../pdf-view/PreviewPane', () => ({
  default: () => <div data-testid="preview-pane">preview</div>,
}));
vi.mock('../../pdf-view/FilledPreviewModal', () => ({
  default: () => <div data-testid="filled-preview-modal">modal</div>,
}));

import { SchemaForm } from './SchemaForm';

// --- A minimal valid schema ------------------------------------------------

function makeSchema(): FormSchema {
  return {
    source: 'pdf',
    form_metadata: {
      title: 'Test Form',
      version: '1.0',
      language: 'en',
      form_number: 'TEST-1',
    },
    sections: [
      { id: 'sec1', label: 'Section One', order: 1, fields: ['f1'] },
    ],
    fields: [
      {
        id: 'f1',
        name: 'Field One',
        spoken_name: 'field one',
        section_id: 'sec1',
        type: 'text',
      } as any,
    ],
  };
}

// SchemaForm reads window.innerWidth at mount (initialViewMode) and on resize.
// Force a stable DESKTOP width so mounts start Simplified only because nothing
// is stored (not because of a mobile-width override), and so the overlay picks
// the desktop VoiceOverlay stub.
function setWidth(width: number) {
  Object.defineProperty(window, 'innerWidth', {
    configurable: true,
    writable: true,
    value: width,
  });
}

describe('SchemaForm view-mode structure (bd polyglot-pdf-fdz8)', () => {
  beforeEach(() => {
    sessionStorage.clear();
    isPreviewUiEnabled.mockReturnValue(true);
    setWidth(1280);
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it('renders the Simplified/Preview toggle only when the preview flag is ON', async () => {
    // Flag OFF: no toggle.
    isPreviewUiEnabled.mockReturnValue(false);
    const { unmount } = render(<SchemaForm schema={makeSchema()} kitId="test" />);
    // Let the stream-ready + connection-manager effects settle.
    await act(async () => {});
    expect(screen.queryByRole('tablist', { name: 'Form view' })).toBeNull();
    unmount();
    cleanup();

    // Flag ON: the toggle renders with both tabs.
    isPreviewUiEnabled.mockReturnValue(true);
    render(<SchemaForm schema={makeSchema()} kitId="test" />);
    await act(async () => {});
    expect(screen.getByRole('tablist', { name: 'Form view' })).toBeTruthy();
    expect(screen.getByRole('tab', { name: 'Simplified' })).toBeTruthy();
    expect(screen.getByRole('tab', { name: 'Preview' })).toBeTruthy();
  });

  it('keeps the voice overlay mounted (same DOM node) across a Simplified->Preview toggle', async () => {
    render(<SchemaForm schema={makeSchema()} kitId="test" />);
    // The connection manager is created only once the (mocked) stream is ready;
    // flush the effects so the overlay renders.
    await act(async () => {});

    // Fresh mount at desktop width with nothing stored -> Simplified, and the
    // overlay is present as a sibling of the form container.
    expect(screen.getByText('Test Form')).toBeTruthy(); // the Simplified <form> header
    const overlayBefore = screen.getByTestId('voice-overlay');
    expect(overlayBefore).toBeTruthy();

    // Toggle to Preview.
    await act(async () => {
      fireEvent.click(screen.getByRole('tab', { name: 'Preview' }));
    });

    // The Preview branch is now showing (Simplified form header gone, preview
    // pane present) -- proving the switched container actually flipped.
    expect(screen.queryByText('Test Form')).toBeNull();
    expect(screen.getByTestId('preview-pane')).toBeTruthy();

    // THE INVARIANT: the overlay node survived the switch as the SAME element.
    // If the overlay were nested inside the view-switch ternary, flipping the
    // branch would remount it and this identity check would fail (a new node).
    const overlayAfter = screen.getByTestId('voice-overlay');
    expect(overlayAfter).toBe(overlayBefore);
  });

  it('resets Preview to Simplified when a live same-tab resize crosses into mobile width (bd polyglot-pdf-ipin)', async () => {
    vi.useFakeTimers();
    try {
      render(<SchemaForm schema={makeSchema()} kitId="test" />);
      // Flush the mount effects (stream-ready, connection manager, overlay).
      await act(async () => {
        vi.runOnlyPendingTimers();
      });

      // Switch to Preview at desktop width.
      act(() => {
        fireEvent.click(screen.getByRole('tab', { name: 'Preview' }));
      });
      expect(screen.getByTestId('preview-pane')).toBeTruthy();
      expect(screen.queryByText('Test Form')).toBeNull();

      // Shrink the SAME tab into mobile width and fire the resize the app
      // listens for (the P1.1 resize-testing technique: defineProperty on
      // innerWidth + dispatch a 'resize' Event). The handler is debounced 250ms.
      act(() => {
        setWidth(390);
        window.dispatchEvent(new Event('resize'));
        vi.advanceTimersByTime(300);
      });

      // The view fell back to Simplified: the form header is back and the
      // Preview pane is gone -- the mobile-defaults-Simplified intent now holds
      // for a live resize, not only a fresh mount.
      expect(screen.getByText('Test Form')).toBeTruthy();
      expect(screen.queryByTestId('preview-pane')).toBeNull();
      expect(screen.getByRole('tab', { name: 'Simplified' }).getAttribute('aria-selected')).toBe('true');
    } finally {
      vi.useRealTimers();
    }
  });
});
