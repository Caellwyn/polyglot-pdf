/**
 * Per-user sign-in for the SCHEMA EDITOR (bd polyglot-pdf-yswp3).
 *
 * Replaces the shared access code (AccessCodeGate + X-Editor-Token) with a real
 * Firebase account per person. The server side landed first
 * (bd polyglot-pdf-hn0jq, backend/services/editor_auth.py): editor routes verify
 * a Firebase ID token and require this surface's OWN role claim, so until this
 * module existed the deployed editor asked for a code the server no longer
 * accepted.
 *
 * DELIBERATELY DUPLICATES frontend/src/firebase/config.ts and the shape of
 * frontend/src/contexts/AuthContext.tsx rather than importing them. Maintainer
 * constraint, 2026-08-20: "separating them fully right now is out of scope.
 * That's its own epic. What I don't want is to create NEW dependencies that I
 * will just need to unravel against later." So schema-editor/ imports NOTHING
 * from frontend/ -- this folder stays liftable. The duplication is the point,
 * not an oversight.
 *
 * What is NOT duplicated, on purpose:
 *   * NO Firestore. The voice app's AuthContext writes a users/ profile doc and
 *     reads an authorized_emails collection on sign-up. The editor's allowlist
 *     is the schema_editor_role CUSTOM CLAIM, stamped by
 *     scripts/bootstrap_editor_user.py -- so there is nothing here to read, and
 *     a profile write would be a new cross-surface dependency.
 *   * NO account creation. An editor account is granted, never self-served: the
 *     bootstrap script stamps a role on an account an operator already made.
 *     A "create account" button could only ever mint an account the server then
 *     refuses with 403, which reads as a broken product.
 *
 * The same Firebase PROJECT is reused deliberately -- a second project is the
 * separation epic's job (same call the server side made), and standing one up
 * here would be a new dependency to unravel.
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

/** The editor's Firebase config, read from the build env (VITE_FIREBASE_*).
 *
 * Same keys the voice app's config uses, because it is the same project -- but
 * read independently here so this folder has no import into frontend/. Only the
 * three keys sign-in actually needs are required; the voice app's storage /
 * messaging / analytics ids are not used by the editor and are omitted rather
 * than carried as dead config. */
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
 * initializeApp would either throw or produce an app whose every call fails with
 * an opaque SDK error. Checking first lets the gate say the real thing ("this
 * build was deployed without Firebase configuration") instead of showing a
 * sign-in form that cannot work.
 */
export function isAuthConfigured(): boolean {
  const cfg = firebaseConfig();
  return Boolean(cfg.apiKey && cfg.authDomain && cfg.projectId);
}

// Lazily created so importing this module never initialises Firebase -- LOCAL
// mode has no sign-in at all, and the test suite must be able to import the
// store without a live SDK.
let _app: FirebaseApp | null = null;
let _auth: Auth | null = null;

function editorAuth(): Auth {
  if (!_auth) {
    if (!isAuthConfigured()) {
      throw new Error(
        'This editor build has no Firebase configuration, so it cannot sign ' +
        'anyone in. Rebuild with VITE_FIREBASE_API_KEY, ' +
        'VITE_FIREBASE_AUTH_DOMAIN and VITE_FIREBASE_PROJECT_ID set.',
      );
    }
    _app = initializeApp(firebaseConfig() as Record<string, string>);
    _auth = getAuth(_app);
    // Survive a reload: an editor mid-kit should not be signed out by F5. The
    // ID token itself is short-lived; the SDK refreshes it from the persisted
    // session, which is why getIdToken() below is called per request rather
    // than cached by us.
    void setPersistence(_auth, browserLocalPersistence).catch(() => {
      // Storage disabled (private browsing): sign-in still works for THIS tab,
      // it simply will not persist. Better than refusing to sign in at all.
    });
  }
  return _auth;
}

/** Subscribe to sign-in state. Returns the SDK's unsubscribe function. */
export function watchEditorUser(cb: (user: User | null) => void): () => void {
  return onAuthStateChanged(editorAuth(), cb);
}

export async function signInWithGoogle(): Promise<void> {
  await signInWithPopup(editorAuth(), new GoogleAuthProvider());
}

export async function signInWithPassword(email: string, password: string): Promise<void> {
  await signInWithEmailAndPassword(editorAuth(), email, password);
}

export async function sendReset(email: string): Promise<void> {
  await sendPasswordResetEmail(editorAuth(), email);
}

export async function signOutEditor(): Promise<void> {
  await signOut(editorAuth());
}

/** The signed-in person's email, for the header's "signed in as" line. */
export function currentEditorEmail(): string | null {
  return _auth?.currentUser?.email ?? null;
}

/**
 * A CURRENT Firebase ID token for the signed-in editor, or null when nobody is
 * signed in.
 *
 * Fetched per request rather than cached here: an ID token expires in about an
 * hour, and the SDK hands back a cached one until it is close to expiry, then
 * refreshes transparently. Caching a copy ourselves would reintroduce exactly
 * the failure this bead removes -- a stale credential that 401s mid-session.
 */
export async function editorIdToken(): Promise<string | null> {
  if (!isAuthConfigured()) return null;
  const user = editorAuth().currentUser;
  if (!user) return null;
  return user.getIdToken();
}
