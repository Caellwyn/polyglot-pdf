/**
 * Integration tests for PDFViewer component
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { PDFViewer } from './PDFViewer';
import type { FormSchema } from '../types/schema';

// Mock schema for testing
const mockSchema: FormSchema = {
  source: 'pdf',
  form_metadata: {
    title: 'I-90',
    form_number: 'I-90',
    total_widgets: 10,
    total_fields: 10,
    version: '1.0',
    language: 'en',
  },
  parts: [],
  sections: [
    {
      id: 'section-1',
      label: 'Part 1',
      order: 1,
      fields: ['field-1', 'field-2'],
    },
  ],
  fields: [
    {
      id: 'field-1',
      name: 'Test Field 1',
      type: 'text',
      section_id: 'section-1',
      pdf_field_name: 'test_field_1',
      read_only: false,
      pdf_position: {
        page: 1,
        x: 100,
        y: 200,
        width: 150,
        height: 30,
      },
    },
    {
      id: 'field-2',
      name: 'Test Field 2',
      type: 'text',
      section_id: 'section-1',
      pdf_field_name: 'test_field_2',
      read_only: false,
    },
  ],
};

describe('PDFViewer Integration', () => {
  const mockSelectField = vi.fn();

  it('should render loading state initially', () => {
    render(
      <PDFViewer
        pdfPath="/test.pdf"
        schema={mockSchema}
        selectedFieldId={null}
        onSelectField={mockSelectField}
      />
    );

    expect(screen.getByText('Loading PDF...')).toBeInTheDocument();
  });

  it('should render toolbar with zoom controls', () => {
    render(
      <PDFViewer
        pdfPath="/test.pdf"
        schema={mockSchema}
        selectedFieldId={null}
        onSelectField={mockSelectField}
      />
    );

    expect(screen.getByTitle('Zoom out')).toBeInTheDocument();
    expect(screen.getByTitle('Zoom in')).toBeInTheDocument();
    expect(screen.getByTitle('Fit to width')).toBeInTheDocument();
    expect(screen.getByText('100%')).toBeInTheDocument();
  });

  it('should display the singular field count for exactly one positioned field', () => {
    // mockSchema has 2 fields but only field-1 carries a pdf_position, so the
    // toolbar counts 1 positioned field -> the singular "1 field" (bd polyglot-pdf-979r).
    render(
      <PDFViewer
        pdfPath="/test.pdf"
        schema={mockSchema}
        selectedFieldId={null}
        onSelectField={mockSelectField}
      />
    );

    expect(screen.getByText('1 field')).toBeInTheDocument();
    expect(screen.queryByText('1 fields')).not.toBeInTheDocument();
  });

  it('should display the plural field count for multiple positioned fields', () => {
    // Give field-2 a pdf_position too -> 2 positioned fields -> plural "2 fields".
    const multiPositioned: FormSchema = {
      ...mockSchema,
      fields: mockSchema.fields.map(f =>
        f.id === 'field-2'
          ? { ...f, pdf_position: { page: 1, x: 50, y: 75, width: 120, height: 25 } }
          : f
      ),
    };
    render(
      <PDFViewer
        pdfPath="/test.pdf"
        schema={multiPositioned}
        selectedFieldId={null}
        onSelectField={mockSelectField}
      />
    );

    expect(screen.getByText('2 fields')).toBeInTheDocument();
  });

  it('should render PDF page after loading', async () => {
    render(
      <PDFViewer
        pdfPath="/test.pdf"
        schema={mockSchema}
        selectedFieldId={null}
        onSelectField={mockSelectField}
      />
    );

    await waitFor(() => {
      expect(screen.queryByText('Loading PDF...')).not.toBeInTheDocument();
    });

    // PDF canvas should be rendered (via PDFPage component)
    const canvas = document.querySelector('canvas');
    expect(canvas).toBeInTheDocument();
  });

  it('should show "No PDF selected" when path is empty', () => {
    render(
      <PDFViewer
        pdfPath=""
        schema={mockSchema}
        selectedFieldId={null}
        onSelectField={mockSelectField}
      />
    );

    expect(screen.getByText('No PDF selected')).toBeInTheDocument();
  });

  it('should update zoom level when buttons are clicked', async () => {
    const { getByTitle, getByText } = render(
      <PDFViewer
        pdfPath="/test.pdf"
        schema={mockSchema}
        selectedFieldId={null}
        onSelectField={mockSelectField}
      />
    );

    const zoomInBtn = getByTitle('Zoom in');
    const zoomOutBtn = getByTitle('Zoom out');

    expect(getByText('100%')).toBeInTheDocument();

    // Zoom in
    zoomInBtn.click();
    await waitFor(() => {
      expect(getByText('125%')).toBeInTheDocument();
    });

    // Zoom out twice
    zoomOutBtn.click();
    await waitFor(() => {
      expect(getByText('100%')).toBeInTheDocument();
    });
  });

  it('should disable zoom out at minimum scale', async () => {
    const { getByTitle, getByText } = render(
      <PDFViewer
        pdfPath="/test.pdf"
        schema={mockSchema}
        selectedFieldId={null}
        onSelectField={mockSelectField}
      />
    );

    const zoomOutBtn = getByTitle('Zoom out');

    // Zoom out to minimum (50%)
    zoomOutBtn.click();
    await waitFor(() => {
      expect(getByText('75%')).toBeInTheDocument();
    });

    zoomOutBtn.click();
    await waitFor(() => {
      expect(getByText('50%')).toBeInTheDocument();
    });

    // Button should be disabled
    expect(zoomOutBtn).toBeDisabled();
  });

  it('should disable zoom in at maximum scale', async () => {
    const { getByTitle, getByText } = render(
      <PDFViewer
        pdfPath="/test.pdf"
        schema={mockSchema}
        selectedFieldId={null}
        onSelectField={mockSelectField}
      />
    );

    const zoomInBtn = getByTitle('Zoom in');

    // Zoom in to maximum (200%)
    for (let i = 0; i < 4; i++) {
      zoomInBtn.click();
      await new Promise(resolve => setTimeout(resolve, 10));
    }

    await waitFor(() => {
      expect(getByText('200%')).toBeInTheDocument();
    });

    // Button should be disabled
    expect(zoomInBtn).toBeDisabled();
  });
});
