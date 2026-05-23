"""
acceleration.observability.health
=================================

Health and readiness checks for the Development Acceleration Analysis pipeline.

Mandated by AAP Rule 1 (Observability). Invoked first by the orchestrator
(``acceleration/scripts/run_acceleration_analysis.py``) BEFORE any extractor,
classifier, or renderer runs.

Returns a structured status object with keys:

- ``git``         - git executable presence and version (``>= 2.40`` enforced).
- ``python``      - Python interpreter version (``>= 3.10`` enforced).
- ``repo``        - repository accessibility (``.git`` directory present and
  ``HEAD`` resolvable via ``git rev-parse``).
- ``output_dir``  - ``acceleration/data/`` writability (existence-or-create
  plus a real temp-file probe).
- ``github_token``- ``GITHUB_TOKEN`` / ``GH_TOKEN`` env var presence and
  scope query against the GitHub ``/user`` endpoint.
- ``overall``     - ``"ok" | "warn" | "fail"`` computed from sub-checks.

Each sub-check returns a dict with the following shape::

    {
        "status": "ok" | "warn" | "fail",
        "details": "<one-sentence human-readable string>",
        # Optional, present per check type:
        "version":      "<semver string>",  # for git, python
        "path":         "<absolute path>",  # for repo, output_dir
        "scopes":       ["repo", ...],      # for github_token
        "required_min": "2.40.0",           # for version-gated checks
        "head_sha":     "<40-hex string>",  # for repo
        "user":         "<github login>",   # for github_token
    }

Status semantics
----------------

- ``ok``   The prerequisite is fully available.
- ``warn`` The prerequisite is degraded but the pipeline can proceed with
  documented limitations (for example, ``GITHUB_TOKEN`` missing means some
  metrics will degrade to "Insufficient signal" per AAP §0.7.2.1).
- ``fail`` The prerequisite is missing in a way the pipeline cannot work
  around (for example, ``git`` is not on ``PATH``).

Module guarantees
-----------------

1. **Stdlib-only at module level.** No third-party packages are imported.
   The single first-party import (:func:`get_logger`) is performed lazily
   inside :func:`check_all` so that callers wanting only an individual
   sub-check do not incur logger configuration.
2. **Side-effect-free at import time.** Importing this module defines
   classes/functions and compiles a regular expression. It does NOT call
   ``git --version``, ``urlopen``, ``os.makedirs``, ``logging.getLogger``,
   or anything else that could fail or mutate state.
3. **No exceptions escape the public surface.** Every public function
   captures expected exceptions and converts them into ``{"status": "fail",
   "details": "<message>"}`` results. Callers can rely on the return value
   being a well-formed dict in every code path.

See also
--------

- ``acceleration/observability/logger.py`` - structured JSON logger this
  module integrates with through the lazily-imported :func:`get_logger`.
- ``acceleration/observability/README.md`` §3.2 - reused-vs-added disclosure
  and runtime expectations for these checks.
- ``acceleration/scripts/run_acceleration_analysis.py`` - the orchestrator
  that consumes :func:`check_all` and writes the result into
  ``acceleration/data/run_manifest.json``.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from typing import Any

# ---------------------------------------------------------------------------
# Public exports
# ---------------------------------------------------------------------------

__all__ = [
    "check_all",
    "check_git",
    "check_python",
    "check_repo",
    "check_output_dir",
    "check_github_token",
]


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

# Minimum git version. The AAP §0.6.1 dependency inventory pins git to
# ``>= 2.40`` because the analysis uses ``--trailers``, ``--name-only``, and
# the ``--follow`` flag combinations which became stable across all platforms
# at that version.
_GIT_MIN: tuple[int, int, int] = (2, 40, 0)

# Minimum Python version. AAP §0.6.1: "python3 >= 3.10". The pipeline relies
# on PEP 604 (``X | Y``) union syntax and structural pattern-matching idioms
# introduced in 3.10.
_PYTHON_MIN: tuple[int, int] = (3, 10)

# Pre-compiled at import time (cheap, no I/O) so that every subsequent
# ``_parse_version`` call avoids re-compilation cost. Matches the first
# ``X.Y[.Z]`` token in an arbitrary string; the patch component is optional
# (defaults to 0 if absent).
_VERSION_RE: re.Pattern[str] = re.compile(r"(\d+)\.(\d+)(?:\.(\d+))?")

# Default analysis output directory. Configurable per call via the
# ``output_dir`` parameter of :func:`check_output_dir` / :func:`check_all`.
_DEFAULT_OUTPUT_DIR: str = "acceleration/data"

# GitHub probe configuration. The probe is the ONLY network call this module
# makes; every other check is local and runs in microseconds.
_GITHUB_USER_URL: str = "https://api.github.com/user"
_GITHUB_API_VERSION: str = "2022-11-28"
_GITHUB_PROBE_TIMEOUT_SECONDS: float = 15.0
_GIT_SUBPROCESS_TIMEOUT_SECONDS: float = 10.0

# User-Agent string for the GitHub probe. GitHub recommends a descriptive
# User-Agent header on every request and may rate-limit anonymous or
# generic-named agents more aggressively.
_USER_AGENT: str = "acceleration-analysis/1.0 (+health.py probe)"


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _parse_version(s: str) -> tuple[int, int, int] | None:
    """Extract ``(major, minor, patch)`` from the first ``X.Y[.Z]`` token in ``s``.

    Parameters
    ----------
    s : str
        Arbitrary string that may contain a version token, for example
        ``"git version 2.42.1"`` or ``"Python 3.10.4"``.

    Returns
    -------
    tuple[int, int, int] | None
        A tuple ``(major, minor, patch)``. ``patch`` defaults to ``0`` when
        the source string lacks a patch component (for example
        ``"git version 2.40"``). Returns ``None`` if no numeric version-like
        token is found in ``s``.
    """

    m = _VERSION_RE.search(s)
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2)), int(m.group(3) or 0))


def _version_str(v: tuple[int, int, int]) -> str:
    """Render a parsed version tuple as a canonical ``X.Y.Z`` string.

    Parameters
    ----------
    v : tuple[int, int, int]
        A version triple as returned by :func:`_parse_version`.

    Returns
    -------
    str
        Dot-separated decimal representation, for example ``"2.42.1"``.
    """

    return ".".join(str(x) for x in v)


# ---------------------------------------------------------------------------
# Sub-check: git availability and version
# ---------------------------------------------------------------------------


def check_git() -> dict[str, Any]:
    """Verify ``git`` is on ``PATH`` and has version ``>= 2.40``.

    The check is a two-step probe:

    1. :func:`shutil.which` locates the ``git`` binary. Absence is a
       ``fail`` because every extractor relies on direct ``git`` invocations.
    2. ``git --version`` runs with a ``10``-second timeout. The first
       ``X.Y[.Z]`` token in the output is parsed and compared against
       :data:`_GIT_MIN`. A version below the minimum is ``warn`` (not
       ``fail``) so that the pipeline can still attempt to run and surface
       a more specific failure if a flag is genuinely unsupported.

    Returns
    -------
    dict[str, Any]
        A dict with at least ``status`` and ``details`` keys plus
        ``required_min`` and (on success) ``version`` and ``path``.
    """

    git_exe = shutil.which("git")
    if not git_exe:
        return {
            "status": "fail",
            "details": "git not found on PATH",
            "required_min": _version_str(_GIT_MIN),
        }

    try:
        result = subprocess.run(
            [git_exe, "--version"],
            capture_output=True,
            text=True,
            timeout=_GIT_SUBPROCESS_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {
            "status": "fail",
            "details": (
                f"git --version timed out after "
                f"{_GIT_SUBPROCESS_TIMEOUT_SECONDS:g} s"
            ),
            "required_min": _version_str(_GIT_MIN),
            "path": git_exe,
        }
    except OSError as exc:
        return {
            "status": "fail",
            "details": f"git --version failed to launch: {exc}",
            "required_min": _version_str(_GIT_MIN),
            "path": git_exe,
        }

    if result.returncode != 0:
        return {
            "status": "fail",
            "details": (
                f"git --version exited with code {result.returncode}: "
                f"{(result.stderr or '').strip() or '<empty stderr>'}"
            ),
            "required_min": _version_str(_GIT_MIN),
            "path": git_exe,
        }

    output = (result.stdout or "").strip()
    parsed = _parse_version(output)
    if parsed is None:
        return {
            "status": "warn",
            "details": (
                f"could not parse git version from: {output!r}; "
                "proceeding with caution"
            ),
            "required_min": _version_str(_GIT_MIN),
            "path": git_exe,
        }

    if parsed < _GIT_MIN:
        return {
            "status": "warn",
            "details": (
                f"{output} is below minimum "
                f"{_version_str(_GIT_MIN)}; some features may not work"
            ),
            "version": _version_str(parsed),
            "required_min": _version_str(_GIT_MIN),
            "path": git_exe,
        }

    return {
        "status": "ok",
        "details": output,
        "version": _version_str(parsed),
        "required_min": _version_str(_GIT_MIN),
        "path": git_exe,
    }


# ---------------------------------------------------------------------------
# Sub-check: Python interpreter version
# ---------------------------------------------------------------------------


def check_python() -> dict[str, Any]:
    """Verify the running Python interpreter is ``>= 3.10``.

    Read directly from :data:`sys.version_info`; no subprocess call needed.
    AAP §0.6.1 pins Python ``>= 3.10`` because the analysis pipeline uses
    PEP 604 union syntax (``X | Y``) in type hints and other idioms that
    pre-3.10 interpreters reject at parse time.

    Returns
    -------
    dict[str, Any]
        A dict with ``status``, ``details``, ``version``, and
        ``required_min`` keys. ``status`` is ``"fail"`` if the interpreter
        is below the minimum; otherwise ``"ok"``.
    """

    major = sys.version_info.major
    minor = sys.version_info.minor
    micro = sys.version_info.micro
    version_str = f"{major}.{minor}.{micro}"
    required_min = f"{_PYTHON_MIN[0]}.{_PYTHON_MIN[1]}"

    if (major, minor) < _PYTHON_MIN:
        return {
            "status": "fail",
            "details": (
                f"Python {version_str} is below minimum {required_min}; "
                "the analysis pipeline requires modern type-hint syntax"
            ),
            "version": version_str,
            "required_min": required_min,
        }

    # ``sys.version`` returns the multi-line build banner; take the first
    # token (e.g. ``"3.13.7"``) for the human-readable details string.
    short = sys.version.split()[0] if sys.version else version_str
    return {
        "status": "ok",
        "details": f"Python {short}",
        "version": version_str,
        "required_min": required_min,
    }


# ---------------------------------------------------------------------------
# Sub-check: repository accessibility
# ---------------------------------------------------------------------------


def check_repo(repo_root: str | None = None) -> dict[str, Any]:
    """Verify that a git repository is accessible at ``repo_root``.

    The check tolerates ``repo_root`` being a sub-directory of the actual
    repository root: it walks up the directory tree looking for a ``.git``
    directory or file (the latter being the ``gitdir:`` redirect file used
    by ``git worktree``). When found, the walk endpoint is the repository
    root used for the subsequent ``git rev-parse HEAD`` probe; this avoids
    the common failure mode where the caller invokes the script from a
    nested directory and ``git -C <cwd> rev-parse`` fails.

    Parameters
    ----------
    repo_root : str, optional
        Path to a directory inside the repository, or the repository root
        itself. ``None`` (the default) resolves to :func:`os.getcwd`.

    Returns
    -------
    dict[str, Any]
        ``status`` is ``"fail"`` if no ``.git`` is found in ``repo_root`` or
        its ancestors, or if ``git rev-parse HEAD`` fails; otherwise
        ``"ok"`` with the resolved ``path`` and the abbreviated ``head_sha``.
    """

    requested = os.path.abspath(repo_root) if repo_root else os.getcwd()
    root = requested

    # Walk up to find a ``.git`` directory OR file (the file form is the
    # ``gitdir:`` redirect used by ``git worktree``).
    cursor = root
    found_root: str | None = None
    while True:
        candidate = os.path.join(cursor, ".git")
        if os.path.isdir(candidate) or os.path.isfile(candidate):
            found_root = cursor
            break
        parent = os.path.dirname(cursor)
        if parent == cursor:
            # Reached the filesystem root with no .git.
            break
        cursor = parent

    if found_root is None:
        return {
            "status": "fail",
            "details": (
                f"no .git directory found at {requested} or any ancestor"
            ),
            "path": requested,
        }

    # Resolve HEAD with a bounded timeout. ``git -C`` ensures the command
    # runs against the discovered repository root regardless of the caller's
    # current directory.
    try:
        result = subprocess.run(
            ["git", "-C", found_root, "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=_GIT_SUBPROCESS_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {
            "status": "fail",
            "details": (
                f"git rev-parse HEAD timed out after "
                f"{_GIT_SUBPROCESS_TIMEOUT_SECONDS:g} s"
            ),
            "path": found_root,
        }
    except FileNotFoundError:
        # ``git`` binary missing. ``check_git`` would have caught this in
        # the aggregator path; return the same diagnostic here for callers
        # that invoke ``check_repo`` standalone.
        return {
            "status": "fail",
            "details": "git executable not found on PATH",
            "path": found_root,
        }
    except OSError as exc:
        return {
            "status": "fail",
            "details": f"git rev-parse HEAD failed to launch: {exc}",
            "path": found_root,
        }

    if result.returncode != 0:
        stderr = (result.stderr or "").strip() or "<empty stderr>"
        return {
            "status": "fail",
            "details": f"git rev-parse HEAD failed: {stderr}",
            "path": found_root,
        }

    head_sha = (result.stdout or "").strip()
    if not head_sha:
        # Highly unusual: rev-parse succeeded but emitted nothing. Treat as
        # a fail so the orchestrator surfaces it.
        return {
            "status": "fail",
            "details": "git rev-parse HEAD returned empty output",
            "path": found_root,
        }

    return {
        "status": "ok",
        "details": f"repo at {found_root}, HEAD={head_sha[:12]}",
        "path": found_root,
        "head_sha": head_sha,
    }


# ---------------------------------------------------------------------------
# Sub-check: output directory writability
# ---------------------------------------------------------------------------


def check_output_dir(output_dir: str = _DEFAULT_OUTPUT_DIR) -> dict[str, Any]:
    """Verify the analysis output directory exists (or can be created) and is writable.

    The check creates ``output_dir`` if it does not yet exist (matching the
    AAP §0.4.1 ``acceleration/data/`` runtime convention) and then probes
    writability by creating and immediately deleting a ``NamedTemporaryFile``
    inside it. A successful probe guarantees that the extractors and the
    metric computer can later write their JSONL outputs without surprise.

    Parameters
    ----------
    output_dir : str, optional
        Path to the analysis output directory. Defaults to
        ``"acceleration/data"`` (resolved relative to the caller's working
        directory and then absolutised).

    Returns
    -------
    dict[str, Any]
        ``status`` is ``"fail"`` if the directory cannot be created or
        cannot be written. ``status`` is ``"ok"`` otherwise. The ``path``
        field always contains the absolute resolved path.
    """

    abs_dir = os.path.abspath(output_dir)

    # ``exist_ok=True`` makes ``makedirs`` idempotent on a pre-existing
    # directory while still surfacing genuine I/O failures (permissions,
    # read-only filesystem).
    try:
        os.makedirs(abs_dir, exist_ok=True)
    except OSError as exc:
        return {
            "status": "fail",
            "details": f"could not create {abs_dir}: {exc}",
            "path": abs_dir,
        }

    # ``os.access`` returns True if the kernel reports the path as writable
    # given the effective UID. The result is a necessary but not sufficient
    # condition (it does not account for filesystem-level read-only mounts
    # or container overlay quirks), so we also probe with a real temp file
    # below.
    if not os.access(abs_dir, os.W_OK):
        return {
            "status": "fail",
            "details": f"{abs_dir} is not writable (access check)",
            "path": abs_dir,
        }

    # Probe with an actual temp file. ``NamedTemporaryFile(delete=True)``
    # removes the file on close in CPython; we also explicitly flush before
    # close so that the filesystem definitively sees the write.
    try:
        with tempfile.NamedTemporaryFile(
            dir=abs_dir,
            prefix=".health_probe_",
            suffix=".tmp",
            delete=True,
        ) as f:
            f.write(b"healthcheck")
            f.flush()
    except OSError as exc:
        return {
            "status": "fail",
            "details": f"could not write a probe file in {abs_dir}: {exc}",
            "path": abs_dir,
        }

    return {
        "status": "ok",
        "details": f"{abs_dir} is writable",
        "path": abs_dir,
    }


# ---------------------------------------------------------------------------
# Sub-check: GitHub token presence and scope query
# ---------------------------------------------------------------------------


def check_github_token(skip_network: bool = False) -> dict[str, Any]:
    """Verify ``GITHUB_TOKEN`` is set and (when ``skip_network=False``) probe its scopes.

    The probe issues a single ``GET https://api.github.com/user`` request
    with the token in the ``Authorization`` header. GitHub returns the
    authenticated user's login in the JSON body and the granted token
    scopes in the ``X-OAuth-Scopes`` response header. Both pieces are
    captured into the result.

    A missing token is ``warn`` (not ``fail``) because the AAP §0.7.2.1
    boundary rules explicitly permit Metrics 1, 8, 9, 10, 11, and 12 to
    degrade to ``Insufficient signal`` rather than fabricate. Network
    errors are likewise ``warn``: the pipeline can still extract every
    git-only metric (2, 3, 4, 5, 6, 7) without GitHub.

    Parameters
    ----------
    skip_network : bool, optional
        If ``True``, skip the GitHub API call entirely. Useful for offline
        environments and for the orchestrator's ``--no-github`` flag. The
        function still records the env-var status; the network probe is
        the only step it skips.

    Returns
    -------
    dict[str, Any]
        Always includes ``status``, ``details``, and ``scopes`` (the
        ``scopes`` list is empty when the probe was skipped or failed to
        return scope information). When the probe succeeds, also includes
        ``user`` (the GitHub login).
    """

    # Accept either env-var spelling. ``GITHUB_TOKEN`` is the GitHub
    # Actions convention; ``GH_TOKEN`` is the ``gh`` CLI convention. Both
    # are interchangeable for this purpose.
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        return {
            "status": "warn",
            "details": (
                "GITHUB_TOKEN not set; metrics 1, 8, 9, 10, 11, 12 may "
                "degrade to Low confidence or Insufficient signal"
            ),
            "scopes": [],
        }

    if skip_network:
        return {
            "status": "warn",
            "details": (
                "GITHUB_TOKEN present but network probe skipped "
                "(skip_network=True)"
            ),
            "scopes": [],
        }

    # Build the request. ``urllib.request.Request`` does not follow
    # redirects unless a ``HTTPRedirectHandler`` is installed; the GitHub
    # ``/user`` endpoint does not redirect, so the default handler chain
    # is fine.
    req = urllib.request.Request(  # noqa: S310 - target URL is constant
        _GITHUB_USER_URL,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": _GITHUB_API_VERSION,
            "User-Agent": _USER_AGENT,
        },
        method="GET",
    )

    try:
        with urllib.request.urlopen(  # noqa: S310 - constant https URL
            req, timeout=_GITHUB_PROBE_TIMEOUT_SECONDS
        ) as resp:
            scopes_header = resp.getheader("X-OAuth-Scopes", "") or ""
            scopes = [s.strip() for s in scopes_header.split(",") if s.strip()]
            raw_body = resp.read()
    except urllib.error.HTTPError as exc:
        # ``HTTPError`` is a subclass of ``URLError`` and must be caught
        # first. ``401`` = bad credentials; ``403`` = rate-limited or
        # forbidden; ``404`` = unexpected (the ``/user`` route exists);
        # treat all non-success codes as ``warn``.
        detail_suffix = ""
        if exc.code == 401:
            detail_suffix = " (likely expired or revoked token)"
        elif exc.code == 403:
            detail_suffix = " (rate-limited or insufficient permissions)"
        return {
            "status": "warn",
            "details": (
                f"GitHub /user returned HTTP {exc.code}: "
                f"{exc.reason}{detail_suffix}"
            ),
            "scopes": [],
        }
    except urllib.error.URLError as exc:
        # Network-layer failure (DNS, refused connection, TLS, timeout
        # before HTTP). Treat as ``warn``: GitHub-only metrics will
        # degrade but git-only metrics still work.
        return {
            "status": "warn",
            "details": f"GitHub API unreachable: {exc.reason}",
            "scopes": [],
        }
    except TimeoutError as exc:
        # Python 3.10+ raises ``TimeoutError`` (a subclass of ``OSError``)
        # when ``timeout`` elapses before any data is read.
        return {
            "status": "warn",
            "details": f"GitHub API timed out after "
                       f"{_GITHUB_PROBE_TIMEOUT_SECONDS:g} s: {exc}",
            "scopes": [],
        }
    except OSError as exc:
        # Catch-all for other socket-level errors not already covered.
        return {
            "status": "warn",
            "details": f"network error contacting GitHub: {exc}",
            "scopes": [],
        }

    # Parse the JSON body. The ``/user`` response always contains a
    # ``login`` field for an authenticated request; defensively default to
    # ``<unknown>`` if the body is somehow malformed.
    try:
        body = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return {
            "status": "warn",
            "details": (
                f"token accepted but /user response was not valid JSON: "
                f"{exc}"
            ),
            "scopes": scopes,
        }

    login = body.get("login", "<unknown>") if isinstance(body, dict) else "<unknown>"
    return {
        "status": "ok",
        "details": f"token valid for user {login}",
        "scopes": scopes,
        "user": login,
    }


# ---------------------------------------------------------------------------
# Aggregator
# ---------------------------------------------------------------------------


def _compute_overall(results: dict[str, dict[str, Any]]) -> str:
    """Reduce sub-check statuses into a single ``overall`` status.

    Precedence order: ``fail`` > ``warn`` > ``ok``. Any sub-check with an
    unrecognised status value is treated as ``warn`` (so the pipeline
    surfaces the anomaly without hard-failing).

    Parameters
    ----------
    results : dict[str, dict[str, Any]]
        Mapping from sub-check name to its result dict. Each value must
        contain a ``status`` field.

    Returns
    -------
    str
        One of ``"ok"``, ``"warn"``, ``"fail"``.
    """

    statuses = {r.get("status", "warn") for r in results.values()}
    if "fail" in statuses:
        return "fail"
    if "warn" in statuses:
        return "warn"
    if statuses == {"ok"}:
        return "ok"
    # Unknown statuses fall through to ``warn`` so the orchestrator can
    # decide. This branch is hard to hit in practice but defensive.
    return "warn"


def _log_subcheck(log: logging.Logger, name: str, result: dict[str, Any]) -> None:
    """Emit a structured log line for a single sub-check result.

    The log level is chosen by ``result["status"]``:

    - ``ok``   -> :data:`logging.INFO`
    - ``warn`` -> :data:`logging.WARNING`
    - ``fail`` -> :data:`logging.ERROR`
    - anything else -> :data:`logging.WARNING`

    The full result dict is attached to the record under
    ``extra={"data": result}`` so that the JSON-line output contains the
    machine-readable status alongside the human-readable summary.

    Parameters
    ----------
    log : logging.Logger
        Logger obtained from :func:`get_logger`.
    name : str
        Sub-check name (for example ``"git"`` or ``"output_dir"``).
    result : dict[str, Any]
        The sub-check result dict.
    """

    status = result.get("status", "warn")
    details = result.get("details", "<no details>")
    message = f"health: {name} -> {status}: {details}"
    level_map = {
        "ok": logging.INFO,
        "warn": logging.WARNING,
        "fail": logging.ERROR,
    }
    level = level_map.get(status, logging.WARNING)
    log.log(level, message, extra={"data": {"check": name, "result": result}})


def check_all(
    repo_root: str | None = None,
    output_dir: str = _DEFAULT_OUTPUT_DIR,
    skip_network: bool = False,
) -> dict[str, Any]:
    """Run every health check and return a single structured status object.

    The ``"overall"`` key is set as follows:

    - ``"ok"``   if every sub-check is ``"ok"``.
    - ``"warn"`` if at least one is ``"warn"`` and none are ``"fail"``.
    - ``"fail"`` if at least one is ``"fail"``.

    The function also emits one JSON log line per sub-check (and a final
    summary line) through :func:`acceleration.observability.logger.get_logger`.
    The logger import is **deferred** to the body of this function so that
    callers wanting only an individual sub-check primitive (for example a
    third-party test runner) do not incur logger configuration.

    Parameters
    ----------
    repo_root : str, optional
        Path to the repository root. Defaults to the current working
        directory; ancestor traversal is applied to locate ``.git``.
    output_dir : str, optional
        Path to the analysis output directory. Defaults to
        ``"acceleration/data"``.
    skip_network : bool, optional
        If ``True``, skip the GitHub token network probe. The token's
        env-var presence is still recorded.

    Returns
    -------
    dict[str, Any]
        A dict with the keys ``git``, ``python``, ``repo``, ``output_dir``,
        ``github_token``, and ``overall``. Each sub-check value is itself a
        dict carrying ``status``, ``details``, and any check-specific
        fields. The ``overall`` value is the reduced status string.

    Examples
    --------
    >>> result = check_all(skip_network=True)  # doctest: +SKIP
    >>> result["overall"]                       # doctest: +SKIP
    'warn'
    >>> result["git"]["status"]                 # doctest: +SKIP
    'ok'
    """

    # Deferred import: see Phase 9 / Phase 14 of the agent prompt. Importing
    # here ensures that consumers calling only ``check_git()`` (for example)
    # do not pay for logger configuration.
    from acceleration.observability.logger import get_logger

    log = get_logger(__name__)
    log.info(
        "Running pipeline health checks",
        extra={"data": {"skip_network": skip_network, "output_dir": output_dir}},
    )

    # Order matters for human readability: foundational prerequisites first
    # (git, python), then environment context (repo, output_dir), then the
    # optional external dependency (github_token).
    results: dict[str, dict[str, Any]] = {}

    results["git"] = check_git()
    _log_subcheck(log, "git", results["git"])

    results["python"] = check_python()
    _log_subcheck(log, "python", results["python"])

    results["repo"] = check_repo(repo_root)
    _log_subcheck(log, "repo", results["repo"])

    results["output_dir"] = check_output_dir(output_dir)
    _log_subcheck(log, "output_dir", results["output_dir"])

    results["github_token"] = check_github_token(skip_network=skip_network)
    _log_subcheck(log, "github_token", results["github_token"])

    overall = _compute_overall(results)

    # The summary is intentionally compact: full per-check detail is
    # available in the dict that the caller receives, while the log line
    # carries only a one-status-per-check map suitable for grep-ability.
    summary = {k: v.get("status", "warn") for k, v in results.items()}
    log.info(
        "Health check complete",
        extra={"data": {"overall": overall, "summary": summary}},
    )

    # Place ``overall`` LAST so that JSON output ordered by insertion (the
    # CPython 3.7+ guarantee) reads top-to-bottom: per-check details, then
    # the reduced status.
    results["overall"] = overall  # type: ignore[assignment]
    return results


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    """Construct the ``argparse.ArgumentParser`` for the ``__main__`` block.

    Extracted into a function so that tests can drive parsing without
    invoking the interpreter via subprocess.

    Returns
    -------
    argparse.ArgumentParser
        A parser with four flags: ``--repo-root``, ``--output-dir``,
        ``--skip-network``, and ``--exit-on-fail``.
    """

    parser = argparse.ArgumentParser(
        prog="python -m acceleration.observability.health",
        description=(
            "Run pipeline health checks and print the result as JSON. "
            "Exits 0 on overall=ok by default; pass --exit-on-fail to exit "
            "1 on overall=warn and 2 on overall=fail."
        ),
    )
    parser.add_argument(
        "--repo-root",
        default=None,
        help=(
            "Path to the repository root. Defaults to the current working "
            "directory; ancestor traversal locates .git."
        ),
    )
    parser.add_argument(
        "--output-dir",
        default=_DEFAULT_OUTPUT_DIR,
        help=(
            "Path to the analysis output directory (default: "
            f"{_DEFAULT_OUTPUT_DIR!r}). The directory is created if "
            "missing and probed for writability."
        ),
    )
    parser.add_argument(
        "--skip-network",
        action="store_true",
        help=(
            "Skip the GitHub /user network probe (useful for offline "
            "environments)."
        ),
    )
    parser.add_argument(
        "--exit-on-fail",
        action="store_true",
        help=(
            "Exit with a non-zero status when overall is not 'ok' "
            "(1 for warn, 2 for fail)."
        ),
    )
    return parser


def _main(argv: list[str] | None = None) -> int:
    """CLI body, separated from the ``__main__`` guard for testability.

    Parameters
    ----------
    argv : list[str] | None, optional
        Arguments excluding the program name. ``None`` (the default)
        passes ``sys.argv[1:]`` implicitly through :mod:`argparse`.

    Returns
    -------
    int
        The intended process exit code: ``0`` (everything ok or
        ``--exit-on-fail`` not set), ``1`` (``--exit-on-fail`` set and
        overall=warn), or ``2`` (``--exit-on-fail`` set and overall=fail).
    """

    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    results = check_all(
        repo_root=args.repo_root,
        output_dir=args.output_dir,
        skip_network=args.skip_network,
    )
    # ``sort_keys=True`` produces a deterministic byte-for-byte output that
    # tests and the orchestrator's run_manifest can compare reliably.
    print(json.dumps(results, indent=2, sort_keys=True))
    if args.exit_on_fail and results.get("overall") != "ok":
        return 2 if results.get("overall") == "fail" else 1
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised via subprocess in tests
    # Support both invocation forms documented in
    # ``acceleration/observability/README.md`` §8.2 and
    # ``acceleration/README.md`` troubleshooting:
    #
    #   python3 -m acceleration.observability.health     (module form)
    #   python3 acceleration/observability/health.py     (script form)
    #
    # The module form already has ``acceleration`` on ``sys.path``. The
    # script form does not, which would make the deferred
    # ``from acceleration.observability.logger import get_logger`` import
    # fail with ``ModuleNotFoundError``. Insert the repository root (two
    # directories up from this file) so both invocations work identically.
    _here = os.path.dirname(os.path.abspath(__file__))
    _repo_root = os.path.dirname(os.path.dirname(_here))
    if _repo_root not in sys.path:
        sys.path.insert(0, _repo_root)
    raise SystemExit(_main())
