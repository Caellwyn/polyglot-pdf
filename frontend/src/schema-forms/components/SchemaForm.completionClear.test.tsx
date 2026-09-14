// @vitest-environment jsdom
//
// SchemaForm's completion-clear grace on download/print (bd polyglot-pdf-8v8i7).
//
// The bead originally wired the auto-clear to the voice session's
// "form complete" event, but fresh-eyes round 1 caught that this fires
// BEFORE the client has the PDF -- complete_link (the backend's own
// "the client is done" record) runs at socket TEARDOWN, not at that event,
// and the socket stays open. The only OBSERVABLE "the client is done" event
// on the frontend is a successful download or print of an ALREADY-COMPLETE
// form. This file pins the corrected trigger:
//   - starts the grace only for a CLIENT-LINK session (never staff)
//   - starts it only when isFormComplete(state) is true
//   - starts it only AFTER fillPDF + downloadPDF/printPDF succeed -- never
//     from the catch branch
//   - a second download/print during the grace does not restart the timer
//
// Mirrors SchemaForm.idleClear.test.tsx's mocking pattern.

import { render, screen, cleanup, act, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import type { FormSchema } from '../types/schema';

vi.mock('../../shared/config', () => ({
  isTestHarnessEnabled: () => true,
}));

vi.mock('../../shared/connection', () => ({
  createConnectionManager: vi.fn(() => ({ connect: vi.fn(), disconnect: vi.fn() })),
}));

vi.mock('../../shared/audioConstraints', () => ({
  MIC_AUDIO_CONSTRAINTS: {},
}));

vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => ({ user: null, logout: vi.fn() }),
}));

vi.mock('../../demo/VoiceOverlay', () => ({
  VoiceOverlay: () => <div data-testid="voice-overlay">overlay</div>,
}));
vi.mock('../../demo/VoiceOverlayMobile', () => ({
  VoiceOverlayMobile: () => <div data-testid="voice-overlay-mobile">overlay-mobile</div>,
}));
vi.mock('../../pdf-view/PreviewPane', () => ({
  default: () => <div data-testid="preview-pane">preview</div>,
}));
vi.mock('../../pdf-view/FilledPreviewModal', () => ({
  default: () => <div data-testid="filled-preview-modal">modal</div>,
}));

let mockFillPDFImpl: () => Promise<Uint8Array> = () => Promise.resolve(new Uint8Array([1, 2, 3]));
const mockDownloadPDF = vi.fn();
const mockPrintPDF = vi.fn();
vi.mock('../utils/pdfFiller', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../utils/pdfFiller')>();
  return {
    ...actual,
    fillPDF: vi.fn(() => mockFillPDFImpl()),
    downloadPDF: (...args: unknown[]) => mockDownloadPDF(...args),
    printPDF: (...args: unknown[]) => mockPrintPDF(...args),
  };
});

let mockHasClientLinkToken = false;
vi.mock('../../shared/sessionCredential', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../shared/sessionCredential')>();
  return {
    ...actual,
    hasClientLinkToken: () => mockHasClientLinkToken,
  };
});

import { SchemaForm } from './SchemaForm';

function makeSchema(complete: boolean): FormSchema {
  return {
    source: 'pdf',
    form_metadata: {
      title: 'Test Form',
      version: '1.0',
      language: 'en',
      form_number: 'TEST-1',
    },
    sections: [{ id: 'sec1', label: 'Section One', order: 1, fields: ['f1'] }],
    fields: [
      {
        id: 'f1',
        name: 'Field One',
        spoken_name: 'field one',
        section_id: 'sec1',
        type: 'text',
        // Pre-seed as confirmed via the initial value on the field def is not
        // how state works -- state is seeded through sessionStorage instead
        // (see beforeEach), so `complete` here only documents intent.
      } as any,
    ],
  };
}

function seedSessionState(schema: FormSchema, confirmed: boolean) {
  sessionStorage.setItem(
    'schema_form_state',
    JSON.stringify({
      schema,
      fieldValues: confirmed ? { f1: { value: 'answer', confirmed: true } } : {},
      currentSectionId: 'sec1',
      completedSections: [],
      validationErrors: {},
      formSessionId: 'fss_test',
      lastUpdated: Date.now(),
    })
  );
}

function setWidth(width: number) {
  Object.defineProperty(window, 'innerWidth', {
    configurable: true,
    writable: true,
    value: width,
  });
}

