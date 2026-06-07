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
			# Filter scope (bd polyglot-pdf-0uu / -h79): a logging.Filter runs on
			# the EMITTING logger only, not on parent loggers reached via
			# propagation. This filter is attached to the root logger and the
			# named "noisy" loggers below, so it runs on records emitted DIRECTLY
			# through those (incl. structlog calls whose underlying stdlib logger
			# is root or a noisy one) -- but NOT on a record emitted through some
			# other logger that merely propagates UP to root. The error path this
			# fix targets (backend.adapters.* / .services.* via bare
			# structlog.get_logger(), named after the calling module) is not root
			# and not in the noisy list, so this guard does not gate its
			# tracebacks; the ERROR exemption keeps the filter correct for any
			# error that IS emitted through a filtered logger.
			if len(msg) > 2000 and record.levelno < logging.ERROR:
				return False
			return True

	# Attach filter to the root logger
	filter_inst = _BinarySuppressFilter()
	logging.getLogger().addFilter(filter_inst)

	# Reduce noisy logging from websocket and other libraries
	noisy_loggers = [
		"websockets", "websockets.protocol", "websockets.server", "websockets.client",
		"uvicorn.protocols.websockets", "uvicorn", "uvicorn.error",
		"wsproto", "asyncio", "httpx"
	]
	
	for logger_name in noisy_loggers:
		logger = logging.getLogger(logger_name)
		logger.setLevel(logging.WARNING)
		logger.addFilter(filter_inst)
	
	# Keep uvicorn access logs at INFO level for visibility
	logging.getLogger("uvicorn.access").setLevel(logging.INFO)

