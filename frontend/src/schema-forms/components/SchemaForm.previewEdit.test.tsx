/**
 * Click-to-edit in Preview mode, end-to-end through the REAL SchemaForm ->
 * PreviewPane -> PDFViewer -> FieldOverlay -> FieldEditPopover chain (bd
 * polyglot-pdf-7esr, epic rubric R3): clicking a field overlay opens a
 * FieldRenderer-backed popover; a change lands in SchemaFormState with
 * UNVERIFIED (bd polyglot-pdf-uum5g: typing is not an assertion) and fans out
 * copy_to, also unverified;
 * Esc and click-outside dismiss.
 *
 * Only the pdfjs internals are mocked (usePDFDocument / PDFPage) plus
 * SchemaForm's heavy voice dependencies -- the same mock set as
 * SchemaForm.test.tsx, minus the PreviewPane stub (the real one is the
 * subject under test).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import React from 'react';
import { render, screen, cleanup, act, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { FormSchema } from '../types/schema';

vi.mock('../../shared/config', () => ({
  isTestHarnessEnabled: () => true,
}));
vi.mock('../../shared/connection', () => ({
  createConnectionManager: vi.fn(() => ({
    connect: vi.fn(),
    disconnect: vi.fn(),
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
// pdfjs internals only -- the rest of the pdf-view chain is REAL.
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
      {
        id: 'f1',
        name: 'Family Name',
        spoken_name: 'family name',
        section_id: 'sec1',
        type: 'text',
        pdf_position: rect(100),
        copy_to: ['f2'],
      } as any,
      {
        id: 'f2',
        name: 'Family Name (copy)',
        spoken_name: 'family name copy',
        section_id: 'sec1',
        type: 'text',
        pdf_position: rect(200),
      } as any,
      // REQUIRED and empty -- the only shape that offers a skip control
      // (bd polyglot-pdf-ykfx0).
      {
        id: 'f3',
        name: 'USCIS Number',
        spoken_name: 'USCIS number',
        section_id: 'sec1',
        type: 'text',
        validation: { required: true },
        pdf_position: rect(300),
      } as any,
    ],
  };
}

function storedFieldValues(): Record<string, any> {
  const raw = sessionStorage.getItem('schema_form_state');
  return raw ? JSON.parse(raw).fieldValues ?? {} : {};
}

async function mountInPreview() {
  render(<SchemaForm schema={makeSchema()} kitId="test" pdfUrl="/fake.pdf" />);
  await act(async () => {});
  fireEvent.click(screen.getByRole('tab', { name: 'Preview' }));
  // PreviewPane is React.lazy -- wait for the lazy chunk to resolve and the
  // real overlay chain to mount.
  await screen.findByTestId('pdf-field-overlay-f1');
}

describe('Preview click-to-edit (bd polyglot-pdf-7esr)', () => {
  beforeEach(() => {
    sessionStorage.clear();
    // Preview is NOT the landing view (bd polyglot-pdf-v437 kept Simplified
    // first), so mountInPreview() clicks the Preview tab to get there. Seeding
    // preview_view_mode here would be dead weight -- the click already lands in
    // Preview, so a seed could not fail and would only make this suite LOOK
    // like it covers stored-preference-honoring. That contract is pinned where
    // it belongs: SchemaForm.test.tsx's 'honors a stored preview choice at
    // desktop width' (component mount) and viewMode.test.ts (the pure helper).
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

  it('click overlay -> popover opens; a typed change lands UNVERIFIED and copy_to fans out; overlay repaints live', async () => {
    await mountInPreview();
    const user = userEvent.setup();

    await user.click(screen.getByTestId('pdf-field-overlay-f1'));
    const popover = screen.getByTestId('pdf-field-edit-popover-f1');
    expect(popover).toBeTruthy();

    // The popover hosts the SAME FieldRenderer input Simplified mode uses.
    const input = popover.querySelector('input') as HTMLInputElement;
    expect(input).toBeTruthy();
    await user.type(input, 'Ramanujan');

    // The PDF-view popover routes through SchemaForm's handleFieldChange -- the
    // SAME handler as the schema form -- which is exactly why this test is worth
    // keeping: it proves the two surfaces cannot drift apart on verification.
    const values = storedFieldValues();
    expect(values.f1.value).toBe('Ramanujan');
    expect(values.f1.confirmed, 'typing in the PDF view is not an assertion either').not.toBe(true);
    expect(values.f1.confirmationMethod).toBeUndefined();
    // copy_to fan-out: a copy the user never looked at is even less of an
    // assertion than the value they typed.
    expect(values.f2.value).toBe('Ramanujan');
    expect(values.f2.confirmed).not.toBe(true);
    expect(values.f2.confirmationMethod).toBeUndefined();

    // Live repaint: the f2 overlay now paints the copied value.
    expect(screen.getByTestId('pdf-field-overlay-f2').textContent).toBe('Ramanujan');
  });

  it('Esc dismisses the popover', async () => {
    await mountInPreview();
    const user = userEvent.setup();
    await user.click(screen.getByTestId('pdf-field-overlay-f1'));
    expect(screen.getByTestId('pdf-field-edit-popover-f1')).toBeTruthy();

    await user.keyboard('{Escape}');
    expect(screen.queryByTestId('pdf-field-edit-popover-f1')).toBeNull();
  });

  it('click-outside dismisses; the X button dismisses', async () => {
    await mountInPreview();
    const user = userEvent.setup();

    await user.click(screen.getByTestId('pdf-field-overlay-f1'));
    expect(screen.getByTestId('pdf-field-edit-popover-f1')).toBeTruthy();
    // Pointer-down outside the popover subtree (the pane background).
    fireEvent.pointerDown(document.body);
    expect(screen.queryByTestId('pdf-field-edit-popover-f1')).toBeNull();

    await user.click(screen.getByTestId('pdf-field-overlay-f1'));
    await user.click(screen.getByRole('button', { name: 'Close editor' }));
    expect(screen.queryByTestId('pdf-field-edit-popover-f1')).toBeNull();
  });

  it('clicking a different overlay moves the editor to that field', async () => {
    await mountInPreview();
    const user = userEvent.setup();

    await user.click(screen.getByTestId('pdf-field-overlay-f1'));
    expect(screen.getByTestId('pdf-field-edit-popover-f1')).toBeTruthy();

    await user.click(screen.getByTestId('pdf-field-overlay-f2'));
    expect(screen.queryByTestId('pdf-field-edit-popover-f1')).toBeNull();
    expect(screen.getByTestId('pdf-field-edit-popover-f2')).toBeTruthy();
  });
});

/**
 * THE SKIP CONTROL REACHES PREVIEW (bd polyglot-pdf-ykfx0).
 *
 * The form view has had a "Skip for now" button since bd polyglot-pdf-4dxt --
 * the sanctioned way to leave a required question deliberately unanswered
 * ("said aloud, or via the skip control", docs/components/schema-forms.md).
 * Preview shipped without one: SchemaForm rendered PreviewPane with
 * onFieldChange/onFieldBlur/onFieldFocus and no onFieldSkip, so a user working
 * on the PDF surface had no interface exit from a field they could not answer.
 *
 * These drive the WHOLE chain -- SchemaForm -> PreviewPane -> PDFViewer ->
 * FieldEditPopover -- because the defect was an ABSENT PROP at the top of it.
 * PreviewPane.skip.test.tsx pins the popover's own gating, but it renders
 * PreviewPane directly, so it is structurally blind to SchemaForm dropping the
 * prop -- which is exactly where the bug lived.
 */
