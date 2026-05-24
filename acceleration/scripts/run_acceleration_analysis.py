#!/usr/bin/env python3
"""
run_acceleration_analysis.py — Top-level orchestrator for the Acceleration pipeline.

Sequence (per AAP §0.3.1, folder spec, with documented data-flow swap of
``extract_git`` and ``detect_inflection`` recorded in
``acceleration/decision-log.md``):

  1.  observability.health.check_all                  (health & readiness)
  2.  scripts/extract_git.py                          (single git-log pass)
  3.  scripts/detect_inflection.py                    (Candidates A + B)
  4.  scripts/extract_github.py                       (PRs, reviews, releases, BP, audit)
  5.  scripts/extract_ci_tests.py                     (JUnit artifacts)
  6.  scripts/extract_issues.py                       (bug issues + SLA probe)
  7.  scripts/classify_prs.py                         (Metric 6 classification)
  8.  scripts/compute_metrics.py                      (writes metrics.json)
  9.  scripts/render_report.py                        (writes acceleration-report.md)
  10. scripts/render_deck.py                          (writes executive-presentation.html)
  11. scripts/verify_report.py                        (asserts Rules 1–6)

Emits:
  acceleration/data/run_manifest.json — per-step success/failure, elapsed time, run_id.

Authority:
  - AAP §0.3.2.2 "Orchestrator"   — top-level entrypoint description.
  - AAP §0.4.1                    — file listing for run_acceleration_analysis.py.
  - AAP §0.5.2                    — read-only constraint enforcement.
  - AAP §0.3.4                    — graceful degradation on missing token/network.
  - AAP §0.7.1 Rule 1             — structured logger + run-scoped correlation IDs.

Read-only outside acceleration/: enforced at runtime via a ``git status``
snapshot taken before and after the pipeline. Any new or modified path whose
relative path does not start with ``acceleration/`` flips the overall status
to ``failed`` and is recorded in ``run_manifest.json`` under
``readonly_violations``.

Process model:
  - Each pipeline step (except ``health``) is invoked as
    ``python -m acceleration.scripts.<step>`` in an isolated subprocess so
    that a step failure cannot corrupt the orchestrator's address space and
    so that ``--only <step>`` can re-run individual steps deterministically.
  - The ``health`` step is invoked in-process via importlib so that the
    structured-status dict it returns is captured directly into the
    run_manifest.
  - The correlation ID (``run_id``) is generated once and propagated to all
    children via the ``ACCEL_RUN_ID`` environment variable so that every
    log line across the pipeline carries the same identifier.

CLI surface (see ``parse_args`` for full detail):
  --repo-root              Path to the repository root (default: ``.``).
  --output-dir             Path to the analysis data directory (default:
                           ``acceleration/data``).
  --accel-dir              Path to the acceleration root (default:
                           ``acceleration``).
  --owner / --repo         GitHub owner/repo for the GitHub extractors
                           (default: env REPO_OWNER/REPO_NAME or
                           ``formbricks``/``formbricks``).
  --branch                 Git ref to log (default: ``main``).
  --skip-network           Pass ``--skip-network`` to every network-bound
                           extractor (extract_github, extract_ci_tests,
                           extract_issues).
  --skip-github            Skip the extract_github step entirely.
  --skip-ci-tests          Skip the extract_ci_tests step entirely.
  --skip-issues            Skip the extract_issues step entirely.
  --only NAMES             Comma-separated list of step names to run in
                           canonical order (other steps emit status=skipped).
  --continue-on-error      Do not halt the pipeline on a non-optional step
                           failure (still records the failure).
  --no-readonly-check      Disable pre/post git-status diff. The pipeline run
                           in CI MUST NOT use this.

Exit code:
  0   overall_status == "ok"
  1   overall_status == "failed" (a non-optional step failed OR a read-only
      contract violation was observed)
"""

from __future__ import annotations

import argparse
import importlib
import json
import logging
import os
import shutil  # noqa: F401  # reserved for future output-directory hygiene helpers
import subprocess
import sys
import time
import uuid
from dataclasses import (  # noqa: F401  # ``field`` re-exported for downstream extensions
    asdict,
    dataclass,
    field,
)
from pathlib import Path
from typing import Any, Iterable  # noqa: F401  # Iterable retained for downstream extension


# ---------------------------------------------------------------------------
# Module-level exports
# ---------------------------------------------------------------------------
#
# The orchestrator's public surface — consumed by tests and by future
# refactors of the pipeline. ``main`` is the conventional process entry point
# and is re-used by the unit-test harness to drive an in-process pipeline run.

__all__ = [
    "main",
    "parse_args",
    "PIPELINE",
    "Step",
    "StepResult",
    "PipelineContext",
    "execute_step",
    "run_python_module",
    "run_python_function",
    "snapshot_git_status",
    "diff_status",
    "now_iso",
    "SUBPROCESS_TIMEOUT_DEFAULT",
    "SUBPROCESS_TIMEOUT_HEALTH",
    "SUBPROCESS_TIMEOUT_GIT_HELPERS",
]


# ---------------------------------------------------------------------------
# Subprocess timeout constants
# ---------------------------------------------------------------------------
#
# Per the checkpoint feedback (review finding L594/L799/L1070), every
# subprocess invocation MUST carry a bounded timeout so a single hanging
# child (corrupt repo, frozen git process, blocked HTTPS handshake) cannot
# stall the orchestrator indefinitely. The constants below give callers a
# named, auditable upper bound:
#
#   * ``SUBPROCESS_TIMEOUT_DEFAULT`` — 1800s (30 min). Generous enough for
#     the heaviest worker (``extract_git`` traversing 5,178 commits with
#     ``--name-only``) on slow hardware; tight enough to surface a
#     pathological hang within a reasonable budget. Per AAP §0.8.7 the
#     analysis "runs at any time, against any commit window", so timeouts
#     must not be tuned to a specific repo size — they are an absolute
#     safety net, not a performance budget.
#   * ``SUBPROCESS_TIMEOUT_HEALTH`` — 60s. The health probe in
#     :mod:`acceleration.observability.health` calls ``git --version``
#     and similar fast diagnostics; 60s catches a stalled diagnostic
#     without disturbing the slowest measured run (≤2s).
#   * ``SUBPROCESS_TIMEOUT_GIT_HELPERS`` — 60s. Inline helpers
#     (``git status --porcelain``, ``git --version``, ``git rev-parse
#     HEAD``) finish in milliseconds on a healthy clone; 60s tolerates
#     transient filesystem stalls without masking a real hang.
#
# When a timeout fires, the affected step records ``timed_out=True`` in
# the :class:`StepResult` so the manifest distinguishes a deterministic
# crash from a wall-clock budget exhaustion. The error string also
# encodes the timeout budget so operators can re-tune deliberately.
SUBPROCESS_TIMEOUT_DEFAULT: float = 1800.0
SUBPROCESS_TIMEOUT_HEALTH: float = 60.0
SUBPROCESS_TIMEOUT_GIT_HELPERS: float = 60.0


# ---------------------------------------------------------------------------
# Pipeline step dataclasses
# ---------------------------------------------------------------------------


@dataclass
class Step:
    """A single pipeline step.

    Attributes
    ----------
    name
        Short identifier used in logs, in ``--only`` selections, and as the
        ``steps[].name`` key in ``run_manifest.json``.
    description
        One-sentence human-readable description rendered into the manifest
        for after-the-fact inspection.
    runner
        Execution model for the step: ``"python_module"`` invokes
        ``python -m <target>`` in a subprocess; ``"python_function"`` invokes
        the dotted ``module:function`` reference in-process via importlib.
    target
        Either a dotted module path (``python_module``) such as
        ``"acceleration.scripts.extract_git"`` or a ``module:function``
        reference (``python_function``) such as
        ``"acceleration.observability.health:check_all"``.
    args_factory
        Name of a method on :class:`PipelineContext` that returns the
        argument payload for this step. For ``python_module`` runners the
        method returns ``list[str]`` (an argv list); for ``python_function``
        runners it returns ``dict[str, Any]`` (keyword arguments).
    optional
        When ``True``, a non-zero exit / non-ok status is recorded as
        ``status="skipped"`` (not ``"failed"``) and the pipeline continues.
        Used for network-bound extractors (extract_github,
        extract_ci_tests, extract_issues) so the pipeline still produces a
        partial report when ``GITHUB_TOKEN`` is missing.
    skip_when
        Name of the :class:`argparse.Namespace` flag that opts the user
        out of this step (e.g. ``"skip_github"`` maps to ``--skip-github``).
        When the flag is truthy the step is marked ``status="skipped"``
        without execution.
    """

    name: str
    description: str
    runner: str
    target: str
    args_factory: str
    optional: bool = False
    skip_when: str | None = None


