// @vitest-environment jsdom
//
// Coverage for ConnectionTimeoutModal (bd polyglot-pdf-jf6w.2): renders the
// recovery copy in the user's language (English fallback), and the buttons wire
// to onReconnect / onCancel.
//
// ASCII-only source (scar #6 / AGENTS.md): non-English assertion strings are
// written as \u escapes, never raw glyphs. JS decodes them at parse time to the
// same characters the modal renders, so coverage is unchanged.
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { ConnectionTimeoutModal } from './ConnectionTimeoutModal';

describe('ConnectionTimeoutModal', () => {
  afterEach(() => {
    cleanup();
  });

  const defaultProps = {
    isOpen: true,
    selectedLanguage: 'English',
    onReconnect: vi.fn(),
    onCancel: vi.fn(),
  };

  it('renders nothing when closed', () => {
    const { container } = render(
      <ConnectionTimeoutModal {...defaultProps} isOpen={false} />
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders English copy and the reconnect button by default', () => {
    render(<ConnectionTimeoutModal {...defaultProps} />);
    expect(screen.getByText('Connection Timed Out')).toBeTruthy();
    expect(screen.getByText('Reconnect')).toBeTruthy();
  });

  it('renders Spanish copy when selectedLanguage is Spanish', () => {
    render(<ConnectionTimeoutModal {...defaultProps} selectedLanguage="Spanish" />);
    // \u escapes (ASCII-only source, scar #6): title = "Se Agot\u00f3 el Tiempo
    // de Conexi\u00f3n"; button = "Reconectar". JS decodes the escapes to the
    // exact glyphs the modal renders, so coverage is unchanged.
    expect(screen.getByText('Se Agot\u00f3 el Tiempo de Conexi\u00f3n')).toBeTruthy();
    expect(screen.getByText('Reconectar')).toBeTruthy();
  });

  it('falls back to English copy for an unknown language', () => {
    render(<ConnectionTimeoutModal {...defaultProps} selectedLanguage="Klingon" />);
    expect(screen.getByText('Connection Timed Out')).toBeTruthy();
  });

  it('invokes onReconnect when the reconnect button is clicked', () => {
    const onReconnect = vi.fn();
    render(<ConnectionTimeoutModal {...defaultProps} onReconnect={onReconnect} />);
    fireEvent.click(screen.getByText('Reconnect'));
    expect(onReconnect).toHaveBeenCalledTimes(1);
  });

  it('invokes onCancel when the cancel button is clicked', () => {
    const onCancel = vi.fn();
    render(<ConnectionTimeoutModal {...defaultProps} onCancel={onCancel} />);
    fireEvent.click(screen.getByText('Not Now'));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it('omits the cancel button when onCancel is not provided', () => {
    render(
      <ConnectionTimeoutModal
        isOpen={true}
        selectedLanguage="English"
        onReconnect={vi.fn()}
      />
    );
    expect(screen.queryByText('Not Now')).toBeNull();
    expect(screen.getByText('Reconnect')).toBeTruthy();
  });
});
