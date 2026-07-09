/**
 * HostedGuide tests: the in-app guided help overlay (bd 92qe.5, expanded to a
 * sectioned, tier-aware panel). Covers section rendering, the author-only
 * Extraction gate, section navigation, and that closing marks the guide seen.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { HostedGuide, hasSeenGuide } from './HostedGuide';

describe('HostedGuide', () => {
  beforeEach(() => {
    window.localStorage.clear();
  });
  afterEach(() => {
    cleanup();
    window.localStorage.clear();
  });

  it('renders the core sections in the rail', () => {
    render(<HostedGuide onClose={() => {}} role="editor" />);
    // Section rail buttons.
    expect(
      screen.getByRole('button', { name: 'Quick start' }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Getting around' }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Field properties' }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Common tasks' }),
    ).toBeInTheDocument();
  });

  it('explains Instructions and Format Hint as AI guidance', () => {
    render(<HostedGuide onClose={() => {}} role="editor" />);
    fireEvent.click(screen.getByRole('button', { name: 'Field properties' }));
    // The section frames both as guidance for the voice AI.
    expect(screen.getByText(/guidance for the voice AI/i)).toBeInTheDocument();
    // "Format Hint" appears in several places in the section; assert presence.
    expect(screen.getAllByText(/Format Hint/).length).toBeGreaterThan(0);
    expect(screen.getByText(/a short shape example/i)).toBeInTheDocument();
  });

  it('shows the Extraction section only for the author tier', () => {
    const { rerender } = render(
      <HostedGuide onClose={() => {}} role="author" />,
    );
    expect(
      screen.getByRole('button', { name: 'Extraction' }),
    ).toBeInTheDocument();

    rerender(<HostedGuide onClose={() => {}} role="editor" />);
    expect(
      screen.queryByRole('button', { name: 'Extraction' }),
    ).not.toBeInTheDocument();
  });

  it('hides the Extraction section in local mode (role null)', () => {
    render(<HostedGuide onClose={() => {}} role={null} />);
    expect(
      screen.queryByRole('button', { name: 'Extraction' }),
    ).not.toBeInTheDocument();
  });

  it('emphasizes attaching the instructions PDF in Extraction', () => {
    render(<HostedGuide onClose={() => {}} role="author" />);
    fireEvent.click(screen.getByRole('button', { name: 'Extraction' }));
    // "instructions PDF" appears in several places; assert presence, not unique.
    expect(screen.getAllByText(/instructions PDF/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/richer per-field help/i)).toBeInTheDocument();
  });

  it('switches the content pane when a rail link is clicked', () => {
    render(<HostedGuide onClose={() => {}} role="editor" />);
    fireEvent.click(screen.getByRole('button', { name: 'Common tasks' }));
    // A Common-tasks-only heading is now visible.
    expect(screen.getByText('Re-order fields')).toBeInTheDocument();
  });

  it('marks the guide seen when closed via Got it', () => {
    const onClose = vi.fn();
    render(<HostedGuide onClose={onClose} role="editor" />);
    expect(hasSeenGuide()).toBe(false);
    fireEvent.click(screen.getByRole('button', { name: 'Got it' }));
    expect(onClose).toHaveBeenCalledOnce();
    expect(hasSeenGuide()).toBe(true);
  });

  it('closes on Escape and marks the guide seen', () => {
    const onClose = vi.fn();
    render(<HostedGuide onClose={onClose} role="editor" />);
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledOnce();
    expect(hasSeenGuide()).toBe(true);
  });
});
