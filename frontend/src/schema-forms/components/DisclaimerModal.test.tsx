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

    it('renders English text by default', () => {
        render(<DisclaimerModal {...defaultProps} />);
        expect(screen.getByText('Important Notice')).toBeTruthy();
        expect(screen.getByText(/This tool helps you fill out your form/)).toBeTruthy();
        expect(screen.getByText('I Agree')).toBeTruthy();
    });

    it('renders Spanish text when selectedLanguage is Spanish', () => {
        render(<DisclaimerModal {...defaultProps} selectedLanguage="Spanish" />);
        expect(screen.getByText('Aviso Importante')).toBeTruthy();
        expect(screen.getByText(/Esta herramienta le ayuda a completar su formulario/)).toBeTruthy();
        expect(screen.getByText('Estoy de Acuerdo')).toBeTruthy();
    });

    it('renders Chinese text when selectedLanguage is Chinese', () => {
        render(<DisclaimerModal {...defaultProps} selectedLanguage="Chinese" />);
        expect(screen.getByText('重要通知')).toBeTruthy();
        expect(screen.getByText(/此工具帮助您填写表格/)).toBeTruthy();
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
