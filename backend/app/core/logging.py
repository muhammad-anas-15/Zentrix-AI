"""structlog setup: JSON lines in staging/prod, readable console in dev. Never log tokens or secrets.

In JSON mode every line on stderr/stdout is JSON, including stdlib loggers (uvicorn, httpx, SQLAlchemy): they are
routed through the same processors. uvicorn's own access log is turned off there; the API middleware logs each
request (method, path without query string, status, duration, request id).
"""

from __future__ import annotations

import logging

import structlog
from structlog.typing import Processor

_HANDLER_MARK = "_zentrix_json"


def configure_logging(json: bool, level: int = logging.INFO) -> None:
    shared: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
    ]
    renderer = structlog.processors.JSONRenderer() if json else structlog.dev.ConsoleRenderer(colors=False)
    structlog.configure(
        processors=[*shared, structlog.processors.format_exc_info, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        cache_logger_on_first_use=True,
    )
    if not json:
        logging.basicConfig(level=level, format="%(message)s")
        return
    root = logging.getLogger()
    for h in [h for h in root.handlers if getattr(h, _HANDLER_MARK, False)]:
        root.removeHandler(h)
    handler = logging.StreamHandler()
    handler.setFormatter(structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=[*shared, structlog.stdlib.add_logger_name],
        processors=[structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                    structlog.processors.format_exc_info, renderer]))
    setattr(handler, _HANDLER_MARK, True)
    root.addHandler(handler)
    root.setLevel(level)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers = []
        lg.propagate = True
    logging.getLogger("uvicorn.access").disabled = True


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
