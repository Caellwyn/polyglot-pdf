/**
 * help.instructions must NOT render as visible form text (bd
 * polyglot-pdf-0x10.2): it is reference material for the voice AI (fed to the
 * SI/guidance paths from the schema), and this is a voice-first product --
 * long printed instructions under every field fight that. The short
 * user-facing hint remains the input placeholder (format_hint / help.inline).
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

function fieldOf(type: string, extra: Partial<FormField> = {}): FormField {
  return {
    id: 'f1',
    name: 'F1',
    spoken_name: 'field one',
    type,
    section_id: 's1',
    help: { instructions: INSTRUCTIONS },
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
});
