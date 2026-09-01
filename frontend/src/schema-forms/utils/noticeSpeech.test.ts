// @vitest-environment jsdom
//
// Speaking the app's own safety notices (bd polyglot-pdf-dft1).
//
// Two properties matter:
//   1. a KEY goes on the wire, never text -- that is what keeps a free route
//      from becoming an open text-to-speech service
//   2. every failure is SILENT -- the words are on screen either way, and a
//      client trying to save their work must never see a speech error
import { describe, it, expect, vi, afterEach } from 'vitest';

import {
  createNoticeSpeaker,
  NOTICE_SAVE_EARLY,
  NOTICE_VOICE_ENDING,
} from './noticeSpeech';

function okResponse() {
  return {
    ok: true,
    status: 200,
    blob: async () => new Blob([new Uint8Array([1, 2, 3])], { type: 'audio/mpeg' }),
  } as unknown as Response;
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('notice speech', () => {
  it('sends a KEY, never the text', async () => {
    const fetchImpl = vi.fn(async () => okResponse());
    const speak = createNoticeSpeaker({
      backendUrl: 'https://api.example',
      fetchImpl: fetchImpl as unknown as typeof fetch,
      play: async () => {},
    });

    await speak('Save your form now so you do not lose your answers.', 'Spanish', NOTICE_VOICE_ENDING);

    const [url, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe('https://api.example/api/tts/notice');
    const body = JSON.parse(String(init.body));
    expect(body).toEqual({ notice: NOTICE_VOICE_ENDING, language: 'Spanish' });
    // The load-bearing assertion: the words are NOT on the wire.
    expect(JSON.stringify(body)).not.toContain('Save your form');
  });

  it('defaults to the early notice', async () => {
    const fetchImpl = vi.fn(async () => okResponse());
    const speak = createNoticeSpeaker({
      backendUrl: 'https://api.example',
      fetchImpl: fetchImpl as unknown as typeof fetch,
      play: async () => {},
    });

    await speak('anything');

    const [, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit];
    expect(JSON.parse(String(init.body)).notice).toBe(NOTICE_SAVE_EARLY);
  });

  it('attaches the bearer token', async () => {
    const fetchImpl = vi.fn(async () => okResponse());
    const speak = createNoticeSpeaker({
      backendUrl: 'https://api.example',
      getToken: async () => 'tok-123',
      fetchImpl: fetchImpl as unknown as typeof fetch,
      play: async () => {},
    });

    await speak('x', 'English', NOTICE_SAVE_EARLY);

    const [, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit];
    expect((init.headers as Record<string, string>).Authorization).toBe('Bearer tok-123');
  });

  it('plays the audio it receives', async () => {
    const play = vi.fn(async () => {});
    const speak = createNoticeSpeaker({
      backendUrl: 'https://api.example',
      fetchImpl: (async () => okResponse()) as unknown as typeof fetch,
      play,
    });

    await speak('x');

    expect(play).toHaveBeenCalledTimes(1);
  });

  it.each([
    ['a refused request', async () => ({ ok: false, status: 400 } as unknown as Response)],
    ['a server error', async () => ({ ok: false, status: 502 } as unknown as Response)],
    ['a network failure', async () => { throw new Error('offline'); }],
  ])('stays SILENT on %s', async (_label, impl) => {
    const speak = createNoticeSpeaker({
      backendUrl: 'https://api.example',
      fetchImpl: impl as unknown as typeof fetch,
      play: async () => {},
    });

    // Resolves, never rejects: the same words are already on screen.
    await expect(speak('x')).resolves.toBeUndefined();
  });

  it('stays silent when PLAYBACK fails', async () => {
    // Mobile autoplay policies reject .play() routinely. That must not surface
    // as an error to a client who is trying to save their work.
    const speak = createNoticeSpeaker({
      backendUrl: 'https://api.example',
      fetchImpl: (async () => okResponse()) as unknown as typeof fetch,
      play: async () => { throw new Error('autoplay blocked'); },
    });

    await expect(speak('x')).resolves.toBeUndefined();
  });
});
