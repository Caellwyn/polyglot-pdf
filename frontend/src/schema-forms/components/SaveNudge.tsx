/**
 * Encourage a client to save their form (bd polyglot-pdf-dft1).
 *
 * A safety net nobody discovers is not a safety net. The saved PDF is the only
 * thing standing between a client and losing every answer -- the browser drops
 * form state after 60 minutes -- so the prompt to save has to find them, not
 * wait to be found.
 *
 * TWO MOMENTS, both asked for by the maintainer (2026-08-27):
 *   EARLY  -- once, after the first section, while there is work worth saving
 *             but before losing it would hurt much. Dismissible, and it stays
 *             dismissed.
 *   ENDING -- when the voice assistant is finishing. Stronger, because this is
 *             the last moment before a client might close the tab, and it is
 *             also the message bd polyglot-pdf-cke6v needs when a client hits
 *             their spend ceiling.
 *
 * SPOKEN, NOT JUST SHOWN. A client working by voice may not be reading the
 * screen at all, so the body text is handed to the TTS route in the client's
 * own language. Speech is best-effort: a failure to speak must never block the
 * modal that carries the same words in writing.
 */
import { useEffect, useRef } from 'react';

import { resumeStrings } from '../resumeStrings';

export type SaveNudgeVariant = 'early' | 'ending';

export interface SaveNudgeProps {
  isOpen: boolean;
  variant: SaveNudgeVariant;
  selectedLanguage?: string;
  /** Speak the body text. Best-effort; rejection is swallowed. */
  speak?: (text: string, language?: string) => Promise<void>;
  onSave: () => void;
  onDismiss: () => void;
}

export function SaveNudge({
  isOpen,
  variant,
  selectedLanguage,
  speak,
  onSave,
  onDismiss,
}: SaveNudgeProps) {
  const t = resumeStrings(selectedLanguage);
  const spokenFor = useRef<string | null>(null);

  const title = variant === 'ending' ? t.voiceEndingTitle : t.saveNudgeTitle;
  const body = variant === 'ending' ? t.voiceEndingBody : t.saveNudgeBody;

  useEffect(() => {
    if (!isOpen || !speak) return;
    // Speak ONCE per opening. Without this guard a re-render mid-utterance
    // starts a second voice over the first, which on a phone sounds like the
    // app malfunctioning at the exact moment it is asking for trust.
    const key = `${variant}:${selectedLanguage ?? ''}`;
    if (spokenFor.current === key) return;
    spokenFor.current = key;
    void speak(body, selectedLanguage).catch(() => {
      // Best-effort by design: the words are on screen either way.
    });
  }, [isOpen, speak, body, variant, selectedLanguage]);

  useEffect(() => {
    if (!isOpen) spokenFor.current = null;   // so a later opening speaks again
  }, [isOpen]);

  if (!isOpen) return null;

  return (
    <div
      className={`save-nudge save-nudge--${variant}`}
      role="dialog"
      aria-modal="true"
      aria-label={title}
    >
      <h2>{title}</h2>
      <p>{body}</p>
      <button type="button" className="save-nudge-save" onClick={onSave}>
        {t.saveNudgeAction}
      </button>
      {/* The EARLY nudge is dismissible; the ENDING one is not -- a client
          about to lose voice should not be able to wave away the only
          instruction that preserves their work by reflex. They can still
          ignore it and keep typing; it simply does not offer "not now". */}
      {variant === 'early' && (
        <button type="button" className="save-nudge-dismiss" onClick={onDismiss}>
          {t.saveNudgeDismiss}
        </button>
      )}
    </div>
  );
}
