/**
 * ConnectionTimeoutModal - connection-recovery prompt (bd polyglot-pdf-jf6w.2).
 *
 * Three variants:
 *
 * - "timeout" (default): shown when the voice connection drops in a way the app
 *   cannot silently auto-recover from (WebFormConnection surfaces the terminal
 *   "reconnect_failed" status -- bd polyglot-pdf-jf6w.3). Offers a primary
 *   "reconnect" button that re-runs the existing connect/restore path; the client
 *   already owns all field state, and vmxx's silent-resume suppresses the
 *   re-greeting, so the resume picks up at the current field. Dismissible via an
 *   optional secondary "not now" button.
 *
 * - "reconnecting" (bd polyglot-pdf-ppfy): a TRANSIENT "please wait" state shown
 *   while the app is auto-reconnecting after a SPONTANEOUS AI-session drop (e.g. a
 *   Gemini 1011 the backend detects and forwards as gemini_session_dropped). It is
 *   passive -- no buttons, not user-dismissible -- and the caller clears it by
 *   flipping isOpen once the session recovers (status -> connected), or swaps to
 *   the "timeout" variant if auto-reconnect gives up (status -> reconnect_failed).
 *
 * - "budget_exhausted" (bd polyglot-pdf-cke6v): the link's SPEND CEILING is used
 *   up. Terminal like "timeout", but with NO RECOVERY action -- a Reconnect
 *   that cannot possibly work reads as a broken app, which is the whole
 *   complaint this variant answers. It DOES carry a dismiss (and must: the
 *   overlay is full-viewport, so a button-less version blocked the typing
 *   and printing its own copy promises). The copy's job is to say what
 *   happened and what still works: typing the remaining answers, and
 *   download/print/preview (all true -- retrieval never redeems the link).
 *
 * Mirrors the DisclaimerModal house pattern (inline per-language copy, no i18n
 * library; copy lives in connectionTimeoutTranslations.ts). The copy renders in
 * the user's selectedLanguage with an English fallback.
 */

import React from 'react';
import { CONNECTION_TIMEOUT_TRANSLATIONS } from './connectionTimeoutTranslations';
import './ConnectionTimeoutModal.css';

export interface ConnectionTimeoutModalProps {
  isOpen: boolean;
  selectedLanguage: string;
  onReconnect: () => void;
  onCancel?: () => void;
  /**
   * "timeout" (default) = terminal give-up with a reconnect button.
   * "reconnecting" = transient auto-reconnect notice, no buttons (bd ppfy).
   * "budget_exhausted" = terminal, no RECOVERY action but dismissible: the
   *   link's spend ceiling is used up, so reconnecting is impossible rather
   *   than merely unlikely. Requires onCancel (bd cke6v).
   */
  variant?: 'timeout' | 'reconnecting' | 'budget_exhausted';
}

export function ConnectionTimeoutModal({
  isOpen,
  selectedLanguage,
  onReconnect,
  onCancel,
  variant = 'timeout',
}: ConnectionTimeoutModalProps) {
  if (!isOpen) return null;

  // Copy in the user's language, fallback to English (mirrors DisclaimerModal).
  const copy =
    CONNECTION_TIMEOUT_TRANSLATIONS[selectedLanguage] ||
    CONNECTION_TIMEOUT_TRANSLATIONS['English'];

  const isReconnecting = variant === 'reconnecting';
  const isBudgetExhausted = variant === 'budget_exhausted';
  const title = isReconnecting
    ? copy.reconnectingTitle
    : isBudgetExhausted
      ? copy.budgetExhaustedTitle
      : copy.title;
  const message = isReconnecting
    ? copy.reconnectingMessage
    : isBudgetExhausted
      ? copy.budgetExhaustedMessage
      : copy.message;

  return (
    <div
      className="connection-timeout-modal-overlay"
      onClick={(e) => e.stopPropagation()}
    >
      <div
        className="connection-timeout-modal-content"
        role="dialog"
        aria-modal="true"
        aria-labelledby="connection-timeout-title"
      >
        <h2
          id="connection-timeout-title"
          className="connection-timeout-modal-title"
        >
          {title}
        </h2>

        <p className="connection-timeout-modal-message">{message}</p>

        {/* The transient reconnecting variant is passive: a spinner, no actions.
            The terminal timeout variant keeps its reconnect / not-now buttons.

            budget_exhausted gets NO RECOVERY action -- no Reconnect, because
            nothing would work, and no spinner, because nothing is coming. But
            it MUST be dismissible (Opus cross-surface r3): this overlay is
            position:fixed at z-index 10000 over the whole viewport, and the
            message itself tells the client they can still type, download and
            print. A terminal message that blocks the page contradicts its own
            copy -- and because the ending save-nudge silences itself once the
            client saves, "press Save" would otherwise summon a scrim with no
            way out. Acknowledging is not recovering. */}
        {isBudgetExhausted ? (
          // REQUIRES onCancel. Rendering the button without a handler would
          // give the client a dead control on a full-viewport overlay -- the
          // unclosable scrim this variant exists to avoid, wearing a button
          // (Opus cross-surface r4). Failing loudly in dev beats shipping a
          // trap: both current callers pass it, and a future one that forgets
          // sees an obviously-missing dismiss rather than a fake one.
          onCancel ? (
            <div className="connection-timeout-modal-buttons">
              <button
                className="connection-timeout-modal-button connection-timeout-modal-button--primary"
                onClick={onCancel}
                type="button"
              >
                {copy.budgetExhaustedDismiss}
              </button>
            </div>
          ) : null
        ) : isReconnecting ? (
          <div
            className="connection-timeout-modal-spinner"
            role="status"
            aria-live="polite"
          />
        ) : (
          <div className="connection-timeout-modal-buttons">
            {onCancel && (
              <button
                className="connection-timeout-modal-button connection-timeout-modal-button--secondary"
                onClick={onCancel}
                type="button"
              >
                {copy.cancelButton}
              </button>
            )}
            <button
              className="connection-timeout-modal-button connection-timeout-modal-button--primary"
              onClick={onReconnect}
              type="button"
            >
              {copy.reconnectButton}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
