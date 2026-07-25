/**
 * FieldEditor "Why this field is flagged" banner severity styling
 * (bd polyglot-pdf-6hhc nit 1): a WARNING-only field must render the banner in
 * amber, matching FieldList.getFieldStatus (which turns a row red only for
 * ERROR-severity). Before the fix the banner was always red, so a WARNING-only
 * field showed a green row + a red banner.
 */
import { describe, it, expect, afterEach } from 'vitest';
import { render, screen, cleanup, within } from '@testing-library/react';
import { FieldEditor } from './FieldEditor';
import type { FormSchema, FormField } from '../types/schema';
import type { LintFinding } from '../utils/remoteKitStore';

// A field that is complete per checkFieldComplete (id/type/pdf_field_name,
// spoken_name, non-placeholder instructions) so no LOCAL completeness error
// contaminates the severity assertion -- the banner reflects only the lint
// findings we inject.
const FIELD: FormField = {
  id: 'f1', name: 'f1', type: 'text', pdf_field_name: 'f1[0]',
  read_only: false, spoken_name: 'field one',
  help: { instructions: 'Fill this in.' },
} as FormField;

const SCHEMA: FormSchema = {
  form_metadata: { title: 'T', version: '1', form_number: 'X' },
  sections: [], fields: [FIELD],
} as unknown as FormSchema;

function finding(severity: 'ERROR' | 'WARNING', message: string): LintFinding {
  return { severity, rule: 'r', path: 'p', message, field_id: 'f1' };
}

function renderWith(lintFindings: LintFinding[]) {
  return render(
    <FieldEditor
      field={FIELD}
      schema={SCHEMA}
      onUpdateField={() => {}}
      lintFindings={lintFindings}
    />,
  );
}

afterEach(cleanup);

describe('FieldEditor flagged-banner severity styling (bd 6hhc)', () => {
  it('renders a WARNING-only banner in amber, not red', () => {
    renderWith([finding('WARNING', 'a soft warning')]);
    const banner = screen.getByTestId('field-problems');
    expect(banner.className).toContain('amber');
    expect(banner.className).not.toContain('red');
    // The warning message renders in amber text.
    expect(within(banner).getByText('a soft warning').className)
      .toContain('amber');
  });

  it('renders an ERROR banner in red', () => {
    renderWith([finding('ERROR', 'a hard error')]);
    const banner = screen.getByTestId('field-problems');
    expect(banner.className).toContain('red');
    expect(banner.className).not.toContain('amber');
  });

  it('a mixed set renders red (errors dominate the container)', () => {
    renderWith([
      finding('ERROR', 'a hard error'),
      finding('WARNING', 'a soft warning'),
    ]);
    const banner = screen.getByTestId('field-problems');
    expect(banner.className).toContain('red');
    // The error is red, the warning stays amber within the red container.
    expect(within(banner).getByText('a hard error').className).toContain('red');
    expect(within(banner).getByText('a soft warning').className)
      .toContain('amber');
  });

  it('renders nothing when there are no findings', () => {
    renderWith([]);
    expect(screen.queryByTestId('field-problems')).toBeNull();
  });
});
