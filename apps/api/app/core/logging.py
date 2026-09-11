"""Structured logging via ``structlog``.

``configure_logging`` is called once at startup. Console renderer in
development; single-line JSON in staging/production. Request-scoped context
(``request_id``, method, path) is injected by
:class:`app.middleware.request_context.RequestContextMiddleware` through
``structlog.contextvars``.
"""

from __future__ import annotations

import logging
import sys

import structlog

from app.core.config import Settings


def configure_logging(settings: Settings) -> None:
    """Configure stdlib logging and structlog for the whole process."""
    level = logging.getLevelName(settings.log_level)
    json_output = settings.log_format == "json"

    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        timestamper,
    ]

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.processors.format_exc_info,
            (
                structlog.processors.JSONRenderer()
                if json_output
                else structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())
            ),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )

    # Route stdlib logging (uvicorn, sqlalchemy, alembic) through structlog.
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared_processors,
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                (
                    structlog.processors.JSONRenderer()
                    if json_output
                    else structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())
                ),
            ],
        )
    )

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)

    for noisy in ("uvicorn.access", "uvicorn.error", "watchfiles.main"):
        logging.getLogger(noisy).handlers = []
        logging.getLogger(noisy).propagate = True

    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a bound structlog logger."""
    return structlog.get_logger(name)  # type: ignore[no-any-return]
