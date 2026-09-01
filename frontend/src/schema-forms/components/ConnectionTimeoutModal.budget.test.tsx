// @vitest-environment jsdom
//
// The spend-exhausted modal (bd polyglot-pdf-cke6v, exit criterion 2).
//
// What this pins is mostly what the modal must NOT do. The bug was a client
// staring at a Reconnect button that could never work; a variant that renders
// one anyway would look correct in every screenshot and be wrong in the only
// way that matters.
import { describe, it, expect, afterEach } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';

import { ConnectionTimeoutModal } from './ConnectionTimeoutModal';
import {
  CONNECTION_TIMEOUT_TRANSLATIONS,
  type ConnectionTimeoutCopy,
} from './connectionTimeoutTranslations';

afterEach(() => cleanup());

function renderBudget(language = 'English') {
  render(
    <ConnectionTimeoutModal
      variant="budget_exhausted"
      isOpen
      selectedLanguage={language}
      onReconnect={() => {}}
    />,
  );
}

describe('the spend-exhausted modal', () => {
  it('offers NO buttons at all', () => {
    renderBudget();
    // Not "no reconnect button" -- no actions, full stop. Every button on this
    // surface would be a dead end.
    expect(screen.queryAllByRole('button')).toEqual([]);
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
      return !copy.budgetExhaustedTitle?.trim() || !copy.budgetExhaustedMessage?.trim();
    });
    expect(missing).toEqual([]);
  });

  it('stays closed when isOpen is false', () => {
    render(
      <ConnectionTimeoutModal
        variant="budget_exhausted"
        isOpen={false}
        selectedLanguage="English"
        onReconnect={() => {}}
      />,
    );
    expect(screen.queryByRole('dialog')).toBeNull();
  });
});
