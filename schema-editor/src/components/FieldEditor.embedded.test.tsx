/**
 * Property-anchored findings in the FieldEditor (sprint-18 C1, bd
 * polyglot-pdf-o7y9, decision 1): a finding renders UNDER the control it
 * concerns (Instructions box, option row, condition builders), the top banner
 * keeps only what has no property home, the header chip scrolls to the first
 * finding, and the sign-off stamps the fingerprints of the findings in hand.
 */
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { FieldEditor } from './FieldEditor';
import { findingFingerprint } from '../utils/lintFindings';
import type { FormSchema, FormField } from '../types/schema';
import type { LintFinding } from '../utils/remoteKitStore';

afterEach(cleanup);

const TEXT_FIELD: FormField = {
  id: 'phone', name: 'Phone', spoken_name: 'phone number', type: 'text',
  section_id: 's1', pdf_field_name: 'P[0]',
  help: { instructions: 'Enter the phone number.', details: 'Booklet text.' },
} as unknown as FormField;

const CHOICE_FIELD: FormField = {
  id: 'race', name: 'Race', spoken_name: 'race', type: 'checkbox_group',
  section_id: 's1', pdf_field_name: '',
  options: [
    { label: 'Alpha', value: 'alpha', pdf_field_name: 'A[0]' },
    { label: 'Beta', value: 'beta', pdf_field_name: 'B[0]' },
  ],
  help: { instructions: 'Pick all that apply.' },
} as unknown as FormField;

function makeSchema(f: FormField): FormSchema {
  return {
    source: 'pdf',
    form_metadata: { title: 'T', form_number: 'T-1', version: '1', language: 'en' },
    parts: [], sections: [{ id: 's1', label: 'S1', order: 1, fields: [f.id] }],
    fields: [f],
  } as unknown as FormSchema;
}

const instructionsFinding: LintFinding = {
  severity: 'WARNING', rule: 'help-instructions-too-long',
  path: 'fields[0] (id=phone).help.instructions',
  message: 'the instructions are too long to be spoken',
  field_id: 'phone',
};
const detailsFinding: LintFinding = {
  severity: 'WARNING', rule: 'help-details-oversize',
  path: 'fields[0] (id=phone).help.details',
  message: 'the details are too long to reach the assistant',
  field_id: 'phone',
};
const conditionFinding: LintFinding = {
  severity: 'ERROR', rule: 'unknown-operator',
  path: 'fields[0] (id=phone).show_if',
  message: 'the condition uses an unrecognized comparison',
  field_id: 'phone',
};
const fieldFinding: LintFinding = {
  severity: 'ERROR', rule: 'field-unbacked',
  path: 'fields[0] (id=phone)',
  message: 'this field names no PDF box',
  field_id: 'phone',
};

