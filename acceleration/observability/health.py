"""
acceleration.observability.health
=================================

Health and readiness checks for the Development Acceleration Analysis pipeline.

Mandated by AAP Rule 1 (Observability). The module is invoked first by
``acceleration/scripts/run_acceleration_analysis.py`` so that the orchestrator
can refuse to start when a required prerequisite (git, Python version,
writable output directory) is missing.

Public surface (matches the contract documented in
``acceleration/observability/README.md`` Section 3.2 verbatim):

- :func:`check_all` - aggregate every sub-check into a single status dict.
- :func:`check_git` - verify ``git`` is on ``PATH`` and at version ``2.40+``.
- :func:`check_repo` - verify the current working directory is inside a
  git work tree.
- :func:`check_output_dir` - verify ``acceleration/data`` (or
  ``ACCEL_OUTPUT_DIR``) is writable.
- :func:`check_github_token` - verify ``GITHUB_TOKEN`` is present
  (``warn`` when absent because the pipeline still runs with degraded
  confidence per AAP Sections 0.7.2.1 and 0.8.3).
- :func:`check_python` - verify the interpreter is Python ``3.10+``.

Each sub-check returns a dict with the shape
``{"status": "ok"|"warn"|"fail", "details": "..."}`` so a downstream caller
(a CI step, a smoke test, the orchestrator) can branch on the status
without parsing free-text output.

Module guarantees
-----------------

1. **Stdlib-only.** Imports are restricted to ``subprocess``, ``os``,
   ``sys``, ``re``, ``shutil``, ``tempfile``, ``pathlib``, and the local
   :mod:`acceleration.observability.logger` module for structured logging.
   The module loads on a clean Python 3.10+ installation without
   ``pip install``.

2. **Side-effect-free at import time.** The module defines functions but
   does not invoke any subprocess, read the environment, or write to disk
   until one of its functions is called.

3. **Always returns; never raises.** Every sub-check guards subprocess
   invocations, file-system probes, and environment reads with explicit
   exception handling. A failure to invoke an external tool produces a
   ``"fail"`` status with the captured error message in ``details``; it
   does not propagate.

4. **Foundational position.** The module is one of the foundational
   artifacts in the analysis pipeline. It imports from
   :mod:`acceleration.observability.logger` so that the orchestrator can
   correlate health-check results with the ``run_id`` used for every other
   log line.

Aggregation rule (see Section 3.2 of ``observability/README.md``)
---------------------------------------------------------------

The ``overall`` key in :func:`check_all`'s return value follows a strict
worst-status-wins rule:

- ``"fail"`` when any sub-check returns ``"fail"``.
- ``"warn"`` when no sub-check is ``"fail"`` but at least one is
  ``"warn"``.
- ``"ok"`` only when every sub-check is ``"ok"``.

The orchestrator treats ``"fail"`` as a stop signal and exits non-zero
before invoking any extractor. ``"warn"`` is non-fatal: the pipeline
proceeds with the affected metrics degraded to
``Insufficient signal - [reason]`` per AAP Section 0.7.2.1.

Environment variables
---------------------

- ``ACCEL_OUTPUT_DIR`` Optional. Overrides the default
  ``acceleration/data`` location probed by :func:`check_output_dir`.

- ``GITHUB_TOKEN`` Optional. When present, :func:`check_github_token`
  returns ``"ok"``; otherwise ``"warn"``. The token's value is never
  echoed in ``details`` (only ``"GITHUB_TOKEN set"`` is reported).

- ``ACCEL_LOG_LEVEL`` Optional. Honored by
  :mod:`acceleration.observability.logger`; controls the verbosity of
  this module's own log lines.

- ``ACCEL_RUN_ID`` Optional. Honored by
  :mod:`acceleration.observability.logger`; ties each health-check log
  line to the orchestrator's run-scoped correlation ID.

See also
--------

- ``acceleration/observability/README.md`` Section 3.2 and Section 8.2 -
  the documented API contract and the copy-pasteable smoke test.
- ``acceleration/decision-log.md`` decision row ``D-002`` - rationale
  for shipping a static metrics manifest (a peer artifact to this
  health-check module).
- ``acceleration/scripts/run_acceleration_analysis.py`` (built in a
  later checkpoint) - the orchestrator that consumes
  :func:`check_all` first.
"""

from __future__ import annotations

