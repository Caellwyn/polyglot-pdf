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
        expect(screen.getByText('重要通知')).toBeTruthy();
        assertBodyText('它帮助您填写表格');
        expect(screen.getByText('我同意')).toBeTruthy();
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
