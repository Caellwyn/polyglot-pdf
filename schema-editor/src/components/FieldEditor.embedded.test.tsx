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
import { statusFromFindings } from '../utils/reviewStatus';
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

  it('an option finding on a field whose Options block never renders falls to the banner', () => {
    // Backend lint checks options[] on EVERY field regardless of type, but
    // the editor's Options block renders only for select/radio/
    // checkbox_group -- without the fallback such a finding was counted by
    // the chip yet rendered nowhere (fresh-eyes round 3).
    const textWithOptions: FormField = {
      ...TEXT_FIELD,
      options: [{ label: 'A', value: 'Bad Value!' }],
    } as unknown as FormField;
    const optionError: LintFinding = {
      severity: 'ERROR', rule: 'option-value-slug',
      path: 'fields[0] (id=phone).options[0]',
      message: 'the value is not in the required format',
      field_id: 'phone',
    };
    render(
      <FieldEditor field={textWithOptions} schema={makeSchema(textWithOptions)}
        onUpdateField={vi.fn()} authorTier lintFindings={[optionError]} />,
    );
    expect(screen.queryByTestId('embedded-findings-option-0')).toBeNull();
    expect(screen.getByTestId('field-problems'))
      .toHaveTextContent('not in the required format');
  });

  it('keeps field-anchored findings in the banner (their only home)', () => {
    render(
      <FieldEditor field={TEXT_FIELD} schema={makeSchema(TEXT_FIELD)}
        onUpdateField={vi.fn()} authorTier lintFindings={[fieldFinding]} />,
    );
    expect(screen.getByTestId('field-problems'))
      .toHaveTextContent('this field names no PDF box');
  });

  it('the header chip counts the findings and scrolls to a PROPERTY anchor, not the banner', () => {
    const scrollSpy = vi.fn();
    window.HTMLElement.prototype.scrollIntoView = scrollSpy;
    // TEXT_FIELD has no spoken position, so the advisory banner renders above
    // every anchor -- the scroll must still land on the property-anchored
    // finding, never be swallowed by the banner (fresh-eyes round 3: a
    // combined document-order selector always hit the banner first).
    render(
      <FieldEditor field={TEXT_FIELD} schema={makeSchema(TEXT_FIELD)}
        onUpdateField={vi.fn()} authorTier
        lintFindings={[instructionsFinding, conditionFinding]} />,
    );
    const chip = screen.getByTestId('field-findings-chip');
    expect(chip).toHaveTextContent('2 to fix'); // one ERROR -> red wording
    fireEvent.click(chip);
    expect(scrollSpy).toHaveBeenCalledTimes(1);
    const scrolled = scrollSpy.mock.instances[0] as HTMLElement;
    expect(scrolled.getAttribute('data-embedded-finding')).toBe('instructions');
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

describe('the timeliness demotion has a reachable EXIT (Opus outer r9)', () => {
  // The demotion is an effective-status derivation, so the STORED status is
  // still reviewed_correct and the <select> already reads "Reviewed -
  // correct" -- re-picking it fires no change event. Without an explicit
  // control the field is permanently amber and nothing the reviewer clicks
  // can clear it.
  const signedOff: FormField = {
    ...TEXT_FIELD,
    _review: { status: 'reviewed_correct', seen_fingerprints: [] },
  } as unknown as FormField;

  it('the dropdown still SHOWS reviewed-correct while the field is demoted', () => {
    // Why the re-confirm control has to exist: the demotion never writes, so
    // the stored status -- and the <select>'s value -- stay
    // "reviewed_correct". A real browser fires no change event when the user
    // re-picks the option already selected, so the dropdown cannot be the
    // exit. (jsdom's fireEvent.change dispatches unconditionally, so that
    // browser behavior is not directly assertable here -- this pins the
    // precondition that makes it true.)
    render(
      <FieldEditor field={signedOff} schema={makeSchema(signedOff)}
        onUpdateField={vi.fn()} authorTier
        lintFindings={[instructionsFinding]} />,
    );
    expect((screen.getByLabelText('Review status') as HTMLSelectElement).value)
      .toBe('reviewed_correct');
    // ...and the field IS demoted, so an exit is genuinely needed.
    expect(statusFromFindings(signedOff, [instructionsFinding])).toBe('review');
  });

  it('offers a re-confirm control that re-stamps the fingerprints', () => {
    const onUpdateField = vi.fn();
    render(
      <FieldEditor field={signedOff} schema={makeSchema(signedOff)}
        onUpdateField={onUpdateField} authorTier
        lintFindings={[instructionsFinding]} />,
    );
    fireEvent.click(screen.getByTestId('reconfirm-review'));
    const updated = onUpdateField.mock.calls[0][0] as FormField;
    expect(updated._review?.seen_fingerprints)
      .toEqual([findingFingerprint(instructionsFinding)]);
  });

  it('offers NO re-confirm while a lint ERROR is on the field (it would no-op)', () => {
    // Red wins over the timeliness clause in both effectiveStatus and
    // isCountedReviewed, so re-stamping would change nothing visible -- a
    // success-shaped no-op (Opus outer review, pass 10). An ERROR is fixed,
    // not confirmed away.
    const newError: LintFinding = {
      severity: 'ERROR', rule: 'field-unbacked',
      path: 'fields[0] (id=phone)', message: 'this field names no PDF box',
      field_id: 'phone',
    };
    render(
      <FieldEditor field={signedOff} schema={makeSchema(signedOff)}
        onUpdateField={vi.fn()} authorTier lintFindings={[newError]} />,
    );
    // The field IS demoted-and-red...
    expect(statusFromFindings(signedOff, [newError])).toBe('error');
    // ...and no re-confirm button is offered.
    expect(screen.queryByTestId('reconfirm-review')).toBeNull();
  });

  it('shows no re-confirm control when the sign-off is still current', () => {
    const current: FormField = {
      ...TEXT_FIELD,
      _review: {
        status: 'reviewed_correct',
        seen_fingerprints: [findingFingerprint(instructionsFinding)],
      },
    } as unknown as FormField;
    render(
      <FieldEditor field={current} schema={makeSchema(current)}
        onUpdateField={vi.fn()} authorTier lintFindings={[instructionsFinding]} />,
    );
    expect(screen.queryByTestId('reconfirm-review')).toBeNull();
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
