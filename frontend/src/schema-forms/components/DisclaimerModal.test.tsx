// @vitest-environment jsdom
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { DisclaimerModal } from './DisclaimerModal';

describe('DisclaimerModal', () => {
    afterEach(() => {
        cleanup();
    });

    const defaultProps = {
        isOpen: true,
        selectedLanguage: 'English',
        onListenAgain: vi.fn(),
        onAgree: vi.fn(),
    };

    // Body-copy coverage RESTORED (Codex review, PR #122): the disclaimer is the
    // mandatory legal notice, so its warning text must stay asserted -- skipping
    // would let a dropped/mistranslated paragraph pass green. The old assertions
    // failed only because the copy was rewritten to the current legal-grade text
    // (bd polyglot-pdf-pwt); each substring below is checked against the current
    // copy. The paragraph is one long text node, so we assert on the rendered
    // document's textContent (a getByText "node" match would resolve up the whole
    // ancestor chain and report "multiple elements"). T1.3 (polyglot-pdf-uov.6)
    // still owns the full disclaimer spec audit.
    const assertBodyText = (needle: string) =>
        expect(document.body.textContent).toContain(needle);

    it('renders English body copy by default', () => {
        render(<DisclaimerModal {...defaultProps} />);
        expect(screen.getByText('Important Notice')).toBeTruthy();
        assertBodyText('It helps you fill out a form');
        expect(screen.getByText('I Agree')).toBeTruthy();
    });

    it('renders Spanish body copy when selectedLanguage is Spanish', () => {
        render(<DisclaimerModal {...defaultProps} selectedLanguage="Spanish" />);
        expect(screen.getByText('Aviso Importante')).toBeTruthy();
        assertBodyText('Le ayuda a completar un formulario');
        expect(screen.getByText('Estoy de Acuerdo')).toBeTruthy();
    });

    it('renders Chinese body copy when selectedLanguage is Chinese', () => {
        render(<DisclaimerModal {...defaultProps} selectedLanguage="Chinese" />);
        // ASCII-only source (scar #6 / AGENTS.md): the Chinese assertion strings are
        // written as \u escapes, never raw glyphs. JS decodes them at parse time to
        // the same characters the modal renders, so coverage is unchanged. Escapes:
        // title = zh "Important Notice", body = zh "It helps you fill out a form",
        // agree button = zh "I Agree".
        expect(screen.getByText('\u91cd\u8981\u901a\u77e5')).toBeTruthy();
        assertBodyText('\u5b83\u5e2e\u52a9\u60a8\u586b\u5199\u8868\u683c');
        expect(screen.getByText('\u6211\u540c\u610f')).toBeTruthy();
    });

    it('falls back to English for unknown languages', () => {
        render(<DisclaimerModal {...defaultProps} selectedLanguage="Klingon" />);
        expect(screen.getByText('Important Notice')).toBeTruthy();
        expect(screen.getByText('I Agree')).toBeTruthy();
    });

    it('does not render when isOpen is false', () => {
        render(<DisclaimerModal {...defaultProps} isOpen={false} />);
        expect(screen.queryByText('Important Notice')).toBeNull();
    });

    it('calls onAgree when agree button is clicked', () => {
        render(<DisclaimerModal {...defaultProps} />);
        fireEvent.click(screen.getByText('I Agree'));
        expect(defaultProps.onAgree).toHaveBeenCalled();
    });

    it('calls onListenAgain when listen again button is clicked', () => {
        render(<DisclaimerModal {...defaultProps} />);
        fireEvent.click(screen.getByText('Listen Again'));
        expect(defaultProps.onListenAgain).toHaveBeenCalled();
    });
});
