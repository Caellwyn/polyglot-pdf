/**
 * Clicking into a field moves the next-field search origin -- but NOT while the
 * model is speaking (bd polyglot-pdf-a08po).
 *
 * Why the suppression matters: under DTI the model holds ONE field's schema at
 * a time and the backend coercion pointer (_current_field_id) is singular. If a
 * click retargeted focus mid-question, the model would be asking about field A
 * while the client's focus said field B, and the spoken answer would land on the
 * wrong field. Typing is unambiguous intent so it always moves the origin;
 * clicking is not (fidgeting during playback is common), so it waits.
 *
 * Driven through the REAL SchemaForm and its REAL field components, so the
 * gesture under test is a genuine DOM focus/typing event rather than a direct
 * handler call. Same mock set as SchemaForm.previewEdit.test.tsx, plus a
 * controllable isModelSpeaking().
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import React from 'react';
import { render, screen, cleanup, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { FormSchema } from '../types/schema';

// Flipped per-test to simulate the model talking over the user's click.
let modelSpeaking = false;

vi.mock('../../shared/config', () => ({
  isTestHarnessEnabled: () => true,
}));
vi.mock('../../shared/connection', () => ({
  createConnectionManager: vi.fn(() => ({
    connect: vi.fn(),
    disconnect: vi.fn(),
    getAudioManager: () => ({
      isModelSpeaking: () => modelSpeaking,
    }),
  })),
}));
vi.mock('../../shared/audioConstraints', () => ({
  MIC_AUDIO_CONSTRAINTS: {},
}));
vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => ({ user: null }),
}));
vi.mock('../../demo/VoiceOverlay', () => ({
  VoiceOverlay: () => <div data-testid="voice-overlay">overlay</div>,
}));
vi.mock('../../demo/VoiceOverlayMobile', () => ({
  VoiceOverlayMobile: () => <div data-testid="voice-overlay-mobile">overlay-mobile</div>,
}));
vi.mock('../../pdf-view/FilledPreviewModal', () => ({
  default: () => <div data-testid="filled-preview-modal">modal</div>,
}));
vi.mock('../../pdf-view/usePDFDocument', () => ({
  usePDFDocument: () => ({
    document: {} as any,
    numPages: 1,
    isLoading: false,
    error: null,
  }),
}));
vi.mock('../../pdf-view/PDFPage', () => ({
  PDFPage: () => <div data-testid="mock-pdf-page" />,
}));

import { SchemaForm } from './SchemaForm';

const rect = (y: number) => ({ page: 1, x: 100, y, width: 120, height: 14 });

function makeSchema(): FormSchema {
  return {
    source: 'pdf',
    form_metadata: { title: 'Test Form', version: '1.0', language: 'en', form_number: 'T-1' },
    sections: [{ id: 'sec1', label: 'Section One', order: 1, fields: ['f1', 'f2', 'f3'] }],
    fields: [
      { id: 'f1', name: 'First', spoken_name: 'first', section_id: 'sec1', type: 'text', pdf_position: rect(100) } as any,
      { id: 'f2', name: 'Second', spoken_name: 'second', section_id: 'sec1', type: 'text', pdf_position: rect(200) } as any,
      { id: 'f3', name: 'Third', spoken_name: 'third', section_id: 'sec1', type: 'text', pdf_position: rect(300) } as any,
    ],
  };
}

function storedOrigin(): string | null | undefined {
  const raw = sessionStorage.getItem('schema_form_state');
  return raw ? JSON.parse(raw).searchOriginFieldId : undefined;
}

/**
 * Mount the SIMPLIFIED view and return the real <input> for each field.
 *
 * Deliberately NOT the Preview/PDF view: that path goes through a React.lazy
 * chunk (PreviewPane -> PDFViewer -> FieldOverlay), and waiting on it made this
 * suite fail intermittently under full-suite load -- a pre-existing fragility in
 * that harness (SchemaForm.previewEdit.test.tsx shows the same flake), not
 * something this bead's behavior depends on. `SectionRenderer` is a direct
 * import, so the simplified view mounts synchronously.
 *
 * The behavior under test is identical on both surfaces: the same
 * `handleFieldFocus` is wired to SectionRenderer's `onFieldFocus` and to
 * PreviewPane's, and a native DOM focus is exactly what a real click produces.
 */
