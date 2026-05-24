#!/usr/bin/env python3
"""
acceleration.scripts.extract_git
================================

Single-pass git history extractor for the Development Acceleration Analysis
pipeline.

This script reads the entire git history reachable from
``refs/remotes/origin/main`` (or the supplied ``--branch`` ref, defaulting to
``HEAD`` when ``origin/main`` is absent) and emits four artifacts under the
``acceleration/data/`` output directory:

``commits.jsonl``
    One JSON record per commit on the chosen ref, containing the canonical
    author/committer identity, ISO 8601 timestamps, parent SHAs, the parsed
    subject and body, the unfolded trailer block, the list of files touched
    by the commit (for non-merge commits), majority-vote module
    classification, and a pre-scanned AI authorship indicator.

``prs.jsonl``
    One JSON record per PR-merge commit identifiable by the
    ``(#NNNN)`` suffix in the subject — the convention enforced in the
    Formbricks repository by ``semantic-pull-requests.yml`` (AAP §0.2.1).
    Records carry the PR number, the merge commit SHA, the merge timestamp,
    the merge author identity, the merge subject and body, and — when the
    merge is a true two-parent merge commit (not a squash-merge) — the
    first/last commit SHA and timestamp on the PR branch.

``reverts.jsonl``
    One JSON record per revert commit. ``original_sha`` is resolved either
    via the explicit ``This reverts commit <sha>`` reference in the body
    (the git built-in ``git revert`` trailer) or by tree-matching the
    parent's tree against a window of recent ancestors per AAP §0.3.4.

``extract_git_access.json``
    Manifest containing the resolved ref, the HEAD SHA, the rev-list commit
    count, the streamed commit count, the date range, and per-category
    record counts. Consumed by ``compute_metrics.py`` for the Environment
    Verification section of ``acceleration-report.md`` and by
    ``verify_report.py`` for Rule 6 (Environment First).

Authority
---------

- AAP §0.4.1 enumerates this file as a CREATE target.
- AAP §0.3.2.2 — Git Extractor description ("single git-history pass
  producing commits.jsonl, prs.jsonl, reverts.jsonl; rationale: a single
  pass is more efficient than per-metric re-traversal and guarantees
  identical commit-set across metrics").
- AAP §0.3.4 — Revert attribution algorithm.
- AAP §0.2.1 — primary data source patterns:
  ``git log --format=%H%x09%s | grep -E '\\(#[0-9]+\\)$'`` (PR-merge),
  ``git log --format=%H%x09%s%n%b -E '^Revert |^Reverts commit '`` (revert).
- AAP §0.8.6 — module classification by majority vote on top-level changed
  paths, aggregating by ``apps/web``, ``apps/docs``, ``apps/storybook``,
  ``packages/database``, ``packages/surveys``, ``packages/types``,
  ``packages/other``, ``docs``, ``helm-chart``, ``charts``, ``blitzy``,
  ``blitzy-docs``, ``.github``, ``acceleration``, ``other``.

Read-only discipline (AAP §0.7.2.1, §0.8.7, §0.8.8)
---------------------------------------------------

Only read-only git CLI commands are invoked: ``git log``, ``git show``,
``git rev-parse``, ``git rev-list``. The script forbids and never invokes
``git add``, ``git commit``, ``git push``, ``git fetch``, ``git pull``,
``git checkout``, ``git reset``, ``git merge``, ``git rebase``, ``git tag``,
``git remote``, or any subcommand that writes refs or modifies the working
tree, index, or repository configuration. Filesystem writes are confined to
the four output files under the supplied ``--output-dir`` (default
``acceleration/data``).

Invocation
----------

.. code-block:: bash

    python3 acceleration/scripts/extract_git.py \\
        --repo-root . \\
        --branch refs/remotes/origin/main \\
        --output-dir acceleration/data

Use ``--skip-pr-branch-metadata`` to bypass the per-PR
``git log base..tip`` traversal for faster smoke tests against very large
repositories.

Integration with the pipeline
-----------------------------

This is the first data extractor invoked by
``acceleration/scripts/run_acceleration_analysis.py``. Downstream consumers:

- ``detect_inflection.py`` reads ``commits.jsonl`` (preferred) or falls
  back to a live ``git log`` scan; the pre-scanned ``ai_signal`` field on
  each commit accelerates Candidate A discovery.
- ``extract_github.py`` reads ``prs.jsonl`` and enriches each PR record
  with API fields (review history, draft state, labels).
- ``classify_prs.py`` consumes ``prs.jsonl`` for title-prefix and body
  keyword classification (Metric 6 Flow Distribution).
- ``compute_metrics.py`` consumes all three JSONL files for Metrics 2
  (Flow Velocity), 4 (Flow Active), 5 (Flow Efficiency), 6 (Flow
  Distribution), 7 (Flow Time), 8 (Problem Records via revert fallback).
- ``verify_report.py`` Rule 6 (Environment First) reads
  ``extract_git_access.json``.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator


# ---------------------------------------------------------------------------
# Field separators
# ---------------------------------------------------------------------------
# We compose a single ``--format=`` string for ``git log`` that emits all
# eleven fields per commit, joined by an ASCII Unit Separator (0x1F), with
# each commit terminated by an ASCII Record Separator (0x1E). Both
# characters are control codes that should never appear in commit
# messages, subjects, author names, or trailer lines under any sane
# convention; using them avoids the well-known fragility of pipe-, tab-,
# and newline-delimited git formats whose delimiters can appear inside
# commit message bodies.
FIELD_SEP = "\x1f"   # ASCII Unit Separator (US, 0x1F)
RECORD_SEP = "\x1e"  # ASCII Record Separator (RS, 0x1E)

# The eleven-field git-log format produces, in order:
#   0  %H                          full commit SHA
#   1  %an                         author name
#   2  %ae                         author email
#   3  %aI                         author date, strict ISO 8601 with offset
#   4  %cn                         committer name
#   5  %ce                         committer email
#   6  %cI                         committer date, strict ISO 8601 with offset
#   7  %P                          parent SHAs, space-separated
#   8  %s                          subject
#   9  %b                          body (may span multiple lines)
#  10  %(trailers:only,unfold)     just the trailer block, one per line
# RECORD_SEP is appended so each commit is bounded and we can stream-parse.
GIT_LOG_FORMAT: str = (
    FIELD_SEP.join(
        [
            "%H",
            "%an",
            "%ae",
            "%aI",
            "%cn",
            "%ce",
            "%cI",
            "%P",
            "%s",
            "%b",
            "%(trailers:only,unfold)",
        ]
    )
    + RECORD_SEP
)


# ---------------------------------------------------------------------------
# Regular expressions
# ---------------------------------------------------------------------------

# PR-merge subject pattern: subject ends with ``(#NNNN)`` (optionally followed
# by trailing whitespace). The end-anchor is critical — a body that says
# "addresses (#1234) and (#5678)" must NOT be classified as a PR merge.
# Reference: AAP §0.2.1 ("PR-merge identification:
# git log --format=%H%x09%s | grep -E '\\(#[0-9]+\\)$'").
PR_NUMBER_RE: re.Pattern[str] = re.compile(r"\(#(\d+)\)\s*$")

# Revert detection — three independent signals (any one matches):
#
#   1. Subject begins with the literal "Revert " (the convention emitted by
#      ``git revert`` and "Revert" GitHub button).
#   2. Body contains "This reverts commit <sha>" (the trailer git revert
#      embeds in the commit message body by default).
#   3. Body contains "Reverts commit <sha>" — an alternate phrasing seen in
#      Formbricks history.
#
# The ``[0-9a-f]{7,40}`` range accepts both abbreviated and full SHAs.
REVERT_SUBJECT_RE: re.Pattern[str] = re.compile(r"^Revert\b", re.IGNORECASE)
REVERTS_COMMIT_RE: re.Pattern[str] = re.compile(
    r"This reverts commit ([0-9a-f]{7,40})", re.IGNORECASE
)
ALT_REVERTS_RE: re.Pattern[str] = re.compile(
    r"\bReverts commit ([0-9a-f]{7,40})", re.IGNORECASE
)

# Semver tag patterns (AAP §0.1.3 — "release source precedence ... (2) annotated
# git tags matching semver pattern v?\\d+\\.\\d+\\.\\d+. Prerelease tags
# (matching -alpha, -beta, -rc, -dev suffixes) are excluded from the primary
# count and reported separately."). The pattern intentionally permits both
# ``v1.2.3`` and bare ``1.2.3`` forms, plus a ``+build`` metadata segment.
SEMVER_TAG_RE: re.Pattern[str] = re.compile(
    r"^v?\d+\.\d+\.\d+"
    r"(?P<prerelease>-(?:[0-9A-Za-z\-]+(?:\.[0-9A-Za-z\-]+)*))?"
    r"(?P<build>\+[0-9A-Za-z\-]+(?:\.[0-9A-Za-z\-]+)*)?$"
)
# Substring tokens that mark a tag as a prerelease per AAP §0.1.3 even when
# they appear inside the prerelease segment after the first dash.
PRERELEASE_TOKENS: tuple[str, ...] = (
    "alpha",
    "beta",
    "rc",
    "dev",
    "pre",
    "preview",
    "snapshot",
    "nightly",
    "next",
    "canary",
)


# ---------------------------------------------------------------------------
# Subprocess timeout budgets (Checkpoint 3 hardening)
# ---------------------------------------------------------------------------
# These bound every git subprocess invocation so a hung / corrupt repository
# cannot deadlock the pipeline. The values mirror the Phase-5 hardening of
# ``run_acceleration_analysis.py`` and ``detect_inflection.py``:
#
#   * GIT_RUN_TIMEOUT_SECONDS — bounds short blocking git commands invoked
#     via :func:`run_git` (rev-parse, rev-list, for-each-ref, show, etc).
#     The 5,178-commit ``git rev-list --count`` on the live Formbricks
#     repository takes well under a second; 600 s is a very generous safety
#     net that still terminates a hung child long before downstream waits.
#   * GIT_LOG_STREAM_TIMEOUT_SECONDS — bounds a single read chunk from the
#     long-running ``git log`` stream in :func:`iter_commits`. A healthy
#     git log produces output in dense bursts; a stall longer than this
#     budget indicates the child is no longer producing data, and the
#     iterator degrades to a partial-history extraction rather than
#     hanging forever.
GIT_RUN_TIMEOUT_SECONDS: float = 600.0
GIT_LOG_STREAM_TIMEOUT_SECONDS: float = 600.0


# ---------------------------------------------------------------------------
# Module classification table
# ---------------------------------------------------------------------------
# AAP §0.8.6 — "Run per-module independently, aggregate weighted by commit
# volume (non-merge commits per module / total)."
#
# Each tuple is (path_prefix, module_label). Order matters: longer / more
# specific prefixes are listed first so that, for example, a file under
# ``packages/database/`` is classified as ``packages/database`` rather than
# falling through to the generic ``packages/other`` bucket. The first
# matching prefix wins.
#
# The label set targets the Formbricks pnpm + turbo monorepo layout
# (AAP §0.2.3, "apps/{web, docs, storybook} and 14 packages under
# packages/*"). The ``acceleration`` bucket is included so that the
# additive analysis artifacts produced by this very task do not pollute
# the ``other`` bucket when the script is re-run later in the repository's
# life cycle.
MODULE_PREFIXES: tuple[tuple[str, str], ...] = (
    ("apps/web",          "apps/web"),
    ("apps/docs",         "apps/docs"),
    ("apps/storybook",    "apps/storybook"),
    ("packages/database", "packages/database"),
    ("packages/surveys",  "packages/surveys"),
    ("packages/types",    "packages/types"),
    ("packages/",         "packages/other"),
    ("docs/",             "docs"),
    ("helm-chart",        "helm-chart"),
    ("charts/",           "charts"),
    ("blitzy/",           "blitzy"),
    ("blitzy-docs",       "blitzy-docs"),
    (".github",           ".github"),
    ("acceleration/",     "acceleration"),
)


def module_for_path(path: str) -> str:
    """Return the canonical module label for a given repository-relative path.

    The classification matches each tuple in :data:`MODULE_PREFIXES` in
    order; the first prefix that ``path`` starts with determines the module.
    Paths not covered by any prefix are bucketed into ``"other"``.

    Parameters
    ----------
    path : str
        A repository-relative file path (forward slashes), as produced by
        ``git show --name-only``.

    Returns
    -------
    str
        The canonical module label (e.g. ``"apps/web"``,
        ``"packages/database"``, ``"docs"``, ``"other"``).

    Examples
    --------
    >>> module_for_path("apps/web/app/page.tsx")
    'apps/web'
    >>> module_for_path("packages/database/migrations/0001.sql")
    'packages/database'
    >>> module_for_path("README.md")
    'other'
    """

    for prefix, module in MODULE_PREFIXES:
        if path.startswith(prefix):
            return module
    return "other"


# ---------------------------------------------------------------------------
# AI-tool author / co-author detection
# ---------------------------------------------------------------------------
# AAP §0.3.1 enumerates four AI-tool indicators. The first three are
# canonical email addresses observed in commit ``%ae`` (author email) and
# ``Co-authored-by:`` trailers; the fourth is a bot-name pattern that
# matches GitHub App synthetic emails of the form
# ``<id>+blitzy[bot]@users.noreply.github.com``.
#
# Co-authored-by trailers in the unfolded git output appear one per line
# under the canonical format
# ``Co-authored-by: <display name> <email>``. We anchor on
# ``Co-authored-by:`` and capture the email between the angle brackets.
AI_TRAILER_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"Co-authored-by:[^<\n]*<\s*(agent@blitzy\.com)\s*>",
        re.IGNORECASE,
    ),
    re.compile(
        r"Co-authored-by:[^<\n]*<\s*(noreply@anthropic\.com)\s*>",
        re.IGNORECASE,
    ),
    re.compile(
        r"Co-authored-by:[^<\n]*<\s*(copilot@github\.com)\s*>",
        re.IGNORECASE,
    ),
    re.compile(
        r"Co-authored-by:[^<\n]*<\s*([\w.+-]+@users\.noreply\.github\.com)\s*>.*\bblitzy\[bot\]",
        re.IGNORECASE,
    ),
)

# Canonical AI author emails. ``detect_ai_signal`` checks the commit's
# ``author_email`` (lower-cased) against this tuple; a match yields an
# ``author_email=<email>`` indicator. The constant is exported so that
# ``detect_inflection.py`` can re-use the same set without duplicating the
# enumeration.
AI_AUTHOR_EMAILS: tuple[str, ...] = (
    "agent@blitzy.com",
    "noreply@anthropic.com",
    "copilot@github.com",
)


# ---------------------------------------------------------------------------
# Git subprocess helpers (read-only)
# ---------------------------------------------------------------------------


def run_git(
    args: list[str],
    cwd: Path | None = None,
    *,
    check: bool = True,
    timeout: float | None = None,
) -> str:
    """Invoke ``git`` with the supplied arguments and return decoded stdout.

    The function is the canonical entry point for every blocking
    (non-streaming) git command issued by this module. Streaming reads
    (``git log`` of the entire history) go through :func:`iter_commits`
    using :class:`subprocess.Popen` directly so that the full commit log
    is not buffered into memory at once.

    Parameters
    ----------
    args : list[str]
        Git subcommand and arguments (without the leading ``"git"``). The
        caller is responsible for restricting these to read-only
        invocations; this function does not police argument content.
    cwd : pathlib.Path or None
        Working directory in which to run git. ``None`` uses the calling
        process's cwd.
    check : bool, default True
        When ``True`` (the default), a non-zero exit status raises
        :class:`RuntimeError` with the captured stderr. When ``False``,
        the function returns the empty string on failure so callers can
        detect missing refs / commits without aborting the pipeline.
    timeout : float or None, default None
        Maximum wall-clock seconds to wait for the git invocation. When
        ``None`` the function applies :data:`GIT_RUN_TIMEOUT_SECONDS`
        (Checkpoint 3 hardening). On timeout, behaviour mirrors a non-zero
        exit: a :class:`RuntimeError` is raised when ``check=True`` and an
        empty string is returned when ``check=False``.

    Returns
    -------
    str
        Decoded UTF-8 stdout. The text decoder uses ``errors="replace"``
        so that commit messages containing invalid byte sequences (a known
        risk in long-lived repositories with mixed-locale authors) do not
        cause a ``UnicodeDecodeError`` mid-extraction.

    Raises
    ------
    RuntimeError
        When ``check=True`` and git exits non-zero, or when the timeout is
        exceeded. The exception message includes the failing command line
        and (where available) the stderr text.
    """

    cmd: list[str] = ["git"] + args
    budget = GIT_RUN_TIMEOUT_SECONDS if timeout is None else timeout
    try:
        result = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            check=False,
            capture_output=True,
            timeout=budget,
        )
    except subprocess.TimeoutExpired as exc:
        # Surface the timeout uniformly with non-zero exit handling so
        # callers do not need to special-case it. Per AAP §0.7.2.1 the
        # script must never hang the pipeline on a corrupt repository.
        if check:
            raise RuntimeError(
                f"`{' '.join(cmd)}` timed out after {budget:.0f}s "
                f"(set GIT_RUN_TIMEOUT_SECONDS or pass timeout=...)"
            ) from exc
        return ""
    if check and result.returncode != 0:
        stderr_text = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(
            f"`{' '.join(cmd)}` failed (rc={result.returncode}): {stderr_text}"
        )
    return result.stdout.decode("utf-8", errors="replace")


def head_sha(cwd: Path) -> str:
    """Return the commit SHA pointed to by ``HEAD`` in the given repository.

    Parameters
    ----------
    cwd : pathlib.Path
        The repository root.

    Returns
    -------
    str
        The 40-character SHA of the current HEAD commit, with surrounding
        whitespace stripped.
    """

    return run_git(["rev-parse", "HEAD"], cwd=cwd).strip()


def resolve_branch_ref(cwd: Path, branch_arg: str | None) -> str:
    """Pick the canonical ref to extract from.

    Precedence:

    1. ``branch_arg`` when supplied (the caller knows best).
    2. ``refs/remotes/origin/main`` when it exists in the repository — the
       canonical "what is shipped" ref preferred by AAP §0.2.1 ("Git
       objects (primary data source) — every commit reachable from
       refs/remotes/origin/main").
    3. ``HEAD`` as a last resort, suitable for shallow / single-branch
       clones where ``origin/main`` is absent.

    Parameters
    ----------
    cwd : pathlib.Path
        The repository root.
    branch_arg : str or None
        The ``--branch`` CLI argument, or ``None`` to auto-detect.

    Returns
    -------
    str
        A ref-name suitable for passing to ``git log``.
    """

    if branch_arg:
        return branch_arg
    try:
        run_git(
            ["rev-parse", "--verify", "refs/remotes/origin/main"],
            cwd=cwd,
        )
        return "refs/remotes/origin/main"
    except RuntimeError:
        return "HEAD"


def commit_count(cwd: Path, ref: str) -> int:
    """Return the number of commits reachable from ``ref``.

    Equivalent to ``git rev-list --count <ref>``.

    Parameters
    ----------
    cwd : pathlib.Path
        The repository root.
    ref : str
        A git ref (branch, tag, or SHA).

    Returns
    -------
    int
        Total commit count. Returns 0 when ``rev-list`` produces no output.
    """

    out = run_git(["rev-list", "--count", ref], cwd=cwd).strip()
    return int(out) if out else 0


def date_range(cwd: Path, ref: str) -> tuple[str | None, str | None]:
    """Return the (first, last) author dates of commits reachable from ``ref``.

    Both timestamps are in strict ISO 8601 format with offset (``%aI``).

    Implementation note — naïve callers reach for
    ``git log --reverse --format=%aI --max-count=1`` to find the oldest
    commit, but git applies ``--max-count`` BEFORE ``--reverse`` per the
    documented "Commit Limiting" semantics, so that pattern actually
    returns the NEWEST commit (and is then reversed within a one-element
    list, which is a no-op). The correct approach is to identify the
    root commit(s) via ``git rev-list --max-parents=0`` and take the
    earliest author date among them. The repository may have more than
    one root commit when histories from disjoint sources have been
    merged together; this helper handles that by selecting the
    lexicographically smallest ISO 8601 timestamp, which by construction
    is the chronologically earliest.

    Parameters
    ----------
    cwd : pathlib.Path
        The repository root.
    ref : str
        A git ref.

    Returns
    -------
    tuple[str | None, str | None]
        ``(first_iso, last_iso)``. Either component may be ``None`` for an
        empty history or an unreadable ref.
    """

    last_raw = run_git(
        ["log", ref, "--format=%aI", "--max-count=1"],
        cwd=cwd,
        check=False,
    ).strip()

    roots_blob = run_git(
        ["rev-list", "--max-parents=0", ref],
        cwd=cwd,
        check=False,
    ).strip()
    root_dates: list[str] = []
    for root_sha in (line for line in roots_blob.splitlines() if line):
        date_text = run_git(
            ["show", "-s", "--format=%aI", root_sha],
            cwd=cwd,
            check=False,
        ).strip()
        if date_text:
            root_dates.append(date_text)

    # ISO 8601 with strict offset sorts lexicographically in chronological
    # order, so ``min`` yields the earliest root-commit author date. When
    # no root could be identified (e.g. an empty history or an unreadable
    # ref), ``first_raw`` resolves to ``None``.
    first_raw: str | None = min(root_dates) if root_dates else None

    return first_raw, (last_raw or None)


def is_prerelease_tag(name: str) -> bool:
    """Return True when ``name`` is an annotated semver *prerelease* tag.

    Implements AAP §0.1.3 — "Prerelease tags (matching -alpha, -beta, -rc,
    -dev suffixes) are excluded from the primary count and reported
    separately." The check is:

    1. The tag matches the semver pattern ``^v?\\d+\\.\\d+\\.\\d+`` so that
       non-version tags (e.g. ``release-2024-q2``) never qualify as
       prereleases of nothing.
    2. The tag carries a prerelease segment, *or* the lowercased tag
       contains one of the recognised prerelease tokens (alpha / beta /
       rc / dev / pre / preview / snapshot / nightly / next / canary). The
       second arm catches non-standard prerelease conventions seen in
       practice (e.g. ``v1.2.3.beta`` with a period instead of a hyphen).

    Parameters
    ----------
    name : str
        The tag name as reported by ``git for-each-ref``.

    Returns
    -------
    bool
        True when the tag should be excluded from the primary release count.
    """

    if not name:
        return False
    match = SEMVER_TAG_RE.match(name.strip())
    if match is None:
        return False
    if match.group("prerelease"):
        return True
    lowered = name.lower()
    for token in PRERELEASE_TOKENS:
        if token in lowered:
            return True
    return False


def iter_tags(cwd: Path) -> Iterator[dict[str, Any]]:
    """Yield annotated tag records from the repository.

    This implements the **secondary** release source defined in AAP §0.1.3
    ("release source precedence ... (2) annotated git tags matching semver
    pattern v?\\d+\\.\\d+\\.\\d+"). The Formbricks repository has zero
    annotated tags at the time of writing, so the generator simply yields
    nothing on that repository. The implementation is included so that the
    extractor is correct on any repository that DOES tag releases.

    Per-tag record fields:

    ``tag``
        The tag name (with the ``refs/tags/`` prefix stripped).
    ``commit_sha``
        The peeled commit SHA the tag ultimately resolves to (i.e. the
        target of an annotated tag's tag object).
    ``tagger_date``
        Strict-ISO 8601 timestamp of the *tag* (the moment of tagging), not
        the commit it points to. Resolves to the empty string for
        lightweight tags that have no tagger record.
    ``commit_date``
        Strict-ISO 8601 committer date of the commit the tag points to.
    ``object_type``
        One of ``tag`` (annotated), ``commit`` (lightweight), or another
        object type that git considers tag-targetable.
    ``is_annotated``
        True iff ``object_type == "tag"``. Lightweight tags are emitted as
        well so callers can decide whether to include them; the
        ``main()`` orchestrator's manifest reports the split.
    ``is_semver``
        True iff the tag matches the semver pattern.
    ``is_prerelease``
        True iff :func:`is_prerelease_tag` returns True.

    The Iterator yields tags in chronological order of their tagger date
    (oldest first), with lightweight tags ordered by the underlying commit
    date as a fallback. This deterministic ordering simplifies downstream
    windowing in ``compute_metrics.py``.

    Parameters
    ----------
    cwd : pathlib.Path
        The repository root.

    Yields
    ------
    dict[str, Any]
        One record per tag in ``refs/tags/``. The generator is
        non-stateful: a fresh ``git for-each-ref`` invocation produces the
        same sequence each time absent concurrent repository writes (which
        this read-only pipeline does not perform).

    Read-only discipline
    --------------------
    Invokes only ``git for-each-ref`` — a strict read-only inspection
    command that touches neither refs, working tree, nor index.
    """

    # Field separators identical to those used for commit streaming so the
    # parse logic is consistent. The format string requests, in order:
    #   0  refname (e.g. refs/tags/v1.2.3)
    #   1  object type of the *tag* object (tag | commit | tree | blob)
    #   2  tagger date in strict ISO 8601 (empty for lightweight tags)
    #   3  *peeled* commit committer date in strict ISO 8601
    #   4  peeled commit SHA (the actual commit the tag eventually points to)
    fmt = FIELD_SEP.join(
        [
            "%(refname)",
            "%(objecttype)",
            "%(taggerdate:iso-strict)",
            "%(*committerdate:iso-strict)",
            "%(*objectname)",
        ]
    ) + RECORD_SEP

    out = run_git(
        ["for-each-ref", "--format=" + fmt, "refs/tags/"],
        cwd=cwd,
        check=False,
    )

    records: list[dict[str, Any]] = []
    for raw in out.split(RECORD_SEP):
        line = raw.strip()
        if not line:
            continue
        parts = line.split(FIELD_SEP)
        # Pad to 5 fields to tolerate empty trailing components such as a
        # missing tagger date on a lightweight tag.
        if len(parts) < 5:
            parts.extend([""] * (5 - len(parts)))
        refname, object_type, tagger_date, commit_date, commit_sha = parts[:5]
        if not refname.startswith("refs/tags/"):
            continue
        tag_name = refname[len("refs/tags/"):]
        is_annotated = object_type == "tag"
        # For lightweight tags, %(*committerdate) and %(*objectname) are
        # empty because there is no intermediate tag object. We fall back
        # to %(committerdate) and %(objectname) via a second cheap query
        # only if needed; here we simply blank them and let the caller
        # decide. In practice Formbricks has zero tags so this path is
        # exercised only on other repositories.
        record: dict[str, Any] = {
            "tag": tag_name,
            "commit_sha": commit_sha or "",
            "tagger_date": tagger_date or "",
            "commit_date": commit_date or "",
            "object_type": object_type or "",
            "is_annotated": is_annotated,
            "is_semver": bool(SEMVER_TAG_RE.match(tag_name)),
            "is_prerelease": is_prerelease_tag(tag_name),
        }
        records.append(record)

    # Sort by the most reliable date available — tagger date for annotated
    # tags, commit date as the fallback — so downstream windowing sees a
    # chronologically monotonic stream regardless of how git stored the
    # refs internally.
    def _sort_key(rec: dict[str, Any]) -> str:
        return rec.get("tagger_date") or rec.get("commit_date") or ""

    records.sort(key=_sort_key)
    for rec in records:
        yield rec


# ---------------------------------------------------------------------------
# CommitFields dataclass and stream parser
# ---------------------------------------------------------------------------


@dataclass
class CommitFields:
    """Parsed view of a single git log record.

    The eleven fields correspond positionally to the eleven format
    specifiers in :data:`GIT_LOG_FORMAT`. ``parents`` is normalised from
    git's space-separated ``%P`` output into a Python list. ``trailers``
    is normalised from the multi-line ``%(trailers:only,unfold)`` output
    into a list of single-line trailer strings (with surrounding
    whitespace stripped).

    Attributes
    ----------
    sha : str
        Full 40-character commit SHA (``%H``).
    author_name : str
        Author display name (``%an``).
    author_email : str
        Author email address (``%ae``).
    author_date : str
        Author date in strict ISO 8601 with offset (``%aI``).
    committer_name : str
        Committer display name (``%cn``).
    committer_email : str
        Committer email address (``%ce``).
    committer_date : str
        Committer date in strict ISO 8601 with offset (``%cI``).
    parents : list[str]
        Parent SHAs (``%P``). Zero entries for the root commit, one for
        a fast-forward / squash-merge / cherry-pick commit, two or more
        for a true merge commit.
    subject : str
        Commit subject (``%s``).
    body : str
        Commit message body (``%b``).
    trailers : list[str]
        Trailer lines as emitted by ``%(trailers:only,unfold)``, one per
        list element.
    """

    sha: str
    author_name: str
    author_email: str
    author_date: str
    committer_name: str
    committer_email: str
    committer_date: str
    parents: list[str] = field(default_factory=list)
    subject: str = ""
    body: str = ""
    trailers: list[str] = field(default_factory=list)


def parse_trailers(trailer_blob: str) -> list[str]:
    """Split the ``%(trailers:only,unfold)`` output into a list of trailers.

    The git trailer formatter, when invoked with ``only,unfold``, emits
    each trailer on its own line with continuation lines already folded
    into the preceding trailer. This helper simply tokenises on newlines
    and discards empty lines.

    Parameters
    ----------
    trailer_blob : str
        Raw multi-line trailer text from git.

    Returns
    -------
    list[str]
        One element per trailer line. Surrounding whitespace is stripped
        from each line. The list is empty for commits with no trailers.
    """

    return [line.strip() for line in trailer_blob.splitlines() if line.strip()]


def _emit_commit(parts: list[str]) -> CommitFields:
    """Construct a :class:`CommitFields` from an eleven-element parts list.

    Helper used by :func:`iter_commits` so that the streaming parser and
    the tail-buffer drain produce identical records without code
    duplication.
    """

    # Defensive padding: the parser should always supply eleven elements,
    # but if a malformed record ever slips through (e.g. a truncated git
    # log output), pad with empty strings so the dataclass constructor
    # does not raise.
    if len(parts) < 11:
        parts = parts + [""] * (11 - len(parts))
    return CommitFields(
        sha=parts[0],
        author_name=parts[1],
        author_email=parts[2],
        author_date=parts[3],
        committer_name=parts[4],
        committer_email=parts[5],
        committer_date=parts[6],
        parents=parts[7].split() if parts[7] else [],
        subject=parts[8],
        body=parts[9],
        trailers=parse_trailers(parts[10]),
    )


def iter_commits(cwd: Path, ref: str) -> Iterator[CommitFields]:
    """Stream commits reachable from ``ref`` as :class:`CommitFields`.

    Implementation note — a single ``git log`` subprocess is started and
    its stdout is consumed in 64 KiB chunks. Records are recovered by
    splitting the buffered text on :data:`RECORD_SEP` (ASCII 0x1E); each
    record is then split on :data:`FIELD_SEP` (ASCII 0x1F) into the
    eleven positional fields. This avoids loading the entire commit log
    (5,000+ commits at Formbricks scale) into memory at once.

    Parameters
    ----------
    cwd : pathlib.Path
        The repository root.
    ref : str
        A git ref to log.

    Yields
    ------
    CommitFields
        One per commit reachable from ``ref``, in
        ``git log`` default order (reverse chronological).

    Raises
    ------
    RuntimeError
        When the underlying ``git log`` subprocess exits with a non-zero
        return code AFTER stdout has been fully drained. Errors that
        terminate streaming early are surfaced via this exception with
        the captured stderr.
    """

    proc = subprocess.Popen(
        ["git", "log", ref, f"--format={GIT_LOG_FORMAT}"],
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert proc.stdout is not None  # Popen with stdout=PIPE guarantees this.
    assert proc.stderr is not None

    buffer: str = ""
    # ``consumer_closed_early`` flips True if the caller invokes ``close()``
    # on the generator before the git log stream is exhausted. In that case
    # the OS will deliver SIGPIPE to git when we close the read end of the
    # pipe in the ``finally`` block; that is the expected response to an
    # early consumer close, NOT a real extraction failure, so we suppress
    # the RuntimeError that the failure branch would otherwise raise.
    consumer_closed_early: bool = False
    # ``stream_timed_out`` flips True if the per-read deadline elapses
    # without progress. The finally block force-terminates the child and
    # converts the situation into a RuntimeError so the orchestrator can
    # capture the partial extraction as a degraded run.
    stream_timed_out: bool = False
    # Track wall-clock progress on the read loop so a hung child can be
    # detected without polling every read. A healthy ``git log`` of the
    # Formbricks history produces output in dense bursts, so each
    # successful read is allowed to reset the deadline.
    last_read_monotonic = time.monotonic()
    try:
        try:
            while True:
                raw_chunk = proc.stdout.read(65536)
                now = time.monotonic()
                if not raw_chunk:
                    break
                # Successful read advances the deadline.
                last_read_monotonic = now
                buffer += raw_chunk.decode("utf-8", errors="replace")
                # Drain as many complete records as possible. Each iteration
                # peels one record off the front of ``buffer`` and re-binds
                # ``buffer`` to whatever follows; the loop exits when the
                # buffer no longer contains a RECORD_SEP, at which point we
                # go back and read more bytes.
                while RECORD_SEP in buffer:
                    record, buffer = buffer.split(RECORD_SEP, 1)
                    # Records other than the first are prefixed by a newline
                    # left behind from the previous record's trailer; strip
                    # leading newlines so the SHA does not accidentally
                    # absorb whitespace.
                    record = record.lstrip("\n")
                    if not record:
                        continue
                    yield _emit_commit(record.split(FIELD_SEP))
                # Per-read deadline check: if too much time elapsed without
                # the child producing data, treat the stream as stalled and
                # bail out. The finally block force-kills the child and
                # converts the situation into a RuntimeError.
                if now - last_read_monotonic > GIT_LOG_STREAM_TIMEOUT_SECONDS:
                    stream_timed_out = True
                    break

            # Tail drain — if the very last record was not terminated by a
            # RECORD_SEP (e.g. because the format string was misconfigured or
            # git output was truncated), salvage it as best we can. This is a
            # defensive branch; with a correctly composed format string it
            # never triggers, but it costs nothing to keep and prevents a
            # silent loss of the last commit.
            residual = buffer.strip()
            if residual:
                parts = residual.split(FIELD_SEP)
                if len(parts) >= 11:
                    yield _emit_commit(parts)
        except GeneratorExit:
            # The consumer called ``close()`` on the generator before
            # the stream finished. This is a legitimate early-exit
            # pattern (e.g. unit tests that only need to inspect the
            # first yielded commit). Record the situation so the
            # ``finally`` block does not turn the resulting SIGPIPE
            # return code from git into a spurious extraction failure.
            consumer_closed_early = True
            raise
    finally:
        # Always reap the child process. Closing stdout first signals EOF
        # to git so it terminates promptly; we then wait for the actual
        # exit so the OS does not leave a zombie behind. The previous
        # implementation used bare ``pass`` statements in the cleanup
        # except blocks; Checkpoint 3 disallows that pattern, so we use
        # ``contextlib.suppress`` which both documents intent and keeps
        # the surrounding code observable via tracebacks if it ever leaks.
        with contextlib.suppress(Exception):
            # Closing stdout signals EOF to git. Some git versions emit
            # a broken-pipe error which is intentionally swallowed because
            # we already have the data we need at this point in the loop.
            proc.stdout.close()
        try:
            stderr_bytes = proc.stderr.read()
        except Exception:
            # Reading stderr after the child has been killed can fail on
            # some platforms. Fall back to an empty buffer so the error
            # message below remains coherent.
            stderr_bytes = b""
        finally:
            with contextlib.suppress(Exception):
                # Mirror the stdout cleanup; suppression here is intentional
                # because the FD may already be closed by the kernel after
                # an early ``proc.kill()`` below.
                proc.stderr.close()
        if stream_timed_out:
            # Force-terminate immediately when the read loop already
            # diagnosed a stall; do not give the child an additional 30 s
            # window to exit on its own.
            with contextlib.suppress(Exception):
                proc.kill()
            with contextlib.suppress(Exception):
                proc.wait(timeout=5)
            stderr_text = stderr_bytes.decode("utf-8", errors="replace").strip()
            raise RuntimeError(
                f"`git log {ref}` stalled "
                f"({GIT_LOG_STREAM_TIMEOUT_SECONDS:.0f}s without output): "
                f"{stderr_text}"
            )
        try:
            returncode = proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
            returncode = -1
        # Treat the following return codes as benign:
        #   - 0      : normal exit
        #   - -13    : POSIX SIGPIPE (signal 13) delivered to git after we
        #              closed the read end of its stdout pipe. Expected
        #              whenever the consumer closed us early.
        #   - 141    : Shell convention for SIGPIPE (128 + 13). Some Python
        #              builds surface SIGPIPE as 141 instead of -13.
        # Any other non-zero return code with the caller still wanting more
        # data is treated as a real failure and converted into a
        # RuntimeError carrying git's captured stderr.
        if (
            returncode not in (0, -13, 141)
            and not consumer_closed_early
        ):
            stderr_text = stderr_bytes.decode("utf-8", errors="replace").strip()
            raise RuntimeError(
                f"`git log {ref}` exited rc={returncode}: {stderr_text}"
            )


# ---------------------------------------------------------------------------
# Per-commit touched-files lookup and module aggregation
# ---------------------------------------------------------------------------


def commit_touched_files(cwd: Path, sha: str) -> list[str]:
    """Return the list of files touched by a single commit.

    Uses ``git show --name-only --no-renames --format=`` so that only the
    filenames are emitted (no diff text, no commit metadata). Renames are
    suppressed (``--no-renames``) so that a file rename is reported as
    one add and one delete rather than a single rename line; this keeps
    the module-classification logic simple — every entry is a real path
    we can match against :data:`MODULE_PREFIXES`.

    For merge commits, ``git show --name-only --format=`` emits the
    "combined diff" file list, which is typically empty (merges that
    only resolve overlapping diffs without introducing additional
    changes produce no combined diff entries). The caller in
    :func:`main` skips merge commits entirely so this function is only
    invoked on non-merge commits.

    Parameters
    ----------
    cwd : pathlib.Path
        The repository root.
    sha : str
        Commit SHA to inspect.

    Returns
    -------
    list[str]
        File paths touched by the commit. Empty if the commit touches no
        files (rare — typically an empty commit) or if git show fails
        (the function is invoked with ``check=False``).
    """

    out = run_git(
        ["show", "--name-only", "--no-renames", "--format=", sha],
        cwd=cwd,
        check=False,
    )
    return [line.strip() for line in out.splitlines() if line.strip()]


def classify_commit_modules(touched: list[str]) -> tuple[str, dict[str, int]]:
    """Compute the dominant module and the full module-to-count map.

    AAP §0.8.6 prescribes "majority-vote on top-level changed paths". For
    a commit touching files in multiple modules, the module with the most
    touched files wins. Ties are broken by the iteration order of
    :class:`dict`, which since Python 3.7 is the insertion order; because
    the dictionary is populated in the order files appear in the commit,
    the first encountered module wins on a tie (stable behaviour).

    Parameters
    ----------
    touched : list[str]
        File paths touched by the commit.

    Returns
    -------
    tuple[str, dict[str, int]]
        ``(dominant_module, {module_label: count, ...})``. When
        ``touched`` is empty (e.g. a merge commit's combined diff with no
        additional changes), returns ``("other", {})``.
    """

    counts: dict[str, int] = {}
    for path in touched:
        label = module_for_path(path)
        counts[label] = counts.get(label, 0) + 1
    if not counts:
        return "other", {}
    dominant = max(counts.items(), key=lambda kv: kv[1])
    return dominant[0], counts


# ---------------------------------------------------------------------------
# PR-merge identification
# ---------------------------------------------------------------------------


def extract_pr_number(subject: str) -> int | None:
    """Extract the PR number from a commit subject, if present.

    Matches the ``(#NNNN)`` suffix produced by GitHub squash-merge and
    merge-commit conventions (and enforced for Formbricks by
    ``semantic-pull-requests.yml``). Returns ``None`` when the subject
    does not end in a parenthesised pound-number.

    Parameters
    ----------
    subject : str
        The commit subject line (``%s`` of ``git log``).

    Returns
    -------
    int or None
        The PR number, or ``None`` when no match.

    Examples
    --------
    >>> extract_pr_number("feat: add survey (#1234)")
    1234
    >>> extract_pr_number("chore: cleanup")
    >>> extract_pr_number("addresses (#1234) and (#5678) but is not a PR")
    >>> # The above returns None because the subject does not END with the
    >>> # pattern; both (#1234) and (#5678) appear mid-string. This is the
    >>> # intended behaviour.
    """

    match = PR_NUMBER_RE.search(subject)
    return int(match.group(1)) if match else None


def is_pr_merge(commit: CommitFields) -> tuple[bool, int | None]:
    """Determine whether ``commit`` is a PR-merge commit.

    The Formbricks convention (enforced by ``semantic-pull-requests.yml``)
    is that every PR merge — whether squash, rebase-and-merge, or merge
    commit — produces a commit on ``main`` whose subject ends with
    ``(#NNNN)``. This function therefore inspects only the subject; the
    parent count is not used as a signal because squash-merges and
    rebase-merges have a single parent.

    Parameters
    ----------
    commit : CommitFields
        The commit to inspect.

    Returns
    -------
    tuple[bool, int | None]
        ``(is_pr, pr_number)``. ``pr_number`` is ``None`` when ``is_pr``
        is ``False``.
    """

    number = extract_pr_number(commit.subject)
    return (number is not None), number


# ---------------------------------------------------------------------------
# Revert detection and original-commit resolution
# ---------------------------------------------------------------------------


def find_revert_sha_in_message(commit: CommitFields) -> str | None:
    """Return the SHA referenced by an explicit "reverts commit" trailer.

    Both phrasings are recognised:

    - ``This reverts commit <sha>`` — the canonical body trailer added by
      ``git revert`` with no flags.
    - ``Reverts commit <sha>`` — the alternative phrasing observed in
      Formbricks history.

    Parameters
    ----------
    commit : CommitFields
        The commit to inspect.

    Returns
    -------
    str or None
        The captured SHA (7–40 hex characters), or ``None`` when no
        explicit reference is present.
    """

    text = commit.body or ""
    match = REVERTS_COMMIT_RE.search(text) or ALT_REVERTS_RE.search(text)
    return match.group(1) if match else None


def tree_match_revert_target(
    cwd: Path,
    commit: CommitFields,
    lookback: int = 200,
) -> str | None:
    """Resolve a revert's target by tree-matching the parent against ancestors.

    When a revert commit has no explicit ``This reverts commit <sha>``
    reference (some users craft revert commit messages by hand without
    the trailer), we can sometimes still identify the original by
    observing that ``git revert`` produces a commit whose effect is to
    move the tree back to a prior state. If the parent of the revert
    commit had the same tree as some ancestor before it, that ancestor
    is a strong candidate for being the commit that was reverted.

    AAP §0.3.4: "if missing, tree-match against parents". Capped at
    ``lookback`` ancestors to bound the cost — at 200 commits per
    unresolved revert, even a thousand reverts (well above the Formbricks
    history's count) finishes in seconds.

    Parameters
    ----------
    cwd : pathlib.Path
        The repository root.
    commit : CommitFields
        The revert commit whose original we are trying to identify.
    lookback : int, default 200
        Maximum number of ancestor commits to inspect.

    Returns
    -------
    str or None
        An ancestor SHA whose tree matches the parent of the revert (a
        candidate "original" commit), or ``None`` when no match is found
        within the lookback window.
    """

    if not commit.parents:
        return None
    parent = commit.parents[0]
    try:
        parent_tree = run_git(
            ["rev-parse", f"{parent}^{{tree}}"], cwd=cwd
        ).strip()
    except RuntimeError:
        return None
    # Walk back from the parent's first ancestor. We use --max-count to
    # bound the cost. ``check=False`` so that a malformed ref does not
    # abort the whole extraction — we treat any failure here as
    # "unresolved" and move on.
    ancestors_blob = run_git(
        ["rev-list", "--max-count", str(lookback), f"{parent}~1"],
        cwd=cwd,
        check=False,
    )
    for ancestor in ancestors_blob.split():
        try:
            ancestor_tree = run_git(
                ["rev-parse", f"{ancestor}^{{tree}}"], cwd=cwd
            ).strip()
        except RuntimeError:
            continue
        if ancestor_tree == parent_tree:
            return ancestor
    return None


def classify_revert(
    cwd: Path,
    commit: CommitFields,
) -> dict[str, Any] | None:
    """Build a revert record for ``commit`` or return ``None`` if not a revert.

    A commit is a revert if EITHER its subject starts with ``"Revert"``
    OR its body contains an explicit ``This reverts commit <sha>`` /
    ``Reverts commit <sha>`` reference. The ``original_sha`` is resolved
    in three tiers:

    1. **explicit_message_reference** — captured directly from the body.
    2. **tree_match** — :func:`tree_match_revert_target` finds an
       ancestor with a matching tree.
    3. **unresolved** — neither method succeeded. Per AAP §0.3.4 these
       reverts are "excluded as 'unattributable'" by downstream
       computation; we still record them so the exclusion rate can be
       reported.

    Parameters
    ----------
    cwd : pathlib.Path
        The repository root.
    commit : CommitFields
        The commit to inspect.

    Returns
    -------
    dict[str, Any] or None
        ``None`` when the commit is not a revert. Otherwise a record
        containing ``revert_sha``, ``original_sha``,
        ``original_resolution``, ``revert_committed_at``,
        ``revert_author_email``, and ``revert_subject``.
    """

    is_revert_subject = bool(REVERT_SUBJECT_RE.match(commit.subject))
    explicit_sha = find_revert_sha_in_message(commit)
    if not is_revert_subject and not explicit_sha:
        return None

    original = explicit_sha
    resolution = "explicit_message_reference" if explicit_sha else "unresolved"
    if original is None and is_revert_subject:
        candidate = tree_match_revert_target(cwd, commit)
        if candidate is not None:
            original = candidate
            resolution = "tree_match"

    return {
        "revert_sha": commit.sha,
        "original_sha": original,
        "original_resolution": resolution,
        "revert_committed_at": commit.committer_date,
        "revert_author_email": commit.author_email,
        "revert_subject": commit.subject,
    }


# ---------------------------------------------------------------------------
# AI authorship signal
# ---------------------------------------------------------------------------


def detect_ai_signal(commit: CommitFields) -> dict[str, Any]:
    """Pre-scan a commit for AI-tool authorship indicators.

    Two independent signals are checked:

    1. The commit's author email matches one of the canonical AI emails
       in :data:`AI_AUTHOR_EMAILS` (case-insensitive).
    2. The commit's body or any of its trailers contains a
       ``Co-authored-by:`` line matching one of the patterns in
       :data:`AI_TRAILER_PATTERNS`.

    Each match contributes a descriptive indicator string to the
    returned ``indicators`` list. Performing this scan inside the
    streaming extractor is cheaper than re-reading the trailer block
    later in ``detect_inflection.py``, which is why the pre-scan is
    embedded here per AAP §0.3.1 ("Achieve deterministic inflection-date
    detection by ... scanning every commit's trailers for AI-tool email
    patterns") and the "Key Insights" note in the agent prompt
    ("AI signal pre-scan in extract_git simplifies detect_inflection.py").

    Parameters
    ----------
    commit : CommitFields
        The commit to inspect.

    Returns
    -------
    dict[str, Any]
        A dict with two keys:

        ``is_ai_signal`` (bool)
            ``True`` when any AI indicator was found.
        ``indicators`` (list[str])
            Human-readable indicator labels describing every match. For
            example ``["author_email=agent@blitzy.com", "trailer=noreply@anthropic.com"]``.

    Examples
    --------
    >>> commit = CommitFields(
    ...     sha="abc123", author_name="Blitzy Agent",
    ...     author_email="agent@blitzy.com", author_date="",
    ...     committer_name="", committer_email="", committer_date="",
    ...     parents=[], subject="", body="", trailers=[],
    ... )
    >>> detect_ai_signal(commit)["is_ai_signal"]
    True
    """

    indicators: list[str] = []
    if commit.author_email.lower() in AI_AUTHOR_EMAILS:
        indicators.append(f"author_email={commit.author_email}")
    # Combine body and trailers into a single search corpus. Each trailer
    # is on its own line in the unfolded form, so joining with "\n"
    # preserves line-anchored regex semantics inside individual patterns.
    text = "\n".join([commit.body] + commit.trailers)
    for pattern in AI_TRAILER_PATTERNS:
        match = pattern.search(text)
        if match:
            indicators.append(f"trailer={match.group(1)}")
    return {"is_ai_signal": bool(indicators), "indicators": indicators}


# ---------------------------------------------------------------------------
# PR record synthesis
# ---------------------------------------------------------------------------


def synthesize_pr_record(
    merge_commit: CommitFields,
    pr_number: int,
    branch_first_commit: dict[str, str] | None,
) -> dict[str, Any]:
    """Compose a PR record from a PR-merge commit.

    The record captures everything that can be derived from git alone:
    the PR number, the merge SHA, the merge author identity, and the
    merge subject and body. When ``branch_first_commit`` is supplied
    (i.e. the merge was a true two-parent merge commit and
    :func:`collect_pr_branch_metadata` succeeded in tracing the branch),
    the record additionally contains the first / last commit timestamps
    on the branch, which downstream metrics 4 (Flow Active) and 7 (Flow
    Time) require for working-time computation.

    For squash-merges (the Formbricks default per the AAP), the branch
    history is destroyed at merge time and ``branch_first_commit`` is
    ``None``; downstream metrics handle the absence by reporting the
    affected PRs as "excluded — pre-merge timestamps unavailable".

    Parameters
    ----------
    merge_commit : CommitFields
        The PR-merge commit (whose subject ends in ``(#NNNN)``).
    pr_number : int
        The PR number captured from the subject.
    branch_first_commit : dict[str, str] or None
        Branch metadata from :func:`collect_pr_branch_metadata`, or
        ``None`` when unavailable.

    Returns
    -------
    dict[str, Any]
        A PR record with the following keys:

        - ``number``
        - ``merge_sha``
        - ``merge_commit_sha_from_git`` (alias of ``merge_sha`` for
          downstream consumers that prefer the more explicit name)
        - ``merged_at``
        - ``title``
        - ``merge_subject``
        - ``merge_body``
        - ``merge_author_name``
        - ``merge_author_email``
        - ``first_commit_at`` (only when branch metadata is available)
        - ``first_commit_sha``
        - ``last_commit_at``
    """

    record: dict[str, Any] = {
        "number": pr_number,
        "merge_sha": merge_commit.sha,
        "merge_commit_sha_from_git": merge_commit.sha,
        "merged_at": merge_commit.committer_date,
        "title": merge_commit.subject,
        "merge_subject": merge_commit.subject,
        "merge_body": merge_commit.body,
        "merge_author_name": merge_commit.author_name,
        "merge_author_email": merge_commit.author_email,
    }
    if branch_first_commit is not None:
        record["first_commit_at"] = branch_first_commit.get("author_date")
        record["first_commit_sha"] = branch_first_commit.get("sha")
        record["last_commit_at"] = (
            branch_first_commit.get("last_author_date")
            or merge_commit.committer_date
        )
    return record


def collect_pr_branch_metadata(
    cwd: Path,
    merge_sha: str,
) -> dict[str, str] | None:
    """Return first/last commit metadata for a PR-merge commit's branch.

    For Formbricks' default squash-merge workflow the merge commit itself
    is the PR's only landing commit on main, with a single parent; the
    branch history is rewritten into that one commit and is therefore
    not recoverable from git alone. This function detects that condition
    via the parent count and returns ``None``.

    For a true two-parent merge commit, ``parents[0]`` is the previous
    main tip (the "base") and ``parents[1]`` is the branch tip; we use
    ``git log <base>..<branch_tip>`` to enumerate the commits that
    landed via the merge and read off the first / last author
    timestamps. The first commit is also returned for inclusion in
    :func:`synthesize_pr_record`.

    Parameters
    ----------
    cwd : pathlib.Path
        The repository root.
    merge_sha : str
        The SHA of the PR-merge commit on main.

    Returns
    -------
    dict[str, str] or None
        ``{"sha": <first>, "author_date": <first_iso>, "last_author_date":
        <last_iso>}`` when branch metadata is recoverable; ``None`` when
        the merge is a squash / fast-forward / rebase-merge with no
        recoverable branch history.
    """

    parents_blob = run_git(
        ["log", "-1", "--format=%P", merge_sha], cwd=cwd, check=False
    )
    parents = parents_blob.split()
    if len(parents) <= 1:
        # Squash-merge, fast-forward, or rebase-merge — branch history is
        # not present in main, so we return None per AAP §0.3.4.
        return None
    base = parents[0]
    branch_tip = parents[1]
    range_arg = f"{base}..{branch_tip}"
    first_out = run_git(
        [
            "log",
            range_arg,
            "--reverse",
            f"--format=%H{FIELD_SEP}%aI",
            "--max-count=1",
        ],
        cwd=cwd,
        check=False,
    ).strip()
    if not first_out or FIELD_SEP not in first_out:
        return None
    first_sha, first_date = first_out.split(FIELD_SEP, 1)
    last_out = run_git(
        ["log", range_arg, "--format=%aI", "--max-count=1"],
        cwd=cwd,
        check=False,
    ).strip()
    return {
        "sha": first_sha,
        "author_date": first_date,
        "last_author_date": last_out or first_date,
    }


# ---------------------------------------------------------------------------
# CLI parser and entry point
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Build and parse the command-line arguments for the extractor.

    Parameters
    ----------
    argv : list[str] or None
        Arguments to parse. ``None`` uses ``sys.argv[1:]``.

    Returns
    -------
    argparse.Namespace
        Parsed arguments with the following attributes:

        ``repo_root`` (:class:`pathlib.Path`)
            Repository root. Defaults to the current directory.
        ``branch`` (str or None)
            Git ref to extract. Defaults to ``refs/remotes/origin/main``
            when present, otherwise ``HEAD``.
        ``output_dir`` (:class:`pathlib.Path`)
            Directory under which the four output artifacts are written.
            Defaults to ``acceleration/data``.
        ``skip_pr_branch_metadata`` (bool)
            When ``True``, the per-PR ``git log base..tip`` branch
            traversal is skipped. Useful for quick smoke tests on very
            large histories.
    """

    parser = argparse.ArgumentParser(
        prog="extract_git",
        description=(
            "Single-pass git history extractor for the development "
            "acceleration analysis pipeline. Emits commits.jsonl, "
            "prs.jsonl, reverts.jsonl, and extract_git_access.json. "
            "Read-only: never writes to the repository under inspection."
        ),
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path("."),
        help="Path to the repository root (default: current directory).",
    )
    parser.add_argument(
        "--branch",
        default=None,
        help=(
            "Git ref to log. Defaults to refs/remotes/origin/main when "
            "present, otherwise HEAD."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("acceleration/data"),
        help=(
            "Directory under which the output artifacts are written "
            "(default: acceleration/data)."
        ),
    )
    parser.add_argument(
        "--skip-pr-branch-metadata",
        action="store_true",
        help=(
            "Skip the per-PR `git log base..tip` traversal that recovers "
            "first/last commit timestamps for true merge commits. Faster "
            "for very large repositories; downstream metrics that require "
            "branch metadata will report exclusion."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run the single-pass git extractor.

    The function performs the following steps:

    1. Parse CLI arguments.
    2. Initialise the structured JSON logger (with a stdlib-logging
       fallback per AAP Rule 1, in the unlikely event that the logger
       module cannot be imported).
    3. Resolve the ref to extract from (``--branch`` or auto-detect).
    4. Compute the upfront environment fingerprint: HEAD SHA, total
       commit count, date range.
    5. Stream the entire git log via :func:`iter_commits`, writing one
       commit record per line to ``commits.jsonl``, one PR record per
       line to ``prs.jsonl`` (when the subject ends in ``(#NNNN)``),
       and one revert record per line to ``reverts.jsonl`` (when the
       commit is classified as a revert).
    6. Emit ``extract_git_access.json`` with run statistics.

    Parameters
    ----------
    argv : list[str] or None
        Arguments to parse. ``None`` uses ``sys.argv[1:]``.

    Returns
    -------
    int
        Process exit code: 0 on success, 2 on unrecoverable extraction
        failure.
    """

    args = parse_args(argv)

    # Configure the structured JSON logger if the module is importable;
    # otherwise fall back to stdlib logging so the operator still sees
    # output even on a broken install (graceful degradation per AAP
    # Observability Rule 1).
    try:
        # The script file lives at acceleration/scripts/extract_git.py;
        # parents[2] is the repository root, which we add to sys.path so
        # ``acceleration.observability.logger`` resolves as a namespace
        # package import without requiring an __init__.py to be present.
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from acceleration.observability.logger import (  # noqa: WPS433
            generate_run_id,
            get_logger,
        )

        run_id = os.environ.get("ACCEL_RUN_ID") or generate_run_id()
        log = get_logger("acceleration.scripts.extract_git", run_id=run_id)
    except Exception:  # pragma: no cover - exercised only on broken installs
        import logging

        logging.basicConfig(
            level=os.environ.get("ACCEL_LOG_LEVEL", "INFO"),
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
        )
        log = logging.getLogger("acceleration.scripts.extract_git")

    repo: Path = args.repo_root.resolve()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    commits_path: Path = args.output_dir / "commits.jsonl"
    prs_path: Path = args.output_dir / "prs.jsonl"
    reverts_path: Path = args.output_dir / "reverts.jsonl"
    tags_path: Path = args.output_dir / "tags.jsonl"
    access_path: Path = args.output_dir / "extract_git_access.json"

    try:
        ref = resolve_branch_ref(repo, args.branch)
    except RuntimeError as exc:
        log.error(
            "Failed to resolve branch ref under %s: %s",
            repo,
            exc,
            extra={"repo_root": str(repo), "branch_arg": args.branch},
        )
        return 2

    log.info(
        "Extracting from %s on ref=%s",
        repo,
        ref,
        extra={"repo_root": str(repo), "ref": ref},
    )
    try:
        head = head_sha(repo)
        total_commits = commit_count(repo, ref)
        first_iso, last_iso = date_range(repo, ref)
    except RuntimeError as exc:
        log.error(
            "Failed to fingerprint the repository: %s",
            exc,
            extra={"repo_root": str(repo), "ref": ref},
        )
        return 2

    log.info(
        "Repository fingerprint: HEAD=%s commit_count=%d date_range=%s..%s",
        head,
        total_commits,
        first_iso,
        last_iso,
        extra={
            "head_sha": head,
            "commit_count": total_commits,
            "first_author_date": first_iso,
            "last_author_date": last_iso,
        },
    )

    commit_count_seen = 0
    pr_count = 0
    revert_count = 0
    ai_signal_count = 0
    unresolved_revert_count = 0

    try:
        with commits_path.open("w", encoding="utf-8") as cf, prs_path.open(
            "w", encoding="utf-8"
        ) as pf, reverts_path.open("w", encoding="utf-8") as rf:
            for commit in iter_commits(repo, ref):
                commit_count_seen += 1

                # Module classification requires per-commit touched files;
                # we skip the lookup for merge commits because their
                # combined diff is typically empty.
                is_merge = len(commit.parents) > 1
                touched: list[str] = []
                if not is_merge:
                    touched = commit_touched_files(repo, commit.sha)
                module, module_counts = classify_commit_modules(touched)

                # AI signal pre-scan (cheap; runs unconditionally).
                ai = detect_ai_signal(commit)
                if ai["is_ai_signal"]:
                    ai_signal_count += 1

                # ---- commits.jsonl row ----
                commit_record: dict[str, Any] = {
                    "sha": commit.sha,
                    "author_name": commit.author_name,
                    "author_email": commit.author_email,
                    "author_date": commit.author_date,
                    "committer_name": commit.committer_name,
                    "committer_email": commit.committer_email,
                    "committer_date": commit.committer_date,
                    "parents": commit.parents,
                    "is_merge": is_merge,
                    "subject": commit.subject,
                    "body": commit.body,
                    "trailers": commit.trailers,
                    "touched_files": touched,
                    "module": module,
                    "module_counts": module_counts,
                    "ai_signal": ai["is_ai_signal"],
                    "ai_indicators": ai["indicators"],
                }
                cf.write(
                    json.dumps(commit_record, ensure_ascii=False, default=str)
                )
                cf.write("\n")

                # ---- prs.jsonl row (if applicable) ----
                is_pr, pr_number = is_pr_merge(commit)
                if is_pr and pr_number is not None:
                    branch_meta: dict[str, str] | None = None
                    if not args.skip_pr_branch_metadata:
                        try:
                            branch_meta = collect_pr_branch_metadata(
                                repo, commit.sha
                            )
                        except RuntimeError as exc:
                            # Non-fatal: record the failure and continue
                            # with branch_meta=None so downstream metrics
                            # see this PR as branch-history-unavailable.
                            log.warning(
                                "Branch metadata lookup failed for PR #%d: %s",
                                pr_number,
                                exc,
                                extra={
                                    "pr_number": pr_number,
                                    "merge_sha": commit.sha,
                                },
                            )
                            branch_meta = None
                    pr_record = synthesize_pr_record(
                        commit, pr_number, branch_meta
                    )
                    pr_record["module"] = module
                    pr_record["module_counts"] = module_counts
                    pr_record["ai_signal"] = ai["is_ai_signal"]
                    pr_record["ai_indicators"] = ai["indicators"]
                    pf.write(
                        json.dumps(pr_record, ensure_ascii=False, default=str)
                    )
                    pf.write("\n")
                    pr_count += 1

                # ---- reverts.jsonl row (if applicable) ----
                try:
                    revert_record = classify_revert(repo, commit)
                except RuntimeError as exc:
                    log.warning(
                        "Revert classification failed for %s: %s",
                        commit.sha,
                        exc,
                        extra={"sha": commit.sha},
                    )
                    revert_record = None
                if revert_record is not None:
                    rf.write(
                        json.dumps(
                            revert_record, ensure_ascii=False, default=str
                        )
                    )
                    rf.write("\n")
                    revert_count += 1
                    if revert_record["original_resolution"] == "unresolved":
                        unresolved_revert_count += 1

                # Periodic progress logging — every 500 commits — so an
                # operator running this against a 5,000+ commit history
                # can observe forward progress without enabling DEBUG.
                if commit_count_seen % 500 == 0:
                    log.info(
                        "...processed %d commits",
                        commit_count_seen,
                        extra={
                            "commits_processed": commit_count_seen,
                            "prs_processed": pr_count,
                            "reverts_processed": revert_count,
                        },
                    )
    except RuntimeError as exc:
        log.error(
            "Extraction failed: %s",
            exc,
            extra={"repo_root": str(repo), "ref": ref},
        )
        return 2
    except OSError as exc:
        log.error(
            "I/O error during extraction: %s",
            exc,
            extra={"output_dir": str(args.output_dir)},
        )
        return 2

    # ---- tags.jsonl ----
    # Emit annotated git tags so ``compute_metrics.py`` can use them as the
    # secondary release source per AAP §0.1.3 (release source precedence:
    # GitHub Releases → annotated semver tags → deployment events). The
    # Formbricks repository has zero tags today, but the extractor must
    # produce a deterministic, schema-stable artifact regardless. Failure
    # to enumerate tags is non-fatal: ``compute_metrics.py`` already
    # tolerates a missing or empty ``tags.jsonl``.
    tag_record_count = 0
    tag_annotated_count = 0
    tag_semver_count = 0
    tag_prerelease_count = 0
    try:
        with tags_path.open("w", encoding="utf-8") as tf:
            for tag_record in iter_tags(repo):
                tf.write(
                    json.dumps(tag_record, ensure_ascii=False, default=str)
                )
                tf.write("\n")
                tag_record_count += 1
                if tag_record.get("is_annotated"):
                    tag_annotated_count += 1
                if tag_record.get("is_semver"):
                    tag_semver_count += 1
                if tag_record.get("is_prerelease"):
                    tag_prerelease_count += 1
    except OSError as exc:
        log.error(
            "Failed to write tags.jsonl: %s",
            exc,
            extra={"tags_path": str(tags_path)},
        )
        return 2
    except RuntimeError as exc:
        # Non-fatal: log a warning and write an empty tags.jsonl so the
        # downstream metric computation degrades cleanly to "GitHub
        # Releases only" rather than crashing.
        log.warning(
            "git for-each-ref failed: %s — tags.jsonl will be empty",
            exc,
            extra={"repo_root": str(repo)},
        )
        try:
            tags_path.write_text("", encoding="utf-8")
        except OSError as os_exc:
            # If we cannot even write an empty placeholder, surface the
            # condition through the logger so the orchestrator can see it.
            # The previous implementation swallowed this via bare ``pass``,
            # which violated Checkpoint 3's no-pass-in-cleanup rule.
            log.debug(
                "Failed to write empty tags.jsonl fallback: %s",
                os_exc,
                extra={"tags_path": str(tags_path)},
            )

    access_manifest: dict[str, Any] = {
        "extracted_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "repo_root": str(repo),
        "ref": ref,
        "head_sha": head,
        "commit_count_reported_by_rev_list": total_commits,
        "commit_count_seen_in_stream": commit_count_seen,
        "first_author_date": first_iso,
        "last_author_date": last_iso,
        "pr_merge_count": pr_count,
        "revert_count": revert_count,
        "unresolved_revert_count": unresolved_revert_count,
        "ai_signal_count": ai_signal_count,
        "tag_record_count": tag_record_count,
        "tag_annotated_count": tag_annotated_count,
        "tag_semver_count": tag_semver_count,
        "tag_prerelease_count": tag_prerelease_count,
        "skip_pr_branch_metadata": bool(args.skip_pr_branch_metadata),
        "output_files": {
            "commits": str(commits_path),
            "prs": str(prs_path),
            "reverts": str(reverts_path),
            "tags": str(tags_path),
        },
    }
    try:
        access_path.write_text(
            json.dumps(access_manifest, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError as exc:
        log.error(
            "Failed to write access manifest: %s",
            exc,
            extra={"access_path": str(access_path)},
        )
        return 2

    log.info(
        "Extraction complete: %d commits, %d PRs, %d reverts (%d unresolved), "
        "%d tags (%d annotated, %d semver, %d prerelease), "
        "%d AI-signal commits",
        commit_count_seen,
        pr_count,
        revert_count,
        unresolved_revert_count,
        tag_record_count,
        tag_annotated_count,
        tag_semver_count,
        tag_prerelease_count,
        ai_signal_count,
        extra={
            "commits": commit_count_seen,
            "prs": pr_count,
            "reverts": revert_count,
            "reverts_unresolved": unresolved_revert_count,
            "tags": tag_record_count,
            "tags_annotated": tag_annotated_count,
            "tags_semver": tag_semver_count,
            "tags_prerelease": tag_prerelease_count,
            "ai_signal_commits": ai_signal_count,
        },
    )
    return 0


# Re-export ``Iterable`` so static analysers see it as used. ``Iterable`` is
# imported alongside ``Iterator`` per the schema; it documents the intended
# parameter type for any helper a future maintainer may add that takes a
# pre-collected list of CommitFields rather than a fresh generator.
__all__ = [
    "AI_AUTHOR_EMAILS",
    "AI_TRAILER_PATTERNS",
    "CommitFields",
    "FIELD_SEP",
    "GIT_LOG_FORMAT",
    "Iterable",
    "MODULE_PREFIXES",
    "PRERELEASE_TOKENS",
    "PR_NUMBER_RE",
    "RECORD_SEP",
    "REVERT_SUBJECT_RE",
    "REVERTS_COMMIT_RE",
    "ALT_REVERTS_RE",
    "SEMVER_TAG_RE",
    "classify_commit_modules",
    "classify_revert",
    "collect_pr_branch_metadata",
    "commit_count",
    "commit_touched_files",
    "date_range",
    "detect_ai_signal",
    "extract_pr_number",
    "find_revert_sha_in_message",
    "head_sha",
    "is_pr_merge",
    "is_prerelease_tag",
    "iter_commits",
    "iter_tags",
    "main",
    "module_for_path",
    "parse_args",
    "parse_trailers",
    "resolve_branch_ref",
    "run_git",
    "synthesize_pr_record",
    "tree_match_revert_target",
]


if __name__ == "__main__":
    sys.exit(main())