describe('findings render at the property they concern (s18 C1)', () => {
  it('anchors instructions/details/condition findings at their controls', () => {
    render(
      <FieldEditor field={TEXT_FIELD} schema={makeSchema(TEXT_FIELD)}
        onUpdateField={vi.fn()} authorTier
        lintFindings={[instructionsFinding, detailsFinding, conditionFinding]} />,
    );
    expect(screen.getByTestId('embedded-findings-instructions'))
      .toHaveTextContent('too long to be spoken');
    // The remedy line (RULE_REMEDIES) renders with the finding.
    expect(screen.getByTestId('embedded-findings-instructions'))
      .toHaveTextContent('Shorten the instructions and move detail into Details.');
    expect(screen.getByTestId('embedded-findings-details'))
      .toHaveTextContent('too long to reach the assistant');
    expect(screen.getByTestId('embedded-findings-conditions'))
      .toHaveTextContent('unrecognized comparison');
    // None of the property-anchored findings duplicate into the banner (which
    // may still carry the client-side advisory reasons -- e.g. this fixture's
    // positionless widget).
    const banner = screen.queryByTestId('field-problems');
    const bannerText = banner?.textContent ?? '';
    expect(bannerText).not.toContain('too long to be spoken');
    expect(bannerText).not.toContain('too long to reach the assistant');
    expect(bannerText).not.toContain('unrecognized comparison');
  });

  it('anchors a translation flag by option VALUE, not index (Opus round 2)', () => {
    // The translation-flag writers put the option's VALUE in the path token;
    // with numeric values ('2' at index 0, like i-90's height field) a
    // digits-mean-index read anchored the flag at the wrong option row.
    const numericValues: FormField = {
      ...CHOICE_FIELD,
      options: [
        { label: 'Two', value: '2', pdf_field_name: 'A[0]' },
        { label: 'Three', value: '3', pdf_field_name: 'B[0]' },
        { label: 'Four', value: '4', pdf_field_name: 'C[0]' },
      ],
    } as unknown as FormField;
    const flag: LintFinding = {
      severity: 'WARNING', rule: 'translation-drift-unresolved',
      path: 'fields[0] (id=race).options[2].label_translations.spanish',
      message: 'translation needs human review',
      field_id: 'race',
    };
    render(
      <FieldEditor field={numericValues} schema={makeSchema(numericValues)}
        onUpdateField={vi.fn()} authorTier lintFindings={[flag]} />,
    );
    // Value '2' is INDEX 0 -- the flag renders at option 0, not option 2.
    expect(screen.getByTestId('embedded-findings-option-0'))
      .toHaveTextContent('needs human review');
    expect(screen.queryByTestId('embedded-findings-option-2')).toBeNull();
  });

  it('anchors an option finding at its option row', () => {
    const optionFinding: LintFinding = {
      severity: 'ERROR', rule: 'option-value-slug',
      path: 'fields[0] (id=race).options[1]',
      message: 'the value is not in the required format',
      field_id: 'race',
    };
    render(
      <FieldEditor field={CHOICE_FIELD} schema={makeSchema(CHOICE_FIELD)}
        onUpdateField={vi.fn()} authorTier lintFindings={[optionFinding]} />,
    );
    expect(screen.getByTestId('embedded-findings-option-1'))
      .toHaveTextContent('not in the required format');
    expect(screen.queryByTestId('embedded-findings-option-0')).toBeNull();
  });

  it('keeps field-anchored findings in the banner (their only home)', () => {
    render(
      <FieldEditor field={TEXT_FIELD} schema={makeSchema(TEXT_FIELD)}
        onUpdateField={vi.fn()} authorTier lintFindings={[fieldFinding]} />,
    );
    expect(screen.getByTestId('field-problems'))
      .toHaveTextContent('this field names no PDF box');
  });

  it('the header chip counts the findings and scrolls to the first one', () => {
    const scrollSpy = vi.fn();
    window.HTMLElement.prototype.scrollIntoView = scrollSpy;
    render(
      <FieldEditor field={TEXT_FIELD} schema={makeSchema(TEXT_FIELD)}
        onUpdateField={vi.fn()} authorTier
        lintFindings={[instructionsFinding, conditionFinding]} />,
    );
    const chip = screen.getByTestId('field-findings-chip');
    expect(chip).toHaveTextContent('2 to fix'); // one ERROR -> red wording
    fireEvent.click(chip);
    expect(scrollSpy).toHaveBeenCalled();
  });

  it('renders no chip for a clean field', () => {
    render(
      <FieldEditor field={TEXT_FIELD} schema={makeSchema(TEXT_FIELD)}
        onUpdateField={vi.fn()} authorTier lintFindings={[]} />,
    );
    expect(screen.queryByTestId('field-findings-chip')).toBeNull();
  });

  it('the chip is scoped to THIS field -- another field\'s ERROR cannot redden it', () => {
    // The prop type invites a whole-schema list; the chip's count and its
    // red/amber banding must ignore off-field findings exactly as the
    // bucketing loop does (fresh-eyes round 1: an unscoped severity count
    // rendered "1 to fix" red for a field carrying only a WARNING).
    const otherFieldError: LintFinding = {
      severity: 'ERROR', rule: 'field-unbacked',
      path: 'fields[1] (id=zip)', message: 'zip names no PDF box',
      field_id: 'zip',
    };
    render(
      <FieldEditor field={TEXT_FIELD} schema={makeSchema(TEXT_FIELD)}
        onUpdateField={vi.fn()} authorTier
        lintFindings={[instructionsFinding, otherFieldError]} />,
    );
    const chip = screen.getByTestId('field-findings-chip');
    expect(chip).toHaveTextContent('1 notice'); // amber wording, count of 1
    expect(chip.className).toContain('bg-amber-100');
  });
});

describe('the sign-off stamps the current findings (s18 C1, decision 3)', () => {
  it('marking reviewed_correct writes the findings\' fingerprints into _review', () => {
    const onUpdateField = vi.fn();
    render(
      <FieldEditor field={TEXT_FIELD} schema={makeSchema(TEXT_FIELD)}
        onUpdateField={onUpdateField} authorTier
        lintFindings={[instructionsFinding]} />,
    );
    fireEvent.change(screen.getByLabelText('Review status'), {
      target: { value: 'reviewed_correct' },
    });
    const updated = onUpdateField.mock.calls[0][0] as FormField;
    expect(updated._review?.seen_fingerprints)
      .toEqual([findingFingerprint(instructionsFinding)]);
  });
});
