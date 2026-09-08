/**
 * Per-user sign-in for the ADMIN CONSOLE (bd polyglot-pdf-b6943).
 *
 * MIRRORS schema-editor/src/utils/editorAuth.ts's shape and reasoning almost
 * exactly -- same Firebase project, same "sign in as yourself, then a
 * server-side role probe" pattern, same DELIBERATE duplication rather than
 * a shared import: the maintainer constraint that kept schema-editor/ from
 * importing frontend/ (2026-08-20: "I don't want to create NEW dependencies
 * that I will just need to unravel against later") applies here with equal
 * force -- admin-console/ imports NOTHING from frontend/ or schema-editor/.
 *
 * What is NOT duplicated, on purpose (same list as editorAuth.ts):
 *   * NO Firestore. The admin console's allowlist is the app_admin CUSTOM
 *     CLAIM, stamped by scripts/bootstrap_admin_user.py -- nothing here to
 *     read, and a profile write would be a new cross-surface dependency.
 *   * NO account creation. Admin access is granted, never self-served: the
 *     bootstrap script stamps a claim on an account an operator already
 *     made. A "create account" button could only ever mint an account the
 *     server then refuses with 403.
 *
 * The same Firebase PROJECT is reused deliberately, for the same reason
 * editorAuth.ts gives: standing up a second project here would be a new
 * dependency a future separation epic has to unravel.
 */
import { initializeApp, type FirebaseApp } from 'firebase/app';
import {
  GoogleAuthProvider,
  browserLocalPersistence,
  getAuth,
  onAuthStateChanged,
  sendPasswordResetEmail,
  setPersistence,
  signInWithEmailAndPassword,
  signInWithPopup,
  signOut,
  type Auth,
  type User,
} from 'firebase/auth';

/** The console's Firebase config, read from the build env (VITE_FIREBASE_*).
 *
 * Same keys the voice app's and schema editor's configs use, because it is
 * the same project -- read independently here so this folder has no import
 * into frontend/ or schema-editor/. Only the three keys sign-in actually
 * needs are required. */
function firebaseConfig() {
  return {
    apiKey: import.meta.env.VITE_FIREBASE_API_KEY as string | undefined,
    authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN as string | undefined,
    projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID as string | undefined,
  };
}

/**
 * True when this build has Firebase credentials baked in.
 *
 * A hosted build with no VITE_FIREBASE_* values cannot sign anyone in, and
 * initializeApp would either throw or produce an app whose every call fails
 * with an opaque SDK error. Checking first lets the gate say the real thing
 * instead of showing a sign-in form that cannot work.
 */
export function isAuthConfigured(): boolean {
  const cfg = firebaseConfig();
  return Boolean(cfg.apiKey && cfg.authDomain && cfg.projectId);
}

// Lazily created so importing this module never initialises Firebase -- the
// test suite must be able to import the store without a live SDK.
let _app: FirebaseApp | null = null;
let _auth: Auth | null = null;

function adminAuth(): Auth {
  if (!_auth) {
    if (!isAuthConfigured()) {
      throw new Error(
        'This console build has no Firebase configuration, so it cannot ' +
        'sign anyone in. Rebuild with VITE_FIREBASE_API_KEY, ' +
        'VITE_FIREBASE_AUTH_DOMAIN and VITE_FIREBASE_PROJECT_ID set.',
      );
    }
    _app = initializeApp(firebaseConfig() as Record<string, string>);
    _auth = getAuth(_app);
    // Survive a reload: an operator mid-review should not be signed out by
    // F5. The ID token itself is short-lived; the SDK refreshes it from the
    // persisted session, which is why adminIdToken() below is called per
    // request rather than cached by us.
    void setPersistence(_auth, browserLocalPersistence).catch(() => {
      // Storage disabled (private browsing): sign-in still works for THIS
      // tab, it simply will not persist.
    });
  }
  return _auth;
}

/** Subscribe to sign-in state. Returns the SDK's unsubscribe function. */
export function watchAdminUser(cb: (user: User | null) => void): () => void {
  return onAuthStateChanged(adminAuth(), cb);
}

export async function signInWithGoogle(): Promise<void> {
  await signInWithPopup(adminAuth(), new GoogleAuthProvider());
}

export async function signInWithPassword(email: string, password: string): Promise<void> {
  await signInWithEmailAndPassword(adminAuth(), email, password);
}

export async function sendReset(email: string): Promise<void> {
  await sendPasswordResetEmail(adminAuth(), email);
}

export async function signOutAdmin(): Promise<void> {
  await signOut(adminAuth());
}

/** The signed-in person's email, for the header's "signed in as" line. */
export function currentAdminEmail(): string | null {
  return _auth?.currentUser?.email ?? null;
}

/**
 * A CURRENT Firebase ID token for the signed-in operator, or null when
 * nobody is signed in.
 *
 * Fetched per request rather than cached here: an ID token expires in about
 * an hour, and the SDK hands back a cached one until it is close to expiry,
 * then refreshes transparently. Caching a copy ourselves would reintroduce
 * exactly the failure this pattern avoids -- a stale credential that 401s
 * mid-session.
 */
export async function adminIdToken(): Promise<string | null> {
  if (!isAuthConfigured()) return null;
  const user = adminAuth().currentUser;
  if (!user) return null;
  return user.getIdToken();
}
