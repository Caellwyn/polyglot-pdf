/**
 * ConnectionTimeoutModal - connection-timeout recovery prompt (bd polyglot-pdf-jf6w.2).
 *
 * Shown when the voice connection drops in a way the app cannot silently
 * auto-recover from (the WebFormConnection surfaces the terminal
 * "reconnect_failed" status -- bd polyglot-pdf-jf6w.3). Offers a primary
 * "reconnect" button that re-runs the existing connect/restore path; the client
 * already owns all field state, and vmxx's silent-resume suppresses the
 * re-greeting, so the resume picks up at the current field.
 *
 * Mirrors the DisclaimerModal house pattern (inline per-language copy, no i18n
 * library; copy lives in connectionTimeoutTranslations.ts). Unlike the
 * disclaimer, this modal IS dismissible -- the user may choose to stay on the
 * form without reconnecting -- so a secondary "not now" button and an optional
 * onCancel are provided. The copy renders in the user's selectedLanguage with an
 * English fallback.
 */

import React from 'react';
import { CONNECTION_TIMEOUT_TRANSLATIONS } from './connectionTimeoutTranslations';
import './ConnectionTimeoutModal.css';

export interface ConnectionTimeoutModalProps {
  isOpen: boolean;
  selectedLanguage: string;
  onReconnect: () => void;
  onCancel?: () => void;
}

export function ConnectionTimeoutModal({
  isOpen,
  selectedLanguage,
  onReconnect,
  onCancel,
}: ConnectionTimeoutModalProps) {
  if (!isOpen) return null;

  // Copy in the user's language, fallback to English (mirrors DisclaimerModal).
  const copy =
    CONNECTION_TIMEOUT_TRANSLATIONS[selectedLanguage] ||
    CONNECTION_TIMEOUT_TRANSLATIONS['English'];

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
          {copy.title}
        </h2>

        <p className="connection-timeout-modal-message">{copy.message}</p>

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
      </div>
    </div>
  );
}
