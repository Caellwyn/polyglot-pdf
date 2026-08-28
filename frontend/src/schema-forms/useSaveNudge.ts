/**
 * WHEN to prompt a client to save (bd polyglot-pdf-dft1).
 *
 * Extracted from the overlay so the timing rules are testable on their own.
 * The component decides how a nudge LOOKS; this decides when it appears, and
 * the "when" is where the judgment lives:
 *
 *   EARLY  -- once, after the first section is complete. There is work worth
 *             saving by then, but losing it would not yet be devastating, so
 *             this is the cheap moment to teach the habit. Dismissible, and it
 *             STAYS dismissed: nagging a client filling a legal form is its own
 *             harm.
 *   ENDING -- when the voice assistant is about to stop, for any reason (the
 *             spend ceiling, an idle timeout, the form finishing). This is the
 *             last moment before a client might close the tab.
 *
 * PERSISTED PER FORM SESSION, not per page load. A client who reloads has not
 * un-learned the nudge, and showing it again on every refresh would train them
 * to dismiss it reflexively -- which is exactly the habit that loses their
 * work.
 */
import { useCallback, useEffect, useState } from 'react';

import type { SaveNudgeVariant } from './components/SaveNudge';

const STORAGE_PREFIX = 'polyglot.saveNudge.';

export interface UseSaveNudgeArgs {
  /** Null until the form session exists; nothing is shown before then. */
  formSessionId: string | null | undefined;
  /** How many sections the client has completed. */
  completedSectionCount: number;
  /** True when the voice assistant is ending, for whatever reason. */
  voiceEnding: boolean;
  /** Only client-link sessions get nudged; staff have their own workflow. */
  enabled: boolean;
  /** Injected for tests. */
  storage?: Pick<Storage, 'getItem' | 'setItem'>;
}

export interface UseSaveNudgeResult {
  variant: SaveNudgeVariant | null;
  dismiss: () => void;
  /** Call after a successful save: the client has the habit, stop asking. */
  markSaved: () => void;
}

function readFlag(
  storage: Pick<Storage, 'getItem' | 'setItem'> | undefined,
  key: string,
): boolean {
  try {
    return storage?.getItem(key) === '1';
  } catch {
    // Private browsing and some embedded webviews throw on storage access.
    // A client who cannot persist the flag should still see the form; the
    // cost is one extra nudge, not a broken page.
    return false;
  }
}

function writeFlag(
  storage: Pick<Storage, 'getItem' | 'setItem'> | undefined,
  key: string,
): void {
  try {
    storage?.setItem(key, '1');
  } catch {
    // See readFlag.
  }
}

export function useSaveNudge({
  formSessionId,
  completedSectionCount,
  voiceEnding,
  enabled,
  storage,
}: UseSaveNudgeArgs): UseSaveNudgeResult {
  const store = storage ?? (typeof window !== 'undefined' ? window.sessionStorage : undefined);
  const earlyKey = `${STORAGE_PREFIX}early.${formSessionId ?? ''}`;
  const endingKey = `${STORAGE_PREFIX}ending.${formSessionId ?? ''}`;

  const [earlyDone, setEarlyDone] = useState(false);
  const [endingDone, setEndingDone] = useState(false);

  // Re-read when the session changes: a resumed form is a new session id, and
  // its flags are its own.
  useEffect(() => {
    if (!formSessionId) return;
    setEarlyDone(readFlag(store, earlyKey));
    setEndingDone(readFlag(store, endingKey));
  }, [formSessionId, store, earlyKey, endingKey]);

  let variant: SaveNudgeVariant | null = null;
  if (enabled && formSessionId) {
    if (voiceEnding && !endingDone) {
      // The ending nudge OUTRANKS the early one: if both would fire, the
      // client is about to lose voice and that is the more urgent message.
      variant = 'ending';
    } else if (!earlyDone && completedSectionCount >= 1) {
      variant = 'early';
    }
  }

  const dismiss = useCallback(() => {
    if (variant === 'ending') {
      setEndingDone(true);
      writeFlag(store, endingKey);
    } else if (variant === 'early') {
      setEarlyDone(true);
      writeFlag(store, earlyKey);
    }
  }, [variant, store, earlyKey, endingKey]);

  const markSaved = useCallback(() => {
    // A client who has saved once knows how. Silence BOTH nudges rather than
    // only the one showing -- the early nudge exists to teach the habit, and
    // they have it.
    setEarlyDone(true);
    setEndingDone(true);
    writeFlag(store, earlyKey);
    writeFlag(store, endingKey);
  }, [store, earlyKey, endingKey]);

  return { variant, dismiss, markSaved };
}
