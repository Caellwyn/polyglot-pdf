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
// We ALSO capture the onNextField callback SchemaForm passes in (5th arg): the
// continuous-mode section-paging test drives it directly to simulate the voice
// model advancing its focus to a field in another section.
let capturedOnNextField: ((fieldId: string | null) => void) | null = null;
vi.mock('../../shared/connection', () => ({
  createConnectionManager: vi.fn(
    (
      _schema: unknown,
      _onStatus: unknown,
      _lang: unknown,
      _stream: unknown,
      onNextField: (fieldId: string | null) => void,
    ) => {
      capturedOnNextField = onNextField;
      return { connect: vi.fn(), disconnect: vi.fn() };
    },
  ),
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
import { SchemaFormStateManager } from '../state/schemaFormState';

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

// A two-section schema for the continuous-mode paging test: the voice model can
// advance focus from a field in sec1 to a field in sec2, and the simplified view
// must page to sec2.
function makeTwoSectionSchema(): FormSchema {
  return {
    source: 'pdf',
    form_metadata: {
      title: 'Two Section Form',
      version: '1.0',
      language: 'en',
      form_number: 'TEST-2',
    },
    sections: [
      { id: 'sec1', label: 'Section One', order: 1, fields: ['f1'] },
      { id: 'sec2', label: 'Section Two', order: 2, fields: ['f2'] },
    ],
    fields: [
      { id: 'f1', name: 'Field One', spoken_name: 'field one', section_id: 'sec1', type: 'text' } as any,
      { id: 'f2', name: 'Field Two', spoken_name: 'field two', section_id: 'sec2', type: 'text' } as any,
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



const VERIFY_SCHEMA = {
  source: 'web',
  form_metadata: { title: 'T', version: '1', language: 'en', form_number: 'T-1' },
  sections: [{ id: 's1', label: 'S1', order: 1, fields: ['f1', 'f2'] }],
  fields: [
    { id: 'f1', name: 'Family Name', spoken_name: 'family name', section_id: 's1', type: 'text' },
    { id: 'f2', name: 'Given Name', spoken_name: 'given name', section_id: 's1', type: 'text' },
  ],
} as unknown as FormSchema;

/**
 * The verify gesture end-to-end through the REAL form (bd polyglot-pdf-96um6,
 * exit criterion 2). Drives actual keystrokes on the actual input, because the
 * whole claim is that ENTER works -- calling the modal's props directly would
 * prove nothing about the wiring.
 */
describe('Enter opens the verify modal (bd polyglot-pdf-96um6)', () => {
  beforeEach(() => { sessionStorage.clear(); });
  afterEach(() => cleanup());

  function typeInto(fieldId: string, text: string) {
    const input = document.getElementById(fieldId) as HTMLInputElement;
    fireEvent.change(input, { target: { value: text } });
    return input;
  }

  it('ENTER on a FILLED field opens the modal', () => {
    render(<SchemaForm schema={VERIFY_SCHEMA} kitId="test" />);
    const input = typeInto('f1', 'Vasquez');

    fireEvent.keyDown(input, { key: 'Enter' });

    expect(screen.getByTestId('verify-field-modal')).toBeTruthy();
    expect(screen.getByTestId('verify-field-value').textContent).toBe('Vasquez');
  });

  it('ENTER on an EMPTY field does NOT open it -- there is nothing to verify', () => {
    // And Enter keeps its existing meaning there, which is the behaviour people
    // may rely on (it reaches <form onSubmit>).
    render(<SchemaForm schema={VERIFY_SCHEMA} kitId="test" />);
    const input = document.getElementById('f1') as HTMLInputElement;

    fireEvent.keyDown(input, { key: 'Enter' });

    expect(screen.queryByTestId('verify-field-modal')).toBeNull();
  });

  it('ENTER on a WHITESPACE-only field does not open it either', () => {
    render(<SchemaForm schema={VERIFY_SCHEMA} kitId="test" />);
    const input = typeInto('f1', '   ');

    fireEvent.keyDown(input, { key: 'Enter' });

    expect(screen.queryByTestId('verify-field-modal')).toBeNull();
  });

  it('the full gesture VERIFIES the field, and only that field', () => {
    render(<SchemaForm schema={VERIFY_SCHEMA} kitId="test" />);
    typeInto('f1', 'Vasquez');
    typeInto('f2', 'Maria');

    fireEvent.keyDown(document.getElementById('f1')!, { key: 'Enter' });
    fireEvent.keyDown(screen.getByTestId('verify-field-checkbox'), { key: 'Enter' });

    const stored = SchemaFormStateManager.load()!;
    expect((stored.fieldValues['f1'] as any).confirmed, 'f1 was verified').toBe(true);
    expect((stored.fieldValues['f1'] as any).confirmationMethod).toBe('manual_edit');
    expect(
      (stored.fieldValues['f2'] as any).confirmed,
      'the neighbour must NOT be swept up -- one deliberate act per field'
    ).not.toBe(true);
  });

  it('ESCAPE leaves the field unverified with the typed value intact', () => {
    render(<SchemaForm schema={VERIFY_SCHEMA} kitId="test" />);
    typeInto('f1', 'Vasquez');
    fireEvent.keyDown(document.getElementById('f1')!, { key: 'Enter' });

    fireEvent.keyDown(document, { key: 'Escape' });

    expect(screen.queryByTestId('verify-field-modal')).toBeNull();
    const stored = SchemaFormStateManager.load()!;
    expect((stored.fieldValues['f1'] as any).value, 'a mis-pressed Enter must not cost the typing').toBe('Vasquez');
    expect((stored.fieldValues['f1'] as any).confirmed).not.toBe(true);
  });

  it('the Enter that opens the modal is DEFAULT-PREVENTED', () => {
    // Enter in a field natively submits the form, which here advances the
    // section -- so the section could move out from under the dialog.
    //
    // Asserted on the EVENT, not on an onSubmit spy: jsdom does NOT implement
    // implicit form submission, so a spy never fires and the test would pass with
    // preventDefault deleted. I wrote that version first; the mutation caught it
    // (removing preventDefault left it green), which is exactly what mutation
    // testing is for. defaultPrevented is the real, observable contract.
    render(<SchemaForm schema={VERIFY_SCHEMA} kitId="test" />);
    typeInto('f1', 'Vasquez');

    const evt = new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true });
    act(() => {
      document.getElementById('f1')!.dispatchEvent(evt);
    });

    expect(screen.getByTestId('verify-field-modal')).toBeTruthy();
    expect(evt.defaultPrevented, 'the native submit must be suppressed').toBe(true);
  });
});