describe('SchemaForm completion-clear grace (bd polyglot-pdf-8v8i7)', () => {
  beforeEach(() => {
    sessionStorage.clear();
    setWidth(1280);
    mockHasClientLinkToken = false;
    mockFillPDFImpl = () => Promise.resolve(new Uint8Array([1, 2, 3]));
    mockDownloadPDF.mockClear();
    mockPrintPDF.mockClear();
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
    vi.useRealTimers();
  });

  it('starts the grace and clears storage after the countdown on a successful download of a COMPLETE client-link form', async () => {
    vi.useFakeTimers();
    // Stub reload -- production code reloads immediately after the wipe (bd
    // polyglot-pdf-8v8i7, fresh-eyes round 2); see the dedicated reload
    // tests below for that behavior itself.
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: { ...window.location, reload: vi.fn() },
    });
    try {
      mockHasClientLinkToken = true;
      const schema = makeSchema(true);
      seedSessionState(schema, true);

      render(<SchemaForm schema={schema} kitId="test" pdfUrl="https://example/form.pdf" />);
      await act(async () => {
        vi.runOnlyPendingTimers();
      });

      const downloadButton = screen.getByRole('button', { name: /download filled pdf/i });
      await act(async () => {
        fireEvent.click(downloadButton);
        await Promise.resolve();
        await Promise.resolve();
      });

      expect(mockDownloadPDF).toHaveBeenCalledTimes(1);
      // Banner appears immediately.
      expect(screen.getByRole('alert', { name: '' }) || screen.getByText(/form is finished/i)).toBeTruthy();
      expect(sessionStorage.getItem('schema_form_state')).not.toBeNull();

      act(() => {
        vi.advanceTimersByTime(60000);
      });

      expect(sessionStorage.getItem('schema_form_state')).toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });

  it('does NOT start the grace on a download of an INCOMPLETE client-link form', async () => {
    vi.useFakeTimers();
    try {
      mockHasClientLinkToken = true;
      const schema = makeSchema(false);
      seedSessionState(schema, false); // f1 unconfirmed -- form is incomplete

      render(<SchemaForm schema={schema} kitId="test" pdfUrl="https://example/form.pdf" />);
      await act(async () => {
        vi.runOnlyPendingTimers();
      });

      const downloadButton = screen.getByRole('button', { name: /download filled pdf/i });
      await act(async () => {
        fireEvent.click(downloadButton);
        await Promise.resolve();
        await Promise.resolve();
      });

      expect(mockDownloadPDF).toHaveBeenCalledTimes(1);
      expect(screen.queryByText(/form is finished/i)).toBeNull();

      act(() => {
        vi.advanceTimersByTime(60000);
      });

      expect(sessionStorage.getItem('schema_form_state')).not.toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });

  it('does NOT start the grace on a download of a COMPLETE STAFF (non-client-link) form', async () => {
    vi.useFakeTimers();
    try {
      mockHasClientLinkToken = false; // staff session
      const schema = makeSchema(true);
      seedSessionState(schema, true);

      render(<SchemaForm schema={schema} kitId="test" pdfUrl="https://example/form.pdf" />);
      await act(async () => {
        vi.runOnlyPendingTimers();
      });

      const downloadButton = screen.getByRole('button', { name: /download filled pdf/i });
      await act(async () => {
        fireEvent.click(downloadButton);
        await Promise.resolve();
        await Promise.resolve();
      });

      expect(mockDownloadPDF).toHaveBeenCalledTimes(1);
      expect(screen.queryByText(/form is finished/i)).toBeNull();

      act(() => {
        vi.advanceTimersByTime(60000);
      });

      expect(sessionStorage.getItem('schema_form_state')).not.toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });

  it('does NOT start the grace when fillPDF FAILS, even on a complete client-link form', async () => {
    vi.useFakeTimers();
    try {
      mockHasClientLinkToken = true;
      mockFillPDFImpl = () => Promise.reject(new Error('backend down'));
      const schema = makeSchema(true);
      seedSessionState(schema, true);

      const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => {});

      render(<SchemaForm schema={schema} kitId="test" pdfUrl="https://example/form.pdf" />);
      await act(async () => {
        vi.runOnlyPendingTimers();
      });

      const downloadButton = screen.getByRole('button', { name: /download filled pdf/i });
      await act(async () => {
        fireEvent.click(downloadButton);
        await Promise.resolve();
        await Promise.resolve();
        await Promise.resolve();
      });

      expect(mockDownloadPDF).not.toHaveBeenCalled();
      expect(screen.queryByText(/form is finished/i)).toBeNull();

      act(() => {
        vi.advanceTimersByTime(60000);
      });

      expect(sessionStorage.getItem('schema_form_state')).not.toBeNull();

      alertSpy.mockRestore();
    } finally {
      vi.useRealTimers();
    }
  });

  it('a second download during the grace does not restart the visible countdown', async () => {
    vi.useFakeTimers();
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: { ...window.location, reload: vi.fn() },
    });
    try {
      mockHasClientLinkToken = true;
      const schema = makeSchema(true);
      seedSessionState(schema, true);

      render(<SchemaForm schema={schema} kitId="test" pdfUrl="https://example/form.pdf" />);
      await act(async () => {
        vi.runOnlyPendingTimers();
      });

      const downloadButton = screen.getByRole('button', { name: /download filled pdf/i });
      await act(async () => {
        fireEvent.click(downloadButton);
        await Promise.resolve();
        await Promise.resolve();
      });

      // Advance partway -- the on-screen countdown should have ticked down
      // from 60.
      act(() => {
        vi.advanceTimersByTime(30000);
      });
      expect(screen.getByText(/30 seconds/i)).toBeTruthy();

      // A second download while the grace is already running must NOT reset
      // the countdown back to 60 -- this is the direct pin of "does not
      // restart it" (a mutation that drops the idempotency guard reintroduces
      // a SECOND timer alongside the first without resetting the visible
      // number back to 60, which is why this asserts the DISPLAYED value
      // rather than only the eventual clear).
      await act(async () => {
        fireEvent.click(downloadButton);
        await Promise.resolve();
        await Promise.resolve();
      });
      expect(screen.getByText(/30 seconds/i)).toBeTruthy();
      expect(screen.queryByText(/60 seconds/i)).toBeNull();

      // Only 30 more seconds (not a fresh 60) should be needed to clear.
      act(() => {
        vi.advanceTimersByTime(30000);
      });

      expect(sessionStorage.getItem('schema_form_state')).toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });

  it('the "Done -- clear now" button clears immediately and reloads, without waiting for the countdown', async () => {
    vi.useFakeTimers();
    const reloadFn = vi.fn();
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: { ...window.location, reload: reloadFn },
    });
    try {
      mockHasClientLinkToken = true;
      const schema = makeSchema(true);
      seedSessionState(schema, true);

      render(<SchemaForm schema={schema} kitId="test" pdfUrl="https://example/form.pdf" />);
      await act(async () => {
        vi.runOnlyPendingTimers();
      });

      const downloadButton = screen.getByRole('button', { name: /download filled pdf/i });
      await act(async () => {
        fireEvent.click(downloadButton);
        await Promise.resolve();
        await Promise.resolve();
      });

      const clearNowButton = screen.getByRole('button', { name: /clear now/i });
      act(() => {
        fireEvent.click(clearNowButton);
      });

      expect(sessionStorage.getItem('schema_form_state')).toBeNull();
      expect(reloadFn).toHaveBeenCalledTimes(1);
    } finally {
      vi.useRealTimers();
    }
  });

  // bd polyglot-pdf-8v8i7, fresh-eyes round 2: clearAllClientState() alone
  // does not stop this component from re-persisting a FRESH
  // schema_form_state on the very next field edit -- it stays mounted with
  // its stale in-memory `state`. The fix reloads the page immediately after
  // the wipe (mirroring the pre-existing "Start Fresh" button in
  // SchemaFormDemo.tsx, which reloads for the same reason).
  it('reloads the page immediately after the completion-clear countdown finishes, exactly once', async () => {
    vi.useFakeTimers();
    const reloadFn = vi.fn();
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: { ...window.location, reload: reloadFn },
    });
    try {
      mockHasClientLinkToken = true;
      const schema = makeSchema(true);
      seedSessionState(schema, true);

      render(<SchemaForm schema={schema} kitId="test" pdfUrl="https://example/form.pdf" />);
      await act(async () => {
        vi.runOnlyPendingTimers();
      });

      const downloadButton = screen.getByRole('button', { name: /download filled pdf/i });
      await act(async () => {
        fireEvent.click(downloadButton);
        await Promise.resolve();
        await Promise.resolve();
      });
      expect(reloadFn).not.toHaveBeenCalled();

      act(() => {
        vi.advanceTimersByTime(60000);
      });

      expect(sessionStorage.getItem('schema_form_state')).toBeNull();
      expect(reloadFn).toHaveBeenCalledTimes(1);
    } finally {
      vi.useRealTimers();
    }
  });

  // The resurrection bug, made observable: reload is stubbed to a no-op (as
  // every test here must be, since jsdom never actually navigates). The
  // correctness property to pin is ORDER -- the wipe must complete before
  // reload fires -- and a stub that only COUNTS calls cannot discriminate
  // that from reload-then-wipe, since both run synchronously in the same
  // callback either way (fresh-eyes round 4 caught an earlier version of
  // this test that did not actually discriminate the order). This version
  // has the reload stub CAPTURE sessionStorage's content at the moment it
  // fires: if reload ever ran before the wipe, the captured value would be
  // non-null.
  it('clears schema_form_state BEFORE reloading, not after', async () => {
    vi.useFakeTimers();
    let storedAtReloadTime: string | null = 'not-called';
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: {
        ...window.location,
        reload: () => {
          storedAtReloadTime = sessionStorage.getItem('schema_form_state');
        },
      },
    });
    try {
      mockHasClientLinkToken = true;
      const schema = makeSchema(true);
      seedSessionState(schema, true);

      render(<SchemaForm schema={schema} kitId="test" pdfUrl="https://example/form.pdf" />);
      await act(async () => {
        vi.runOnlyPendingTimers();
      });

      const downloadButton = screen.getByRole('button', { name: /download filled pdf/i });
      await act(async () => {
        fireEvent.click(downloadButton);
        await Promise.resolve();
        await Promise.resolve();
      });

      act(() => {
        vi.advanceTimersByTime(60000);
      });

      expect(storedAtReloadTime).toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });
});
