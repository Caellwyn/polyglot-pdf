/**
 * WhoAmIPage (bd polyglot-pdf-dp1zq fresh-eyes round-1 gap): this page had
 * no test file at all before this fix. It pins the two things this bead's
 * fix touches -- the page renders the signed-in identity fields, and it now
 * carries the same one-sentence PageIntro header every other console tab
 * got in this diff (App.tsx:109 lists "Who am I" as the first tab; it was
 * the one page in src/components/ that got missed).
 */
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { WhoAmIPage } from './WhoAmIPage';
import type { WhoAmI } from '../utils/adminApi';

const WHO: WhoAmI = { uid: 'uid-123', email: 'admin@example.com' };

describe('WhoAmIPage', () => {
  it('renders the signed-in identity', () => {
    render(<WhoAmIPage who={WHO} />);
    expect(screen.getByText('admin@example.com')).toBeInTheDocument();
    expect(screen.getByText('uid-123')).toBeInTheDocument();
  });

  it('falls back to a placeholder when email is null', () => {
    render(<WhoAmIPage who={{ uid: 'uid-456', email: null }} />);
    expect(screen.getByText('(no email on this account)')).toBeInTheDocument();
  });

  it('renders exactly one purpose header describing what the page is for', () => {
    render(<WhoAmIPage who={WHO} />);
    const intros = screen.getAllByTestId('page-intro');
    expect(intros).toHaveLength(1);
    expect(intros[0]).toHaveTextContent(
      'Confirms which account you are signed in as and which build of the console you are running.',
    );
  });
});
