// @vitest-environment jsdom
//
// The spend-exhausted modal (bd polyglot-pdf-cke6v, exit criterion 2).
//
// What this pins is mostly what the modal must NOT do. The bug was a client
// staring at a Reconnect button that could never work; a variant that renders
// one anyway would look correct in every screenshot and be wrong in the only
// way that matters.
import { describe, it, expect, afterEach, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';

import { ConnectionTimeoutModal } from './ConnectionTimeoutModal';
import {
  CONNECTION_TIMEOUT_TRANSLATIONS,
  type ConnectionTimeoutCopy,
} from './connectionTimeoutTranslations';

afterEach(() => cleanup());

function renderBudget(language = 'English') {
  // onCancel is REQUIRED for this variant -- the dismiss is what stops a
  // full-viewport overlay from trapping the client, so the component renders
  // no button without a handler rather than a dead one.
  render(
    <ConnectionTimeoutModal
      variant="budget_exhausted"
      isOpen
      selectedLanguage={language}
      onReconnect={() => {}}
      onCancel={() => {}}
    />,
  );
}

describe('the spend-exhausted modal', () => {
  it('offers no RECOVERY action, but IS dismissible', () => {
    // The first version of this test asserted zero buttons -- and pinned a
    // trap (Opus cross-surface r3). This overlay is position:fixed at z-index
    // 10000 across the whole viewport, so a button-less terminal modal
    // physically blocked the typing and printing its own message promises. On
    // desktop the client reached it by pressing the save nudge's Save (which
    // silences the nudge); on mobile, which has no nudge, it fired at once.
    //
    // So: exactly one button, and it dismisses rather than recovers.
    renderBudget();
    const buttons = screen.queryAllByRole('button');
    expect(buttons).toHaveLength(1);
    expect(buttons[0].textContent)
      .toBe(CONNECTION_TIMEOUT_TRANSLATIONS['English'].budgetExhaustedDismiss);
  });

  it('calls onCancel -- not onReconnect -- when that button is pressed', () => {
    // The distinction that matters: acknowledging is not recovering. Wiring it
    // to onReconnect would re-run the connect path against a spent link.
    const onReconnect = vi.fn();
    const onCancel = vi.fn();
    render(
      <ConnectionTimeoutModal
        variant="budget_exhausted"
        isOpen
        selectedLanguage="English"
        onReconnect={onReconnect}
        onCancel={onCancel}
      />,
    );

    fireEvent.click(screen.getByRole('button'));

    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(onReconnect).not.toHaveBeenCalled();
  });

  it('does not show the reconnect or not-now labels from the other variant', () => {
    renderBudget();
    const en = CONNECTION_TIMEOUT_TRANSLATIONS['English'];
    expect(screen.queryByText(en.reconnectButton)).toBeNull();
    expect(screen.queryByText(en.cancelButton)).toBeNull();
  });

  it('shows no spinner either -- nothing is coming', () => {
    // The "reconnecting" variant renders role="status" as a wait indicator.
    // Reusing it here would promise a recovery that will never arrive.
    renderBudget();
    expect(screen.queryByRole('status')).toBeNull();
  });

  it('tells the client to save, and names what still works', () => {
    // NOT "says the work is safe" -- the copy deliberately warns that answers
    // CAN be lost unless saved (it is the lifted voiceEnding text; the earlier
    // reassuring English was dropped because it contradicted its own 17
    // translations, Opus cross-surface r1).
    renderBudget();
    const body = screen.getByText(CONNECTION_TIMEOUT_TRANSLATIONS['English'].budgetExhaustedMessage);
    expect(body).toBeTruthy();
    // ALLOWLIST the promises, rather than banning words: assert the remedies
    // the client can actually act on are present. A message that dropped these
    // would still "have text" and still be useless.
    const text = body.textContent ?? '';
    expect(text).toMatch(/type/i);
    expect(text).toMatch(/download/i);
    expect(text).toMatch(/print/i);
  });

  it('renders the client language, not English, when one is chosen', () => {
    renderBudget('Spanish');
    const es = CONNECTION_TIMEOUT_TRANSLATIONS['Spanish'];
    expect(screen.getByText(es.budgetExhaustedMessage)).toBeTruthy();
    expect(screen.queryByText(CONNECTION_TIMEOUT_TRANSLATIONS['English'].budgetExhaustedMessage))
      .toBeNull();
  });

  it('falls back to English for a language with no copy', () => {
    renderBudget('Klingon');
    expect(screen.getByText(CONNECTION_TIMEOUT_TRANSLATIONS['English'].budgetExhaustedMessage))
      .toBeTruthy();
  });

  it('gives EVERY shipped language both budget strings', () => {
    // Derived from the shipped table, never a typed language list: this repo
    // supports 17 languages growing toward ~90, so a hand-written list is stale
    // on the next addition. A language missing these keys would silently render
    // `undefined` for a client who reads no English.
    const langs = Object.keys(CONNECTION_TIMEOUT_TRANSLATIONS);
    expect(langs.length).toBeGreaterThan(1);

    const missing = langs.filter((lang) => {
      const copy = CONNECTION_TIMEOUT_TRANSLATIONS[lang] as ConnectionTimeoutCopy;
      return (
        !copy.budgetExhaustedTitle?.trim() ||
        !copy.budgetExhaustedMessage?.trim() ||
        // The dismiss label too: without it a client who reads no English
        // gets a blank button on the only control that unblocks the page.
        !copy.budgetExhaustedDismiss?.trim()
      );
    });
    expect(missing).toEqual([]);
  });

  it('renders NO button rather than a dead one when onCancel is missing', () => {
    // Omitting onCancel on this variant is now a TYPE ERROR (bd
    // polyglot-pdf-leakz), so a forgetful caller is caught at author time.
    // But this repo's CI is NON-BLOCKING (ci.yml, bd polyglot-pdf-uov.3): a
    // red typecheck reports without gating the merge, so the RUNTIME guard
    // this test exercises is a real backstop, not decoration. The cast below
    // deliberately defeats the type to reach it.
    //
    // The property under test is the same either way: no dead button on a
    // full-viewport overlay whose only exit is that button.
    const props = {
      variant: 'budget_exhausted',
      isOpen: true,
      selectedLanguage: 'English',
      onReconnect: () => {},
    } as unknown as React.ComponentProps<typeof ConnectionTimeoutModal>;

    render(<ConnectionTimeoutModal {...props} />);
    expect(screen.queryAllByRole('button')).toEqual([]);
  });

  it('stays closed when isOpen is false', () => {
    render(
      <ConnectionTimeoutModal
        variant="budget_exhausted"
        isOpen={false}
        selectedLanguage="English"
        onReconnect={() => {}}
        onCancel={() => {}}
      />,
    );
    expect(screen.queryByRole('dialog')).toBeNull();
  });
});
