> **ARCHIVED 2026-06-01 (bd polyglot-pdf-4p0).** Superseded by
> [`../components/auth.md`](../components/auth.md), which documents the auth surface
> as actually built (this plan was largely aspirational — see the component doc's
> plan-vs-reality notes). Kept verbatim for history only — do not edit or cite as
> current.

# Authorization & User Profiles - Project Plan

**Status**: Active / Planning
**Last Updated**: January 2026
**Feature**: Authentication (Email + Google) & User Profiles (Firestore)

## 1. Overview

We are implementing a robust Authorization layer and User Profile system. The architecture maintains our "Stateless Backend" philosophy by leveraging **Firebase Authentication** for identity management and **Firestore** for user profile storage. The Python backend (Cloud Run) will remain stateless, verifying ID tokens for protected operations (WebSocket connections) via the Firebase Admin SDK.

### Architecture
-   **Frontend**: Handles Login/Signup (Email/Password + Google). Manages `AuthContext`. Stores zero sensitive data; relies on Firebase SDK.
-   **Backend**: Cloud Run service. Uses **Application Default Credentials (ADC)** to initialize Firebase Admin SDK. Verifies ID Tokens on WebSocket handshake.
-   **Database**: Firestore.
    -   **Database Name/Scope**: `polyglotusers` (Note: Verify if this is a named database ID or a collection. Default assumption: Named Database or Collection).
    -   **Collection**: `users` (stored within the `polyglotusers` DB).

## 2. Configuration & Prerequisites

-   [x] **Firebase Project**: `polyglot-forms-919f2` (Production) / `polyglot-demo-aa709` (Demo)
-   [x] **Auth Providers**: Email/Password, Google.
-   [x] **Database**: Firestore initialized. Name: `polyglotusers`.
-   [ ] **Dependencies**:
    -   Frontend: `firebase`
    -   Backend: `firebase-admin`

## 3. Implementation Steps

Each step is designed to be small, independently testable, and commit-ready.

### Phase 1: dependencies & Configuration

- [ ] **1.1 Frontend Dependencies**
    -   Action: `npm install firebase` in `frontend/`.
    -   Verification: Check `package.json`.

- [ ] **1.2 Backend Dependencies**
    -   Action: Add `firebase-admin` to `backend/requirements.txt`.
    -   Action: Rebuild/install locally (`pip install -r requirements.txt`).
    -   Verification: Run `python -c "import firebase_admin; print(firebase_admin.__version__)"`.

- [ ] **1.3 Firebase Config (Frontend)**
    -   Action: Create `frontend/src/firebase/config.ts`.
    -   Detail: Export initialized `auth` and `db` instances.
    -   Verification: Console log `auth` object on app load.

- [ ] **1.4 Firebase Admin Init (Backend)**
    -   Action: Create `backend/services/auth.py`.
    -   Detail: Initialize app with ADC (no args). Handle named database `polyglotusers` if applicable.
    -   Verification: Create a test script `backend/tests/manual/test_auth_init.py` that initializes app and lists users (should be empty but no error).

### Phase 2: Frontend Authentication (The "Shell")

- [ ] **2.1 Auth Context**
    -   Action: Create `frontend/src/contexts/AuthContext.tsx`.
    -   Detail: Provide `user`, `loading`, `signInWithGoogle`, `logout`.
    -   Verification: Wrap App in Provider. Use React DevTools to see context state change when manually toggling mocked state.

- [ ] **2.2 Login Page UI**
    -   Action: Create `frontend/src/components/auth/Login.tsx`.
    -   Detail: Simple UI with "Sign in with Google" button (and Email/Pass form).
    -   Verification: Page renders at `/login`.

- [ ] **2.3 Routing Updates**
    -   Action: Update `frontend/src/App.tsx`.
    -   Detail: Add `/login` route.
    -   Verification: Navigate to `/login` manually.

- [ ] **2.4 Protected Route Component**
    -   Action: Create `frontend/src/components/auth/ProtectedRoute.tsx`.
    -   Detail: Redirect to `/login` if `!user`. Render children if `user`.
    -   Verification: Wrap a dummy route. Try to access it while logged out (redirects) and logged in (shows content).

### Phase 3: User Profiles (Firestore)

- [ ] **3.1 Firestore Rules**
    -   Action: Create `firestore.rules` (or update via Console).
    -   Rule: `allow read, write: if request.auth != null && request.auth.uid == userId;`
    -   Verification: Use Firestore Simulator in Console.

- [ ] **3.2 Profile Creation on Signup**
    -   Action: Update `AuthContext` or `Login.tsx`.
    -   Detail: On successful login/signup, check if `users/{uid}` exists in `polyglotusers`. If not, create it.
    -   Fields: `uid`, `email`, `displayName`, `photoURL`, `createdAt`, `lastLogin`.
    -   Verification: Login with Google. Check Firestore Console for new document.

- [ ] **3.3 Profile Page UI**
    -   Action: Create `frontend/src/components/auth/UserProfile.tsx`.
    -   Detail: Display user info from Firestore (not just Auth token). Allow editing `displayName`.
    -   Verification: Update name, refresh page, see new name.

### Phase 4: Backend Enforcement (The "Gate")

- [ ] **4.1 Token Verification Service**
    -   Action: Update `backend/services/auth.py`.
    -   Detail: Add `verify_token(token_str) -> dict`. Verify it decodes and returns claims.
    -   Verification: Unit test with a mocked token using `unittest.mock`.

- [ ] **4.2 WebSocket Guard**
    -   Action: Update `backend/main.py` WebSocket endpoint.
    -   Detail: Read `token` from Query Params. Call `verify_token`. Close connection with 4001/4003 if invalid.
    -   Verification: Connect via Postman/wscat without token (fail). Connect with valid ID token (success).

### Phase 5: Cleanup & Polish

- [ ] **5.1 Navigation Integration**
    -   Action: Add User Avatar/Login Status to Header.
    -   Detail: Dropdown with "Profile" and "Logout".

- [ ] **5.2 Session Persistence**
    -   Action: Verify `sessionStorage` vs `localStorage` behavior per requirements (likely `indexedDB` via Firebase default, but we treat session as ephemeral).

## 4. Testing Strategy

-   **Unit Tests**: `vitest` for AuthContext logic.
-   **Integration**: End-to-end flow (Login -> Profile -> Form -> Websocket).
-   **Manual**:
    1.  Incognito window (fresh session).
    2.  Login with Google.
    3.  Confirm Profile created in DB.
    4.  Open Form.
    5.  Verify specific "User Connected" log in backend includes `user_id`.
