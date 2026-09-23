"""
Disclaimer Acceptance Logging Routes

Provides endpoint for logging user acceptance of disclaimer modal.
Creates audit trail for legal protection and compliance tracking.
"""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends

from ..utils.rate_limit import TOO_MANY, rate_limited
from pydantic import BaseModel, Field, field_validator
import structlog

# ALIASED deliberately: the route handler below is also called
# log_disclaimer_acceptance, and a bare import would be SHADOWED by it at
# import time -- the call would resolve to the handler, raise TypeError on
# the kwargs, and get swallowed by the fail-open except, so the durable
# write would silently never happen (caught in fresh-eyes review of bd
# polyglot-pdf-0dsv4, after tests that patched the shadowed name passed).
from ..utils.confirmation_logger import (
	log_disclaimer_acceptance as write_durable_acceptance_record,
)

_log = structlog.get_logger(module="disclaimer_routes")

router = APIRouter(prefix="/api", tags=["disclaimer"])

# Timestamp bounds (bd polyglot-pdf-q34sy, closed by sprint 23 C4). Unlike its
# sibling fields (form_session_id, language, user_agent, script_version --
# bounded by bd polyglot-pdf-g3kui), timestamp had no Field constraint at all:
# zero, negative, or a far-future value was written verbatim into the durable
# confirmation_events legal-evidence record. The record's core claim is WHEN
# acceptance happened, so an absurd value here does more damage than an
# oversized string field would.
#
# _MIN_TIMESTAMP_MS is not before this route existed (2025-11-01 UTC, ahead of
# the route's actual add date so the bound never has to be revisited for
# clock skew on old deploys); the buffer is generous on purpose -- the goal is
# to catch zero/negative/obviously-wrong values, not to model exact clock
# drift.
_MIN_TIMESTAMP_MS = 1761955200000  # 2025-11-01T00:00:00Z
# How far into the future a client clock is allowed to be. A few minutes
# covers real client clock skew without admitting a fabricated future date.
_MAX_FUTURE_SKEW_MS = 5 * 60 * 1000


class DisclaimerAcceptanceRequest(BaseModel):
	"""Request to log disclaimer acceptance.

	EVERY FIELD IS BOUNDED (bd polyglot-pdf-g3kui). This route is
	UNAUTHENTICATED and cannot be gated: a client filling a form has no account
	by design -- the magic link is their only entry (maintainer, 2026-08-24) --
	so requiring a token would 401 every real user at the Agree button. Since
	bd polyglot-pdf-0dsv4 the route also writes DURABLY to the legal-evidence
	collection, so an unbounded body is an unbounded write to that collection.

	None of these are free text: a session id is a generated token, a language
	is one of a fixed set, a timestamp is a number, and the other two are a
	user-agent string and a 16-char hash. The caps are set well above every
	real value and reject at the MODEL, so an oversized body never reaches the
	handler or the sink.
	"""

	form_session_id: str = Field(
		..., min_length=1, max_length=128,
		description="Frontend form session ID",
	)
	language: str = Field(
		..., min_length=1, max_length=64,
		description="Language user selected (e.g., 'Spanish', 'English')",
	)
	timestamp: int = Field(..., description="Unix timestamp (milliseconds) when user clicked 'I Agree'")

	@field_validator("timestamp")
	@classmethod
	def _bound_timestamp(cls, v: int) -> int:
		"""Reject an obviously-invalid acceptance time (bd polyglot-pdf-q34sy).

		Zero, negative, and pre-route values are refused by the lower bound;
		a value more than a few minutes in the future is refused by the upper
		bound (real client clock skew, not a fabricated future date). Both
		raise ValueError, which Pydantic turns into a 422 -- the caller never
		reaches the handler, so an out-of-bound value never touches the
		durable confirmation_events sink.
		"""
		if v < _MIN_TIMESTAMP_MS:
			raise ValueError(
				f"timestamp {v} is before this route existed "
				f"(minimum {_MIN_TIMESTAMP_MS})"
			)
		now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
		if v > now_ms + _MAX_FUTURE_SKEW_MS:
			raise ValueError(
				f"timestamp {v} is more than {_MAX_FUTURE_SKEW_MS}ms in the future"
			)
		return v
	user_agent: Optional[str] = Field(
		None, max_length=512,
		description="Browser user agent string",
	)
	# Which exact disclaimer TEXT the user agreed to (sprint 20, bd
	# polyglot-pdf-s1iex.7). Optional for two DIFFERENT reasons: a client one
	# deploy behind simply predates the field, while the legacy model-read
	# path omits it because the client sources the value from the intro
	# player, which is only constructed when the intro flag is on. The second
	# case is a KNOWN AUDIT GAP -- the user read deterministic scripted text
	# and the record still names nothing (bd polyglot-pdf-pyebx).
	script_version: Optional[str] = Field(
		None, max_length=64,
		description="Hash of the scripted intro text the user saw/heard (intro_tts.script_version)",
	)


@router.post("/disclaimer-acceptance")
async def log_disclaimer_acceptance(
	data: DisclaimerAcceptanceRequest,
	# Sprint 23 PF-5 (bd o2fub): no oracle to protect here, so an over-budget
	# caller gets a plain 429 rather than a look-alike refusal.
	_limit: None = Depends(rate_limited("disclaimer_acceptance", status_code=429, detail=TOO_MANY)),
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

	# DURABLE record (bd polyglot-pdf-0dsv4). The structlog line above ages out
	# with the log bucket; this writes the same acceptance to the confirmation
	# sink -- Firestore plus the per-session file -- keyed on form_session_id,
	# so read_confirmation_log() returns the acceptance and the field
	# confirmations as ONE timestamp-ordered session record.
	#
	# FAIL-OPEN, deliberately: a sink outage must never 500 an Agree click and
	# block the user from starting their form. _submit_firestore_write already
	# swallows and logs its own failures, but the file write and any import-time
	# error are caught here so nothing on this path can reach the client.
	try:
		write_durable_acceptance_record(
			form_session_id=data.form_session_id,
			language=data.language,
			timestamp_unix_ms=data.timestamp,
			script_version=data.script_version,
			user_agent=data.user_agent,
			# No firm_id, PERMANENTLY: a client filling a form has no account
			# by design -- the magic link is their only entry, and only firms,
			# managers and devs have auth accounts (maintainer, 2026-08-24) --
			# so this route can never carry a client token. Written as None so
			# the record shape matches the rest of the collection; the firm is
			# recovered via firm_of_events(), which is the long-term answer,
			# not a stopgap (bd polyglot-pdf-g3kui).
			firm_id=None,
		)
	except TypeError as e:
		# A TypeError here is a WIRING error, not an outage: the call reached
		# something with the wrong signature. That is exactly how this feature
		# shipped broken once (the util was shadowed by this route handler,
		# which shares its name -- bd polyglot-pdf-0dsv4), and it fails on
		# EVERY request rather than intermittently. Logging it under the same
		# event name as a transient sink failure would bury a 100%-failure
		# bug inside normal degradation noise, so it gets its own name.
		_log.error(
			"disclaimer_acceptance_wiring_error",
			form_session_id=data.form_session_id,
			error_type=type(e).__name__,
			note="the durable-write call has the wrong signature; this fails on every request",
		)
	except Exception as e:
		_log.error(
			"disclaimer_acceptance_durable_write_failed",
			form_session_id=data.form_session_id,
			error_type=type(e).__name__,
		)

	return {
		"status": "logged",
		"timestamp": iso_timestamp,
		"session_id": data.form_session_id,
	}
