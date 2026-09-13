from __future__ import annotations

import logging
import os
import structlog
import re
import sys
import traceback
from types import TracebackType
from typing import Any, Dict, Optional, Tuple, Type


# ============================================================================
# PII-safe exception rendering (bd polyglot-pdf-e4dt8 / E3.8)
# ============================================================================
#
# THE CONSTRAINT. structlog's stock `format_exc_info` processor renders the
# exception MESSAGE into the JSON "exception" field. In a form-filling app
# that message routinely embeds a field VALUE -- a parse error over an
# A-number, a validation error naming a date of birth -- and that field goes
# to stdout -> Cloud Run -> Cloud Logging, where PII must never land
# (docs/standards/hipaa-pii-policy.md; bd polyglot-pdf-p84m, a P0).
#
# THE OLD, LOCAL RESPONSE. Two call sites in
# backend/adapters/live_ai_gemini.py were rewritten to log
# `error_type=type(e).__name__` and to gate `self._log.exception(...)` behind
# DEV_LOGGING_ENABLED. That fixed those two sites and left every other
# `.exception()` / `exc_info=True` site under backend/ (see
# EXCEPTION_LOGGING_SITES below) rendering the message straight through --
# CLAUDE.md scar #8, an instance fixed and the set left un-enumerated.
#
# THE FIX HERE. Replace the processor, so the guarantee holds at the ONE place
# every site renders through rather than at each caller. `format_exc_info` is
# out; `pii_safe_exception_processor` emits:
#
#   error_type   the exception class NAME (queryable on its own, so a Cloud
#                Logging filter can count by type without parsing a trace)
#   stack_trace  a synthetic traceback carrying only FRAMES -- file, line,
#                function -- plus each exception's TYPE, and NO message, NO
#                locals, NO source lines.
#   severity     the level, UPPERCASED.
#
# WHY THAT EXACT SHAPE. Cloud Error Reporting ingests a log entry as an error
# when it carries an uppercase `severity` of ERROR or above plus a
# stack_trace-shaped field, and it GROUPS on the frames. The pre-existing
# alternative -- a bare `error_type=...` line -- is PII-safe but ungroupable:
# Error Reporting shows nothing and the operator is back to grepping. A file
# path, a line number and a function name are repository facts, not user data,
# so frames give grouping and a debuggable location at no privacy cost.
#
# WHY THE MESSAGE IS DROPPED RATHER THAN SCRUBBED. There is no reliable way to
# tell a message that embeds a field value from one that does not: the value
# arrives as arbitrary user speech, so no pattern covers it. Dropping the
# message wholesale is the only rule that cannot be defeated by an input.
# Developers who need the message have the DEV_LOGGING_ENABLED file log
# (backend/utils/dev_file_logger.py), which never leaves the machine.

# Frame budget. A runaway recursion produces thousands of identical frames;
# Cloud Logging truncates the entry and Error Reporting groups it badly.
# Innermost frames are the informative ones, so keep the tail.
_MAX_FRAMES = 30
# Chain budget. `raise X from Y from Z ...` can nest arbitrarily deep.
_MAX_CHAIN = 5


def _frame_lines(tb: Optional[TracebackType]) -> list:
	"""file:line:function for each frame -- never source text, never locals.

	traceback.extract_tb() reads the source line into FrameSummary.line for
	rendering; we deliberately never touch that attribute. Rendering it would
	re-open the leak by a different door for a raise like
	`raise ValueError("bad " + field_value)`, whose SOURCE text is clean but
	whose rendered line, in some renderers, is not.
	"""
	frames = traceback.extract_tb(tb)
	if len(frames) > _MAX_FRAMES:
		frames = frames[-_MAX_FRAMES:]
	return [
		'  File "{}", line {}, in {}'.format(f.filename, f.lineno, f.name)
		for f in frames
	]


