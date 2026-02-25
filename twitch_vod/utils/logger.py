"""
Structured logging setup.

Uses structlog if available, falls back to stdlib logging.
Set LOG_LEVEL env var to control verbosity (default: INFO).
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any

_LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()


def get_logger(name: str) -> "BoundLogger":
    try:
        import structlog  # type: ignore

        structlog.configure(
            wrapper_class=structlog.make_filtering_bound_logger(
                getattr(logging, _LOG_LEVEL, logging.INFO)
            ),
        )
        return structlog.get_logger(name)
    except ImportError:
        return _StdlibLogger(name)


class _StdlibLogger:
    """Thin wrapper around stdlib logging that mimics structlog's API."""

    def __init__(self, name: str) -> None:
        self._log = logging.getLogger(name)
        if not logging.root.handlers:
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(
                logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
            )
            logging.root.addHandler(handler)
            logging.root.setLevel(getattr(logging, _LOG_LEVEL, logging.INFO))

    def _format(self, msg: str, **kw: Any) -> str:
        if kw:
            pairs = " ".join(f"{k}={v}" for k, v in kw.items())
            return f"{msg} | {pairs}"
        return msg

    def debug(self, msg: str, **kw: Any) -> None:
        self._log.debug(self._format(msg, **kw))

    def info(self, msg: str, **kw: Any) -> None:
        self._log.info(self._format(msg, **kw))

    def warning(self, msg: str, **kw: Any) -> None:
        self._log.warning(self._format(msg, **kw))

    def error(self, msg: str, **kw: Any) -> None:
        self._log.error(self._format(msg, **kw))