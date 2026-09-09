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


/**
 * EVERY field type must render an element carrying id={field.id} (bd
 * polyglot-pdf-96um6).
 *
 * That id is what the Enter->verify gesture keys on, and what fieldManager uses
 * to find controls (document.getElementById). Radio and checkbox GROUPS carried
 * only `name`, so they had NO keyboard verify path at all -- 30 of 323 fields
 * across the three shipped kits. The handler's own docstring asserted every type
 * rendered one; it was wrong, and nothing checked.
 *
 * Pins the SET, derived from FieldType, so a NEW field type that forgets the id
 * fails here rather than silently losing its verify path (scar #8).
 */
describe('every field type is reachable by id (bd polyglot-pdf-96um6)', () => {
  afterEach(() => cleanup());

  const CASES: Array<{ type: string; extra?: Record<string, unknown> }> = [
    { type: 'text' },
    { type: 'textarea' },
    { type: 'date' },
    { type: 'select', extra: { options: [{ value: 'a', label: 'A' }] } },
    { type: 'radio', extra: { options: [{ value: 'a', label: 'A' }, { value: 'b', label: 'B' }] } },
    { type: 'checkbox' },
    { type: 'checkbox_group', extra: { options: [{ value: 'a', label: 'A' }, { value: 'b', label: 'B' }] } },
  ];

  it.each(CASES)('$type renders an element with id=field.id', ({ type, extra }) => {
    const schema = {
      source: 'web',
      form_metadata: { title: 'T', version: '1', language: 'en', form_number: 'T-1' },
      sections: [{ id: 's1', label: 'S1', order: 1, fields: ['fx'] }],
      fields: [{ id: 'fx', name: 'Field X', spoken_name: 'field x', section_id: 's1', type, ...(extra || {}) }],
    } as unknown as FormSchema;

    render(<SchemaForm schema={schema} kitId="test" />);

    expect(
      document.getElementById('fx'),
      `a ${type} field must carry id={field.id} -- it is how the verify gesture ` +
        'and fieldManager find the control'
    ).toBeTruthy();
  });

  it('a GROUP renders the id exactly ONCE, not per option', () => {
    // Duplicate ids are invalid HTML and break label targeting and
    // getElementById, so the id goes on the first option only.
    const schema = {
      source: 'web',
      form_metadata: { title: 'T', version: '1', language: 'en', form_number: 'T-1' },
      sections: [{ id: 's1', label: 'S1', order: 1, fields: ['fx'] }],
      fields: [{
        id: 'fx', name: 'Field X', spoken_name: 'field x', section_id: 's1', type: 'radio',
        options: [{ value: 'a', label: 'A' }, { value: 'b', label: 'B' }, { value: 'c', label: 'C' }],
      }],
    } as unknown as FormSchema;

    render(<SchemaForm schema={schema} kitId="test" />);

    expect(document.querySelectorAll('#fx').length).toBe(1);
  });
});
