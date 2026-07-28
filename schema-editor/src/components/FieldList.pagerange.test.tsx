/**
 * Page-range diagnostics in the field list (bd polyglot-pdf-g63j).
 *
 * A field whose pdf_position names a page the PDF does not have paints NOWHERE
 * on the preview: PDFViewer renders pages 1..numPages and filters overlays by
 * exact page match, so the row simply has no highlight and -- before this bead
 * -- no explanation either. That silent failure is what let two mis-labeled
 * W-7 fields read as "phantom". The list now names it, but only once the PDF
 * has loaded and reported its page count.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { FieldList } from './FieldList';
import type { FormSchema, FormField } from '../types/schema';

const RECT = { x: 10, y: 10, width: 50, height: 12 };

function field(id: string, extra: Partial<FormField> = {}): FormField {
  return {
    id, name: id, type: 'text', pdf_field_name: `pdf.${id}`,
    spoken_name: `spoken ${id}`, section_id: 'sec-1', read_only: false,
    help: { instructions: 'All set.' },
    pdf_position: { page: 1, ...RECT },
    ...extra,
  } as unknown as FormField;
}

function schemaWith(fields: FormField[]): FormSchema {
  return {
    source: 'pdf',
    form_metadata: {
      title: 'T', form_number: 'T', total_widgets: fields.length,
      total_fields: fields.length, version: '1', language: 'en',
    },
    parts: [],
    sections: [{ id: 'sec-1', label: 'Section 1', order: 1, fields: fields.map(f => f.id) }],
    fields,
  } as unknown as FormSchema;
}

function renderList(schema: FormSchema, pageCount?: number) {
  render(
    <FieldList
      schema={schema}
      selectedFieldId={null}
      onSelectField={vi.fn()}
      pageCount={pageCount}
    />,
  );
}

const titleOf = (id: string) =>
  screen.getByTestId(`field-status-${id}`).getAttribute('title') ?? '';

describe('FieldList page-range diagnostics (bd g63j)', () => {
  it('names a field claiming a page beyond the document', () => {
    renderList(schemaWith([field('off', {
      pdf_position: { page: 9, ...RECT },
    })]), 3);
    expect(titleOf('off')).toContain('claims page 9');
    expect(titleOf('off')).toContain('3 page(s)');
  });

  it('treats page 0 as out of range (the schema convention is 1-based)', () => {
    renderList(schemaWith([field('zeroth', {
      pdf_position: { page: 0, ...RECT },
    })]), 3);
    expect(titleOf('zeroth')).toContain('claims page 0');
  });

  it('stays quiet before the PDF reports a page count', () => {
    // No pageCount prop: the editor cannot know the range yet, so it must not
    // guess -- a schema-only context never invents a defect.
    renderList(schemaWith([field('off', {
      pdf_position: { page: 9, ...RECT },
    })]));
    expect(titleOf('off')).not.toContain('claims page');
  });

  it('says nothing about pages for a properly positioned field', () => {
    renderList(schemaWith([field('good')]), 3);
    expect(titleOf('good')).not.toContain('claims page');
  });

  it('names an un-positioned field WITHOUT the false "Missing PDF field name"', () => {
    // The misleading message that started the whole investigation: this field
    // HAS a widget name, so saying it is missing one was simply wrong.
    renderList(schemaWith([field('norect', {
      pdf_position: undefined,
    })]), 3);
    const title = titleOf('norect');
    expect(title).toContain('No position recorded');
    expect(title).not.toContain('Missing PDF field name');
  });
});