describe('Preview mode skip control, end to end (bd polyglot-pdf-ykfx0)', () => {
  // Same setup as the sibling describe: a fresh session per test, and DESKTOP
  // width -- a mobile-width mount demotes a Preview choice, so without this the
  // suite would never reach the surface under test.
  beforeEach(() => {
    sessionStorage.clear();
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

  it('offers Skip for now on a required empty field and RECORDS the skip', async () => {
    await mountInPreview();
    const user = userEvent.setup();

    await user.click(screen.getByTestId('pdf-field-overlay-f3'));
    const skip = screen.getByRole('button', { name: /skip for now/i });

    await user.click(skip);

    // Assert the STATE, not merely that a handler fired: the point of the
    // affordance is that the field ends up resolved the same way the form
    // view's button resolves it (markFieldSkipped -> skipped: true).
    const stored = storedFieldValues();
    expect(
      stored.f3?.skipped,
      'the skip must land in SchemaFormState, not just call a callback',
    ).toBe(true);
  });

  it('does NOT offer it on a field that is not required', async () => {
    // f1 is optional, so there is nothing to skip -- matching SectionRenderer's
    // gate, so the same field never offers the control in one view and
    // withholds it in the other.
    await mountInPreview();
    const user = userEvent.setup();

    await user.click(screen.getByTestId('pdf-field-overlay-f1'));

    expect(screen.queryByRole('button', { name: /skip for now/i })).toBeNull();
  });

  it('stops offering it once the field is skipped', async () => {
    await mountInPreview();
    const user = userEvent.setup();

    await user.click(screen.getByTestId('pdf-field-overlay-f3'));
    await user.click(screen.getByRole('button', { name: /skip for now/i }));

    // Re-open the editor on the same field: it is resolved now.
    await user.click(screen.getByTestId('pdf-field-overlay-f3'));
    expect(screen.queryByRole('button', { name: /skip for now/i })).toBeNull();
    expect(screen.getByText(/needs follow-up/i)).toBeTruthy();
  });
});
