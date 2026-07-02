"""
Disclaimer Acceptance Logging Routes

Provides endpoint for logging user acceptance of disclaimer modal.
Creates audit trail for legal protection and compliance tracking.
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
import structlog

_log = structlog.get_logger().bind(module="disclaimer_routes")

router = APIRouter(prefix="/api", tags=["disclaimer"])


class DisclaimerAcceptanceRequest(BaseModel):
	"""Request to log disclaimer acceptance"""

	form_session_id: str = Field(..., description="Frontend form session ID")
	language: str = Field(..., description="Language user selected (e.g., 'Spanish', 'English')")
	timestamp: int = Field(..., description="Unix timestamp (milliseconds) when user clicked 'I Agree'")
	user_agent: Optional[str] = Field(None, description="Browser user agent string")


@router.post("/disclaimer-acceptance")
async def log_disclaimer_acceptance(
	data: DisclaimerAcceptanceRequest,
	request: Request
) -> dict:
	"""
	Log user's acceptance of disclaimer modal.

	This creates an audit trail for legal protection. Logs include:
	- Timestamp of acceptance
	- Selected language
	- Form session ID
	- User agent and IP address

	Returns:
		{"status": "logged", "timestamp": <iso_string>}
	"""
	# Get client IP address
	client_ip = request.client.host if request.client else "unknown"

	# Convert timestamp to ISO format for readability
	iso_timestamp = datetime.fromtimestamp(data.timestamp / 1000).isoformat()

	# Structured logging for audit trail
	_log.info(
		"disclaimer_accepted",
		form_session_id=data.form_session_id,
		language=data.language,
		timestamp_unix_ms=data.timestamp,
		timestamp_iso=iso_timestamp,
		user_agent=data.user_agent,
		client_ip=client_ip,
	)

	return {
		"status": "logged",
		"timestamp": iso_timestamp,
		"session_id": data.form_session_id,
	}
