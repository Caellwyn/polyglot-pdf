/**
 * The "Show field IDs" toolbar toggle (bd polyglot-pdf-w70y).
 *
 * Covers what the FieldOverlay unit tests cannot: that the toggle exists in the
 * toolbar, that its state actually reaches EVERY overlay on the page, and that
 * flipping it does not disturb zoom. The per-label rendering rules (sizing,
 * truncation, suppression, colour) live in FieldOverlay.fieldids.test.tsx.
 *
 * The mock/harness below is lifted from PDFViewer.phase5.test.tsx, whose header
 * explains why the wait sequence is what it is: pageDimensions is a ref filled
 * later by PDFPage's render promise, and overlays mount only once it is
 * populated -- so an overlay in the DOM is the reliable ready signal.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent, act } from '@testing-library/react';
import { PDFViewer } from './PDFViewer';
import type { FormSchema } from '../types/schema';
import * as pdfjsLib from 'pdfjs-dist';

vi.mock('pdfjs-dist', () => ({
  GlobalWorkerOptions: { workerSrc: '' },
  getDocument: vi.fn(),
}));

const makeSchema = (ids: [string, string] = ['field1', 'field2']): FormSchema => ({
  source: 'pdf',
  form_metadata: {
    title: 'Test PDF Form',
    form_number: 'TEST-001',
    total_widgets: 2,
    total_fields: 2,
    version: '1.0',
    language: 'en',
  },
  parts: [],
  sections: [],
  fields: [
    {
      id: ids[0],
      name: 'Test Field 1',
      type: 'text',
      pdf_field_name: 'field1',
      read_only: false,
      spoken_name: 'Test Field 1',
      pdf_position: { page: 1, x: 100, y: 500, width: 200, height: 20 },
    },
    {
      id: ids[1],
      name: 'Test Field 2',
      type: 'text',
      pdf_field_name: 'field2',
      read_only: false,
      spoken_name: 'Test Field 2',
      pdf_position: { page: 1, x: 100, y: 400, width: 200, height: 20 },
    },
  ],
});

function mockSinglePagePdf() {
  const mockGetPage = vi.fn().mockResolvedValue({
    getViewport: ({ scale }: { scale: number }) => ({
      width: 612 * scale,
      height: 792 * scale,
    }),
    render: vi.fn().mockReturnValue({ promise: Promise.resolve(), cancel: vi.fn() }),
    cleanup: vi.fn(),
  });
  const mockDocument = { numPages: 1, getPage: mockGetPage, destroy: vi.fn() };
  vi.mocked(pdfjsLib.getDocument).mockReturnValue({
    promise: Promise.resolve(mockDocument as any),
    destroy: vi.fn(),
  } as any);
}

async function renderLoadedViewer(schema: FormSchema, onSelectField = vi.fn()) {
  const result = render(
    <PDFViewer
      pdfPath="/test.pdf"
      schema={schema}
      selectedFieldId={null}
      onSelectField={onSelectField}
    />,
  );
  await waitFor(() => {
    expect(document.querySelectorAll('canvas').length).toBe(1);
  });
  await act(async () => { await Promise.resolve(); });
  await screen.findByTestId(`field-overlay-${schema.fields[0].id}`);
  return result;
}

describe('PDFViewer -- Show field IDs toggle', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // jsdom has no canvas backend; PDFPage's onPageLoad fires only when
    // getContext returns something, and an empty object is enough (same stub the
    // phase5 suite uses).
    HTMLCanvasElement.prototype.getContext = vi.fn(() => ({})) as any;
    mockSinglePagePdf();
  });

  it('renders the checkbox, unchecked by default', async () => {
    await renderLoadedViewer(makeSchema());
    const toggle = screen.getByLabelText('Show field IDs') as HTMLInputElement;
    expect(toggle).toBeInTheDocument();
    expect(toggle.checked).toBe(false);
  });

  it('defaults to box mode: overlays present, no ID labels', async () => {
    const { container } = await renderLoadedViewer(makeSchema());
    expect(screen.getByTestId('field-overlay-field1')).toBeInTheDocument();
    expect(container.querySelector('.field-id-label')).toBeNull();
  });

  it('checking it labels EVERY overlay on the page', async () => {
    // Two distinct fields, so this proves the prop reaches the whole map, not
    // just the first overlay.
    await renderLoadedViewer(makeSchema());
    fireEvent.click(screen.getByLabelText('Show field IDs'));

    expect(screen.getByTestId('field-id-label-field1').textContent).toBe('field1');
    expect(screen.getByTestId('field-id-label-field2').textContent).toBe('field2');
  });

  it('unchecking returns to box mode', async () => {
    const { container } = await renderLoadedViewer(makeSchema());
    const toggle = screen.getByLabelText('Show field IDs');

    fireEvent.click(toggle);
    expect(container.querySelector('.field-id-label')).not.toBeNull();

    fireEvent.click(toggle);
    expect(container.querySelector('.field-id-label')).toBeNull();
  });

  it('still selects the field when a labelled overlay is clicked', async () => {
    const onSelectField = vi.fn();
    await renderLoadedViewer(makeSchema(), onSelectField);
    fireEvent.click(screen.getByLabelText('Show field IDs'));

    fireEvent.click(screen.getByTestId('field-overlay-field1'));
    expect(onSelectField).toHaveBeenCalledWith('field1');
  });

  it('does not disturb the zoom scale', async () => {
    // Guards against anyone wiring the checkbox into setScale.
    await renderLoadedViewer(makeSchema());
    expect(screen.getByText('100%')).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText('Show field IDs'));
    expect(screen.getByText('100%')).toBeInTheDocument();
  });

  it('re-labels when a field ID changes (rename)', async () => {
    // Documents the update mechanism: the overlay map is keyed on field.id, so a
    // rename unmounts and remounts that overlay and the new label appears with
    // no subscription of any kind. Renames commit only on Enter / the Rename
    // button, so this rerender is exactly what the editor does on save.
    const { rerender } = await renderLoadedViewer(makeSchema(['old_name', 'field2']));
    fireEvent.click(screen.getByLabelText('Show field IDs'));
    expect(screen.getByTestId('field-id-label-old_name').textContent).toBe('old_name');

    rerender(
      <PDFViewer
        pdfPath="/test.pdf"
        schema={makeSchema(['new_name', 'field2'])}
        selectedFieldId={null}
        onSelectField={vi.fn()}
      />,
    );

    expect(screen.getByTestId('field-id-label-new_name').textContent).toBe('new_name');
    expect(screen.queryByTestId('field-id-label-old_name')).toBeNull();
  });
});