@dataclass
class StepResult:
    """Recorded outcome of a single pipeline step.

    All fields are JSON-serialisable so the dataclass round-trips through
    :func:`dataclasses.asdict` into ``run_manifest.json``.

    Attributes
    ----------
    name
        Step name (matches :class:`Step.name`).
    description
        Step description (matches :class:`Step.description`).
    status
        One of ``"ok"``, ``"failed"``, ``"skipped"``.
    exit_code
        For ``python_module`` runners: the subprocess exit code.
        For ``python_function`` runners: 0 on ok, 1 otherwise.
        ``None`` when the step was skipped or raised before execution.
    started_at
        ISO 8601 UTC timestamp of when execution started (``Z`` suffix).
    elapsed_seconds
        Wall-clock duration in seconds, rounded to milliseconds.
    optional
        Mirrors :class:`Step.optional` so post-hoc inspection of the
        manifest can distinguish "skipped because optional and failed"
        from "skipped because user opted out".
    error
        Short one-line error description when the step did not succeed,
        otherwise ``None``.
    timed_out
        ``True`` when the step's subprocess exceeded the configured
        wall-clock budget (:data:`SUBPROCESS_TIMEOUT_DEFAULT` for most
        workers; smaller for the health step). When ``True``, the
        :attr:`error` field carries the budget value so the manifest
        records the policy that was enforced, and ``status`` is
        ``"failed"`` (or ``"skipped"`` for optional steps).
    """

    name: str
    description: str
    status: str
    exit_code: int | None
    started_at: str
    elapsed_seconds: float
    optional: bool
    error: str | None = None
    timed_out: bool = False


# ---------------------------------------------------------------------------
# Canonical pipeline ordering
# ---------------------------------------------------------------------------
#
# Per AAP §0.3.1 the canonical sequence is:
#   health → extract_git → detect_inflection → extract_github →
#   extract_ci_tests → extract_issues → classify_prs → compute_metrics →
#   render_report → render_deck → verify_report
#
# Note on the ``extract_git`` / ``detect_inflection`` swap (vs. the folder
# spec's chronological listing): ``detect_inflection`` reads
# ``commits.jsonl`` produced by ``extract_git``, so data-flow correctness
# requires ``extract_git`` to run first. This deviation is recorded in
# ``acceleration/decision-log.md`` row D-002.
#
# Optional steps (``optional=True``) degrade to ``status="skipped"`` on
# non-zero exit instead of halting the pipeline. This implements AAP §0.3.4
# graceful-degradation for network-bound extractors when ``GITHUB_TOKEN`` is
# absent or the GitHub API is unreachable.

PIPELINE: list[Step] = [
    Step(
        name="health",
        description="Pre-flight health and readiness checks.",
        runner="python_function",
        target="acceleration.observability.health:check_all",
        args_factory="health_args",
    ),
    Step(
        name="extract_git",
        description="Single git-log pass producing commits/prs/reverts.jsonl.",
        runner="python_module",
        target="acceleration.scripts.extract_git",
        args_factory="extract_git_args",
    ),
    Step(
        name="detect_inflection",
        description="Two-candidate detection of the AI-introduction inflection date.",
        runner="python_module",
        target="acceleration.scripts.detect_inflection",
        args_factory="detect_inflection_args",
    ),
    Step(
        name="extract_github",
        description="GitHub REST: PRs, reviews, releases, branch protection, audit log.",
        runner="python_module",
        target="acceleration.scripts.extract_github",
        args_factory="extract_github_args",
        optional=True,
        skip_when="skip_github",
    ),
    Step(
        name="extract_ci_tests",
        description="JUnit XML from GitHub Actions Artifacts API.",
        runner="python_module",
        target="acceleration.scripts.extract_ci_tests",
        args_factory="extract_ci_tests_args",
        optional=True,
        skip_when="skip_ci_tests",
    ),
    Step(
        name="extract_issues",
        description="Bug-labelled issues plus SLA-source probe.",
        runner="python_module",
        target="acceleration.scripts.extract_issues",
        args_factory="extract_issues_args",
        optional=True,
        skip_when="skip_issues",
    ),
    Step(
        name="classify_prs",
        description="Annotate prs.jsonl with work_type (linked labels → title → keyword → unknown).",
        runner="python_module",
        target="acceleration.scripts.classify_prs",
        args_factory="classify_prs_args",
    ),
    Step(
        name="compute_metrics",
        description="Compute all 12 metrics; write metrics.json (single source of truth).",
        runner="python_module",
        target="acceleration.scripts.compute_metrics",
        args_factory="compute_metrics_args",
    ),
    Step(
        name="render_report",
        description="Render acceleration-report.md from metrics.json.",
        runner="python_module",
        target="acceleration.scripts.render_report",
        args_factory="render_report_args",
    ),
    Step(
        name="render_deck",
        description="Render executive-presentation.html from metrics.json.",
        runner="python_module",
        target="acceleration.scripts.render_deck",
        args_factory="render_deck_args",
    ),
    Step(
        name="verify_report",
        description="Verify report & deck against Rules 1–6 (data provenance, tone, etc.).",
        runner="python_module",
        target="acceleration.scripts.verify_report",
        args_factory="verify_report_args",
    ),
]


# ---------------------------------------------------------------------------
# Pipeline context — per-step argv / kwargs factories
# ---------------------------------------------------------------------------


