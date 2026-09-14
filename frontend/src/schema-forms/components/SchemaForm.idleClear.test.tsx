// @vitest-environment jsdom
//
// SchemaForm's idle-timeout auto-clear (bd polyglot-pdf-8v8i7).
//
// `status` becomes 'idle_timeout' when WebFormConnection's onStatusChange
// callback fires with that value (already the case before this bead --
// see webFormConnection.ts's handleMessage). This pins the NEW behavior
// layered on that existing signal: an on-screen warning appears immediately,
// and SchemaFormStateManager.clearAllClientState() runs a few seconds later
// so the warning is actually readable before the wipe.
//
// Mirrors SchemaForm.test.tsx's mocking pattern: the connection manager is a
// stub whose onStatusChange callback (2nd arg) is captured so the test can
// drive `status` directly, without a real WebSocket.

import { render, screen, cleanup, act } from '@testing-library/react';
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

import { SchemaForm } from './SchemaForm';
import { SchemaFormStateManager } from '../state/schemaFormState';

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

describe('SchemaForm idle-timeout auto-clear (bd polyglot-pdf-8v8i7)', () => {
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

  it('shows an on-screen warning immediately, then clears client state a few seconds later', async () => {
    vi.useFakeTimers();
    try {
      render(<SchemaForm schema={makeSchema()} kitId="test" />);
      await act(async () => {
        vi.runOnlyPendingTimers();
      });

      expect(capturedOnStatus).toBeTruthy();
      // SchemaForm's own mount-time init() has already written real form
      // state under this key -- that IS the state the idle-clear wipes.
      expect(sessionStorage.getItem('schema_form_state')).not.toBeNull();

      act(() => {
        capturedOnStatus!('idle_timeout');
      });

      // Warning appears immediately -- before the clear delay elapses.
      expect(screen.getByRole('alert').textContent).toMatch(/timed out/i);
      expect(sessionStorage.getItem('schema_form_state')).not.toBeNull();

      // Advance past the clear delay.
      act(() => {
        vi.advanceTimersByTime(5000);
      });

      expect(sessionStorage.getItem('schema_form_state')).toBeNull();
      expect(screen.queryByRole('alert')).toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });

  it('tells a CLIENT-LINK session that reopening their link resumes the form (bd polyglot-pdf-8v8i7)', async () => {
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

  it('does NOT mention reopening a link for a STAFF session', async () => {
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

      expect(screen.getByRole('alert').textContent).not.toMatch(/reopen/i);
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
        vi.advanceTimersByTime(10000);
      });

      expect(screen.queryByRole('alert')).toBeNull();
      expect(sessionStorage.getItem('schema_form_state')).not.toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });
});
