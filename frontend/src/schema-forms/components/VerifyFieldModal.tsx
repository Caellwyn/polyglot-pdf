/**
 * VerifyFieldModal - the explicit manual-verification gesture (bd
 * polyglot-pdf-96um6).
 *
 * WHY THIS EXISTS. "Verified" is load-bearing in this product's audit record:
 * the firm reviews a draft and the applicant undertakes review
 * (docs/standards/confirmation-and-audit.md). It used to be produced by a
 * keystroke -- tabbing through three fields wrote three audit records -- and bd
 * polyglot-pdf-uum5g stopped that. This modal is what REPLACES it: the
 * keyboard-only way to make the claim deliberately, once, per field.
 *
 * Until this shipped there was NO keyboard path to verification at all (only the
 * verbal confirm and the skip control), so a typing-only user could not finish a
 * form. That is the hole this fills.
 *
 * THE GESTURE: Enter on a filled field opens this; the checkbox takes focus, so
 * Enter-then-Enter or Enter-then-space verifies. Escape dismisses, leaving the
 * field UNVERIFIED with the typed value intact -- a mis-pressed Enter must never
 * cost the user their typing. Dismissal does nothing to the value at all, which
 * is the safest possible implementation of that promise: the value was already
 * stored on keystroke.
 *
 * NOT A NEW MODAL FRAMEWORK: this mirrors the ConnectionTimeoutModal /
 * DisclaimerModal house pattern (inline per-language copy in its own
 * translations module, role="dialog" + aria-modal, its own .css) and takes its
 * Escape/click-outside handling from FieldEditPopover (pointerdown, not click,
 * so a drag starting outside dismisses too).
 */

import React, { useEffect, useRef, useState } from 'react';
import { getVerifyFieldCopy } from './verifyFieldTranslations';
import './VerifyFieldModal.css';

interface VerifyFieldModalProps {
  isOpen: boolean;
  /** The field's human-readable name, from the form kit (never translated). */
  fieldName: string;
  /**
   * The value being verified, shown back so the user checks the real thing.
   * A single checkbox passes a BOOLEAN, which renders as a translated Yes/No --
   * "true"/"false" is meaningless to a user, and excluding checkboxes instead
   * would leave them with no keyboard verify path at all.
   */
  value: string | boolean;
  selectedLanguage: string;
  /** Called when the user asserts the answer is correct. */
  onVerify: () => void;
  /** Called on Escape, click-outside, or the dismiss button. Leaves it unverified. */
  onCancel: () => void;
}