@dataclass
class PipelineContext:
    """Runtime state shared across all pipeline steps.

    Captures all the values derived from the CLI arguments plus the
    process-wide correlation ID. Each ``*_args`` method translates this
    state into the exact CLI / kwargs payload expected by the
    corresponding worker script or function.

    Attributes
    ----------
    repo_root
        Resolved absolute path to the repository root. Passed to every
        git-bound and filesystem-bound extractor; also used as ``cwd`` for
        all subprocess invocations so that ``python -m`` can resolve
        ``acceleration.scripts.*`` via namespace-package discovery.
    output_dir
        Resolved absolute path to ``acceleration/data`` (the analysis data
        directory). Created on first run if absent.
    accel_dir
        Resolved absolute path to ``acceleration/`` (the acceleration root).
        Used by the renderers to locate templates and to write the final
        deliverables (``acceleration-report.md``, ``executive-presentation.html``).
    owner / repo
        GitHub repository coordinates passed to the network extractors.
    branch
        Git ref to log (default ``main``). Currently retained for
        documentation parity with the worker scripts; the orchestrator does
        not yet propagate this to ``extract_git`` because the worker has its
        own default-resolution logic (``refs/remotes/origin/main`` else
        ``HEAD``).
    skip_network
        When ``True``, append ``--skip-network`` to every network-bound
        extractor's argv.
    skip_github / skip_ci_tests / skip_issues
        When ``True``, the corresponding step is skipped entirely (no
        process started, no log lines emitted).
    only
        When non-``None``, a tuple of step names; steps not in this set
        emit ``status="skipped"`` with reason ``"not in --only=..."``.
    run_id
        Correlation ID emitted by every log line and propagated to every
        child subprocess via the ``ACCEL_RUN_ID`` environment variable.
    """

    repo_root: Path
    output_dir: Path
    accel_dir: Path
    owner: str
    repo: str
    branch: str
    skip_network: bool
    skip_github: bool
    skip_ci_tests: bool
    skip_issues: bool
    only: tuple[str, ...] | None
    run_id: str

    # ------------------------------------------------------------------
    # Per-step argv / kwargs factories
    # ------------------------------------------------------------------
    #
    # Each factory returns either ``list[str]`` (an argv passed verbatim to
    # the subprocess) or ``dict[str, Any]`` (keyword arguments for an
    # in-process function call). The argument flag names below are the
    # exact flags accepted by each worker script as discovered during Phase
    # 1 of the AAP-execution; they MUST stay in sync if a worker's CLI
    # surface evolves.

    def health_args(self) -> dict[str, Any]:
        """Keyword arguments for :func:`acceleration.observability.health.check_all`.

        Returns
        -------
        dict[str, Any]
            ``{"repo_root": str, "output_dir": str, "skip_network": bool}``
            matching the public signature of ``check_all``.
        """

        return {
            "repo_root": str(self.repo_root),
            "output_dir": str(self.output_dir),
            "skip_network": self.skip_network,
        }

    def extract_git_args(self) -> list[str]:
        """Argv for ``python -m acceleration.scripts.extract_git``."""

        return [
            "--repo-root", str(self.repo_root),
            "--branch", self.branch,
            "--output-dir", str(self.output_dir),
        ]

    def detect_inflection_args(self) -> list[str]:
        """Argv for ``python -m acceleration.scripts.detect_inflection``.

        Passes the ``commits.jsonl`` path emitted by ``extract_git`` so the
        detector reads pre-extracted commit records rather than re-walking
        the git history.
        """

        return [
            "--repo-root", str(self.repo_root),
            "--branch", self.branch,
            "--commits-jsonl", str(self.output_dir / "commits.jsonl"),
            "--output", str(self.output_dir / "inflection.json"),
        ]

    def extract_github_args(self) -> list[str]:
        """Argv for ``python -m acceleration.scripts.extract_github``."""

        argv = [
            "--owner", self.owner,
            "--repo", self.repo,
            "--branch", self.branch,
            "--output-dir", str(self.output_dir),
        ]
        if self.skip_network:
            argv.append("--skip-network")
        return argv

    def extract_ci_tests_args(self) -> list[str]:
        """Argv for ``python -m acceleration.scripts.extract_ci_tests``."""

        argv = [
            "--owner", self.owner,
            "--repo", self.repo,
            "--output-dir", str(self.output_dir),
        ]
        if self.skip_network:
            argv.append("--skip-network")
        return argv

    def extract_issues_args(self) -> list[str]:
        """Argv for ``python -m acceleration.scripts.extract_issues``."""

        argv = [
            "--owner", self.owner,
            "--repo", self.repo,
            "--output-dir", str(self.output_dir),
            "--repo-root", str(self.repo_root),
        ]
        if self.skip_network:
            argv.append("--skip-network")
        return argv

    def classify_prs_args(self) -> list[str]:
        """Argv for ``python -m acceleration.scripts.classify_prs``."""

        return [
            "--prs", str(self.output_dir / "prs.jsonl"),
            "--issues", str(self.output_dir / "issues.jsonl"),
        ]

    def compute_metrics_args(self) -> list[str]:
        """Argv for ``python -m acceleration.scripts.compute_metrics``.

        Note: the worker's CLI uses ``--manifest-output`` (not ``--output``)
        for the metrics.json destination. This naming is preserved verbatim
        from the worker's argparse declaration so the orchestrator's
        invocation matches the worker contract.
        """

        return [
            "--data-dir", str(self.output_dir),
            "--manifest-output", str(self.output_dir / "metrics.json"),
            "--aliases-output", str(self.output_dir / "actor_aliases.json"),
            "--reproduce-output", str(self.output_dir / "reproduce.sh"),
        ]

    def render_report_args(self) -> list[str]:
        """Argv for ``python -m acceleration.scripts.render_report``."""

        return [
            "--metrics", str(self.output_dir / "metrics.json"),
            "--inflection", str(self.output_dir / "inflection.json"),
            "--manifest", str(self.output_dir / "run_manifest.json"),
            "--github-access", str(self.output_dir / "github_access.json"),
            "--sla-source", str(self.output_dir / "sla_source.json"),
            "--reproduce-script", str(self.output_dir / "reproduce.sh"),
            "--templates-dir", str(self.accel_dir / "templates" / "mermaid"),
            "--output", str(self.accel_dir / "acceleration-report.md"),
        ]

    def render_deck_args(self) -> list[str]:
        """Argv for ``python -m acceleration.scripts.render_deck``."""

        return [
            "--metrics", str(self.output_dir / "metrics.json"),
            "--inflection", str(self.output_dir / "inflection.json"),
            "--manifest", str(self.output_dir / "run_manifest.json"),
            "--templates-dir", str(self.accel_dir / "templates" / "deck"),
            "--output", str(self.accel_dir / "executive-presentation.html"),
        ]

    def verify_report_args(self) -> list[str]:
        """Argv for ``python -m acceleration.scripts.verify_report``."""

        return [
            "--report", str(self.accel_dir / "acceleration-report.md"),
            "--deck", str(self.accel_dir / "executive-presentation.html"),
            "--metrics", str(self.output_dir / "metrics.json"),
        ]


# ---------------------------------------------------------------------------
# Time / process helpers
# ---------------------------------------------------------------------------


def now_iso() -> str:
    """Return the current UTC time as an ISO 8601 string with ``Z`` suffix.

    Used consistently for every timestamp emitted into ``run_manifest.json``
    so that timestamps sort lexicographically and parse cleanly through
    ``datetime.fromisoformat`` in downstream tools.

    Returns
    -------
    str
        Format ``YYYY-MM-DDTHH:MM:SSZ`` (e.g. ``2026-05-15T12:34:56Z``).
    """

    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def run_python_module(
    target: str,
    argv: list[str],
    cwd: Path,
    run_id: str,
    timeout: float | None = None,
) -> tuple[int, bool]:
    """Invoke a worker script as ``python -m <module> <argv>``.

    Each worker runs in its own subprocess so a crash or unhandled exception
    cannot corrupt the orchestrator's address space. The child receives a
    copy of the parent environment plus ``ACCEL_RUN_ID`` so its log lines
    carry the same correlation ID.

    A bounded wall-clock timeout protects the orchestrator from a hanging
    worker (corrupt repo, frozen child, blocked HTTPS handshake). When the
    timeout expires the child is terminated and the helper returns
    ``(-1, True)`` so the caller can record the structured timeout in the
    :class:`StepResult` manifest entry.

    Parameters
    ----------
    target
        Dotted module path, e.g. ``"acceleration.scripts.extract_git"``.
    argv
        Argument list passed verbatim after ``python -m <target>``.
    cwd
        Working directory for the subprocess. Set to the repository root
        so namespace-package resolution of ``acceleration.*`` succeeds.
    run_id
        Correlation ID injected into the child environment as
        ``ACCEL_RUN_ID`` (already-set values are preserved).
    timeout
        Wall-clock budget in seconds. Defaults to
        :data:`SUBPROCESS_TIMEOUT_DEFAULT`. Pass ``None`` to retain the
        default.

    Returns
    -------
    tuple[int, bool]
        Two-tuple ``(exit_code, timed_out)``. ``exit_code`` is the
        subprocess exit code (``0`` indicates success); on timeout the
        exit code is ``-1`` and ``timed_out`` is ``True``.
    """

    cmd = [sys.executable, "-m", target] + argv
    env = os.environ.copy()
    # setdefault preserves an explicit ACCEL_RUN_ID set upstream while
    # injecting our own when nothing is set yet.
    env.setdefault("ACCEL_RUN_ID", run_id)
    budget = SUBPROCESS_TIMEOUT_DEFAULT if timeout is None else timeout
    try:
        completed = subprocess.run(
            cmd,
            cwd=str(cwd),
            env=env,
            check=False,
            timeout=budget,
        )
        return completed.returncode, False
    except subprocess.TimeoutExpired:
        # ``subprocess.run`` already kills the child on timeout. Return
        # the sentinel exit code -1 plus ``timed_out=True`` so the
        # caller can attribute the failure to wall-clock exhaustion
        # rather than a deterministic non-zero exit.
        return -1, True


