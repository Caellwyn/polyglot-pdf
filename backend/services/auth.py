import os
import firebase_admin
from firebase_admin import auth, credentials, firestore
from fastapi import HTTPException, status
import structlog

logger = structlog.get_logger()

# Initialize Firebase Admin
# In Cloud Run, credentials are auto-detected (ADC).
# Locally, requires `gcloud auth application-default login`.
try:
    if not firebase_admin._apps:
        # Check if running locally/custom creds needed, or just default
        # For this setup, we assume ADC is sufficient.
        firebase_admin.initialize_app()
        logger.info("firebase_admin_initialized", method="ADC")
except Exception as e:
    logger.error("firebase_admin_init_failed", error=str(e))
    # We don't raise immediately to allow import, but verify_token will fail if not init

def verify_token(token: str) -> dict:
    """
    Verifies a Firebase ID Token.
    Returns the decoded token dict (claims) if valid.
    Raises HTTPException(401) if invalid.
    """
    # Development Bypass
    if os.getenv("VFF_DISABLE_AUTH", "false").lower() == "true":
         logger.warning("auth_bypassed_via_env")
         return {"uid": "dev_user", "email": "dev@example.com"}

    try:
        decoded_token = auth.verify_id_token(token)
        return decoded_token
    except Exception as e:
        logger.warning("token_verification_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

def get_db():
    """Returns Firestore client"""
    return firestore.client()
