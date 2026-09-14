// @vitest-environment jsdom
//
// SchemaForm's idle-WIPE GRACE (bd polyglot-pdf-8v8i7, Opus cross-surface
// round 5).
//
// `status === 'idle_timeout'` is the BACKEND's 120-second no-inbound-traffic
// WebSocket watchdog (backend/config.py's WS_IDLE_TIMEOUT_SEC) -- it means
// the socket went quiet, NOT "the client walked away". Two untouched
// consumers react to the exact same status: VoiceOverlay/VoiceOverlayMobile
// render a Reconnect button off it, and VoiceOverlay's useSaveNudge treats it
// as `voiceEnding` and pops a Save modal with a spoken notice. A short
// unconditional wipe (the earlier, now-replaced design) would destroy the
// client's only copy of their answers while the app is actively telling them
// to save it.
//
// So this pins the CORRECTED design: a long (IDLE_WIPE_GRACE_MS), ACTIVITY-
// CANCELLABLE grace. Cancelled by any document-level pointerdown/keydown/
// touchstart, the "Keep my answers" button, `status` leaving 'idle_timeout',
// or a save (the `polyglot:save-form` event). Re-arms if `status` returns to
// 'idle_timeout' again.
//
// Mirrors SchemaForm.test.tsx's mocking pattern: the connection manager is a
// stub whose onStatusChange callback (2nd arg) is captured so the test can
// drive `status` directly, without a real WebSocket.

