from __future__ import annotations

import json
import logging
import os
import sys
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone

_SEVERITY_MAP = {
    logging.DEBUG: "DEBUG",
    logging.INFO: "INFO",
    logging.WARNING: "WARNING",
    logging.ERROR: "ERROR",
    logging.CRITICAL: "CRITICAL",
}

_ON_GCP = os.getenv("K_SERVICE") is not None or os.getenv("FUNCTION_TARGET") is not None
_LOG_RECORD_FIELDS = frozenset(logging.makeLogRecord({}).__dict__)


class _CloudJsonFormatter(logging.Formatter):
    """Structured JSON formatter compatible with Cloud Logging."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "severity": _SEVERITY_MAP.get(record.levelno, "DEFAULT"),
            "message": record.getMessage(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "function_name": getattr(record, "function_name", record.name),
            "trace_id": getattr(record, "trace_id", _get_trace_id()),
            "request_id": getattr(record, "request_id", _get_trace_id()),
        }
        if record.exc_info and record.exc_info[0] is not None:
            payload["exception"] = self.formatException(record.exc_info)
        extras = {
            k: v
            for k, v in record.__dict__.items()
            if k not in _LOG_RECORD_FIELDS and k not in ("message", "msg")
        }
        if extras:
            payload.update(extras)
        return json.dumps(payload, default=str)


class _LocalFormatter(logging.Formatter):
    """Human-readable formatter for local development."""

    FMT = "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s"

    def __init__(self):
        super().__init__(self.FMT, datefmt="%H:%M:%S")


_trace_id_ctx: ContextVar[str | None] = ContextVar("trace_id", default=None)


def _get_trace_id() -> str:
    trace_id = _trace_id_ctx.get()
    if trace_id is None:
        trace_id = uuid.uuid4().hex[:16]
        _trace_id_ctx.set(trace_id)
    return trace_id


def set_trace_id(trace_id: str) -> None:
    _trace_id_ctx.set(trace_id)


def clear_trace_id() -> None:
    _trace_id_ctx.set(None)


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    handler = logging.StreamHandler(sys.stdout if _ON_GCP else sys.stderr)
    handler.setFormatter(_CloudJsonFormatter() if _ON_GCP else _LocalFormatter())
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG if os.getenv("DEBUG") else logging.INFO)
    logger.propagate = False
    return logger
