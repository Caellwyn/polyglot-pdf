/**
 * DisclaimerModal - Mandatory disclaimer acceptance flow
 *
 * Features:
 * - Non-dismissible modal (no X button, no outside click, no ESC key)
 * - Displays disclaimer text in English
 * - "Listen Again" button triggers Gemini to re-read disclaimer
 * - "I Agree" button logs agreement and proceeds to form
 * - Button text translated to user's selected language
 */

import React, { useEffect } from 'react';
import './DisclaimerModal.css';

export interface DisclaimerModalProps {
  isOpen: boolean;
  selectedLanguage: string;
  onListenAgain: () => void;
  onAgree: () => void;
}

// Translation data for button text
const BUTTON_TRANSLATIONS: Record<string, { listenAgain: string; agree: string }> = {
  'English': { listenAgain: 'Listen Again', agree: 'I Agree' },
  'Spanish': { listenAgain: 'Escuchar de Nuevo', agree: 'Estoy de Acuerdo' },
  'Chinese': { listenAgain: '再听一次', agree: '我同意' },
  'Tagalog': { listenAgain: 'Pakinggan Muli', agree: 'Sumasang-ayon Ako' },
  'Arabic': { listenAgain: 'استمع مرة أخرى', agree: 'أوافق' },
  'French': { listenAgain: 'Écouter à Nouveau', agree: 'J\'accepte' },
  'Korean': { listenAgain: '다시 듣기', agree: '동의합니다' },
  'German': { listenAgain: 'Nochmal Anhören', agree: 'Ich Stimme Zu' },
  'Portuguese': { listenAgain: 'Ouvir Novamente', agree: 'Eu Concordo' },
  'Hindi': { listenAgain: 'फिर से सुनें', agree: 'मैं सहमत हूं' },
  'Italian': { listenAgain: 'Ascolta di Nuovo', agree: 'Accetto' },
  'Urdu': { listenAgain: 'دوبارہ سنیں', agree: 'میں متفق ہوں' },
  'Persian': { listenAgain: 'دوباره گوش کنید', agree: 'موافقم' },
  'Dutch': { listenAgain: 'Opnieuw Beluisteren', agree: 'Ik Ga Akkoord' },
  'Ukrainian': { listenAgain: 'Послухати Знову', agree: 'Я Погоджуюсь' },
  'Swedish': { listenAgain: 'Lyssna Igen', agree: 'Jag Godkänner' },
  'Afrikaans': { listenAgain: 'Luister Weer', agree: 'Ek Stem Saam' },
  'Quechua': { listenAgain: 'Wakmanta Uyariy', agree: 'Aceptani' },
};

export function DisclaimerModal({ isOpen, selectedLanguage, onListenAgain, onAgree }: DisclaimerModalProps) {
  // Prevent ESC key from closing modal
  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        e.stopPropagation();
      }
    };

    document.addEventListener('keydown', handleKeyDown, true);
    return () => document.removeEventListener('keydown', handleKeyDown, true);
  }, [isOpen]);

  // Prevent scroll on body when modal is open
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }
    return () => {
      document.body.style.overflow = '';
    };
  }, [isOpen]);

  if (!isOpen) return null;

  // Get button text in user's language, fallback to English
  const buttons = BUTTON_TRANSLATIONS[selectedLanguage] || BUTTON_TRANSLATIONS['English'];

  return (
    <div
      className="disclaimer-modal-overlay"
      onClick={(e) => e.stopPropagation()} // Prevent any click from closing
    >
      <div
        className="disclaimer-modal-content"
        role="dialog"
        aria-modal="true"
        aria-labelledby="disclaimer-title"
      >
        <h2 id="disclaimer-title" className="disclaimer-modal-title">
          Important Notice
        </h2>

        <div className="disclaimer-modal-text">
          <p>
            This tool helps you fill out your form, but it does not provide legal advice.
          </p>
          <p>
            Please review all information carefully before submitting.
          </p>
          <p>
            For complex cases, consult an immigration attorney.
          </p>
        </div>

        <div className="disclaimer-modal-buttons">
          <button
            className="disclaimer-modal-button disclaimer-modal-button--secondary"
            onClick={onListenAgain}
            type="button"
          >
            {buttons.listenAgain}
          </button>
          <button
            className="disclaimer-modal-button disclaimer-modal-button--primary"
            onClick={onAgree}
            type="button"
          >
            {buttons.agree}
          </button>
        </div>
      </div>
    </div>
  );
}