# When the module is launched directly (``python3
# acceleration/observability/health.py`` per the troubleshooting hint in
# ``acceleration/README.md`` Section 7), Python sets ``sys.path[0]`` to the
# directory containing this script. The ``acceleration`` package therefore
# is not importable. Prepend the repository root so the canonical import
# below resolves. The block is a no-op when the module is imported normally
# (``from acceleration.observability.health import check_all``) because
# ``__package__`` is non-empty in that case.
import sys as _sys
from pathlib import Path as _Path

if __package__ in (None, ""):
    _repo_root = _Path(__file__).resolve().parent.parent.parent
    if str(_repo_root) not in _sys.path:
        _sys.path.insert(0, str(_repo_root))

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from acceleration.observability.logger import get_logger

# ---------------------------------------------------------------------------
# Public exports
# ---------------------------------------------------------------------------

__all__ = [
    "check_all",
    "check_git",
    "check_repo",
    "check_output_dir",
    "check_github_token",
    "check_python",
]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Minimum git version per AAP Section 0.6.1. Older git releases lack the
# ``--reverse`` and ``--name-only`` semantics the extractor relies on.
MIN_GIT_VERSION: tuple[int, int] = (2, 40)

# Minimum Python version per AAP Section 0.6.1. Python 3.10 introduced the
# PEP 604 union type syntax (``str | None``) used throughout this module.
MIN_PYTHON_VERSION: tuple[int, int] = (3, 10)

# Default output directory probed by :func:`check_output_dir` when
# ``ACCEL_OUTPUT_DIR`` is not set in the environment. Matches the path
# enumerated in AAP Section 0.5.1.
DEFAULT_OUTPUT_DIR: str = "acceleration/data"

# Three allowed status values for every sub-check. Other strings are not
# permitted in the contract and would break the aggregation rule.
_STATUS_OK: str = "ok"
_STATUS_WARN: str = "warn"
_STATUS_FAIL: str = "fail"

# Pattern used to parse the version line produced by ``git --version``.
# ``git --version`` prints either ``git version 2.51.0`` (Linux/macOS) or
# ``git version 2.51.0.windows.1`` (Git for Windows); both are captured by
# this regex.
_GIT_VERSION_PATTERN: re.Pattern[str] = re.compile(
    r"git version (\d+)\.(\d+)(?:\.(\d+))?",
)

# Subprocess timeout in seconds. ``git --version`` and
# ``git rev-parse --is-inside-work-tree`` are sub-second operations on a
# healthy system; a 5-second timeout protects the orchestrator from a
# wedged invocation on a misconfigured host.
_SUBPROCESS_TIMEOUT: float = 5.0

# Logger for this module. Configured lazily by ``logger.get_logger``; the
# call here is safe because :mod:`acceleration.observability.logger` is
# side-effect-free at import time.
_LOG = get_logger(__name__)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _make_result(status: str, details: str) -> dict[str, Any]:
    """Construct a single sub-check result dict.

    Parameters
    ----------
    status : str
        One of ``"ok"``, ``"warn"``, ``"fail"``. The aggregation rule in
        :func:`check_all` depends on these exact spellings.
    details : str
        Human-readable diagnostic. Never carries secrets (the
        ``GITHUB_TOKEN`` check, for example, reports only whether the
        variable is set, not its value).

    Returns
    -------
    dict[str, Any]
        ``{"status": status, "details": details}``.

    Notes
    -----
    The helper is private (underscore-prefixed) to keep the public surface
    aligned with the documented contract.
    """

    return {"status": status, "details": details}


# ---------------------------------------------------------------------------
# Sub-checks
# ---------------------------------------------------------------------------


