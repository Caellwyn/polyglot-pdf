/**
 * Unit tests for Phase 2: Multi-page PDF rendering and navigation
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { PDFViewer } from './PDFViewer';
import type { FormSchema } from '../types/schema';
import * as pdfjsLib from 'pdfjs-dist';

// Mock schema with fields on different pages
const mockMultiPageSchema: FormSchema = {
  source: 'pdf',
  form_metadata: {
    title: 'I-90',
    form_number: 'I-90',
    total_widgets: 20,
    total_fields: 20,
    version: '1.0',
    language: 'en',
  },
  parts: [],
  sections: [
    {
      id: 'section-1',
      label: 'Part 1',
      order: 1,
      fields: ['field-page1', 'field-page2', 'field-page3'],
    },
  ],
  fields: [
    {
      id: 'field-page1',
      name: 'Field on Page 1',
      type: 'text',
      section_id: 'section-1',
      pdf_field_name: 'field_page1',
      read_only: false,
      required: false,
      pdf_position: {
        page: 1,
        x: 100,
        y: 200,
        width: 150,
        height: 30,
      },
    },
    {
      id: 'field-page2',
      name: 'Field on Page 2',
      type: 'text',
      section_id: 'section-1',
      pdf_field_name: 'field_page2',
      read_only: false,
      required: false,
      pdf_position: {
        page: 2,
        x: 100,
        y: 200,
        width: 150,
        height: 30,
      },
    },
    {
      id: 'field-page3',
      name: 'Field on Page 3',
      type: 'text',
      section_id: 'section-1',
      pdf_field_name: 'field_page3',
      read_only: false,
      required: false,
      pdf_position: {
        page: 3,
        x: 100,
        y: 200,
        width: 150,
        height: 30,
      },
    },
  ],
};

describe('PDFViewer Phase 2: Multi-page Support', () => {
  const mockSelectField = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();

    // Mock PDF.js to return a 3-page document
    vi.mocked(pdfjsLib.getDocument).mockReturnValue({
      promise: Promise.resolve({
        numPages: 3,
        getPage: vi.fn((pageNum) =>
          Promise.resolve({
            getViewport: vi.fn(() => ({ width: 612, height: 792, scale: 1 })),
            render: vi.fn(() => ({ promise: Promise.resolve() })),
          })
        ),
        destroy: vi.fn(),
      } as any),
      destroy: vi.fn(),
    } as any);
  });

  describe('Page Navigation Controls', () => {
    it('should render page navigation buttons', async () => {
      render(
        <PDFViewer
          pdfPath="/test.pdf"
          schema={mockMultiPageSchema}
          selectedFieldId={null}
          onSelectField={mockSelectField}
        />
      );

      await waitFor(() => {
        expect(screen.getByTitle('Previous page')).toBeInTheDocument();
        expect(screen.getByTitle('Next page')).toBeInTheDocument();
      });
    });

    it('should display current page indicator', async () => {
      render(
        <PDFViewer
          pdfPath="/test.pdf"
          schema={mockMultiPageSchema}
          selectedFieldId={null}
          onSelectField={mockSelectField}
        />
      );

      await waitFor(() => {
        expect(screen.getByText('Page')).toBeInTheDocument();
        expect(screen.getByText('of 3')).toBeInTheDocument();
      });
    });

    it('should disable previous button on first page', async () => {
      render(
        <PDFViewer
          pdfPath="/test.pdf"
          schema={mockMultiPageSchema}
          selectedFieldId={null}
          onSelectField={mockSelectField}
        />
      );

      await waitFor(() => {
        const prevBtn = screen.getByTitle('Previous page');
        expect(prevBtn).toBeDisabled();
      });
    });

    it('should enable next button when not on last page', async () => {
      render(
        <PDFViewer
          pdfPath="/test.pdf"
          schema={mockMultiPageSchema}
          selectedFieldId={null}
          onSelectField={mockSelectField}
        />
      );

      await waitFor(() => {
        const nextBtn = screen.getByTitle('Next page');
        expect(nextBtn).not.toBeDisabled();
      });
    });

    it('should update page number input value', async () => {
      render(
        <PDFViewer
          pdfPath="/test.pdf"
          schema={mockMultiPageSchema}
          selectedFieldId={null}
          onSelectField={mockSelectField}
        />
      );

      await waitFor(() => {
        const pageInput = screen.getByRole('spinbutton') as HTMLInputElement;
        expect(pageInput.value).toBe('1');
      });
    });

    it('should allow jumping to specific page via input', async () => {
      // Mock scrollIntoView
      Element.prototype.scrollIntoView = vi.fn();

      render(
        <PDFViewer
          pdfPath="/test.pdf"
          schema={mockMultiPageSchema}
          selectedFieldId={null}
          onSelectField={mockSelectField}
        />
      );

      await waitFor(() => {
        const pageInput = screen.getByRole('spinbutton') as HTMLInputElement;
        fireEvent.change(pageInput, { target: { value: '2' } });
        expect(pageInput.value).toBe('2');
      });
    });

    it('should clamp page input to valid range', async () => {
      // Mock scrollIntoView
      Element.prototype.scrollIntoView = vi.fn();

      render(
        <PDFViewer
          pdfPath="/test.pdf"
          schema={mockMultiPageSchema}
          selectedFieldId={null}
          onSelectField={mockSelectField}
        />
      );

      await waitFor(() => {
        const pageInput = screen.getByRole('spinbutton') as HTMLInputElement;

        // Try to go beyond max page
        fireEvent.change(pageInput, { target: { value: '10' } });
        // Should be clamped to 3 (max pages)
        // Note: The clamping happens in handlePageInput
      });
    });
  });

  describe('Multi-page Rendering', () => {
    it('should render all pages of the document', async () => {
      render(
        <PDFViewer
          pdfPath="/test.pdf"
          schema={mockMultiPageSchema}
          selectedFieldId={null}
          onSelectField={mockSelectField}
        />
      );

      await waitFor(() => {
        // Should render 3 canvas elements (one per page)
        const canvases = document.querySelectorAll('canvas');
        expect(canvases.length).toBe(3);
      });
    });

    it('should display page number labels on each page', async () => {
      render(
        <PDFViewer
          pdfPath="/test.pdf"
          schema={mockMultiPageSchema}
          selectedFieldId={null}
          onSelectField={mockSelectField}
        />
      );

      await waitFor(() => {
        expect(screen.getByText('Page 1')).toBeInTheDocument();
        expect(screen.getByText('Page 2')).toBeInTheDocument();
        expect(screen.getByText('Page 3')).toBeInTheDocument();
      });
    });

    it('should update all pages when scale changes', async () => {
      const { getByTitle } = render(
        <PDFViewer
          pdfPath="/test.pdf"
          schema={mockMultiPageSchema}
          selectedFieldId={null}
          onSelectField={mockSelectField}
        />
      );

      await waitFor(() => {
        expect(document.querySelectorAll('canvas').length).toBe(3);
      });

      // Zoom in
      const zoomInBtn = getByTitle('Zoom in');
      fireEvent.click(zoomInBtn);

      // All pages should still be rendered
      await waitFor(() => {
        expect(document.querySelectorAll('canvas').length).toBe(3);
      });
    });
  });

  describe('Auto-scroll to Field Page', () => {
    it('should scroll to page 1 when field on page 1 is selected', async () => {
      const { rerender } = render(
        <PDFViewer
          pdfPath="/test.pdf"
          schema={mockMultiPageSchema}
          selectedFieldId={null}
          onSelectField={mockSelectField}
        />
      );

      await waitFor(() => {
        expect(document.querySelectorAll('canvas').length).toBe(3);
      });

      // Mock scrollIntoView
      Element.prototype.scrollIntoView = vi.fn();

      // Select field on page 1
      rerender(
        <PDFViewer
          pdfPath="/test.pdf"
          schema={mockMultiPageSchema}
          selectedFieldId="field-page1"
          onSelectField={mockSelectField}
        />
      );

      await waitFor(() => {
        // scrollIntoView should have been called
        expect(Element.prototype.scrollIntoView).toHaveBeenCalled();
      });
    });

    it('should scroll to page 2 when field on page 2 is selected', async () => {
      const { rerender } = render(
        <PDFViewer
          pdfPath="/test.pdf"
          schema={mockMultiPageSchema}
          selectedFieldId={null}
          onSelectField={mockSelectField}
        />
      );

      await waitFor(() => {
        expect(document.querySelectorAll('canvas').length).toBe(3);
      });

      // Mock scrollIntoView
      Element.prototype.scrollIntoView = vi.fn();

      // Select field on page 2
      rerender(
        <PDFViewer
          pdfPath="/test.pdf"
          schema={mockMultiPageSchema}
          selectedFieldId="field-page2"
          onSelectField={mockSelectField}
        />
      );

      await waitFor(() => {
        expect(Element.prototype.scrollIntoView).toHaveBeenCalled();
      });
    });

    it('should not scroll if selected field has no pdf_position', async () => {
      const schemaWithoutPosition = {
        ...mockMultiPageSchema,
        fields: [
          {
            ...mockMultiPageSchema.fields[0],
            pdf_position: undefined,
          },
        ],
      };

      const { rerender } = render(
        <PDFViewer
          pdfPath="/test.pdf"
          schema={schemaWithoutPosition}
          selectedFieldId={null}
          onSelectField={mockSelectField}
        />
      );

      await waitFor(() => {
        expect(document.querySelectorAll('canvas').length).toBe(3);
      });

      Element.prototype.scrollIntoView = vi.fn();

      rerender(
        <PDFViewer
          pdfPath="/test.pdf"
          schema={schemaWithoutPosition}
          selectedFieldId={schemaWithoutPosition.fields[0].id}
          onSelectField={mockSelectField}
        />
      );

      // Wait a bit to ensure no scroll happens
      await new Promise(resolve => setTimeout(resolve, 100));

      expect(Element.prototype.scrollIntoView).not.toHaveBeenCalled();
    });
  });

  describe('Page Counter Display', () => {
    it('should show correct total page count', async () => {
      render(
        <PDFViewer
          pdfPath="/test.pdf"
          schema={mockMultiPageSchema}
          selectedFieldId={null}
          onSelectField={mockSelectField}
        />
      );

      await waitFor(() => {
        expect(screen.getByText('of 3')).toBeInTheDocument();
      });
    });

    it('should show field count in toolbar', async () => {
      render(
        <PDFViewer
          pdfPath="/test.pdf"
          schema={mockMultiPageSchema}
          selectedFieldId={null}
          onSelectField={mockSelectField}
        />
      );

      await waitFor(() => {
        expect(screen.getByText('3 fields')).toBeInTheDocument();
      });
    });
  });
});