import { render, screen, cleanup, act, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import type { FormSchema } from '../types/schema';

vi.mock('../../shared/config', () => ({
  isTestHarnessEnabled: () => true,
}));

let capturedOnStatus: ((status: string) => void) | null = null;
vi.mock('../../shared/connection', () => ({
  createConnectionManager: vi.fn((_schema: unknown, onStatus: (status: string) => void) => {
    capturedOnStatus = onStatus;
    return { connect: vi.fn(), disconnect: vi.fn() };
  }),
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

let mockHasClientLinkToken = false;
vi.mock('../../shared/sessionCredential', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../shared/sessionCredential')>();
  return {
    ...actual,
    hasClientLinkToken: () => mockHasClientLinkToken,
  };
});

import { SchemaForm, IDLE_WIPE_GRACE_MS } from './SchemaForm';

function makeSchema(): FormSchema {
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
      { id: 'f1', name: 'Field One', spoken_name: 'field one', section_id: 'sec1', type: 'text' } as any,
    ],
  };
}

function setWidth(width: number) {
  Object.defineProperty(window, 'innerWidth', {
    configurable: true,
    writable: true,
    value: width,
  });
}

function stubReload() {
  const reloadFn = vi.fn();
  Object.defineProperty(window, 'location', {
    configurable: true,
    value: { ...window.location, reload: reloadFn },
  });
  return reloadFn;
}

describe('SchemaForm idle-wipe grace (bd polyglot-pdf-8v8i7)', () => {
  beforeEach(() => {
    sessionStorage.clear();
    setWidth(1280);
    capturedOnStatus = null;
    mockHasClientLinkToken = false;
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
    vi.useRealTimers();
  });

  it('shows the banner immediately on idle_timeout, with the full grace remaining', async () => {
    vi.useFakeTimers();
    stubReload();
    try {
      render(<SchemaForm schema={makeSchema()} kitId="test" />);
      await act(async () => {
        vi.runOnlyPendingTimers();
      });

      expect(capturedOnStatus).toBeTruthy();
      expect(sessionStorage.getItem('schema_form_state')).not.toBeNull();

      act(() => {
        capturedOnStatus!('idle_timeout');
      });

      const alertText = screen.getByRole('alert').textContent ?? '';
      expect(alertText).toMatch(/inactive/i);
      expect(alertText).toMatch(/10:00/); // full IDLE_WIPE_GRACE_MS, formatted
      expect(sessionStorage.getItem('schema_form_state')).not.toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });

  it('clears client state and reloads exactly once after the FULL grace elapses with no activity', async () => {
    vi.useFakeTimers();
    const reloadFn = stubReload();
    try {
      render(<SchemaForm schema={makeSchema()} kitId="test" />);
      await act(async () => {
        vi.runOnlyPendingTimers();
      });

      act(() => {
        capturedOnStatus!('idle_timeout');
      });
      expect(reloadFn).not.toHaveBeenCalled();

      act(() => {
        vi.advanceTimersByTime(IDLE_WIPE_GRACE_MS);
      });

      expect(sessionStorage.getItem('schema_form_state')).toBeNull();
      expect(reloadFn).toHaveBeenCalledTimes(1);
    } finally {
      vi.useRealTimers();
    }
  });

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
      render(<SchemaForm schema={makeSchema()} kitId="test" />);
      await act(async () => {
        vi.runOnlyPendingTimers();
      });

      act(() => {
        capturedOnStatus!('idle_timeout');
      });
      act(() => {
        vi.advanceTimersByTime(IDLE_WIPE_GRACE_MS);
      });

      expect(storedAtReloadTime).toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });

  it('a keydown one second before the grace ends CANCELS the wipe', async () => {
    vi.useFakeTimers();
    const reloadFn = stubReload();
    try {
      render(<SchemaForm schema={makeSchema()} kitId="test" />);
      await act(async () => {
        vi.runOnlyPendingTimers();
      });

      act(() => {
        capturedOnStatus!('idle_timeout');
      });

      // Advance to 1 second before the grace would elapse (9:59 of a 10:00
      // grace), then simulate a keydown anywhere in the document.
      act(() => {
        vi.advanceTimersByTime(IDLE_WIPE_GRACE_MS - 1000);
      });
      act(() => {
        document.dispatchEvent(new KeyboardEvent('keydown', { bubbles: true }));
      });

      // Advance well past when the ORIGINAL grace would have elapsed.
      act(() => {
        vi.advanceTimersByTime(IDLE_WIPE_GRACE_MS);
      });

      expect(sessionStorage.getItem('schema_form_state')).not.toBeNull();
      expect(reloadFn).not.toHaveBeenCalled();
      expect(screen.queryByRole('alert')).toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });

  it('a pointerdown cancels the wipe (not just keydown)', async () => {
    vi.useFakeTimers();
    const reloadFn = stubReload();
    try {
      render(<SchemaForm schema={makeSchema()} kitId="test" />);
      await act(async () => {
        vi.runOnlyPendingTimers();
      });

      act(() => {
        capturedOnStatus!('idle_timeout');
      });
      act(() => {
        document.dispatchEvent(new Event('pointerdown', { bubbles: true }));
      });
      act(() => {
        vi.advanceTimersByTime(IDLE_WIPE_GRACE_MS);
      });

      expect(sessionStorage.getItem('schema_form_state')).not.toBeNull();
      expect(reloadFn).not.toHaveBeenCalled();
    } finally {
      vi.useRealTimers();
    }
  });

  it('status leaving idle_timeout (e.g. a successful Reconnect) cancels the wipe', async () => {
    vi.useFakeTimers();
    const reloadFn = stubReload();
    try {
      render(<SchemaForm schema={makeSchema()} kitId="test" />);
      await act(async () => {
        vi.runOnlyPendingTimers();
      });

      act(() => {
        capturedOnStatus!('idle_timeout');
      });
      act(() => {
        capturedOnStatus!('connected');
      });
      act(() => {
        vi.advanceTimersByTime(IDLE_WIPE_GRACE_MS);
      });

      expect(sessionStorage.getItem('schema_form_state')).not.toBeNull();
      expect(reloadFn).not.toHaveBeenCalled();
      expect(screen.queryByRole('alert')).toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });

  it('the "Keep my answers" button cancels the wipe', async () => {
    vi.useFakeTimers();
    const reloadFn = stubReload();
    try {
      render(<SchemaForm schema={makeSchema()} kitId="test" />);
      await act(async () => {
        vi.runOnlyPendingTimers();
      });

      act(() => {
        capturedOnStatus!('idle_timeout');
      });

      const keepButton = screen.getByRole('button', { name: /keep my answers/i });
      act(() => {
        fireEvent.click(keepButton);
      });

      expect(screen.queryByRole('alert')).toBeNull();

      act(() => {
        vi.advanceTimersByTime(IDLE_WIPE_GRACE_MS);
      });

      expect(sessionStorage.getItem('schema_form_state')).not.toBeNull();
      expect(reloadFn).not.toHaveBeenCalled();
    } finally {
      vi.useRealTimers();
    }
  });

  it('a save (the polyglot:save-form event) cancels the wipe', async () => {
    vi.useFakeTimers();
    const reloadFn = stubReload();
    try {
      render(<SchemaForm schema={makeSchema()} kitId="test" />);
      await act(async () => {
        vi.runOnlyPendingTimers();
      });

      act(() => {
        capturedOnStatus!('idle_timeout');
      });
      act(() => {
        window.dispatchEvent(new CustomEvent('polyglot:save-form'));
      });
      act(() => {
        vi.advanceTimersByTime(IDLE_WIPE_GRACE_MS);
      });

      expect(sessionStorage.getItem('schema_form_state')).not.toBeNull();
      expect(reloadFn).not.toHaveBeenCalled();
      expect(screen.queryByRole('alert')).toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });

  it('RE-ARMS from the full duration on a second idle_timeout', async () => {
    vi.useFakeTimers();
    const reloadFn = stubReload();
    try {
      render(<SchemaForm schema={makeSchema()} kitId="test" />);
      await act(async () => {
        vi.runOnlyPendingTimers();
      });

      // First idle drop, cancelled by a reconnect.
      act(() => {
        capturedOnStatus!('idle_timeout');
      });
      act(() => {
        vi.advanceTimersByTime(IDLE_WIPE_GRACE_MS - 1000);
      });
      act(() => {
        capturedOnStatus!('connected');
      });
      expect(screen.queryByRole('alert')).toBeNull();

      // Second idle drop -- must start from the FULL grace, not the 1 second
      // that was left when it was cancelled.
      act(() => {
        capturedOnStatus!('idle_timeout');
      });
      expect(screen.getByRole('alert').textContent).toMatch(/10:00/);

      act(() => {
        vi.advanceTimersByTime(IDLE_WIPE_GRACE_MS - 1000);
      });
      // Not yet elapsed on the SECOND arming.
      expect(sessionStorage.getItem('schema_form_state')).not.toBeNull();
      expect(reloadFn).not.toHaveBeenCalled();

      act(() => {
        vi.advanceTimersByTime(1000);
      });
      expect(sessionStorage.getItem('schema_form_state')).toBeNull();
      expect(reloadFn).toHaveBeenCalledTimes(1);
    } finally {
      vi.useRealTimers();
    }
  });

  it('tells a CLIENT-LINK session to reopen their link afterward to resume an unfinished form', async () => {
    vi.useFakeTimers();
    try {
      mockHasClientLinkToken = true;
      render(<SchemaForm schema={makeSchema()} kitId="test" />);
      await act(async () => {
        vi.runOnlyPendingTimers();
      });

      act(() => {
        capturedOnStatus!('idle_timeout');
      });

      expect(screen.getByRole('alert').textContent).toMatch(/reopen your original link/i);
    } finally {
      vi.useRealTimers();
    }
  });

  it('does NOT mention reopening a link for a STAFF session (same banner and grace apply though)', async () => {
    vi.useFakeTimers();
    try {
      mockHasClientLinkToken = false;
      render(<SchemaForm schema={makeSchema()} kitId="test" />);
      await act(async () => {
        vi.runOnlyPendingTimers();
      });

      act(() => {
        capturedOnStatus!('idle_timeout');
      });

      const alertText = screen.getByRole('alert').textContent ?? '';
      expect(alertText).not.toMatch(/reopen/i);
      expect(alertText).toMatch(/inactive/i);
    } finally {
      vi.useRealTimers();
    }
  });

  it('does not show the warning or clear state for a normal "connected" status', async () => {
    vi.useFakeTimers();
    try {
      render(<SchemaForm schema={makeSchema()} kitId="test" />);
      await act(async () => {
        vi.runOnlyPendingTimers();
      });

      act(() => {
        capturedOnStatus!('connected');
      });
      act(() => {
        vi.advanceTimersByTime(IDLE_WIPE_GRACE_MS);
      });

      expect(screen.queryByRole('alert')).toBeNull();
      expect(sessionStorage.getItem('schema_form_state')).not.toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });
});
