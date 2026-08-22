"""
Disclaimer Acceptance Logging Routes

Provides endpoint for logging user acceptance of disclaimer modal.
Creates audit trail for legal protection and compliance tracking.
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter
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
	# Which exact disclaimer TEXT the user agreed to (sprint 20, bd
	# polyglot-pdf-s1iex.7). Optional for two DIFFERENT reasons: a client one
	# deploy behind simply predates the field, while the legacy model-read
	# path omits it because the client sources the value from the intro
	# player, which is only constructed when the intro flag is on. The second
	# case is a KNOWN AUDIT GAP -- the user read deterministic scripted text
	# and the record still names nothing (bd polyglot-pdf-pyebx).
	script_version: Optional[str] = Field(
		None,
		description="Hash of the scripted intro text the user saw/heard (intro_tts.script_version)",
	)


@router.post("/disclaimer-acceptance")
async def log_disclaimer_acceptance(
	data: DisclaimerAcceptanceRequest,
) -> dict:
	"""
	Log user's acceptance of disclaimer modal.

	This creates an audit trail for legal protection. Logs include:
	- Timestamp of acceptance
	- Selected language
	- Form session ID
	- User agent (device class -- deliberate low-sensitivity retention)
	- script_version: WHICH TEXT they agreed to (bd polyglot-pdf-s1iex.7)

	`script_version` is what turns determinism into EVIDENCE. Sol's intro is
	synthesized from a fixed per-language script, so the record can now name
	the exact text -- without it the log proves someone clicked Agree but not
	what they were told. Non-PII: a hash of copy that ships in the client
	bundle. None on a client one deploy behind, and None on the legacy
	model-read path -- NOT because that path lacks deterministic text (it
	serves the same scripted paragraphs), but because the client reads the
	value off the intro player, which exists only when the intro flag is on.
	On the default deployment that leaves a real evidence gap, tracked by bd
	polyglot-pdf-pyebx.

	The client IP is deliberately NOT logged (bd polyglot-pdf-z2is): an IP is
	PII under GDPR/CCPA, and the acceptance evidence that matters is the
	form_session_id + timestamp + language + disclaimer flow itself. Re-add
	only as a deliberate decision once counsel answers what retention is
	legally required (bd polyglot-pdf-pol2).

	Returns:
		{"status": "logged", "timestamp": <iso_string>}
	"""
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
		script_version=data.script_version,
	)

	return {
		"status": "logged",
		"timestamp": iso_timestamp,
		"session_id": data.form_session_id,
	}
