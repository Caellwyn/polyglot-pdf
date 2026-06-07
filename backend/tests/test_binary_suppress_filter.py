"""Guard for the binary-suppress log filter attachment (bd polyglot-pdf-h79).

configure_logging() installs a _BinarySuppressFilter that drops binary/frame
dumps and over-long INFO lines. The filter must run on records emitted through
MODULE-NAMED loggers (e.g. backend.adapters.live_ai_gemini, the name a bare
structlog.get_logger() gives the underlying stdlib logger) -- the bulk of backend
output. A logging.Filter only runs on the logger/handler it is attached to and on
records that REACH that handler; a logger-level filter does NOT run on records that
merely propagate up to root. So the filter is attached to the root StreamHandler,
where it gates every propagated record. These tests prove that attachment holds and
that a module-named logger's long record is suppressed (it was inert before h79).
"""

import logging

import pytest

from backend.utils.logging import configure_logging


@pytest.fixture
def configured_root():
    """Run configure_logging() and restore root logger state afterward."""
    root = logging.getLogger()
    saved_handlers = root.handlers[:]
    saved_filters = root.filters[:]
    saved_level = root.level
    handler_saved_filters = {h: h.filters[:] for h in saved_handlers}
    try:
        configure_logging()
        yield root
    finally:
        root.handlers[:] = saved_handlers
        root.filters[:] = saved_filters
        root.setLevel(saved_level)
        for h, filt in handler_saved_filters.items():
            h.filters[:] = filt


def _binary_suppress_handler(root):
    """The root handler carrying the _BinarySuppressFilter, or None."""
    for handler in root.handlers:
        for filt in handler.filters:
            if type(filt).__name__ == "_BinarySuppressFilter":
                return handler, filt
    return None, None


def test_filter_attached_to_root_handler(configured_root):
    handler, filt = _binary_suppress_handler(configured_root)
    assert handler is not None, "binary-suppress filter is not on any root handler"
    assert filt is not None


def test_long_record_from_module_logger_suppressed(configured_root):
    """A >2000-char INFO record emitted through a module-named logger (reaching
    root by propagation) is dropped by the handler filter -- the case that was
    inert when the filter lived only on loggers (bd polyglot-pdf-h79)."""
    handler, filt = _binary_suppress_handler(configured_root)
    assert filt is not None
    module_logger = logging.getLogger("backend.adapters.live_ai_gemini")
    long_record = module_logger.makeRecord(
        module_logger.name, logging.INFO, __file__, 0, "x" * 2595, (), None
    )
    # The handler-level filter must reject the propagated long INFO record.
    assert filt.filter(long_record) is False


def test_error_traceback_not_suppressed(configured_root):
    """A long ERROR record (rendered traceback) must survive -- the ERROR
    exemption keeps real failures debuggable in Cloud Run."""
    _, filt = _binary_suppress_handler(configured_root)
    assert filt is not None
    err_logger = logging.getLogger("backend.adapters.live_ai_gemini")
    long_error = err_logger.makeRecord(
        err_logger.name, logging.ERROR, __file__, 0, "x" * 2595, (), None
    )
    assert filt.filter(long_error) is True


def test_short_record_passes(configured_root):
    _, filt = _binary_suppress_handler(configured_root)
    assert filt is not None
    logger = logging.getLogger("backend.services.callback_handler")
    rec = logger.makeRecord(logger.name, logging.INFO, __file__, 0, "ok", (), None)
    assert filt.filter(rec) is True
