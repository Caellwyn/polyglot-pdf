// @vitest-environment jsdom
//
// The save nudges (bd polyglot-pdf-dft1).
//
// What matters here is that a client working BY VOICE, in a language that is
// not English, on a phone they are not looking at, still learns that saving is
// how they keep their work.
import { describe, it, expect, vi, afterEach } from 'vitest';
import { cleanup, render, screen, fireEvent, waitFor } from '@testing-library/react';

import { SaveNudge } from './SaveNudge';
import { RESUME_TRANSLATIONS } from '../resumeStrings';

const EN = RESUME_TRANSLATIONS.English;

afterEach(() => {
  // No auto-cleanup is configured in this project; without this a previous
  // render stays in the document and the next query finds the stale one.
  cleanup();
  vi.restoreAllMocks();
});

describe('SaveNudge', () => {
  it('shows the EARLY nudge with a way to dismiss it', () => {
    const onDismiss = vi.fn();
    render(
      <SaveNudge isOpen variant="early" onSave={vi.fn()} onDismiss={onDismiss} />,
    );

    expect(screen.getByText(EN.saveNudgeTitle)).toBeTruthy();
    fireEvent.click(screen.getByText(EN.saveNudgeDismiss));
    expect(onDismiss).toHaveBeenCalled();
  });

  it('does NOT offer dismiss on the ENDING nudge', () => {
    // A client about to lose voice should not be able to wave away the only
    // instruction that preserves their work by reflex.
    render(
      <SaveNudge isOpen variant="ending" onSave={vi.fn()} onDismiss={vi.fn()} />,
    );

    expect(screen.getByText(EN.voiceEndingTitle)).toBeTruthy();
    expect(screen.queryByText(EN.saveNudgeDismiss)).toBeNull();
  });

  it('SPEAKS the body so a client not looking at the screen still hears it', async () => {
    const speak = vi.fn(async () => {});
    render(
      <SaveNudge isOpen variant="early" speak={speak} onSave={vi.fn()} onDismiss={vi.fn()} />,
    );

    await waitFor(() => expect(speak).toHaveBeenCalled());
    expect(speak).toHaveBeenCalledWith(EN.saveNudgeBody, undefined);
  });

  it('speaks in the CLIENT language, not English', async () => {
    const speak = vi.fn(async () => {});
    render(
      <SaveNudge
        isOpen
        variant="early"
        selectedLanguage="Spanish"
        speak={speak}
        onSave={vi.fn()}
        onDismiss={vi.fn()}
      />,
    );

    await waitFor(() => expect(speak).toHaveBeenCalled());
    expect(speak).toHaveBeenCalledWith(RESUME_TRANSLATIONS.Spanish.saveNudgeBody, 'Spanish');
  });

  it('speaks ONCE per opening, not on every render', async () => {
    // A second voice starting over the first sounds like the app breaking, at
    // the exact moment it is asking the client to trust it.
    const speak = vi.fn(async () => {});
    const { rerender } = render(
      <SaveNudge isOpen variant="early" speak={speak} onSave={vi.fn()} onDismiss={vi.fn()} />,
    );
    await waitFor(() => expect(speak).toHaveBeenCalledTimes(1));

    rerender(
      <SaveNudge isOpen variant="early" speak={speak} onSave={vi.fn()} onDismiss={vi.fn()} />,
    );
    rerender(
      <SaveNudge isOpen variant="early" speak={speak} onSave={vi.fn()} onDismiss={vi.fn()} />,
    );

    expect(speak).toHaveBeenCalledTimes(1);
  });

  it('speaks again when it is REOPENED', async () => {
    const speak = vi.fn(async () => {});
    const { rerender } = render(
      <SaveNudge isOpen variant="early" speak={speak} onSave={vi.fn()} onDismiss={vi.fn()} />,
    );
    await waitFor(() => expect(speak).toHaveBeenCalledTimes(1));

    rerender(
      <SaveNudge isOpen={false} variant="early" speak={speak} onSave={vi.fn()} onDismiss={vi.fn()} />,
    );
    rerender(
      <SaveNudge isOpen variant="early" speak={speak} onSave={vi.fn()} onDismiss={vi.fn()} />,
    );

    await waitFor(() => expect(speak).toHaveBeenCalledTimes(2));
  });

  it('still SHOWS the words when speech fails', async () => {
    // Speech is best-effort. A TTS failure must never cost the client the
    // written instruction.
    const speak = vi.fn(async () => {
      throw new Error('tts unavailable');
    });
    render(
      <SaveNudge isOpen variant="early" speak={speak} onSave={vi.fn()} onDismiss={vi.fn()} />,
    );

    await waitFor(() => expect(speak).toHaveBeenCalled());
    expect(screen.getByText(EN.saveNudgeBody)).toBeTruthy();
  });

  it('works with no speech support at all', () => {
    render(<SaveNudge isOpen variant="early" onSave={vi.fn()} onDismiss={vi.fn()} />);
    expect(screen.getByText(EN.saveNudgeBody)).toBeTruthy();
  });

  it('triggers the save', () => {
    const onSave = vi.fn();
    render(<SaveNudge isOpen variant="early" onSave={onSave} onDismiss={vi.fn()} />);
    fireEvent.click(screen.getByText(EN.saveNudgeAction));
    expect(onSave).toHaveBeenCalled();
  });

  it('renders nothing when closed, and stays silent', () => {
    const speak = vi.fn(async () => {});
    const { container } = render(
      <SaveNudge
        isOpen={false}
        variant="early"
        speak={speak}
        onSave={vi.fn()}
        onDismiss={vi.fn()}
      />,
    );
    expect(container.innerHTML).toBe('');
    expect(speak).not.toHaveBeenCalled();
  });
});