def check_git() -> dict[str, Any]:
    """Verify ``git`` is on ``PATH`` and at version ``2.40`` or newer.

    Returns
    -------
    dict[str, Any]
        ``{"status": "ok", "details": "git X.Y.Z"}`` when the version
        satisfies :data:`MIN_GIT_VERSION`; ``{"status": "fail", ...}``
        when git is missing, unreadable, or below the minimum version.

    Examples
    --------
    >>> result = check_git()
    >>> set(result) == {"status", "details"}
    True
    """

    # ``shutil.which`` is the canonical stdlib way to test PATH visibility;
    # it returns ``None`` when the executable is not found.
    git_path = shutil.which("git")
    if git_path is None:
        return _make_result(
            _STATUS_FAIL,
            "git not found on PATH; install git 2.40 or later",
        )

    try:
        proc = subprocess.run(
            [git_path, "--version"],
            capture_output=True,
            text=True,
            timeout=_SUBPROCESS_TIMEOUT,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return _make_result(
            _STATUS_FAIL,
            f"git --version timed out after {_SUBPROCESS_TIMEOUT:.0f}s",
        )
    except OSError as exc:
        # PATH says git exists but the binary failed to launch (corrupt
        # install, insufficient permissions). Capture the OS error so the
        # operator can diagnose without re-running.
        return _make_result(
            _STATUS_FAIL,
            f"failed to invoke git: {exc}",
        )

    if proc.returncode != 0:
        return _make_result(
            _STATUS_FAIL,
            f"git --version exited with code {proc.returncode}: "
            f"{(proc.stderr or proc.stdout).strip()}",
        )

    match = _GIT_VERSION_PATTERN.search(proc.stdout or "")
    if match is None:
        return _make_result(
            _STATUS_FAIL,
            f"could not parse git version from output: {proc.stdout.strip()!r}",
        )

    major = int(match.group(1))
    minor = int(match.group(2))
    patch = int(match.group(3)) if match.group(3) is not None else 0

    if (major, minor) < MIN_GIT_VERSION:
        return _make_result(
            _STATUS_FAIL,
            f"git {major}.{minor}.{patch} is older than the required "
            f"{MIN_GIT_VERSION[0]}.{MIN_GIT_VERSION[1]}",
        )

    return _make_result(
        _STATUS_OK,
        f"git {major}.{minor}.{patch}",
    )


def check_repo(cwd: str | None = None) -> dict[str, Any]:
    """Verify the working directory is inside a git work tree.

    Parameters
    ----------
    cwd : str, optional
        The directory whose membership in a git work tree is being
        tested. Defaults to the process's current working directory.

    Returns
    -------
    dict[str, Any]
        ``{"status": "ok", "details": "Inside work tree at /path/to/repo"}``
        when the directory is inside a checkout; ``{"status": "fail", ...}``
        otherwise.

    Notes
    -----
    Uses ``git rev-parse --is-inside-work-tree``, which prints ``true``
    when invoked inside any subdirectory of a git checkout. ``--show-toplevel``
    is also captured so that the operator can confirm which clone the
    pipeline will analyze.
    """

    git_path = shutil.which("git")
    if git_path is None:
        return _make_result(
            _STATUS_FAIL,
            "git not found on PATH; install git 2.40 or later",
        )

    try:
        inside = subprocess.run(
            [git_path, "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=_SUBPROCESS_TIMEOUT,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return _make_result(
            _STATUS_FAIL,
            f"git rev-parse --is-inside-work-tree timed out after "
            f"{_SUBPROCESS_TIMEOUT:.0f}s",
        )
    except OSError as exc:
        return _make_result(
            _STATUS_FAIL,
            f"failed to invoke git rev-parse: {exc}",
        )

    if inside.returncode != 0 or (inside.stdout or "").strip() != "true":
        # ``git rev-parse`` exits non-zero with a ``fatal: not a git
        # repository`` message on stderr when invoked outside a checkout.
        # Surface either signal so the operator sees a useful diagnostic.
        diagnostic = (inside.stderr or inside.stdout or "").strip()
        return _make_result(
            _STATUS_FAIL,
            f"not inside a git work tree"
            + (f": {diagnostic}" if diagnostic else ""),
        )

    # Locate the repository root for the success diagnostic.
    try:
        toplevel = subprocess.run(
            [git_path, "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=_SUBPROCESS_TIMEOUT,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        # If the second invocation fails for any reason, we still report
        # ``ok`` because the primary check passed; the root path is
        # informational.
        return _make_result(_STATUS_OK, "Inside work tree")

    root = (toplevel.stdout or "").strip()
    if toplevel.returncode == 0 and root:
        return _make_result(_STATUS_OK, f"Inside work tree at {root}")
    return _make_result(_STATUS_OK, "Inside work tree")


def check_output_dir(path: str | None = None) -> dict[str, Any]:
    """Verify the analysis output directory exists and is writable.

    Parameters
    ----------
    path : str, optional
        Directory path to probe. When ``None``, the function reads
        ``ACCEL_OUTPUT_DIR`` from the environment and falls back to
        :data:`DEFAULT_OUTPUT_DIR` ("acceleration/data").

    Returns
    -------
    dict[str, Any]
        ``{"status": "ok", "details": "<path> is writable"}`` when the
        directory exists and accepts a write probe;
        ``{"status": "warn", ...}`` when the directory does not exist
        but its parent is writable (the orchestrator will create it);
        ``{"status": "fail", ...}`` when neither the directory nor its
        parent accepts a write probe.

    Notes
    -----
    The write probe creates and immediately removes a temporary file via
    :func:`tempfile.NamedTemporaryFile`. The probe never leaves residue
    even if the function raises midway through.
    """

    if path is None:
        path = os.environ.get("ACCEL_OUTPUT_DIR", DEFAULT_OUTPUT_DIR)

    target = Path(path)

    if target.exists():
        if not target.is_dir():
            return _make_result(
                _STATUS_FAIL,
                f"{target} exists but is not a directory",
            )
        try:
            # ``tempfile.NamedTemporaryFile`` with ``delete=True`` would
            # remove the file when the handle closes; in this branch we
            # delete explicitly so that we keep the test idempotent even
            # on platforms where ``delete=True`` is unreliable.
            probe = tempfile.NamedTemporaryFile(
                prefix=".accel-health-",
                suffix=".tmp",
                dir=str(target),
                delete=False,
            )
            probe.close()
            os.unlink(probe.name)
        except OSError as exc:
            return _make_result(
                _STATUS_FAIL,
                f"{target} is not writable: {exc}",
            )
        return _make_result(_STATUS_OK, f"{target} is writable")

    # Target does not exist; check whether the parent accepts the
    # ``mkdir``-equivalent the orchestrator would perform on start.
    parent = target.parent if str(target.parent) else Path(".")
    if not parent.exists():
        return _make_result(
            _STATUS_FAIL,
            f"{target} does not exist and parent {parent} is missing",
        )
    if not parent.is_dir():
        return _make_result(
            _STATUS_FAIL,
            f"{target} does not exist and parent {parent} is not a directory",
        )

    try:
        probe = tempfile.NamedTemporaryFile(
            prefix=".accel-health-",
            suffix=".tmp",
            dir=str(parent),
            delete=False,
        )
        probe.close()
        os.unlink(probe.name)
    except OSError as exc:
        return _make_result(
            _STATUS_FAIL,
            f"{target} does not exist and parent {parent} is not writable: {exc}",
        )

    return _make_result(
        _STATUS_WARN,
        f"{target} does not exist; will be created (parent {parent} is writable)",
    )


def check_github_token() -> dict[str, Any]:
    """Report whether ``GITHUB_TOKEN`` is set in the environment.

    Returns
    -------
    dict[str, Any]
        ``{"status": "ok", "details": "GITHUB_TOKEN set"}`` when the
        variable is set to a non-empty string;
        ``{"status": "warn", "details": "GITHUB_TOKEN not set"}``
        otherwise. The function never returns ``"fail"`` because the
        pipeline can still run with degraded confidence per AAP
        Section 0.7.2.1 (Boundaries) and AAP Section 0.8.3
        (Confidence Rubric).

    Notes
    -----
    The token's value is never echoed in ``details``. The check tests
    only for non-empty presence; it does NOT validate that the token has
    the right scopes (``repo``, ``read:org``, ``read:audit_log``) because
    that requires a network call that this preflight stage avoids.
    """

    token = os.environ.get("GITHUB_TOKEN", "")
    if token:
        return _make_result(
            _STATUS_OK,
            "GITHUB_TOKEN set",
        )

    return _make_result(
        _STATUS_WARN,
        "GITHUB_TOKEN not set; metrics 8, 9, 10, 11, 12 will degrade per "
        "AAP \u00a70.7.2.1 (Boundaries) and \u00a70.8.3 (Confidence Rubric)",
    )


def check_python() -> dict[str, Any]:
    """Verify the running interpreter is Python ``3.10`` or newer.

    Returns
    -------
    dict[str, Any]
        ``{"status": "ok", "details": "Python X.Y.Z"}`` when the
        interpreter satisfies :data:`MIN_PYTHON_VERSION`;
        ``{"status": "fail", ...}`` otherwise.

    Notes
    -----
    The check reads :data:`sys.version_info` and does not depend on
    ``python --version`` (which would re-launch the interpreter and
    return its own version, not necessarily this one).
    """

    info = sys.version_info
    if (info.major, info.minor) < MIN_PYTHON_VERSION:
        return _make_result(
            _STATUS_FAIL,
            f"Python {info.major}.{info.minor}.{info.micro} is older than "
            f"the required {MIN_PYTHON_VERSION[0]}.{MIN_PYTHON_VERSION[1]}",
        )

    return _make_result(
        _STATUS_OK,
        f"Python {info.major}.{info.minor}.{info.micro}",
    )


# ---------------------------------------------------------------------------
# Aggregator
# ---------------------------------------------------------------------------


def check_all(
    cwd: str | None = None,
    output_dir: str | None = None,
) -> dict[str, Any]:
    """Run every sub-check and aggregate the results.

    Parameters
    ----------
    cwd : str, optional
        Directory passed through to :func:`check_repo`. Defaults to the
        process's current working directory.
    output_dir : str, optional
        Directory passed through to :func:`check_output_dir`. Defaults
        to ``ACCEL_OUTPUT_DIR`` (or :data:`DEFAULT_OUTPUT_DIR` when the
        environment variable is unset).

    Returns
    -------
    dict[str, Any]
        A dict with exactly six keys: ``git``, ``repo``, ``output_dir``,
        ``github_token``, ``python``, and ``overall``. The first five
        are sub-check results in the shape returned by
        :func:`_make_result`. The ``overall`` key carries one of the
        same three string values (``"ok"``, ``"warn"``, ``"fail"``)
        following the aggregation rule documented in this module's
        module-level docstring.

    Examples
    --------
    >>> result = check_all()
    >>> set(result) == {
    ...     "git", "repo", "output_dir", "github_token", "python", "overall"
    ... }
    True
    >>> result["overall"] in {"ok", "warn", "fail"}
    True

    Notes
    -----
    The function is intentionally synchronous and has no parameters
    beyond the two optional path overrides. The orchestrator calls it
    once at start-up; sub-second total runtime keeps the preflight
    invisible to the operator.
    """

    _LOG.info(
        "health.check_all starting",
        extra={"cwd": cwd, "output_dir": output_dir},
    )

    results: dict[str, Any] = {
        "git": check_git(),
        "repo": check_repo(cwd=cwd),
        "output_dir": check_output_dir(path=output_dir),
        "github_token": check_github_token(),
        "python": check_python(),
    }

    statuses = {entry["status"] for entry in results.values()}
    if _STATUS_FAIL in statuses:
        overall = _STATUS_FAIL
    elif _STATUS_WARN in statuses:
        overall = _STATUS_WARN
    else:
        overall = _STATUS_OK

    results["overall"] = overall

    # Emit a single summary log line so the orchestrator can see the
    # aggregate verdict without having to re-read every sub-check.
    _LOG.info(
        "health.check_all complete",
        extra={
            "overall": overall,
            "git": results["git"]["status"],
            "repo": results["repo"]["status"],
            "output_dir": results["output_dir"]["status"],
            "github_token": results["github_token"]["status"],
            "python": results["python"]["status"],
        },
    )

    return results


# ---------------------------------------------------------------------------
# Smoke test entrypoint
# ---------------------------------------------------------------------------


def _smoke_test(argv: list[str] | None = None) -> int:
    """Run :func:`check_all` and print the result as JSON to stdout.

    This is the body of the ``__main__`` block, extracted into a
    function so that automated tests can drive it without invoking the
    interpreter via a subprocess. The output shape matches the
    copy-pasteable smoke test documented in
    ``acceleration/observability/README.md`` Section 8.2.

    Parameters
    ----------
    argv : list[str], optional
        Command-line arguments excluding the program name. ``None``
        (the default) instructs :mod:`argparse` to read
        :data:`sys.argv`.

    Returns
    -------
    int
        ``0`` when ``overall`` is ``"ok"`` or ``"warn"``; ``1`` when
        ``overall`` is ``"fail"``. The non-zero exit is the signal the
        orchestrator (and CI smoke tests) use to short-circuit before
        invoking any extractor.
    """

    parser = argparse.ArgumentParser(
        description=(
            "Health-check smoke test - runs every sub-check and prints the "
            "aggregate result as JSON to stdout."
        ),
    )
    parser.add_argument(
        "--cwd",
        default=None,
        help=(
            "Directory passed to check_repo "
            "(default: current working directory)."
        ),
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help=(
            "Directory passed to check_output_dir "
            "(default: ACCEL_OUTPUT_DIR or 'acceleration/data')."
        ),
    )
    args = parser.parse_args(argv)

    result = check_all(cwd=args.cwd, output_dir=args.output_dir)

    # ``indent=2`` matches the copy-pasteable smoke test in
    # README.md \u00a78.2. ``sort_keys=False`` preserves the documented key
    # ordering (git, repo, output_dir, github_token, python, overall).
    print(json.dumps(result, indent=2, sort_keys=False))

    return 0 if result["overall"] != _STATUS_FAIL else 1


if __name__ == "__main__":
    raise SystemExit(_smoke_test())
