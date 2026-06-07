from __future__ import annotations

import logging
import os
import structlog
import re


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
			# Render exc_info (set by .exception() or exc_info=True) into a
			# JSON-serializable "exception" string. Without this, JSONRenderer
			# emits only "exc_info": true and DROPS the traceback, making caught
			# errors (e.g. event_handling_error in live_ai_gemini) undebuggable
			# in Cloud Run logs (bd polyglot-pdf-0uu).
			structlog.processors.format_exc_info,
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
	noisy_loggers = [
		"websockets", "websockets.protocol", "websockets.server", "websockets.client",
		"uvicorn.protocols.websockets", "uvicorn", "uvicorn.error",
		"wsproto", "asyncio", "httpx"
	]

	for logger_name in noisy_loggers:
		logger = logging.getLogger(logger_name)
		logger.setLevel(logging.WARNING)
	
	# Keep uvicorn access logs at INFO level for visibility
	logging.getLogger("uvicorn.access").setLevel(logging.INFO)

