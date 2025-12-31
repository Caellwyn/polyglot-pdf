# Implementation Plan: Dual Deployment Channels

Establish two independent deployment channels to allow a stable portfolio version (Demo) and a production version (Business).

## Projects & Owners

| Channel | Owner | GCP Project (Backend/GCS) | Firebase Project (Hosting) |
| :--- | :--- | :--- | :--- |
| **Production** | Business | `polyglot-forms-919f2` | `polyglot-forms-919f2` |
| **Demo** | Personal | `polyglot-demo-482921` | `polyglot-demo-aa709` |

## Step-by-Step Implementation

### Phase 1: Infrastructure Automation
Create a project setup script to handle "IAM nonsense" and APIablement for the demo project.

1.  **Create `scripts/setup-gcp-project.sh`**:
    - Enable: Cloud Run, Cloud Build, Artifact Registry, Vertex AI (aiplatform), Cloud Storage.
    - Create: `polyglot-backend-sa` service account.
    - Assign Roles: `aiplatform.user`, `storage.objectViewer`, `logging.logWriter`.

### Phase 2: Configuration Updates
1.  **Modify `.firebaserc`**:
    - Add `prod` alias for `polyglot-forms-919f2`.
    - Add `demo` alias for `polyglot-demo-aa709`.

### Phase 3: Deployment Channel Scripts
1.  **Create `deploy-production.sh`**:
    - Account verification (enforce `@caellwynai.com`).
    - Call `deploy-all.sh --all` with production variables.
2.  **Create `deploy-demo.sh`**:
    - Account verification (enforce `@gmail.com`).
    - Two-stage deployment:
        1. Backend/GCS to `GCP_PROJECT`.
        2. Frontend to `FIREBASE_PROJECT`.

## Manual Verification & Testing

### 1. Infrastructure Setup Verification
Run the setup script and verify through GCP Console or CLI:
```bash
chmod +x scripts/setup-gcp-project.sh
./scripts/setup-gcp-project.sh polyglot-demo-482921
```
- **Check**: `gcloud services list --enabled --project polyglot-demo-482921` includes Vertex AI.
- **Check**: `gcloud iam service-accounts list --project polyglot-demo-482921` shows the new SA.

### 2. Demo Deployment Verification
Run the demo deployment:
```bash
chmod +x deploy-demo.sh
./deploy-demo.sh
```
- **Verify Backend**: `gcloud run services describe polyglot-backend --project polyglot-demo-482921`
- **Verify Frontend URL**: `https://polyglot-demo-aa709.web.app`
- **Test App**:
    - Open the Demo URL.
    - Select a form (e.g., I-90).
    - Activate microphone and speak.
    - **Check**: If voice fill works, Vertex AI permissions and Service Account are correct.

### 3. Account Switch Verification
- Run `./deploy-production.sh` immediately after a demo deployment.
- **Check**: The script should detect the account mismatch and prompt for `gcloud auth login`.
