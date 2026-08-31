/**
 * Speak one of the app's own safety notices (bd polyglot-pdf-dft1).
 *
 * Posts a KEY, never text: the words live server-side, which is what keeps a
 * free route from becoming an open text-to-speech service. See
 * backend/services/notice_tts.py.
 *
 * FREE ON PURPOSE. /api/tts/notice is require_auth, not the paid dependency --
 * speaking "save your form now" must not burn the client's link, and must
 * still work for a client whose budget is already exhausted (maintainer,
 * 2026-08-27).
 *
 * BEST-EFFORT ALWAYS. Every failure resolves quietly: the same words are on
 * screen, and a client trying to save their work should never see a speech
 * error.
 */

/** Keys the backend will speak. Mirrors KNOWN_NOTICES. */
export const NOTICE_SAVE_EARLY = 'save_early';
export const NOTICE_VOICE_ENDING = 'voice_ending';

export interface NoticeSpeechDeps {
  backendUrl: string;
  getToken?: () => Promise<string | undefined>;
  /** Injected for tests; defaults to the real Audio element.
   *
   * Takes the BLOB, not a URL: object-URL creation is the caller's business,
   * and doing it inside `speak` made the whole path untestable (jsdom has no
   * URL.createObjectURL, so it threw and the silent-failure catch hid it --
   * a passing-looking test that never played anything). */
  play?: (audio: Blob) => Promise<void>;
  fetchImpl?: typeof fetch;
}

async function playViaAudio(clip: Blob): Promise<void> {
  const url = URL.createObjectURL(clip);
  try {
    const audio = new Audio(url);
    await audio.play();
  } finally {
    // Revoke only after play() has been kicked off, or the element may lose
    // its source mid-load on slower devices.
    URL.revokeObjectURL(url);
  }
}

export function createNoticeSpeaker(deps: NoticeSpeechDeps) {
  const doFetch = deps.fetchImpl ?? ((...a: Parameters<typeof fetch>) => fetch(...a));
  const play = deps.play ?? playViaAudio;

  return async function speak(_text: string, language?: string, notice?: string): Promise<void> {
    // `_text` is accepted so this matches SaveNudge's `speak` signature, and
    // deliberately NOT sent: the server owns the words.
    const key = notice ?? NOTICE_SAVE_EARLY;
    try {
      const token = deps.getToken ? await deps.getToken() : undefined;
      const response = await doFetch(`${deps.backendUrl}/api/tts/notice`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ notice: key, language }),
      });
      if (!response.ok) return;             // silent: the words are on screen
      await play(await response.blob());
    } catch {
      // Network, autoplay policy, decode failure -- all silent by design.
    }
  };
}