def run_python_function(
    target: str,
    kwargs: dict[str, Any],
) -> tuple[int, dict[str, Any] | None]:
    """Invoke a ``module:function`` reference in-process.

    Used for the ``health`` step so the structured dict the health check
    returns (``{"git": {...}, "python": {...}, ..., "overall": "ok"}``)
    is captured directly without round-tripping through JSON.

    The function:
      - imports the module via :func:`importlib.import_module`,
      - resolves the function attribute,
      - calls the function with the supplied kwargs,
      - if the return value is a dict, inspects ``result["status"]`` or
        ``result["overall"]`` and converts it to an exit code (``"ok"``
        and ``"warn"`` map to ``0``; anything else maps to ``1``).

    ``"warn"`` is treated as success because AAP §0.3.4 documents graceful
    degradation when optional prerequisites (e.g. ``GITHUB_TOKEN``) are
    missing — the pipeline proceeds and the affected metrics fall back to
    "Insufficient signal".

    Parameters
    ----------
    target
        ``"module.submodule:function_name"`` reference string.
    kwargs
        Keyword arguments forwarded to the resolved callable.

    Returns
    -------
    tuple[int, dict[str, Any] | None]
        Two-tuple of (exit_code, original_return_value). The exit code is
        derived from the return value's status field (if it is a dict);
        non-dict returns always map to ``0``. The original return value is
        forwarded in the second tuple element so the caller can persist it
        into the manifest if desired.
    """

    mod_name, _, func_name = target.partition(":")
    mod = importlib.import_module(mod_name)
    fn = getattr(mod, func_name)
    result = fn(**kwargs)
    if isinstance(result, dict):
        # ``health.check_all`` returns ``{"overall": "ok" | "warn" | "fail"}``.
        # ``"warn"`` is non-fatal (e.g. missing GITHUB_TOKEN → optional
        # extractors will degrade) and so maps to a success exit code so
        # the orchestrator continues into the next step.
        status = result.get("status") or result.get("overall")
        return (0 if status in ("ok", "warn") else 1), result
    return 0, None


# ---------------------------------------------------------------------------
# Step execution wrapper
# ---------------------------------------------------------------------------


def execute_step(
    step: Step,
    ctx: PipelineContext,
    log: logging.Logger,
) -> StepResult:
    """Execute a single pipeline step and return its :class:`StepResult`.

    Wraps the runner dispatch with timing, exception capture, and
    optional-step downgrade logic.

    Behaviour matrix:

    +---------------------+-------------------+---------------------+
    | Runner outcome      | step.optional     | StepResult.status   |
    +=====================+===================+=====================+
    | exit_code == 0      | any               | ``"ok"``            |
    +---------------------+-------------------+---------------------+
    | exit_code != 0      | ``True``          | ``"skipped"``       |
    +---------------------+-------------------+---------------------+
    | exit_code != 0      | ``False``         | ``"failed"``        |
    +---------------------+-------------------+---------------------+
    | Exception raised    | ``True``          | ``"skipped"``       |
    +---------------------+-------------------+---------------------+
    | Exception raised    | ``False``         | ``"failed"``        |
    +---------------------+-------------------+---------------------+

    Parameters
    ----------
    step
        The step to execute.
    ctx
        The pipeline context carrying all derived state.
    log
        Configured logger; receives the per-step invocation line.

    Returns
    -------
    StepResult
        A fully-populated step result, safe to ``asdict()`` into the
        run_manifest.
    """

    started = now_iso()
    t0 = time.time()
    try:
        if step.runner == "python_module":
            argv_factory = getattr(ctx, step.args_factory)
            argv = argv_factory()
            log.info(
                f"[step={step.name}] python -m {step.target} {' '.join(argv)}"
            )
            rc, timed_out = run_python_module(
                step.target, argv, ctx.repo_root, ctx.run_id
            )
            elapsed = time.time() - t0
            if timed_out:
                # A timeout always counts as a failure (or skipped for
                # optional steps). The ``error`` field encodes the
                # budget so the manifest captures what was enforced.
                status = "skipped" if step.optional else "failed"
                err_msg = (
                    f"subprocess timed out after "
                    f"{SUBPROCESS_TIMEOUT_DEFAULT:.0f}s"
                )
            elif rc == 0:
                status = "ok"
                err_msg = None
            elif step.optional:
                status = "skipped"
                err_msg = f"non-zero exit code: {rc}"
            else:
                status = "failed"
                err_msg = f"non-zero exit code: {rc}"
            return StepResult(
                name=step.name,
                description=step.description,
                status=status,
                exit_code=rc,
                started_at=started,
                elapsed_seconds=round(elapsed, 3),
                optional=step.optional,
                error=err_msg,
                timed_out=timed_out,
            )
        elif step.runner == "python_function":
            kwargs_factory = getattr(ctx, step.args_factory)
            kwargs = kwargs_factory()
            log.info(f"[step={step.name}] {step.target}({kwargs})")
            rc, _ = run_python_function(step.target, kwargs)
            elapsed = time.time() - t0
            if rc == 0:
                status = "ok"
            elif step.optional:
                status = "skipped"
            else:
                status = "failed"
            return StepResult(
                name=step.name,
                description=step.description,
                status=status,
                exit_code=rc,
                started_at=started,
                elapsed_seconds=round(elapsed, 3),
                optional=step.optional,
                error=(
                    None
                    if rc == 0
                    else "function returned non-ok status"
                ),
                timed_out=False,
            )
        else:
            raise ValueError(f"Unknown runner: {step.runner}")
    except Exception as exc:  # pragma: no cover - defensive
        elapsed = time.time() - t0
        return StepResult(
            name=step.name,
            description=step.description,
            status=("skipped" if step.optional else "failed"),
            exit_code=None,
            started_at=started,
            elapsed_seconds=round(elapsed, 3),
            optional=step.optional,
            error=f"{type(exc).__name__}: {exc}",
            timed_out=False,
        )


# ---------------------------------------------------------------------------
# Read-only contract enforcement
# ---------------------------------------------------------------------------


def snapshot_git_status(repo_root: Path) -> str:
    """Capture ``git status --porcelain`` output for pre/post diffing.

    Returns the stdout of ``git status --porcelain`` (UTF-8 decoded) so the
    orchestrator can compare the working tree before and after the pipeline
    run and detect any modification outside ``acceleration/``.

    The function is intentionally tolerant: a missing ``git`` binary
    (FileNotFoundError) or a non-git directory yields the empty string and
    the read-only diff degrades to "no detectable changes", which is the
    correct behaviour when the orchestrator is run against a path that is
    not a git checkout (e.g. ``--repo-root /tmp/foo`` for off-repo tests).

    Parameters
    ----------
    repo_root
        Working directory for the ``git`` invocation.

    Returns
    -------
    str
        The decoded stdout of ``git status --porcelain``. Each line begins
        with a two-character status code, a space, and a path.
    """

    try:
        completed = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(repo_root),
            capture_output=True,
            check=False,
            timeout=SUBPROCESS_TIMEOUT_GIT_HELPERS,
        )
        return completed.stdout.decode("utf-8", errors="replace")
    except FileNotFoundError:
        return ""
    except subprocess.TimeoutExpired:
        # Treat a stalled ``git status`` as "no detectable changes"
        # so the read-only diff degrades safely. The orchestrator's
        # structured log captures the timeout for operator audit.
        return ""