def pii_safe_exception_info(
	exc_type: Optional[Type[BaseException]],
	exc_value: Optional[BaseException],
	exc_tb: Optional[TracebackType],
) -> Dict[str, Any]:
	"""Render an exception as TYPE + FRAMES, with the message removed.

	Returns a dict with "error_type" and "stack_trace". Pure and side-effect
	free, so the guarantee is testable without any logging plumbing (see
	backend/tests/unit/test_error_shape.py).

	The chain (__cause__ from an explicit `raise X from Y`, __context__ from
	an implicit re-raise inside an except block) is WALKED, because Python's
	own rendering walks it and the inner exception is usually the one that
	touched the field value. Each link contributes its frames and its type;
	none contributes its message.
	"""
	if exc_type is None:
		return {}

	# PASS 1: walk OUTWARD from the exception we were handed to its causes,
	# collecting (type, tb, joiner-that-introduces-the-NEXT-one-out).
	links = []
	seen = set()
	cur_type: Optional[Type[BaseException]] = exc_type
	cur_value: Optional[BaseException] = exc_value
	cur_tb: Optional[TracebackType] = exc_tb

	while cur_type is not None and len(links) < _MAX_CHAIN:
		links.append((cur_type, cur_tb))
		if cur_value is None:
			break
		# id() guards a self-referential or cyclic chain, which __context__
		# can produce when an exception is re-raised inside its own handler.
		if id(cur_value) in seen:
			break
		seen.add(id(cur_value))

		nxt = cur_value.__cause__
		if nxt is None and not cur_value.__suppress_context__:
			nxt = cur_value.__context__
		if nxt is None:
			break
		cur_type, cur_value, cur_tb = type(nxt), nxt, nxt.__traceback__

	# PASS 2: render OLDEST-CAUSE-FIRST, the order Python itself prints, so
	# the trace reads top-down from the original failure to the one that
	# surfaced. The joiner text is Python's, minus the messages.
	blocks = []
	for depth, (link_type, link_tb) in enumerate(reversed(links)):
		if depth:
			blocks.append(
				"\nThe above exception was the direct cause of the following "
				"exception:\n")
		lines = ["Traceback (most recent call last):"]
		lines.extend(_frame_lines(link_tb))
		# TYPE ONLY on the terminating line. Python would print
		# "ValueError: <message>"; we print "ValueError" and stop.
		lines.append(getattr(link_type, "__name__", str(link_type)))
		blocks.append("\n".join(lines))

	return {
		"error_type": getattr(exc_type, "__name__", str(exc_type)),
		"stack_trace": "\n".join(blocks),
	}


def _normalize_exc_info(exc_info: Any) -> Optional[Tuple]:
	"""Turn structlog's several exc_info spellings into a (type, value, tb).

	structlog hands this processor whatever the caller passed:
	  * True             -- from `log.warning(..., exc_info=True)` and from
	                        `log.exception(...)`, which sets it to True.
	  * an exception     -- from `log.error(..., exc_info=exc)`.
	  * a 3-tuple        -- from an explicit sys.exc_info() call.
	Anything else (None, False) means "no exception here".
	"""
	if exc_info is None or exc_info is False:
		return None
	if exc_info is True:
		info = sys.exc_info()
		return info if info[0] is not None else None
	if isinstance(exc_info, BaseException):
		return (type(exc_info), exc_info, exc_info.__traceback__)
	if isinstance(exc_info, tuple) and len(exc_info) == 3:
		return exc_info if exc_info[0] is not None else None
	return None


def pii_safe_exception_processor(logger, method_name, event_dict):
	"""structlog processor: replace exc_info with PII-safe type + frames.

	Drop-in replacement for structlog.processors.format_exc_info in the chain
	configured below. Consumes "exc_info" (so JSONRenderer never sees the raw
	traceback object, and never emits a bare `"exc_info": true`) and adds
	"error_type" + "stack_trace" in its place.

	Also uppercases the level into "severity". Cloud Logging reads `severity`,
	not structlog's lowercase `level`, and Error Reporting only ingests an
	entry whose severity is ERROR or above -- so without this the frames would
	be emitted and then ignored. `level` is left in place: existing log
	queries and the token-cost tooling read it.
	"""
	level = event_dict.get("level")
	if isinstance(level, str):
		event_dict["severity"] = level.upper()

	if "exc_info" not in event_dict:
		return event_dict

	info = _normalize_exc_info(event_dict.pop("exc_info"))
	if info is None:
		return event_dict

	event_dict.update(pii_safe_exception_info(*info))
	return event_dict


