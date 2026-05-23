"""
acceleration.observability.logger
=================================

Structured JSON logger for the Development Acceleration Analysis pipeline.

Mandated by AAP Rule 1 (Observability) and decision-log row D-003. Imported by
every script in ``acceleration/scripts/`` to produce one JSON object per log
line, tagged with a run-scoped correlation ID.

Output format (one JSON object per line, UTF-8, written to ``sys.stdout``):

.. code-block:: json

    {
      "timestamp": "2026-05-15T12:34:56.789012Z",
      "level": "INFO",
      "name": "acceleration.scripts.extract_git",
      "message": "Extracted 5178 commits",
      "correlation_id": "8c7b9f5e-2a4d-4f6a-8b9e-1c2d3e4f5a6b",
      "ts": "2026-05-15T12:34:56.789012Z",
      "logger": "acceleration.scripts.extract_git",
      "msg": "Extracted 5178 commits",
      "run_id": "8c7b9f5e-2a4d-4f6a-8b9e-1c2d3e4f5a6b",
      "extra": {"commits": 5178, "duration_ms": 1234}
    }

Field-name contract
-------------------

Each record carries BOTH the canonical aggregator-friendly field names
(``timestamp`` / ``name`` / ``message`` / ``correlation_id``) AND the compact
pipeline-internal aliases (``ts`` / ``logger`` / ``msg`` / ``run_id``). This
satisfies (a) downstream log aggregators (Datadog, Loki, OpenSearch, Splunk)
whose default source-type parsers key on the canonical names without requiring
a remapping rule, and (b) the existing internal consumers
(:file:`observability/dashboard.html`, :file:`observability/README.md`) which
were originally documented against the compact names. Both alias sets carry
the same value byte-for-byte. The trade-off — slightly larger per-line byte
cost in exchange for parser-defaults compatibility — is recorded in
:file:`decision-log.md` row ``D-014``.

Module guarantees
-----------------

1. **Stdlib-only.** No third-party imports are required at any point. The
   module loads on a clean Python 3.10+ installation without ``pip install``.

2. **Side-effect-free at import time.** The module defines classes and helper
   functions but does not configure the root logger, allocate a UUID, or read
   the environment until ``get_logger`` (or one of the helpers) is called.

3. **Foundational position.** This module is the most foundational artifact in
   the analysis pipeline and MUST NOT import from any other ``acceleration.*``
   module. Every other Python script under ``acceleration/`` depends on it.

4. **Logs to stdout.** Each log record is written to ``sys.stdout`` so that
   any modern log shipper attached to the process picks the lines up via the
   conventional stdout channel. Scripts that need to emit machine-readable
   output for capture by a caller (for example, a JSON document piped into
   another tool) MUST write to an explicit file path rather than relying on
   stdout being log-free. The orchestrator captures stdout into the run
   manifest separately, so log lines coexist cleanly with any auxiliary
   stdout writes a script may produce.

Environment variables
---------------------

- ``ACCEL_RUN_ID``  Optional. If present, used as the default correlation ID
  injected into every log record where no explicit ``run_id`` is supplied.
  Otherwise a UUID4 is generated lazily on first use of ``get_default_run_id``.

- ``ACCEL_LOG_LEVEL``  Optional. One of ``DEBUG``, ``INFO``, ``WARNING``,
  ``ERROR``, ``CRITICAL``. Defaults to ``INFO`` when unset or invalid.

Public surface
--------------

- :func:`generate_run_id` - return a fresh UUID4 string.
- :func:`set_default_run_id` - set the process-wide default correlation ID.
- :func:`get_default_run_id` - read (and lazily allocate) the process-wide
  default correlation ID.
- :func:`get_logger` - factory returning a configured ``logging.Logger``.
- :class:`JsonFormatter` - ``logging.Formatter`` emitting one JSON object per
  line.
- :class:`CorrelationFilter` - ``logging.Filter`` that injects ``run_id`` into
  every record processed by the logger it is attached to.

See also
--------

- ``acceleration/observability/README.md`` - reused-vs-added disclosure for
  Rule 1 observability components and a "How to Exercise Locally" walkthrough.
- ``acceleration/decision-log.md`` decision row ``D-003`` - rationale for
  shipping a self-contained Python logger rather than importing the Formbricks
  application's ``@formbricks/logger`` / ``@opentelemetry/sdk-node`` stack.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from typing import Any

# ---------------------------------------------------------------------------
# Public exports
# ---------------------------------------------------------------------------

__all__ = [
    "JsonFormatter",
    "CorrelationFilter",
    "generate_run_id",
    "set_default_run_id",
    "get_default_run_id",
    "get_logger",
]

# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------
# The process-wide default correlation ID is generated lazily on first use so
# that simply importing this module remains side-effect-free. ``_configured``
# guards ``_configure_root_logger`` so that the root logger is set up exactly
# once across the process lifetime even when ``get_logger`` is called many
# times.

_default_run_id: str | None = None
_configured: bool = False

# Names of the standard ``logging.LogRecord`` attributes. These must be
# excluded from the ``extra`` JSON object emitted by :class:`JsonFormatter` so
# that the output does not duplicate internal logging metadata. The set also
# contains ``run_id`` (managed at the top level of the payload) and ``taskName``
# (added in Python 3.12 for asyncio task identification).
_RESERVED_RECORD_ATTRS: frozenset[str] = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "message",
        "module",
        "msecs",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "taskName",
        "thread",
        "threadName",
        # Custom payload fields managed at the top level of the JSON object:
        "run_id",
    }
)

# Recognised log-level names, used to validate ``ACCEL_LOG_LEVEL``.
_VALID_LOG_LEVELS: frozenset[str] = frozenset(
    {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
)


# ---------------------------------------------------------------------------
# Correlation-ID helpers
# ---------------------------------------------------------------------------


def generate_run_id() -> str:
    """Return a fresh UUID4 string suitable for use as a correlation ID.

    Returns
    -------
    str
        A canonical UUID4 string (32 hexadecimal characters arranged in the
        standard ``8-4-4-4-12`` layout).
    """

    return str(uuid.uuid4())


def set_default_run_id(run_id: str) -> None:
    """Set the process-wide default correlation ID.

    The default is used by :func:`get_logger` whenever no explicit ``run_id``
    is passed and by :class:`CorrelationFilter` whenever a record arrives
    without one already attached.

    Parameters
    ----------
    run_id : str
        The correlation ID to apply for the remainder of this process. May be
        any non-empty string; UUID4 (via :func:`generate_run_id`) is the
        recommended format for cross-system correlation.
    """

    global _default_run_id
    _default_run_id = run_id


def get_default_run_id() -> str:
    """Return the current process-wide correlation ID.

    Lazily initialised on first use. The resolution order is:

    1. Whatever value was last passed to :func:`set_default_run_id`.
    2. The value of the ``ACCEL_RUN_ID`` environment variable, if set.
    3. A freshly generated UUID4 string.

    Returns
    -------
    str
        The current process-wide correlation ID.
    """

    global _default_run_id
    if _default_run_id is None:
        # Honour an environment-supplied run_id so that the orchestrator can
        # group child-process logs into the same correlation as the parent.
        env_run_id = os.environ.get("ACCEL_RUN_ID")
        _default_run_id = env_run_id if env_run_id else generate_run_id()
    return _default_run_id


# ---------------------------------------------------------------------------
# JSON formatter
# ---------------------------------------------------------------------------


class JsonFormatter(logging.Formatter):
    """Render each :class:`logging.LogRecord` as a single JSON object.

    Output fields (in stable, predictable order). Each record carries BOTH
    a canonical aggregator-friendly name AND a compact pipeline-internal
    alias for the timestamp, logger name, message body, and correlation ID.
    Both values are byte-for-byte identical per record.

    Canonical names (parser-default-friendly for Datadog / Loki / OpenSearch /
    Splunk):

    ``timestamp``
        ISO 8601 UTC timestamp with microsecond precision and a trailing
        ``Z`` suffix.

    ``level``
        Logging level name (``DEBUG``, ``INFO``, ``WARNING``, ``ERROR``,
        ``CRITICAL``).

    ``name``
        The logger name, typically the caller's ``__name__``.

    ``message``
        The rendered log message produced by ``record.getMessage()``.

    ``correlation_id``
        Run-scoped correlation ID injected by :class:`CorrelationFilter`.
        ``None`` if no filter has run, which should not happen when the
        logger was obtained via :func:`get_logger`.

    Compact aliases (pipeline-internal, consumed by
    :file:`observability/dashboard.html`):

    ``ts`` (alias of ``timestamp``)
    ``logger`` (alias of ``name``)
    ``msg`` (alias of ``message``)
    ``run_id`` (alias of ``correlation_id``)

    Other fields:

    ``extra`` (optional)
        Any keyword arguments the caller passed via the ``extra=`` parameter
        of the logging call, plus any other non-reserved attributes set on
        the record. Omitted when empty.

    ``exc_info`` (optional)
        Exception type, message, and full traceback. Present only when the
        caller invoked ``logger.exception(...)`` or supplied ``exc_info=``.

    ``format_error`` (optional)
        Present only if JSON serialisation failed. Carries the error message
        from ``json.dumps``; the payload is degraded to message-only content.

    The formatter never raises. If a value in the ``extra`` payload is not
    JSON-serialisable, ``json.dumps`` is invoked with ``default=str`` to
    coerce it to a string; if even that fails, the formatter falls back to a
    minimal safe record carrying only the core fields plus the
    ``format_error`` diagnostic.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Render ``record`` as a single-line JSON object.

        Parameters
        ----------
        record : logging.LogRecord
            The log record to format.

        Returns
        -------
        str
            A single line of JSON ending without a trailing newline; the
            underlying :class:`logging.StreamHandler` appends the newline.
        """

        # Render the user-provided message. ``record.getMessage()`` applies
        # %-formatting using ``record.args``. We guard against malformed
        # format strings so that the formatter cannot raise out from inside
        # the logging call site.
        try:
            message = record.getMessage()
        except Exception as exc:  # pragma: no cover - defensive
            message = f"<unrenderable message: {exc}>"

        # Compute the canonical values once and emit them under BOTH the
        # aggregator-friendly canonical name AND the compact pipeline-internal
        # alias. The byte cost of duplication is accepted in exchange for
        # parser-defaults compatibility with Datadog / Loki / OpenSearch /
        # Splunk on one side and continued backward compatibility with the
        # internal dashboard / README consumers on the other. See
        # decision-log row D-014 for the trade-off discussion.
        ts_value = self._format_timestamp(record.created)
        name_value = record.name
        message_value = message
        correlation_id_value = getattr(record, "run_id", None)

        payload: dict[str, Any] = {
            # Canonical aggregator-friendly names (Datadog / Loki / OpenSearch
            # / Splunk default source-type parsers key on these).
            "timestamp": ts_value,
            "level": record.levelname,
            "name": name_value,
            "message": message_value,
            "correlation_id": correlation_id_value,
            # Compact pipeline-internal aliases (consumed by
            # observability/dashboard.html and observability/README.md).
            "ts": ts_value,
            "logger": name_value,
            "msg": message_value,
            "run_id": correlation_id_value,
        }

        # Collect every non-reserved attribute on the record into a single
        # ``extra`` object. Logging's ``extra=`` kwarg sets attributes
        # directly on the record's ``__dict__``; iterating it here is the
        # canonical way to discover them. Attributes starting with an
        # underscore are treated as private to the logging framework or to
        # the caller and are excluded.
        extra: dict[str, Any] = {}
        for key, value in record.__dict__.items():
            if key in _RESERVED_RECORD_ATTRS:
                continue
            if key.startswith("_"):
                continue
            extra[key] = value
        if extra:
            payload["extra"] = extra

        # Capture exception information when present. The 3-tuple may also
        # be ``(None, None, None)`` in pathological cases; guard each
        # accessor.
        if record.exc_info:
            exc_type, exc_value, _exc_tb = record.exc_info
            payload["exc_info"] = {
                "type": exc_type.__name__ if exc_type else None,
                "message": str(exc_value) if exc_value is not None else None,
                "traceback": self.formatException(record.exc_info),
            }
        elif record.exc_text:
            # A previously-rendered exception text on the record without a
            # live ``exc_info`` tuple (rare; see logging cookbook).
            payload["exc_info"] = {
                "type": None,
                "message": None,
                "traceback": record.exc_text,
            }

        # Capture stack info when ``stack_info=True`` was passed to the
        # logging call.
        if record.stack_info:
            payload["stack_info"] = record.stack_info

        # First attempt: full payload with ``default=str`` coercion for any
        # non-JSON-native types in ``extra`` (e.g. ``Path``, ``Decimal``,
        # ``datetime``). If a custom ``__str__`` raises, fall through to the
        # minimal safe record.
        try:
            return json.dumps(payload, default=str, ensure_ascii=False)
        except (TypeError, ValueError) as exc:
            safe_payload: dict[str, Any] = {
                # Canonical names
                "timestamp": ts_value,
                "level": payload["level"],
                "name": name_value,
                "message": message_value,
                "correlation_id": correlation_id_value,
                # Compact aliases
                "ts": ts_value,
                "logger": name_value,
                "msg": message_value,
                "run_id": correlation_id_value,
                "format_error": str(exc),
            }
            return json.dumps(safe_payload, default=str, ensure_ascii=False)

    @staticmethod
    def _format_timestamp(created: float) -> str:
        """Convert a Unix timestamp into an ISO 8601 UTC string.

        The result has microsecond precision and a trailing ``Z`` instead of
        the ``+00:00`` offset emitted by :meth:`datetime.isoformat`.

        Parameters
        ----------
        created : float
            A Unix timestamp (seconds since the epoch), typically
            ``record.created``.

        Returns
        -------
        str
            For example, ``"2026-05-15T12:34:56.789012Z"``.
        """

        dt = datetime.fromtimestamp(created, tz=timezone.utc)
        iso = dt.isoformat(timespec="microseconds")
        # Replace ``+00:00`` with ``Z`` for the conventional UTC suffix
        # consumed by JSON-line log aggregators (Loki, OpenSearch, Datadog,
        # Splunk, Elastic).
        if iso.endswith("+00:00"):
            iso = iso[:-6] + "Z"
        return iso


# ---------------------------------------------------------------------------
# Correlation filter
# ---------------------------------------------------------------------------


class CorrelationFilter(logging.Filter):
    """Inject a ``run_id`` attribute into every record passed through.

    Resolution order, evaluated per record:

    1. If the record already has a non-``None`` ``run_id`` attribute (for
       example, because the caller passed ``extra={"run_id": "..."}``),
       leave it unchanged. This lets callers override the correlation ID
       on a per-call basis.
    2. Otherwise, use the run_id configured on this filter instance.
    3. Otherwise, fall back to :func:`get_default_run_id`.

    The filter always returns ``True`` (it is an injection filter, never a
    rejection filter).
    """

    def __init__(self, run_id: str | None = None) -> None:
        """Construct the filter.

        Parameters
        ----------
        run_id : str, optional
            The correlation ID this filter should inject when the record
            does not already carry one. If ``None``, the filter defers to
            :func:`get_default_run_id` at filter time.
        """

        super().__init__()
        self._run_id = run_id

    def filter(self, record: logging.LogRecord) -> bool:
        """Inject ``run_id`` on ``record`` and admit the record.

        Parameters
        ----------
        record : logging.LogRecord
            The log record about to be emitted.

        Returns
        -------
        bool
            Always ``True``. This filter never rejects records.
        """

        existing = getattr(record, "run_id", None)
        if existing is None:
            record.run_id = self._run_id if self._run_id else get_default_run_id()
        return True


# ---------------------------------------------------------------------------
# Logger configuration
# ---------------------------------------------------------------------------


def _resolve_log_level() -> int:
    """Translate ``ACCEL_LOG_LEVEL`` into a numeric ``logging`` level.

    Returns
    -------
    int
        The numeric level (e.g. :data:`logging.INFO`). Defaults to
        :data:`logging.INFO` when the environment variable is unset or
        contains an unrecognised value.
    """

    raw = os.environ.get("ACCEL_LOG_LEVEL", "INFO").upper().strip()
    if raw in _VALID_LOG_LEVELS:
        return getattr(logging, raw)
    return logging.INFO


def _configure_root_logger() -> None:
    """Configure the root logger exactly once for the process.

    Replaces any prior handlers on the root logger with a single
    :class:`logging.StreamHandler` routed to :data:`sys.stdout` using
    :class:`JsonFormatter`. The level is taken from ``ACCEL_LOG_LEVEL``.

    Stdout was chosen so that any log shipper attached to the process
    picks the lines up via the conventional stdout channel. Scripts that
    need to emit non-log machine-readable output for capture by a caller
    MUST write to an explicit file path rather than relying on stdout
    being log-free; the orchestrator's run-manifest capture handles
    log/output interleaving deterministically.

    Idempotent: subsequent calls are no-ops thanks to the module-level
    ``_configured`` guard.
    """

    global _configured
    if _configured:
        return

    root = logging.getLogger()

    # Remove any prior handlers (for example, anything attached by a calling
    # script through ``logging.basicConfig``). This prevents duplicate
    # emissions through both the default handler and ours.
    for handler in list(root.handlers):
        root.removeHandler(handler)

    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    root.setLevel(_resolve_log_level())

    _configured = True


def get_logger(name: str, run_id: str | None = None) -> logging.Logger:
    """Return a configured logger that emits one JSON object per line.

    On first call this configures the root logger (a single stdout
    :class:`StreamHandler` using :class:`JsonFormatter`). Subsequent calls
    re-use the root configuration.

    A :class:`CorrelationFilter` is attached to the named logger so that
    every record it produces carries a ``run_id`` field (which is duplicated
    in the emitted JSON under the canonical alias ``correlation_id``). If
    the named logger already has a :class:`CorrelationFilter` attached, the
    prior filter is removed first so that the ``run_id`` resolution is
    deterministic across repeated calls.

    Parameters
    ----------
    name : str
        Logger name. Convention: the caller's ``__name__`` (for example
        ``"acceleration.scripts.extract_git"``).
    run_id : str, optional
        Run-scoped correlation ID for this logger. When ``None``, the
        process-wide default (from :func:`get_default_run_id`) is used.

    Returns
    -------
    logging.Logger
        A logger that emits one JSON object per line to ``sys.stdout``. Each
        record carries both the canonical aggregator-friendly field names
        (``timestamp`` / ``name`` / ``message`` / ``correlation_id``) and the
        compact pipeline-internal aliases (``ts`` / ``logger`` / ``msg`` /
        ``run_id``).

    Examples
    --------
    >>> log = get_logger("acceleration.scripts.extract_git", run_id="abc")
    >>> log.info("Extracted %d commits", 5178, extra={"branch": "main"})
    # writes one JSON line to stdout with both run_id="abc" and
    # correlation_id="abc", and extra={"branch": "main"}
    """

    _configure_root_logger()
    logger = logging.getLogger(name)

    # Idempotently replace any prior CorrelationFilter so that the resolved
    # run_id is always the one supplied to the most recent call (Behaviour 2
    # in the specification).
    for existing_filter in list(logger.filters):
        if isinstance(existing_filter, CorrelationFilter):
            logger.removeFilter(existing_filter)
    logger.addFilter(CorrelationFilter(run_id))

    return logger


# ---------------------------------------------------------------------------
# Smoke test entrypoint
# ---------------------------------------------------------------------------


def _smoke_test(argv: list[str] | None = None) -> int:
    """Emit a few sample JSON log lines for a manual or scripted smoke test.

    This is the body of the ``__main__`` block, extracted into a function so
    that automated tests can drive it without invoking the interpreter via a
    subprocess.

    Parameters
    ----------
    argv : list[str], optional
        Command-line arguments excluding the program name. ``None`` (the
        default) instructs :mod:`argparse` to read :data:`sys.argv`.

    Returns
    -------
    int
        ``0`` on success. Any unexpected exception is allowed to propagate
        so the caller (or the interpreter) can surface it.
    """

    parser = argparse.ArgumentParser(
        description="Logger smoke test - emits sample JSON log lines to stdout.",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="Override the run_id (default: read ACCEL_RUN_ID, otherwise auto-generate).",
    )
    parser.add_argument(
        "--message",
        default="hello from acceleration.observability.logger",
        help="Message body for the first sample log line.",
    )
    parser.add_argument(
        "--level",
        default="INFO",
        help=(
            "Log level for the sample message "
            "(one of DEBUG, INFO, WARNING, ERROR, CRITICAL; case-insensitive)."
        ),
    )
    args = parser.parse_args(argv)

    if args.run_id:
        set_default_run_id(args.run_id)

    log = get_logger("acceleration.observability.logger.smoke")
    level_name = args.level.upper().strip()
    level = getattr(logging, level_name, logging.INFO)

    # Use ``time.monotonic`` to time the smoke test itself and report the
    # elapsed milliseconds as part of the final log line. This exercises the
    # ``time`` import declared in ``external_imports`` and demonstrates the
    # timing-instrumentation use case for downstream callers.
    started = time.monotonic()

    log.log(
        level,
        args.message,
        extra={"sample_key": "sample_value", "iteration": 1},
    )
    log.info(
        "Second message - verifying multiple lines",
        extra={"iteration": 2},
    )
    try:
        raise RuntimeError("intentional test exception")
    except RuntimeError:
        log.exception(
            "Caught an intentional test exception",
            extra={"iteration": 3},
        )

    elapsed_ms = int((time.monotonic() - started) * 1000)
    log.info(
        "Smoke test complete",
        extra={"iteration": 4, "elapsed_ms": elapsed_ms},
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(_smoke_test())
