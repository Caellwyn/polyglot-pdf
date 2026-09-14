// @vitest-environment jsdom
//
// StaffHeader (bd polyglot-pdf-8v8i7): the voice app's staff-only logout
// control. Renders nothing for a client-link session; for a staff session,
// clicking Log out calls the EXISTING useAuth().logout() AND wipes this
// device's stored form/onboarding/client-link state, so a staff member
// walking away from a shared law-office tablet leaves nothing behind.

import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

const mockLogout = vi.fn(() => Promise.resolve());
let mockUser: { email: string } | null = { email: 'staff@example.com' };

vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => ({ user: mockUser, logout: mockLogout }),
}));

let mockHasClientLinkToken = false;
vi.mock('../../shared/sessionCredential', () => ({
  hasClientLinkToken: () => mockHasClientLinkToken,
  // SchemaFormStateManager.clearAllClientState() also imports this from the
  // same module; mocking the module wholesale means every export it uses
  // must be present here too, or that call throws "no export defined".
  clearClientLinkToken: () => {},
}));

import { StaffHeader } from './StaffHeader';
import { SchemaFormStateManager } from '../state/schemaFormState';
import { saveOnboardingState, ONBOARDING_FORM_KEY } from '../onboardingStorage';

describe('StaffHeader (bd polyglot-pdf-8v8i7)', () => {
  beforeEach(() => {
    sessionStorage.clear();
    mockUser = { email: 'staff@example.com' };
    mockHasClientLinkToken = false;
    mockLogout.mockClear();
  });

  afterEach(() => {
    cleanup();
  });

  it('renders nothing for a client-link session', () => {
    mockHasClientLinkToken = true;
    const { container } = render(<StaffHeader />);
    expect(container.firstChild).toBeNull();
  });

  it('renders nothing when there is no signed-in user', () => {
    mockUser = null;
    const { container } = render(<StaffHeader />);
    expect(container.firstChild).toBeNull();
  });

  it('renders a logout control for a signed-in staff user', () => {
    render(<StaffHeader />);
    expect(screen.getByRole('button', { name: /log out/i })).toBeTruthy();
  });

  it('calls useAuth().logout() and clears client state on click', async () => {
    sessionStorage.setItem('schema_form_state', JSON.stringify({ fieldValues: {} }));
    saveOnboardingState({ formId: 'i-90', language: 'English' });

    render(<StaffHeader />);
    fireEvent.click(screen.getByRole('button', { name: /log out/i }));

    await waitFor(() => expect(mockLogout).toHaveBeenCalledTimes(1));
    expect(sessionStorage.getItem('schema_form_state')).toBeNull();
    expect(sessionStorage.getItem(ONBOARDING_FORM_KEY)).toBeNull();
  });

  it('still clears client state even when logout() itself rejects', async () => {
    mockLogout.mockRejectedValueOnce(new Error('network error'));
    sessionStorage.setItem('schema_form_state', JSON.stringify({ fieldValues: {} }));

    render(<StaffHeader />);
    fireEvent.click(screen.getByRole('button', { name: /log out/i }));

    await waitFor(() => expect(sessionStorage.getItem('schema_form_state')).toBeNull());
  });
});