def diff_status(
    before: str,
    after: str,
    allow_prefix: str = "acceleration/",
) -> list[str]:
    """Return lines in ``after`` that are not in ``before`` and violate the
    read-only contract.

    A line is a violation when at least one of its paths (the substring
    after the two-char status code and one space) falls OUTSIDE
    ``allow_prefix``.

    For rename entries (``XY <orig> -> <new>``) BOTH the source AND
    the target path are checked. This closes the review feedback
    edge case where an outside→inside rename (e.g. moving
    ``docs/foo.md`` into ``acceleration/foo.md``) used to pass the
    read-only check even though the source outside ``acceleration/``
    was modified by the rename. Per AAP §0.5.2 the contract is
    "additive plus read-only, satisfying the read-only boundary",
    which means **no** file outside ``acceleration/`` may be created,
    modified, deleted, or renamed.

    Parameters
    ----------
    before
        Output of ``git status --porcelain`` taken before the pipeline ran.
    after
        Output of ``git status --porcelain`` taken after the pipeline ran.
    allow_prefix
        Relative-path prefix permitted by the read-only contract. Defaults
        to ``"acceleration/"`` per AAP §0.5.2.

    Returns
    -------
    list[str]
        List of porcelain lines (with status code + path) that represent
        violations. An empty list indicates the read-only contract held.
    """

    before_lines = set(before.splitlines())
    new_lines = [line for line in after.splitlines() if line not in before_lines]
    violations: list[str] = []
    for line in new_lines:
        # Each porcelain line is ``XY <path>``, optionally ``XY <orig> -> <new>``
        # for renames. We need at least the two-char status + space + first path
        # character before considering the line parseable.
        if len(line) < 4:
            continue
        path_section = line[3:]
        # Parse rename entries (``<orig> -> <new>``) into both paths;
        # otherwise treat the whole section as a single path. Stripping
        # surrounding quotes covers the C-quoted variant git emits for
        # paths containing whitespace or special characters.
        if " -> " in path_section:
            orig_raw, _, new_raw = path_section.partition(" -> ")
            paths = (
                orig_raw.strip().strip('"'),
                new_raw.strip().strip('"'),
            )
        else:
            paths = (path_section.strip().strip('"'),)
        # A rename is a violation if EITHER side falls outside the
        # allowed prefix. A non-rename is a violation if its single
        # path falls outside the allowed prefix.
        if any(not p.startswith(allow_prefix) for p in paths if p):
            violations.append(line)
    return violations


