/**
 * FieldList 'To review' highlight (bd polyglot-pdf-6cfu.3).
 *
 * A section whose id carries the sec_to_review prefix (minted by the
 * deterministic division derivation for fields a human must re-file) renders
 * with the amber re-file badge while it still holds fields; an emptied one
 * (and every ordinary section) does not.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { FieldList } from './FieldList';
import type { FormSchema, FormField } from '../types/schema';

function f(id: string, sectionId: string): FormField {
  return {
    id, name: id, type: 'text', pdf_field_name: `pdf.${id}`,
    spoken_name: `spoken ${id}`, section_id: sectionId,
    help: { instructions: 'All set.' },
  } as unknown as FormField;
}

function renderList(schema: FormSchema) {
  render(
    <FieldList
      schema={schema}
      selectedFieldId={null}
      onSelectField={vi.fn()}
    />,
  );
}

describe('FieldList to-review highlight', () => {
  it('badges a To-review section that still holds fields', () => {
    renderList({
      form_metadata: { title: 'T', version: '1' },
      sections: [
        { id: 'sec_real', label: 'Real', order: 1, fields: ['f1'] },
        { id: 'sec_to_review_p1', label: 'To review', order: 2, fields: ['f2'] },
      ],
      fields: [f('f1', 'sec_real'), f('f2', 'sec_to_review_p1')],
    } as unknown as FormSchema);
    expect(screen.getByText('re-file required')).toBeInTheDocument();
  });

  it('does not badge an emptied To-review section or ordinary sections', () => {
    renderList({
      form_metadata: { title: 'T', version: '1' },
      sections: [
        { id: 'sec_real', label: 'Real', order: 1, fields: ['f1'] },
        { id: 'sec_to_review_p1', label: 'To review', order: 2, fields: [] },
      ],
      fields: [f('f1', 'sec_real')],
    } as unknown as FormSchema);
    expect(screen.queryByText('re-file required')).toBeNull();
  });
});
