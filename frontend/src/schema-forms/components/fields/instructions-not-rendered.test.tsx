/**
 * help.instructions must NOT render as visible form text (bd
 * polyglot-pdf-0x10.2): it is reference material for the voice AI (fed to the
 * SI/guidance paths from the schema), and this is a voice-first product --
 * long printed instructions under every field fight that. The short
 * user-facing hint remains the input placeholder (format_hint / help.inline).
 *
 * help.details is under the SAME contract (bd polyglot-pdf-wsao.1): verbatim
 * official-booklet excerpts for the AI's guidance block + secretary catalog,
 * never on-screen -- pages of IRS/USCIS prose under a field would be worse
 * than instructions ever were.
 *
 * One test per field component family so a future "helpful" re-add fails
 * loudly here.
 */

import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import { TextField } from './TextField';
import { TextAreaField } from './TextAreaField';
import { DateField } from './DateField';
import { SelectField } from './SelectField';
import { RadioField } from './RadioField';
import { CheckboxField } from './CheckboxField';
import type { FormField } from '../../types/schema';

const INSTRUCTIONS =
  'Reason You Are Submitting: you must check the box to indicate the reason.';
const DETAILS =
  'a. Nonresident alien required to get an ITIN to claim tax treaty benefit. ' +
  'If you check this box you must also check box h.';

function fieldOf(type: string, extra: Partial<FormField> = {}): FormField {
  return {
    id: 'f1',
    name: 'F1',
    spoken_name: 'field one',
    type,
    section_id: 's1',
    help: { instructions: INSTRUCTIONS, details: DETAILS },
    ...extra,
  } as unknown as FormField;
}

const OPTIONS = [
  { value: 'a', label: 'Choice A' },
  { value: 'b', label: 'Choice B' },
];

afterEach(cleanup);

describe('help.instructions is AI guidance, never on-screen text (bd 0x10.2)', () => {
  const cases: Array<[string, () => void]> = [
    ['TextField', () => {
      render(<TextField field={fieldOf('text')} value="" onChange={vi.fn()} />);
    }],
    ['TextAreaField', () => {
      render(<TextAreaField field={fieldOf('textarea')} value="" onChange={vi.fn()} />);
    }],
    ['DateField', () => {
      render(<DateField field={fieldOf('date')} value="" onChange={vi.fn()} />);
    }],
    ['SelectField', () => {
      render(
        <SelectField field={fieldOf('select', { options: OPTIONS })} value="" onChange={vi.fn()} />,
      );
    }],
    ['RadioField', () => {
      render(
        <RadioField field={fieldOf('radio', { options: OPTIONS })} value="" onChange={vi.fn()} />,
      );
    }],
    ['CheckboxField', () => {
      render(<CheckboxField field={fieldOf('checkbox')} value={false} onChange={vi.fn()} />);
    }],
    ['CheckboxField (group)', () => {
      render(
        <CheckboxField
          field={fieldOf('checkbox_group', { options: OPTIONS })}
          value={[]}
          onChange={vi.fn()}
        />,
      );
    }],
  ];

  it.each(cases)('%s renders no instructions text', (_name, doRender) => {
    doRender();
    expect(screen.queryByText(INSTRUCTIONS)).toBeNull();
    expect(document.querySelector('.form-field__instructions')).toBeNull();
  });

  it.each(cases)('%s renders no details text (bd wsao.1)', (_name, doRender) => {
    doRender();
    expect(screen.queryByText(DETAILS)).toBeNull();
    // Substring guard too: details must not surface inside any rendered node.
    expect(document.body.textContent).not.toContain('tax treaty benefit');
  });
});