# EVERY file under backend/ that renders an exception through structlog --
# i.e. calls `.exception(...)` or passes `exc_info=`. Pinned as a SET
# (CLAUDE.md scar #8) by backend/tests/unit/test_error_shape.py, which
# re-derives it from the AST and fails on any addition or removal.
#
# This is a REGISTER, not a permission gate: structlog has ONE global
# processor chain, so every site below renders through
# pii_safe_exception_processor by construction. The list's job is to make an
# addition VISIBLE at review time, and to let a reviewer check the claim "all
# of them are safe" against a real enumeration instead of against recall.
#
# backend/utils/logging.py itself is excluded (it DEFINES the processor),
# as are backend/tests/** and backend/scripts/** (operator probes, the same
# carve-out backend/tests/unit/test_deployed_iam_envelope.py draws).
EXCEPTION_LOGGING_SITES = (
	"backend/adapters/live_ai_gemini.py",
	"backend/routes/editor_kit_routes.py",
	"backend/services/validation_handler.py",
)


def configure_logging() -> None:
	"""Configure stdlib logging and structlog.

	Logging level can be controlled via LOG_LEVEL environment variable.
	If not set, defaults to INFO.
	"""
	
	# Get log level from environment or default to INFO
	log_level_str = os.getenv("LOG_LEVEL", "INFO").upper()
	log_level = getattr(logging, log_level_str, logging.INFO)
	
	# Configure stdlib logging
	logging.basicConfig(level=log_level, format="%(message)s")
	
	# Ensure root logger level is set
	logging.getLogger().setLevel(log_level)
	
	# Configure structlog - let stdlib logging handle level filtering
	structlog.configure(
		processors=[
			structlog.processors.add_log_level,
			structlog.processors.TimeStamper(fmt="iso"),
			# Render exc_info (set by .exception() or exc_info=True) into
			# JSON-serializable "error_type" + "stack_trace" fields, and
			# uppercase the level into "severity". Without SOME exc_info
			# processor here, JSONRenderer emits only "exc_info": true and
			# DROPS the traceback, making caught errors (e.g.
			# event_handling_error in live_ai_gemini) undebuggable in Cloud
			# Run logs (bd polyglot-pdf-0uu).
			#
			# This is DELIBERATELY NOT structlog.processors.format_exc_info,
			# which renders the exception MESSAGE -- and in a form-filling app
			# that message can embed a field VALUE (bd polyglot-pdf-p84m, a
			# P0). See the module header above for the full rationale and for
			# why the shape below is what Cloud Error Reporting groups on.
			# Pinned by backend/tests/unit/test_error_shape.py.
			pii_safe_exception_processor,
			structlog.processors.JSONRenderer(),
		],
		logger_factory=structlog.stdlib.LoggerFactory(),
		wrapper_class=structlog.stdlib.BoundLogger,  # Use stdlib bound logger, not filtering one
		cache_logger_on_first_use=True,
	)

	# Define filter to suppress binary dumps
	class _BinarySuppressFilter(logging.Filter):
		# Match markers like '< BINARY' or '> BINARY', '[NNN bytes]',
		# or long runs of hex byte tokens (e.g. 'df ff ab 00 ...')
		_hex_run = r'(?:\b[0-9a-fA-F]{2}\b(?:\s+[0-9a-fA-F]{2}\b){8,})'
		_pattern = re.compile(r'(<|>)\s*BINARY\b|\[\s*\d+\s*bytes\s*\]|' + _hex_run, re.IGNORECASE)

		def filter(self, record: logging.LogRecord) -> bool:
			msg = record.getMessage()
			if not msg:
				return True
			# If the message looks like a binary/frame dump, suppress it.
			if self._pattern.search(msg):
				return False
			# Also suppress extremely long messages which commonly indicate byte
			# dumps (defensive). EXEMPT ERROR-and-above so a rendered exception
			# traceback (format_exc_info -> JSON "exception" field) -- legitimate
			# multi-line content that routinely exceeds 2000 chars -- is never
			# dropped; error logs are exactly when we need the traceback. Binary
			# dumps log at INFO/DEBUG, so the guard still catches them.
			#
			# Filter scope (bd polyglot-pdf-0uu / -h79): a logging.Filter runs
			# uniformly on every record that reaches the HANDLER it is attached
			# to, regardless of which logger emitted the record. We attach this
			# filter to the root StreamHandler below (not just to loggers), so it
			# DOES gate the module-named structlog records (backend.adapters.* /
			# .services.* via bare structlog.get_logger(), named after the calling
			# module) that previously reached root only by propagation -- handler
			# filters run on propagated records, logger filters do not. The ERROR
			# exemption keeps a rendered exception traceback (format_exc_info ->
			# JSON "exception" field, routinely >2000 chars) from being dropped.
			if len(msg) > 2000 and record.levelno < logging.ERROR:
				return False
			return True

	# Attach the filter to the root logger's StreamHandler (created by
	# basicConfig above). A HANDLER-level filter runs on every record that
	# reaches the handler -- including records that propagated up from a
	# module-named structlog logger -- whereas a LOGGER-level filter runs only on
	# records emitted directly through that logger. Handler attachment is what
	# makes the suppression apply to the bulk of (module-named) structlog output
	# (bd polyglot-pdf-h79). Fall back to a root-logger filter if no handler is
	# present (basicConfig should always create one, but be defensive).
	filter_inst = _BinarySuppressFilter()

	def _has_binary_filter(target) -> bool:
		# Idempotency: configure_logging() may run more than once (import-time
		# call + a test re-invoking it). Don't stack a duplicate filter on a
		# handler/logger that already carries one. Match by class NAME, not
		# isinstance: _BinarySuppressFilter is defined fresh inside each
		# configure_logging() call, so a second call's class object differs from
		# the first's -- an isinstance check would miss the first call's instances
		# and stack a duplicate anyway (Copilot review of PR #106).
		return any(type(f).__name__ == "_BinarySuppressFilter" for f in target.filters)

	root_handlers = logging.getLogger().handlers
	if root_handlers:
		for handler in root_handlers:
			if not _has_binary_filter(handler):
				handler.addFilter(filter_inst)
	else:
		root = logging.getLogger()
		if not _has_binary_filter(root):
			root.addFilter(filter_inst)

	# Reduce noisy logging from websocket and other libraries. The level cap is
	# per-logger; the binary-suppress filter now lives on the root handler above,
	# so it already covers records these loggers propagate to root -- no per-logger
	# addFilter needed.
	# uvicorn.access is in this list on purpose, not exempted: its INFO line is
	# the full request target, and /ws/fill carries the caller's credential
	# in the query string (?token=), so an access line at INFO writes a live
	# Firebase ID token or magic-link token into stdout -> Cloud Logging. The
	# deployed image also passes --no-access-log (Dockerfile); this cap is the
	# independent guard for a uvicorn started without that flag. Pinned by
	# tests/test_logging_access_log.py (bd polyglot-pdf-6rj0j).
	noisy_loggers = [
		"websockets", "websockets.protocol", "websockets.server", "websockets.client",
		"uvicorn.protocols.websockets", "uvicorn", "uvicorn.error", "uvicorn.access",
		"wsproto", "asyncio", "httpx"
	]

	for logger_name in noisy_loggers:
		logger = logging.getLogger(logger_name)
		logger.setLevel(logging.WARNING)