export function VerifyFieldModal({
  isOpen,
  fieldName,
  value,
  selectedLanguage,
  onVerify,
  onCancel,
}: VerifyFieldModalProps) {
  const copy = getVerifyFieldCopy(selectedLanguage);
  const checkboxRef = useRef<HTMLInputElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const [checked, setChecked] = useState(false);

  // The checkbox takes focus so the gesture is two keystrokes (bd 96um6). A
  // focused checkbox responds to BOTH Enter and space, which is why the bead
  // specifies focusing it rather than the confirm button.
  useEffect(() => {
    if (isOpen) {
      setChecked(false); // never inherit a previous field's tick
      checkboxRef.current?.focus();
    }
  }, [isOpen]);

  // Escape + click-outside dismissal, same shape as FieldEditPopover.
  useEffect(() => {
    if (!isOpen) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation();
        onCancel();
      }
    };
    const onPointerDown = (e: PointerEvent) => {
      if (contentRef.current && !contentRef.current.contains(e.target as Node)) {
        onCancel();
      }
    };
    document.addEventListener('keydown', onKeyDown);
    document.addEventListener('pointerdown', onPointerDown);
    return () => {
      document.removeEventListener('keydown', onKeyDown);
      document.removeEventListener('pointerdown', onPointerDown);
    };
  }, [isOpen, onCancel]);

  if (!isOpen) return null;

  // Enter anywhere in the modal verifies once the box is ticked. This is what
  // makes Enter-then-Enter work: the first Enter opened the modal, the second
  // lands here with the checkbox focused.
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      // A BUTTON handles its own Enter (it activates natively and fires onClick),
      // so intercepting here would swallow it -- Enter on "Not yet" did nothing
      // at all, a silent dead end for anyone who tabs to it (fresh-eyes finding).
      if ((e.target as HTMLElement)?.tagName === 'BUTTON') return;

      e.preventDefault();
      e.stopPropagation(); // never reach the form's submit handler
      if (checked || e.target === checkboxRef.current) {
        onVerify();
      }
      return;
    }

    // SPACE on the focused checkbox completes the gesture too, because the exit
    // criterion is "a second Enter OR SPACE verifies" -- and for eleven review
    // rounds this modal only handled Enter while I scored that criterion PASS.
    // My own test even titled itself "SPACE ... then the confirm button is live",
    // documenting that space did NOT verify, and I read it as coverage.
    //
    // Space is NOT intercepted: a focused checkbox toggles itself natively on
    // space, and preventDefault would kill that. So the toggle is allowed to
    // land and the verify runs after it -- which also means space UNTICKING a
    // ticked box must NOT verify, hence reading the post-toggle state rather
    // than assuming space means "on".
    // Space is handled on KEY UP, not keydown -- see handleKeyUp below.
  };

  // SPACE completes the gesture, on KEY UP.
  //
  // Not intercepted on keydown: a focused checkbox toggles itself natively on
  // space, and preventDefault would kill that. The toggle lands between keydown
  // and keyup, so keyup reads the SETTLED state synchronously -- which is why
  // this is not a deferred callback. An earlier version used
  // requestAnimationFrame and could have fired onVerify after the modal
  // unmounted, holding a stale closure; keyup has no such window.
  //
  // Reading the post-toggle state also means space UNTICKING a ticked box does
  // not verify, which is the correct reading of "space verifies".
  const handleKeyUp = (e: React.KeyboardEvent) => {
    if (e.key !== ' ') return;
    if (e.target !== checkboxRef.current) return;
    e.stopPropagation();
    if (checkboxRef.current?.checked) onVerify();
  };

  return (
    <div className="verify-field-modal-overlay" data-testid="verify-field-modal">
      <div
        ref={contentRef}
        className="verify-field-modal-content"
        role="dialog"
        aria-modal="true"
        aria-labelledby="verify-field-title"
        onKeyDown={handleKeyDown}
      onKeyUp={handleKeyUp}
      >
        <h2 id="verify-field-title" className="verify-field-modal-title">
          {copy.title}
        </h2>

        <div className="verify-field-modal-field">
          <span className="verify-field-modal-field-label">
            {copy.fieldLabelPrefix}: {fieldName}
          </span>
          {/* The value is shown back so the user verifies the REAL answer rather
              than a remembered one. */}
          <span className="verify-field-modal-value" data-testid="verify-field-value">
            {typeof value === 'boolean' ? (value ? copy.booleanYes : copy.booleanNo) : value}
          </span>
        </div>

        <label className="verify-field-modal-checkbox-row">
          <input
            ref={checkboxRef}
            type="checkbox"
            checked={checked}
            onChange={e => setChecked(e.target.checked)}
            data-testid="verify-field-checkbox"
          />
          <span>{copy.checkboxLabel}</span>
        </label>

        <div className="verify-field-modal-actions">
          <button
            type="button"
            className="verify-field-modal-cancel"
            onClick={onCancel}
            data-testid="verify-field-cancel"
          >
            {copy.cancelButton}
          </button>
          <button
            type="button"
            className="verify-field-modal-confirm"
            onClick={onVerify}
            disabled={!checked}
            data-testid="verify-field-confirm"
          >
            {copy.confirmButton}
          </button>
        </div>
      </div>
    </div>
  );
}

export default VerifyFieldModal;
