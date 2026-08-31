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
 * Driven through the REAL SchemaForm -> PreviewPane -> PDFViewer -> FieldOverlay
 * chain, because the click IS the gesture under test -- the same mock set as
 * SchemaForm.previewEdit.test.tsx, plus a controllable isModelSpeaking().
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import React from 'react';
import { render, screen, cleanup, act, fireEvent } from '@testing-library/react';
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

async function mountInPreview() {
  render(<SchemaForm schema={makeSchema()} kitId="test" pdfUrl="/fake.pdf" />);
  await act(async () => {});
  fireEvent.click(screen.getByRole('tab', { name: 'Preview' }));
  await screen.findByTestId('pdf-field-overlay-f1');
}

describe('click-to-focus moves the search origin (bd a08po)', () => {
  beforeEach(() => {
    sessionStorage.clear();
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
  });

  it('with the model SILENT, clicking a field makes it the search origin', async () => {
    await mountInPreview();
    const user = userEvent.setup();

    await user.click(screen.getByTestId('pdf-field-overlay-f3'));

    expect(storedOrigin()).toBe('f3');
  });

  it('while the model is SPEAKING, a click does NOT move the search origin', async () => {
    await mountInPreview();
    const user = userEvent.setup();

    // Establish a known origin while silent...
    await user.click(screen.getByTestId('pdf-field-overlay-f1'));
    expect(storedOrigin()).toBe('f1');

    // ...then click elsewhere mid-utterance. The origin must not follow: the
    // model is mid-question about f1 and a spoken answer belongs to f1.
    modelSpeaking = true;
    await user.click(screen.getByTestId('pdf-field-overlay-f3'));

    expect(storedOrigin()).toBe('f1');
  });

  it('once the model stops speaking, clicks move the origin again', async () => {
    await mountInPreview();
    const user = userEvent.setup();

    modelSpeaking = true;
    await user.click(screen.getByTestId('pdf-field-overlay-f3'));
    expect(storedOrigin()).toBeNull();

    modelSpeaking = false;
    await user.click(screen.getByTestId('pdf-field-overlay-f3'));
    expect(storedOrigin()).toBe('f3');
  });

  it('TYPING moves the origin even while the model is speaking', async () => {
    // The asymmetry that makes the suppression safe: a click is ambiguous, but
    // nobody types into a field by accident. A user who starts typing has
    // declared which field they are on, mid-utterance or not.
    await mountInPreview();
    const user = userEvent.setup();

    await user.click(screen.getByTestId('pdf-field-overlay-f2'));
    modelSpeaking = true;
    await user.type(screen.getByTestId('pdf-field-edit-popover-f2').querySelector('input')!, 'X');

    expect(storedOrigin()).toBe('f2');
  });
});
