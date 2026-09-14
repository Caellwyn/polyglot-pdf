/**
 * The staff-only header control for the voice form-filling app (bd
 * polyglot-pdf-8v8i7). Renders nothing for a client-link session (no
 * Firebase user to log out, and a client should never see a "log out and
 * clear this device" affordance for a form they're actively filling).
 *
 * The logout button calls the EXISTING `useAuth().logout()` (owned by
 * AuthContext.tsx, out of scope for this bead) and then wipes this device's
 * stored form/onboarding/client-link state through the same Clear-form path
 * the completion and idle-timeout triggers use, so a staff member stepping
 * away from a shared law-office tablet leaves nothing behind for the next
 * person who signs in.
 */
import { useState } from "react";
import { useAuth } from "../../contexts/AuthContext";
import { hasClientLinkToken } from "../../shared/sessionCredential";
import { SchemaFormStateManager } from "../state/schemaFormState";

export function StaffHeader() {
  const { user, logout } = useAuth();
  const [loggingOut, setLoggingOut] = useState(false);

  if (!user || hasClientLinkToken()) {
    return null;
  }

  const handleLogout = async () => {
    if (loggingOut) return;
    setLoggingOut(true);
    try {
      await logout();
    } catch (error) {
      console.error('[StaffHeader] logout() failed:', error);
    } finally {
      // Clear regardless of whether the Firebase sign-out itself succeeded --
      // a failed sign-out is still a staff member walking away from the
      // device, and stale form state must not survive that.
      SchemaFormStateManager.clearAllClientState();
      setLoggingOut(false);
    }
  };

  return (
    <div className="schema-form__staff-header">
      <span className="schema-form__staff-header-email">{user.email}</span>
      <button
        type="button"
        className="schema-form__staff-header-logout"
        onClick={handleLogout}
        disabled={loggingOut}
      >
        {loggingOut ? "Logging out..." : "Log out"}
      </button>
    </div>
  );
}
