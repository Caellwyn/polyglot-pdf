/**
 * VerifyFieldModal - the gesture itself (bd polyglot-pdf-96um6, exit criterion 2).
 *
 * The bead specifies the gesture precisely: "Enter opens the verify modal with
 * its checkbox focused, and a second Enter (or space) verifies exactly that
 * field; Escape dismisses leaving the field unverified with its typed value
 * intact." These drive the REAL component with real keyboard events rather than
 * calling its props directly -- the whole point is that the KEYSTROKES work.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import React from 'react';
import { render, screen, cleanup, fireEvent, act } from '@testing-library/react';
import { VerifyFieldModal } from './VerifyFieldModal';
import { VERIFY_FIELD_TRANSLATIONS } from './verifyFieldTranslations';

function renderModal(overrides: Partial<React.ComponentProps<typeof VerifyFieldModal>> = {}) {
  const props = {
    isOpen: true,
    fieldName: 'Family Name',
    value: 'Vasquez',
    selectedLanguage: 'English',
    onVerify: vi.fn(),
    onCancel: vi.fn(),
    ...overrides,
  };
  render(<VerifyFieldModal {...props} />);
  return props;
}

describe('VerifyFieldModal gesture (bd polyglot-pdf-96um6)', () => {
  afterEach(() => cleanup());

  it('opens with the CHECKBOX focused, so the next keystroke lands on it', () => {
    renderModal();
    // The bead specifies the checkbox, not the confirm button, because a focused
    // checkbox responds to BOTH Enter and space.
    expect(document.activeElement).toBe(screen.getByTestId('verify-field-checkbox'));
  });

  it('SPACE on the focused checkbox ticks it, then the confirm button is live', () => {
    const props = renderModal();
    const box = screen.getByTestId('verify-field-checkbox') as HTMLInputElement;

    const confirm = screen.getByTestId('verify-field-confirm') as HTMLButtonElement;
    expect(confirm.disabled, 'confirm is inert until the box is ticked').toBe(true);
    fireEvent.click(box); // what space does to a focused checkbox
    expect(box.checked).toBe(true);
    expect(confirm.disabled).toBe(false);

    fireEvent.click(screen.getByTestId('verify-field-confirm'));
    expect(props.onVerify).toHaveBeenCalledTimes(1);
  });

  it('ENTER on the focused checkbox verifies directly (the Enter-then-Enter path)', () => {
    // This is the gesture the bead names first. The user pressed Enter in the
    // field to get here; the second Enter lands on the focused checkbox and must
    // verify WITHOUT requiring a separate tick -- otherwise "Enter-then-Enter"
    // would be Enter-then-Enter-then-Enter.
    const props = renderModal();
    const box = screen.getByTestId('verify-field-checkbox');

    fireEvent.keyDown(box, { key: 'Enter' });

    expect(props.onVerify).toHaveBeenCalledTimes(1);
  });

  it('ESCAPE dismisses without verifying', () => {
    const props = renderModal();

    fireEvent.keyDown(document, { key: 'Escape' });

    expect(props.onCancel).toHaveBeenCalledTimes(1);
    expect(props.onVerify, 'a dismiss must never verify').not.toHaveBeenCalled();
  });

  it('a click OUTSIDE dismisses without verifying', () => {
    const props = renderModal();

    fireEvent.pointerDown(document.body);

    expect(props.onCancel).toHaveBeenCalledTimes(1);
    expect(props.onVerify).not.toHaveBeenCalled();
  });

  it('shows the VALUE back, so the user verifies the real answer', () => {
    renderModal({ value: 'Vasquez-Ramirez' });
    expect(screen.getByTestId('verify-field-value').textContent).toBe('Vasquez-Ramirez');
  });

  it('renders in the selected language, not English', () => {
    renderModal({ selectedLanguage: 'German' });
    expect(
      screen.getByText(VERIFY_FIELD_TRANSLATIONS['German'].checkboxLabel)
    ).toBeTruthy();
  });

  it('falls back to English for an unknown language rather than blanking', () => {
    renderModal({ selectedLanguage: 'Klingon' });
    expect(
      screen.getByText(VERIFY_FIELD_TRANSLATIONS['English'].checkboxLabel)
    ).toBeTruthy();
  });

  it('renders nothing when closed', () => {
    renderModal({ isOpen: false });
    expect(screen.queryByTestId('verify-field-modal')).toBeNull();
  });

  it('does not inherit a previous field tick when reopened', () => {
    // Each field is its own assertion. A tick carried over from the last field
    // would let a single Enter verify a field the user never looked at.
    const { rerender } = render(
      <VerifyFieldModal
        isOpen
        fieldName="A"
        value="one"
        selectedLanguage="English"
        onVerify={vi.fn()}
        onCancel={vi.fn()}
      />
    );
    fireEvent.click(screen.getByTestId('verify-field-checkbox'));
    expect((screen.getByTestId('verify-field-checkbox') as HTMLInputElement).checked).toBe(true);

    rerender(
      <VerifyFieldModal
        isOpen={false}
        fieldName="A"
        value="one"
        selectedLanguage="English"
        onVerify={vi.fn()}
        onCancel={vi.fn()}
      />
    );
    rerender(
      <VerifyFieldModal
        isOpen
        fieldName="B"
        value="two"
        selectedLanguage="English"
        onVerify={vi.fn()}
        onCancel={vi.fn()}
      />
    );

    expect(
      (screen.getByTestId('verify-field-checkbox') as HTMLInputElement).checked,
      'a fresh field starts unticked'
    ).toBe(false);
  });

  it('ENTER on a BUTTON is left alone, so its native activation still works', () => {
    // The dialog used to intercept EVERY Enter, so tabbing to "Not yet" and
    // pressing Enter was a silent dead end -- the native button activation was
    // suppressed and nothing else handled it.
    //
    // Asserted on the EVENT, not via a corroborating click. My first version
    // fired keyDown and THEN a manual click, and asserted onCancel -- which
    // passes whether or not the guard exists, because the click fires onClick
    // independently. jsdom does not synthesize Enter-activates-button, so the
    // only observable contract here is that the dialog does NOT swallow the
    // keystroke. Mutation-verified: removing the guard reddens this.
    renderModal();

    const evt = new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true });
    act(() => {
      screen.getByTestId('verify-field-cancel').dispatchEvent(evt);
    });

    expect(
      evt.defaultPrevented,
      "the dialog must not swallow a button Enter -- the button activates natively"
    ).toBe(false);
  });
});