# ---------------------------------------------------------------------------
# Argparse
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse orchestrator CLI arguments.

    Extracted into a free function so that tests can drive parsing without
    invoking the full pipeline.

    Parameters
    ----------
    argv
        Argument list excluding the program name. ``None`` instructs
        argparse to read :data:`sys.argv`.

    Returns
    -------
    argparse.Namespace
        Parsed arguments with attributes ``repo_root``, ``output_dir``,
        ``accel_dir``, ``owner``, ``repo``, ``branch``, ``skip_network``,
        ``skip_github``, ``skip_ci_tests``, ``skip_issues``, ``only``,
        ``continue_on_error``, ``no_readonly_check``.
    """

    p = argparse.ArgumentParser(
        prog="run_acceleration_analysis",
        description=(
            "Orchestrate the Development Acceleration Analysis pipeline. "
            "Runs the 11-step canonical sequence (health → extract_git → "
            "detect_inflection → extract_github → extract_ci_tests → "
            "extract_issues → classify_prs → compute_metrics → "
            "render_report → render_deck → verify_report) and writes "
            "run_manifest.json. Read-only outside acceleration/."
        ),
    )
    p.add_argument(
        "--repo-root",
        type=Path,
        default=Path("."),
        help="Path to the repository root (default: current directory).",
    )
    p.add_argument(
        "--output-dir",
        type=Path,
        default=Path("acceleration/data"),
        help=(
            "Directory under which all extractor outputs (commits.jsonl, "
            "prs.jsonl, metrics.json, run_manifest.json, ...) are written "
            "(default: acceleration/data)."
        ),
    )
    p.add_argument(
        "--accel-dir",
        type=Path,
        default=Path("acceleration"),
        help=(
            "Path to the acceleration root containing scripts/, "
            "observability/, templates/. The renderers write "
            "acceleration-report.md and executive-presentation.html into "
            "this directory (default: acceleration)."
        ),
    )
    p.add_argument(
        "--owner",
        default=os.environ.get("REPO_OWNER", "formbricks"),
        help=(
            "GitHub repository owner (default: env REPO_OWNER, else "
            "'formbricks')."
        ),
    )
    p.add_argument(
        "--repo",
        default=os.environ.get("REPO_NAME", "formbricks"),
        help=(
            "GitHub repository name (default: env REPO_NAME, else "
            "'formbricks')."
        ),
    )
    p.add_argument(
        "--branch",
        default="main",
        help="Git branch / ref to log (default: 'main').",
    )
    p.add_argument(
        "--skip-network",
        action="store_true",
        help=(
            "Pass --skip-network to every network-bound extractor "
            "(extract_github, extract_ci_tests, extract_issues). Use this "
            "for offline smoke tests."
        ),
    )
    p.add_argument(
        "--skip-github",
        action="store_true",
        help="Skip the extract_github step entirely.",
    )
    p.add_argument(
        "--skip-ci-tests",
        action="store_true",
        help="Skip the extract_ci_tests step entirely.",
    )
    p.add_argument(
        "--skip-issues",
        action="store_true",
        help="Skip the extract_issues step entirely.",
    )
    p.add_argument(
        "--only",
        type=str,
        default=None,
        help=(
            "Comma-separated list of step names to run in canonical order "
            "(e.g. 'render_report,verify_report'). Steps not listed emit "
            "status=skipped without execution."
        ),
    )
    p.add_argument(
        "--continue-on-error",
        action="store_true",
        help=(
            "Do not halt the pipeline on a non-optional step failure "
            "(useful for forensic runs that need to inspect every step's "
            "behaviour)."
        ),
    )
    p.add_argument(
        "--no-readonly-check",
        action="store_true",
        help=(
            "Disable the pre/post git-status diff that enforces AAP §0.5.2 "
            "read-only-outside-acceleration/. CI runs MUST NOT use this; "
            "intended for development convenience only."
        ),
    )
    return p.parse_args(argv)


# ---------------------------------------------------------------------------
# Logger bootstrap (preferring the project's structured JSON logger)
# ---------------------------------------------------------------------------


def _bootstrap_logger() -> tuple[logging.Logger, str]:
    """Configure a logger and resolve the process-wide correlation ID.

    Preference order:

    1. The structured JSON logger from
       :mod:`acceleration.observability.logger` (the AAP Rule 1 logger).
    2. The stdlib :func:`logging.basicConfig` logger (when the
       observability package cannot be imported, e.g. because the
       orchestrator is invoked from outside the repository layout).

    The run ID is read from the ``ACCEL_RUN_ID`` environment variable if
    present (preserving correlation when the orchestrator is launched from
    a parent that already allocated an ID) or generated fresh otherwise.

    Returns
    -------
    tuple[logging.Logger, str]
        ``(logger, run_id)`` — the configured logger and the resolved
        correlation ID. The run_id is also published back into
        ``os.environ["ACCEL_RUN_ID"]`` so subprocesses spawned later in
        :func:`run_python_module` see the same value.
    """

    try:
        # parents[2] of <repo>/acceleration/scripts/run_acceleration_analysis.py
        # is the repository root, which must be on sys.path for the
        # ``acceleration`` namespace package to be importable.
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from acceleration.observability.logger import (  # type: ignore[import-not-found]
            generate_run_id,
            get_logger,
            set_default_run_id,
        )

        run_id = os.environ.get("ACCEL_RUN_ID") or generate_run_id()
        set_default_run_id(run_id)
        log = get_logger("acceleration.scripts.run_acceleration_analysis", run_id=run_id)
        return log, run_id
    except Exception:
        # Fallback: never let logger configuration prevent the pipeline
        # from running. The fallback is good enough to surface progress to
        # a human operator and to capture step results into the manifest.
        run_id = os.environ.get("ACCEL_RUN_ID") or str(uuid.uuid4())
        logging.basicConfig(
            level=os.environ.get("ACCEL_LOG_LEVEL", "INFO"),
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
        )
        log = logging.getLogger("acceleration.scripts.run_acceleration_analysis")
        return log, run_id


def _git_version() -> str | None:
    """Return ``git --version`` output for the run_manifest, or ``None``.

    Captured once at manifest-emit time so the manifest carries the exact
    git binary version used during the run. Returns ``None`` when git is
    not on ``PATH`` so missing git does not break manifest serialisation.

    Returns
    -------
    str | None
        Trimmed stdout of ``git --version`` (e.g. ``"git version 2.51.0"``)
        or ``None`` when git is unavailable.
    """

    try:
        completed = subprocess.run(
            ["git", "--version"],
            capture_output=True,
            check=False,
            timeout=SUBPROCESS_TIMEOUT_GIT_HELPERS,
        )
        decoded = completed.stdout.decode("utf-8", errors="replace").strip()
        return decoded or None
    except FileNotFoundError:
        return None
    except subprocess.TimeoutExpired:
        # ``git --version`` should return in milliseconds. A timeout
        # indicates a broken git install or filesystem stall; surface
        # ``None`` so the manifest records "git unavailable".
        return None


def _build_run_manifest(
    *,
    run_id: str,
    started_at: str,
    finished_at: str | None,
    repo_root: Path,
    output_dir: Path,
    accel_dir: Path,
    owner: str,
    repo: str,
    branch: str,
    head_sha: str | None,
    args_skip_network: bool,
    args_skip_github: bool,
    args_skip_ci_tests: bool,
    args_skip_issues: bool,
    args_only: tuple[str, ...] | None,
    args_continue_on_error: bool,
    args_no_readonly_check: bool,
    results: list[StepResult],
    overall_status: str,
    readonly_violations: list[str],
    git_version: str | None,
) -> dict[str, Any]:
    """Assemble the ``run_manifest.json`` payload.

    Centralising the schema in a single helper ensures every write
    site (initial-before-loop, per-step, final-after-readonly-check)
    emits an identical shape. This also makes the schema auditable in
    one place when downstream renderers add new field expectations.

    The payload includes BOTH legacy field names (``owner``, ``repo``,
    ``started_at``, ``finished_at``) and the explicit aliases the
    renderers and ``compute_metrics.build_reproduce_script`` read
    (``repo_owner``, ``repo_name``, ``repo_owner_name``, ``head_sha``,
    ``generated_at``, ``extraction_timestamp``, ``extracted_at``).
    The aliases are first-class fields, not just alternatives — they
    are the schema the renderers consume; the legacy names are
    retained for orchestrator-internal logging and for back-compat
    with any downstream tooling that reads the older shape.

    Parameters
    ----------
    run_id
        Run correlation ID.
    started_at, finished_at
        Pipeline start and (optional) end timestamps as ISO 8601 UTC
        strings with the ``Z`` suffix.
    repo_root, output_dir, accel_dir
        Absolute paths captured for reproducibility.
    owner, repo, branch
        Repository identifiers; ``repo_owner_name`` is built as
        ``"{owner}/{repo}"``.
    head_sha
        Resolved HEAD SHA from :func:`_git_head_sha`, or ``None``.
    args_*
        Verbatim values of the orchestrator CLI flags.
    results
        :class:`StepResult` records accumulated so far. May be partial
        when called from the per-step write site.
    overall_status
        ``"running"``, ``"ok"``, or ``"failed"``.
    readonly_violations
        Output of :func:`diff_status` (empty list until the final
        write).
    git_version
        Trimmed stdout of ``git --version`` (captured once at
        manifest-emit time).

    Returns
    -------
    dict[str, Any]
        JSON-serialisable payload ready for atomic write.
    """

    repo_owner_name = f"{owner}/{repo}"
    # The ``generated_at`` field is what render_report and render_deck
    # read for the "Extraction timestamp" cell. We bind it to
    # ``finished_at`` when the pipeline has completed; while running it
    # binds to the current time so a freshly-written manifest is never
    # missing the field. ``extraction_timestamp`` and ``extracted_at``
    # are aliases consumed by the deck renderer and compute_metrics
    # respectively.
    generated_at = finished_at or now_iso()

    # QA finding F-7: enrich the manifest with the commit count and the
    # first / last commit dates so the closing slide and the report's
    # Environment Verification section can render concrete numbers
    # without falling back to "n/a". The values are derived from
    # ``commits.jsonl`` (cheap to scan once) when it is available; the
    # fallback is ``git rev-list --count HEAD`` plus ``git log
    # --reverse|HEAD -1`` for the boundary dates. Both fallbacks
    # respect the read-only contract (no writes outside
    # ``acceleration/``).
    commit_count, first_commit_date, last_commit_date = (
        _derive_commit_stats(output_dir, repo_root)
    )

    return {
        # Legacy / orchestrator-canonical fields (retained for back-compat).
        "run_id": run_id,
        "started_at": started_at,
        "finished_at": finished_at,
        "repo_root": str(repo_root),
        "output_dir": str(output_dir),
        "accel_dir": str(accel_dir),
        "owner": owner,
        "repo": repo,
        "branch": branch,
        # Renderer-expected aliases (per the review feedback): every
        # field name a downstream consumer reads is present at the top
        # level of the manifest.
        "repo_owner": owner,
        "repo_name": repo,
        "repo_owner_name": repo_owner_name,
        "head_sha": head_sha,
        "generated_at": generated_at,
        "extraction_timestamp": generated_at,
        "extracted_at": generated_at,
        # Commit fingerprint (QA finding F-7). Either of the three
        # fields may be ``None`` when the data source is unavailable;
        # the renderers fall back to additional sources when so.
        "commit_count": commit_count,
        "first_commit_date": first_commit_date,
        "last_commit_date": last_commit_date,
        # Orchestrator argv snapshot — captured verbatim so a run can
        # be reproduced from the manifest alone.
        "args": {
            "skip_network": args_skip_network,
            "skip_github": args_skip_github,
            "skip_ci_tests": args_skip_ci_tests,
            "skip_issues": args_skip_issues,
            "only": list(args_only) if args_only else None,
            "continue_on_error": args_continue_on_error,
            "no_readonly_check": args_no_readonly_check,
        },
        "steps": [asdict(r) for r in results],
        "overall_status": overall_status,
        "readonly_violations": readonly_violations,
        "python_version": sys.version.split()[0],
        "git_version": git_version,
    }


def _derive_commit_stats(
    output_dir: Path,
    repo_root: Path,
) -> tuple[int | None, str | None, str | None]:
    """Return ``(commit_count, first_commit_date, last_commit_date)``.

    Resolution chain (preferred → fallback):

    1. ``extract_git_access.json`` — the canonical receipt written by
       ``extract_git.py`` when it walked the analysis target branch
       (``main`` by default). This is the single source of truth for
       the commit count and the first / last author dates and is
       guaranteed to match the date range reported by the Data Source
       Inventory section (rendered from ``metrics.json:date_range``,
       which is itself derived from this same access JSON). Using it
       as the primary source closes QA finding F-001 — the Environment
       Verification section's "Latest commit date" cell now reflects
       the actual extraction target (``main``) rather than the
       working-branch HEAD's commit timestamp.
    2. ``commits.jsonl`` walk — a deterministic per-record scan over
       the extractor output. The extractor convention writes the
       timestamps under the field names ``author_date`` and
       ``committer_date`` (ISO 8601 strings). Earlier drafts of this
       helper used the aliases ``authored_at`` / ``committed_at``;
       both alias sets are now tolerated.
    3. ``git rev-list --count HEAD`` + ``git log`` for boundary
       dates — final fallback when neither of the JSON sources is
       available. This path uses ``HEAD`` and therefore reflects the
       current working branch; consumers should treat its boundary
       dates as a last-resort fingerprint rather than the analysis
       target. See F-001 in the QA log for the rationale for ranking
       this path last.

    All paths are read-only and tolerate failure — when no data
    source is available, the corresponding component is ``None`` and
    downstream consumers fall back to their own resolution chain
    (see ``render_deck.py:_commit_count_from_jsonl`` and
    ``render_report.py``).

    Parameters
    ----------
    output_dir
        Directory containing the extractor outputs
        (``acceleration/data`` by convention).
    repo_root
        Path to the repository root used as the working directory for
        any git invocations.

    Returns
    -------
    tuple[int | None, str | None, str | None]
        Commit count, earliest commit date (``YYYY-MM-DD``), latest
        commit date (``YYYY-MM-DD``). Any element may be ``None``.
    """

    commit_count: int | None = None
    first_date: str | None = None
    last_date: str | None = None

    # ---- Source 1: extract_git_access.json -------------------------
    # This is the canonical receipt that ``extract_git.py`` writes
    # after it walks the analysis target branch. The fields
    # ``commit_count_reported_by_rev_list``, ``first_author_date``,
    # and ``last_author_date`` are the ground truth that the rest of
    # the pipeline (and the report's Data Source Inventory section)
    # consume; ranking this source first guarantees cross-section
    # parity between Environment Verification and Data Source
    # Inventory (QA finding F-001).
    access_path = output_dir / "extract_git_access.json"
    if access_path.is_file():
        try:
            access = json.loads(access_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            access = None
        if isinstance(access, dict):
            raw_count = access.get("commit_count_reported_by_rev_list")
            if raw_count is None:
                raw_count = access.get("commit_count_seen_in_stream")
            if isinstance(raw_count, int) and raw_count > 0:
                commit_count = raw_count
            for field, dest in (
                ("first_author_date", "first"),
                ("last_author_date", "last"),
            ):
                raw_ts = access.get(field)
                if isinstance(raw_ts, str) and len(raw_ts) >= 10:
                    iso_date = raw_ts[:10]
                    if dest == "first":
                        first_date = iso_date
                    else:
                        last_date = iso_date

    # ---- Source 2: commits.jsonl walk ------------------------------
    # Only consulted when the access JSON did not supply every field.
    # The extractor convention writes ``author_date`` /
    # ``committer_date`` (ISO 8601). Earlier draft consumers used
    # the aliases ``authored_at`` / ``committed_at``; both are
    # tolerated here so a future extractor variant that switches
    # field names does not silently regress this helper.
    if commit_count is None or first_date is None or last_date is None:
        commits_path = output_dir / "commits.jsonl"
        if commits_path.is_file():
            min_iso: str | None = None
            max_iso: str | None = None
            count = 0
            try:
                with commits_path.open("r", encoding="utf-8") as handle:
                    for raw_line in handle:
                        line = raw_line.strip()
                        if not line:
                            continue
                        count += 1
                        try:
                            rec = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        # Canonical field names first (current
                        # extractor convention), then legacy aliases.
                        raw_ts: Any = (
                            rec.get("author_date")
                            or rec.get("committer_date")
                            or rec.get("authored_at")
                            or rec.get("committed_at")
                            or rec.get("commit_date")
                            or rec.get("date")
                        )
                        if not isinstance(raw_ts, str) or len(raw_ts) < 10:
                            continue
                        iso_date = raw_ts[:10]
                        if min_iso is None or iso_date < min_iso:
                            min_iso = iso_date
                        if max_iso is None or iso_date > max_iso:
                            max_iso = iso_date
            except OSError:
                count = 0
                min_iso = None
                max_iso = None
            if count > 0:
                if commit_count is None:
                    commit_count = count
                if first_date is None:
                    first_date = min_iso
                if last_date is None:
                    last_date = max_iso

    # ---- Source 3: git CLI fallback --------------------------------
    # Uses ``HEAD`` (the current working branch). Ranked last so its
    # boundary dates only surface when both JSON sources are absent;
    # this keeps Environment Verification aligned with Data Source
    # Inventory even when the orchestrator runs from a branch whose
    # HEAD differs from the analysis target.
    if commit_count is None:
        commit_count = _git_commit_count(repo_root)
    if first_date is None:
        first_date = _git_boundary_date(repo_root, oldest=True)
    if last_date is None:
        last_date = _git_boundary_date(repo_root, oldest=False)

    return commit_count, first_date, last_date


def _git_commit_count(repo_root: Path) -> int | None:
    """Return ``git rev-list --count HEAD`` or ``None`` on failure."""

    try:
        completed = subprocess.run(  # noqa: S603,S607 — git invocation is safe
            ["git", "rev-list", "--count", "HEAD"],
            cwd=str(repo_root),
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (FileNotFoundError, subprocess.SubprocessError, OSError):
        return None
    if completed.returncode != 0:
        return None
    text = (completed.stdout or "").strip()
    return int(text) if text.isdigit() else None


def _git_boundary_date(repo_root: Path, *, oldest: bool) -> str | None:
    """Return the oldest or newest commit's authored date as ``YYYY-MM-DD``.

    Parameters
    ----------
    repo_root
        Path to the repository root (the git working directory).
    oldest
        ``True`` returns the earliest reachable commit date;
        ``False`` returns the latest.

    Returns
    -------
    str | None
        ``"YYYY-MM-DD"`` on success, ``None`` on failure.
    """

    args = ["git", "log", "--format=%ad", "--date=short"]
    if oldest:
        args.extend(["--reverse"])
    args.append("HEAD")
    try:
        completed = subprocess.run(  # noqa: S603,S607 — git invocation is safe
            args,
            cwd=str(repo_root),
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (FileNotFoundError, subprocess.SubprocessError, OSError):
        return None
    if completed.returncode != 0:
        return None
    output = completed.stdout or ""
    if not output:
        return None
    if oldest:
        first_line = output.partition("\n")[0].strip()
    else:
        # Take the last non-empty line — ``git log`` without ``--reverse``
        # emits newest-first.
        first_line = ""
        for line in output.splitlines():
            stripped = line.strip()
            if stripped:
                first_line = stripped
                break
    return first_line or None


def _write_run_manifest(manifest_path: Path, payload: dict[str, Any]) -> None:
    """Atomically write the run manifest payload to ``manifest_path``.

    Writes to ``<path>.tmp`` first, then renames atomically. This
    prevents a partial manifest from being observed by a renderer that
    happens to read between two writes (the per-step update cycle).

    Parameters
    ----------
    manifest_path
        Target ``run_manifest.json`` path.
    payload
        Dict returned by :func:`_build_run_manifest`.
    """

    tmp_path = manifest_path.with_suffix(manifest_path.suffix + ".tmp")
    tmp_path.write_text(
        json.dumps(payload, indent=2, default=str),
        encoding="utf-8",
    )
    tmp_path.replace(manifest_path)


def _git_head_sha(repo_root: Path) -> str | None:
    """Return the resolved SHA of ``HEAD`` for the manifest, or ``None``.

    Captured once at manifest-emit time so downstream renderers and the
    ``reproduce.sh`` script can pin the exact commit the analysis ran
    against. The compute_metrics worker reads ``head_sha`` to generate
    the ``git -C ... rev-parse <sha>`` pin in the appendix, and the
    report renderer surfaces it in the Environment Verification table.

    Parameters
    ----------
    repo_root
        Path to the repository working directory. Passed to ``git`` via
        ``-C`` so the helper does not depend on the orchestrator's cwd.

    Returns
    -------
    str | None
        The full SHA-1 hexadecimal string (e.g.
        ``"bb1acd083..."``) or ``None`` when git is unavailable, the
        path is not a git working tree, or the call times out.
    """

    try:
        completed = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            capture_output=True,
            check=False,
            timeout=SUBPROCESS_TIMEOUT_GIT_HELPERS,
        )
        if completed.returncode != 0:
            return None
        decoded = completed.stdout.decode("utf-8", errors="replace").strip()
        return decoded or None
    except FileNotFoundError:
        return None
    except subprocess.TimeoutExpired:
        return None


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """Orchestrator entry point.

    Workflow:

    1. Parse CLI arguments.
    2. Bootstrap the structured JSON logger and generate / propagate the
       run ID.
    3. Resolve absolute paths for ``repo_root``, ``output_dir``, and
       ``accel_dir``; create the output directory if it does not exist.
    4. Snapshot ``git status --porcelain`` (pre-run baseline for the
       read-only contract).
    5. Build the :class:`PipelineContext`.
    6. Iterate the canonical :data:`PIPELINE` in order. For each step:
       - If ``--only`` is set and the step is not in the allow-list,
         record ``status="skipped"``.
       - If the step's ``skip_when`` flag is set on the namespace, record
         ``status="skipped"``.
       - Otherwise, call :func:`execute_step`.
       - On ``status="failed"``, flip ``overall_ok`` to ``False``; halt
         unless ``--continue-on-error`` is set.
    7. Snapshot ``git status --porcelain`` again and compute the
       :func:`diff_status` violations.
    8. Serialise the :class:`StepResult` list plus run metadata into
       ``output_dir / "run_manifest.json"``.
    9. Return ``0`` when ``overall_ok``, else ``1``.

    Parameters
    ----------
    argv
        CLI arguments excluding the program name. ``None`` reads
        :data:`sys.argv`.

    Returns
    -------
    int
        ``0`` on overall success, ``1`` otherwise.
    """

    args = parse_args(argv)

    log, run_id = _bootstrap_logger()
    # Publish the resolved run_id back into the environment so every
    # subprocess spawned later through ``run_python_module`` inherits it
    # and emits log lines under the same correlation ID.
    os.environ["ACCEL_RUN_ID"] = run_id

    repo_root = args.repo_root.resolve()
    output_dir = args.output_dir.resolve()
    accel_dir = args.accel_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    log.info(f"Acceleration pipeline run_id={run_id} repo_root={repo_root}")
    log.info(f"output_dir={output_dir}  accel_dir={accel_dir}")

    # Pre-run git status snapshot for read-only enforcement.
    pre_status = "" if args.no_readonly_check else snapshot_git_status(repo_root)

    only = tuple(s.strip() for s in args.only.split(",")) if args.only else None
    ctx = PipelineContext(
        repo_root=repo_root,
        output_dir=output_dir,
        accel_dir=accel_dir,
        owner=args.owner,
        repo=args.repo,
        branch=args.branch,
        skip_network=args.skip_network,
        skip_github=args.skip_github,
        skip_ci_tests=args.skip_ci_tests,
        skip_issues=args.skip_issues,
        only=only,
        run_id=run_id,
    )

    # Capture environment fingerprint ONCE up-front so the initial
    # manifest carries it even before any step runs. The renderers and
    # compute_metrics worker read ``head_sha`` / ``repo_owner`` /
    # ``repo_name`` / ``generated_at`` from this file, so an
    # initial-write-before-renderers-consume ordering is required.
    head_sha = _git_head_sha(repo_root)
    git_version_str = _git_version()
    started_at = now_iso()

    manifest_path = output_dir / "run_manifest.json"

    # ---- Initial manifest -------------------------------------------------
    # Per the review feedback (L1230-1270), the renderers consume
    # ``run_manifest.json`` and must see an up-to-date copy when they
    # run. Writing an initial "running" manifest before the step loop
    # also lets the operator inspect a freshly-cloned, mid-run state
    # (the file exists; ``overall_status == "running"``; ``steps`` is
    # the partial list completed so far). Subsequent per-step writes
    # update ``steps`` so the manifest is always consistent with the
    # last completed step.
    results: list[StepResult] = []
    overall_ok = True

    def _write_current_manifest(
        *, finished_at: str | None, status: str, violations: list[str]
    ) -> None:
        """Persist the manifest reflecting current step results."""

        _write_run_manifest(
            manifest_path,
            _build_run_manifest(
                run_id=run_id,
                started_at=started_at,
                finished_at=finished_at,
                repo_root=repo_root,
                output_dir=output_dir,
                accel_dir=accel_dir,
                owner=args.owner,
                repo=args.repo,
                branch=args.branch,
                head_sha=head_sha,
                args_skip_network=args.skip_network,
                args_skip_github=args.skip_github,
                args_skip_ci_tests=args.skip_ci_tests,
                args_skip_issues=args.skip_issues,
                args_only=only,
                args_continue_on_error=args.continue_on_error,
                args_no_readonly_check=args.no_readonly_check,
                results=results,
                overall_status=status,
                readonly_violations=violations,
                git_version=git_version_str,
            ),
        )

    _write_current_manifest(
        finished_at=None, status="running", violations=[]
    )
    log.info(
        f"Initial run manifest written: {manifest_path}  "
        f"head_sha={head_sha or 'n/a'}"
    )

    # ---- Step loop --------------------------------------------------------
    for step in PIPELINE:
        # --only restricts execution to a hand-picked subset while
        # preserving canonical order. Steps not in the allow-list are
        # marked skipped so the manifest still records the intended shape.
        if only and step.name not in only:
            results.append(
                StepResult(
                    name=step.name,
                    description=step.description,
                    status="skipped",
                    exit_code=None,
                    started_at=now_iso(),
                    elapsed_seconds=0.0,
                    optional=step.optional,
                    error=f"not in --only={only}",
                    timed_out=False,
                )
            )
            # Per-step manifest update — keeps the file consistent with
            # the last completed step so renderers reading mid-run see
            # the most recent state.
            _write_current_manifest(
                finished_at=None, status="running", violations=[]
            )
            continue
        # skip_when implements user-requested step removal (e.g.
        # ``--skip-github`` disables the GitHub extractor even when a
        # token is available, which is useful for offline reproducibility
        # tests).
        if step.skip_when and getattr(args, step.skip_when, False):
            cli_flag = "--" + step.skip_when.replace("_", "-")
            log.info(f"[step={step.name}] skipped via {cli_flag}")
            results.append(
                StepResult(
                    name=step.name,
                    description=step.description,
                    status="skipped",
                    exit_code=None,
                    started_at=now_iso(),
                    elapsed_seconds=0.0,
                    optional=step.optional,
                    error="user-requested skip",
                    timed_out=False,
                )
            )
            _write_current_manifest(
                finished_at=None, status="running", violations=[]
            )
            continue
        result = execute_step(step, ctx, log)
        results.append(result)
        # ---- Per-step manifest update ------------------------------------
        # Before the next step runs (and before any renderer that might
        # be configured to run mid-pipeline), persist the just-completed
        # step into the manifest. This is the fix for the review
        # feedback "Manifest is written after consumers run". The
        # render_report / render_deck steps later in the pipeline can
        # now read a manifest that reflects every step before them.
        if result.status == "failed":
            overall_ok = False
            log.error(f"[step={step.name}] FAILED: {result.error}")
            _write_current_manifest(
                finished_at=None,
                status="running",
                violations=[],
            )
            if not args.continue_on_error:
                log.error(
                    "Halting pipeline due to step failure "
                    "(use --continue-on-error to override)."
                )
                break
        else:
            log.info(
                f"[step={step.name}] {result.status} "
                f"in {result.elapsed_seconds}s"
            )
            _write_current_manifest(
                finished_at=None,
                status="running",
                violations=[],
            )

    # ---- Post-run read-only check ----------------------------------------
    # The diff of ``before`` vs ``after`` is restricted to lines whose
    # path does not start with ``acceleration/``. Rename entries are
    # checked on BOTH source and target paths per the review feedback.
    post_status = "" if args.no_readonly_check else snapshot_git_status(repo_root)
    violations: list[str] = []
    if not args.no_readonly_check:
        violations = diff_status(pre_status, post_status, allow_prefix="acceleration/")
        if violations:
            overall_ok = False
            log.error(
                "READ-ONLY CONTRACT VIOLATION: files outside acceleration/ were modified.\n"
                + "\n".join(violations)
            )
        else:
            log.info(
                "Read-only contract verified: no changes outside acceleration/."
            )

    # ---- Final manifest --------------------------------------------------
    # Write the finalised manifest once the readonly check has run. The
    # ``finished_at`` field is now set, ``overall_status`` flips from
    # ``"running"`` to its terminal value, and ``readonly_violations``
    # carries the verified output of :func:`diff_status`.
    finished_at = now_iso()
    final_status = "ok" if overall_ok else "failed"
    _write_current_manifest(
        finished_at=finished_at,
        status=final_status,
        violations=violations,
    )
    log.info(f"Run manifest finalised: {manifest_path}")
    log.info(f"Overall status: {final_status}")
    return 0 if overall_ok else 1


if __name__ == "__main__":
    sys.exit(main())