async function mountSimplified() {
  render(<SchemaForm schema={makeSchema()} kitId="test" pdfUrl="/fake.pdf" />);
  await act(async () => {});
  return {
    f1: screen.getByLabelText(/First/i) as HTMLInputElement,
    f2: screen.getByLabelText(/Second/i) as HTMLInputElement,
    f3: screen.getByLabelText(/Third/i) as HTMLInputElement,
  };
}

describe('click-to-focus moves the search origin (bd a08po)', () => {
  beforeEach(() => {
    // Install a REAL, freshly-backed sessionStorage for every test in this file.
    //
    // This is not belt-and-braces, it is required: sibling suites -- notably
    // schema-forms/state/schemaFormState.test.ts:28 -- ASSIGN `global.sessionStorage`
    // to their own vi.fn()-based mock and never restore it, and one of their
    // cases deliberately leaves a corrupt `'invalid json{'` value in it. When
    // vitest schedules those files into the same worker before this one, this
    // suite inherited that mock: SchemaForm's mount then failed to parse state,
    // the lazy PreviewPane never rendered, and the overlay lookup timed out --
    // intermittently, depending purely on file ordering.
    //
    // Clearing the ambient object is NOT enough (their `clear` is a spy over a
    // closure this file cannot reach), so replace the object outright. It is
    // re-installed per test rather than once, because a sibling can swap it back
    // in between tests.
    const store = new Map<string, string>();
    Object.defineProperty(global, 'sessionStorage', {
      configurable: true,
      value: {
        getItem: (k: string) => (store.has(k) ? store.get(k)! : null),
        setItem: (k: string, v: string) => { store.set(k, String(v)); },
        removeItem: (k: string) => { store.delete(k); },
        clear: () => store.clear(),
        key: (i: number) => Array.from(store.keys())[i] ?? null,
        get length() { return store.size; },
      },
    });
    modelSpeaking = false;
    Object.defineProperty(window, 'innerWidth', {
      configurable: true,
      writable: true,
      value: 1280,
    });
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
    // Reset the module-level speaking flag (it is NOT a vi mock, so
    // clearAllMocks does not touch it). Leaving it true would leak "the model
    // is talking" into whatever runs next in this worker.
    modelSpeaking = false;
    sessionStorage.clear();
  });

  it('with the model SILENT, clicking a field makes it the search origin', async () => {
    const f = await mountSimplified();
    const user = userEvent.setup();

    await user.click(f.f3);

    expect(storedOrigin()).toBe('f3');
  });

  it('while the model is SPEAKING, a click does NOT move the search origin', async () => {
    const f = await mountSimplified();
    const user = userEvent.setup();

    // Establish a known origin while silent...
    await user.click(f.f1);
    expect(storedOrigin()).toBe('f1');

    // ...then click elsewhere mid-utterance. The origin must not follow: the
    // model is mid-question about f1 and a spoken answer belongs to f1.
    modelSpeaking = true;
    await user.click(f.f3);

    expect(storedOrigin()).toBe('f1');
  });

  it('once the model stops speaking, clicks move the origin again', async () => {
    const f = await mountSimplified();
    const user = userEvent.setup();

    modelSpeaking = true;
    await user.click(f.f3);
    expect(storedOrigin()).toBeNull();

    // Click AWAY and back once the model is silent. Clicking f3 a second time
    // while it already holds DOM focus fires no new focus event -- that is real
    // browser behavior, not a harness quirk, so the test has to move focus off
    // and back to produce a genuine second gesture.
    modelSpeaking = false;
    await user.click(f.f1);
    await user.click(f.f3);
    expect(storedOrigin()).toBe('f3');
  });

  it('TYPING moves the origin even while the model is speaking', async () => {
    // The asymmetry that makes the suppression safe: a click is ambiguous, but
    // nobody types into a field by accident. A user who starts typing has
    // declared which field they are on, mid-utterance or not.
    const f = await mountSimplified();
    const user = userEvent.setup();

    modelSpeaking = true;
    await user.type(f.f2, 'X');

    expect(storedOrigin()).toBe('f2');
  });
});
