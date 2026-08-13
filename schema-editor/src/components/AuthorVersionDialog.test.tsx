/**
 * The author-version dialog (bd polyglot-pdf-xzw5): what an author sees when
 * publishing a form that has no government edition date.
 *
 * The normalization helpers are pinned directly because they MIRROR a backend
 * rule (editor_kit_routes' publish gate). A drift between the two shows the
 * author one value and stores another, which is exactly the confusion the
 * dialog exists to prevent.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import {
  AuthorVersionDialog, normalizeAuthorVersion, todayIsoLocal,
} from './AuthorVersionDialog';

describe('normalizeAuthorVersion (mirrors the backend publish gate)', () => {
  it('trims surrounding whitespace', () => {
    expect(normalizeAuthorVersion('  2026-08-07  ')).toBe('2026-08-07');
  });

  it('strips a leading v/V when a DIGIT follows', () => {
    expect(normalizeAuthorVersion('v2026-08-07')).toBe('2026-08-07');
    expect(normalizeAuthorVersion('V2')).toBe('2');
  });

  it('leaves a leading v alone when a LETTER follows', () => {
    // The trap in a naive lstrip('vV'): "version-3" would become "ersion-3",
    // silently mangling a perfectly reasonable version string.
    expect(normalizeAuthorVersion('version-3')).toBe('version-3');
    expect(normalizeAuthorVersion('vNext')).toBe('vNext');
  });

  it('yields an empty string for whitespace-only input', () => {
    expect(normalizeAuthorVersion('   ')).toBe('');
    expect(normalizeAuthorVersion('')).toBe('');
  });
});

describe('todayIsoLocal', () => {
  it('formats the LOCAL date, not the UTC one', () => {
    // 2026-08-07 23:30 local. toISOString() would roll this to the 8th for any
    // timezone east of Greenwich, prefilling tomorrow's date as the version.
    const late = new Date(2026, 7, 7, 23, 30, 0);
    expect(todayIsoLocal(late)).toBe('2026-08-07');
  });

  it('zero-pads single-digit months and days', () => {
    expect(todayIsoLocal(new Date(2026, 0, 5))).toBe('2026-01-05');
  });
});

describe('AuthorVersionDialog', () => {
  const props = {
    kitLabel: 'Acme Intake',
    onConfirm: vi.fn(),
    onCancel: vi.fn(),
  };

  it('prefills todays date so the common case is one keypress', () => {
    render(<AuthorVersionDialog {...props} />);
    const input = screen.getByLabelText('Version') as HTMLInputElement;
    expect(input.value).toBe(todayIsoLocal());
  });

  it('confirms with the NORMALIZED value, not the raw text', () => {
    const onConfirm = vi.fn();
    render(<AuthorVersionDialog {...props} onConfirm={onConfirm} />);

    fireEvent.change(screen.getByLabelText('Version'), { target: { value: ' v9 ' } });
    fireEvent.click(screen.getByText('Save version & publish'));

    expect(onConfirm).toHaveBeenCalledWith('9');
  });

  it('refuses to confirm an empty version', () => {
    const onConfirm = vi.fn();
    render(<AuthorVersionDialog {...props} onConfirm={onConfirm} />);

    fireEvent.change(screen.getByLabelText('Version'), { target: { value: '   ' } });
    const publish = screen.getByText('Save version & publish') as HTMLButtonElement;

    expect(publish.disabled).toBe(true);
    fireEvent.click(publish);
    expect(onConfirm).not.toHaveBeenCalled();
    expect(screen.getByText(/A version is required/)).toBeTruthy();
  });

  it('shows the previous version so the next entry is an obvious increment', () => {
    render(<AuthorVersionDialog {...props} previousVersion="2026-01-01" />);
    expect(screen.getByText('2026-01-01')).toBeTruthy();
  });

  it('warns that the value cannot be changed later', () => {
    // The immutability is a real constraint (it is what confirmation records
    // name), so the author must know BEFORE committing, not after.
    render(<AuthorVersionDialog {...props} />);
    expect(screen.getByText(/cannot change this later/)).toBeTruthy();
  });

  it('cancels on Escape and on the Cancel button', () => {
    const onCancel = vi.fn();
    render(<AuthorVersionDialog {...props} onCancel={onCancel} />);

    fireEvent.keyDown(screen.getByLabelText('Version'), { key: 'Escape' });
    expect(onCancel).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByText('Cancel'));
    expect(onCancel).toHaveBeenCalledTimes(2);
  });

  it('submits on Enter', () => {
    const onConfirm = vi.fn();
    render(<AuthorVersionDialog {...props} onConfirm={onConfirm} />);
    fireEvent.keyDown(screen.getByLabelText('Version'), { key: 'Enter' });
    expect(onConfirm).toHaveBeenCalledWith(todayIsoLocal());
  });

  it('does not cancel or double-submit while busy', () => {
    const onConfirm = vi.fn();
    const onCancel = vi.fn();
    render(
      <AuthorVersionDialog {...props} onConfirm={onConfirm} onCancel={onCancel} busy />,
    );

    fireEvent.click(screen.getByText('Cancel'));
    expect(onCancel).not.toHaveBeenCalled();

    fireEvent.keyDown(screen.getByLabelText('Version'), { key: 'Enter' });
    expect(onConfirm).not.toHaveBeenCalled();
  });
});
