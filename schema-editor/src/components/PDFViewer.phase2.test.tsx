/**
 * Unit tests for Phase 2: Multi-page PDF rendering and navigation
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent, act } from '@testing-library/react';
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

    // jsdom has no canvas backend, so HTMLCanvasElement.getContext returns null,
    // which makes PDFPage bail before rendering (and before onPageLoad, which
    // populates pageDimensions). Stub a minimal 2d context so the render path --
    // and the auto-scroll effect that depends on pageDimensions -- can run.
    HTMLCanvasElement.prototype.getContext = vi.fn(() => ({})) as any;

    // Mock PDF.js to return a 3-page document
    vi.mocked(pdfjsLib.getDocument).mockReturnValue({
      promise: Promise.resolve({
        numPages: 3,
        getPage: vi.fn(() =>
          Promise.resolve({
            getViewport: vi.fn(() => ({ width: 612, height: 792, scale: 1 })),
            // render task exposes both promise and cancel (PDFPage's cleanup
            // calls renderTaskRef.current.cancel() on rerender/unmount).
            render: vi.fn(() => ({ promise: Promise.resolve(), cancel: vi.fn() })),
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
      // Mock scrollIntoView (handlePageInput -> scrollToPage calls it)
      Element.prototype.scrollIntoView = vi.fn();

      render(
        <PDFViewer
          pdfPath="/test.pdf"
          schema={mockMultiPageSchema}
          selectedFieldId={null}
          onSelectField={mockSelectField}
        />
      );

      // Wait for ALL 3 pages to render before firing input: handlePageInput ->
      // scrollToPage only calls setCurrentPage when the target page's ref is
      // registered (pageRefs.get(page)), which happens as each page div commits.
      // Gating on the spinbutton alone would race the page-ref registration and
      // flake (fresh-eyes, bd 840i).
      await waitFor(() => {
        expect(document.querySelectorAll('canvas').length).toBe(3);
      });
      const pageInput = screen.getByRole('spinbutton') as HTMLInputElement;

      // The input is controlled by currentPage, which handlePageInput clamps to
      // [1, numPages] (here numPages = 3). An over-max entry must NOT leave the
      // displayed value at the raw input; it clamps to the max page.
      fireEvent.change(pageInput, { target: { value: '10' } });
      await waitFor(() => expect(pageInput.value).toBe('3'));

      // A below-min entry clamps up to page 1 (the `|| 1` + Math.max(1, ...)).
      fireEvent.change(pageInput, { target: { value: '0' } });
      await waitFor(() => expect(pageInput.value).toBe('1'));
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
    it('scrolls AND sets the current page to the selected field page (page 2)', async () => {
      // NOTE (bd polyglot-pdf-840i): the pixel scroll TARGET is not observable
      // under jsdom (every getBoundingClientRect / offset returns 0, so a page-1
      // and page-2 target produce the same 0 coordinates). But the auto-scroll
      // effect ALSO calls setCurrentPage(field.pdf_position.page), and that IS
      // observable: the page-number input (role spinbutton, value={currentPage})
      // reflects it. So selecting field-page2 (pdf_position.page === 2) must drive
      // the input to "2" -- this catches page-routing regressions that the bare
      // "scrollTo was called" assertion could not (it would pass even if the wrong
      // page were selected).
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
      // Flush the page-render promises so PDFPage's onPageLoad fires and
      // populates pageDimensions (a ref, set in a microtask after render). The
      // auto-scroll effect depends on it; in a real browser this completes before
      // a user can select a field, in jsdom we flush it explicitly.
      await act(async () => { await Promise.resolve(); });

      // Sanity: starts on page 1 before any field is selected.
      expect((screen.getByRole('spinbutton') as HTMLInputElement).value).toBe('1');

      // The auto-scroll effect centers the field via the scroll container's
      // scrollTo (jsdom does not implement it, so it must be mocked).
      const scrollToSpy = vi.fn();
      Element.prototype.scrollTo = scrollToSpy;

      // Select a field that HAS a pdf_position on PAGE 2.
      rerender(
        <PDFViewer
          pdfPath="/test.pdf"
          schema={mockMultiPageSchema}
          selectedFieldId="field-page2"
          onSelectField={mockSelectField}
        />
      );

      await waitFor(() => {
        expect(scrollToSpy).toHaveBeenCalled();
      });
      // The selected field is on page 2, so currentPage -- and the page-number
      // input -- must read "2", not the page-1 default.
      await waitFor(() => {
        expect((screen.getByRole('spinbutton') as HTMLInputElement).value).toBe('2');
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
