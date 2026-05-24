#!/usr/bin/env python3
"""
acceleration.scripts.classify_prs
=================================

PR work-type classifier for the Development Acceleration Analysis pipeline.

Annotates every record in ``acceleration/data/prs.jsonl`` with two new
fields, ``work_type`` and ``classification_source``, and rewrites the
JSONL atomically in place. The classifier feeds Metric 6 (Flow
Distribution) downstream in ``compute_metrics.py``.

Priority order (AAP §0.3.4)
---------------------------

For each PR record, the four classification strategies below are
tried in strict order; the first to produce a non-``None`` result
wins. This priority is deliberate: explicit human triage on linked
issues is the highest-fidelity signal, followed by author-asserted
PR-title prefix (enforced by ``.github/workflows/semantic-pull-requests.yml``),
followed by heuristic keyword matching, with an ``unknown`` fallback.

1. **Linked-issue labels** — scan the PR title + body for
   ``Fixes #N`` / ``Closes #N`` / ``Resolves #N`` references; look
   up each referenced issue in ``issues.jsonl``; map the resolved
   issue's labels through :data:`ISSUE_LABEL_TO_WORK_TYPE`. The
   body source is ``pr["body"]`` (API-derived, populated by
   ``extract_github.py``) when available, falling back to
   ``pr["merge_body"]`` (git-derived, populated by
   ``extract_git.py``) so the path remains functional in the
   AAP §0.8.2 graceful-degradation codepath where no
   ``GITHUB_TOKEN`` is supplied.

2. **PR-title conventional-commit prefix** — match the leading
   ``type:`` / ``type(scope):`` token against
   :data:`CONVENTIONAL_TO_WORK_TYPE`. The 12 accepted types are
   the ones enforced by the ``amannn/action-semantic-pull-request``
   workflow on this repository: ``fix``, ``feat``, ``chore``,
   ``docs``, ``style``, ``refactor``, ``perf``, ``test``, ``build``,
   ``ci``, ``revert``, ``ossgg``. ``security`` is recognised
   additionally because AAP §0.3.4 names it explicitly even though
   the workflow does not enforce it.

3. **Keyword match** — case-insensitive word-boundary regex
   matching against the concatenated PR title + body using
   :data:`KEYWORD_TO_WORK_TYPE`. The body source uses the same
   ``pr["body"]`` → ``pr["merge_body"]`` preference order as
   priority-1 so this path also stays functional in the AAP §0.8.2
   graceful-degradation codepath. Patterns are intentionally
   conservative (e.g. ``\\bfix(?:ing|ed|es)?\\b`` rather than the
   bare token ``fix``) to avoid matching arbitrary code-fragment
   substrings or commit-message stems that happened to land in a
   PR body's diff excerpt.

4. **Unknown** — the fallback when no strategy fired.
   ``compute_metrics.py`` enforces the AAP §0.3.4 confidence rule
   that downgrades Metric 6 to ``Low`` when the unknown rate
   exceeds 20%; this script logs a warning at the same threshold
   so the operator notices before the metric is rendered.

Authority
---------

- AAP §0.4.1 — enumerates ``acceleration/scripts/classify_prs.py``
  as a CREATE target.
- AAP §0.3.2.2 — *"PR Classifier (``acceleration/scripts/classify_prs.py``)
  — implements the Metric 6 priority order (linked-issue labels →
  PR-title conventional prefix → keyword match → unknown);
  rationale: classification logic is non-trivial and worth isolating
  from extraction."*
- AAP §0.3.4 — Flow Distribution classification priority order
  and the > 20% unknown-rate confidence-downgrade rule.
- AAP §0.7.2.4 — Quality gate: *"All 12 metrics populated or marked
  'Insufficient signal — [reason]' with deviation documented."*
- Source: ``.github/workflows/semantic-pull-requests.yml`` — the
  authoritative set of permitted PR-title prefixes on this
  repository.
- Source: ``.github/ISSUE_TEMPLATE/bug_report.yml`` — applies the
  ``bug`` label automatically, which is the primary signal for the
  ``defect`` mapping in :data:`ISSUE_LABEL_TO_WORK_TYPE`.
- Source: ``.github/ISSUE_TEMPLATE/feature_request.yml`` — supplies
  the ``feature`` issue type, justifying the ``feature`` /
  ``enhancement`` / ``feat`` entries in :data:`ISSUE_LABEL_TO_WORK_TYPE`.

Read-only discipline (AAP §0.7.2.1, §0.8.7, §0.8.8)
---------------------------------------------------

- Reads: ``acceleration/data/prs.jsonl`` and
  ``acceleration/data/issues.jsonl``.
- Writes: exactly one file — ``acceleration/data/prs.jsonl`` —
  in-place via atomic ``temp file + Path.replace`` rename so a
  crashed run never leaves a half-written PR list on disk.
- No network access, no ``git`` invocation, no ``gh`` invocation.

Stdlib-only by design (AAP §0.6.1, §0.8.8). The module loads on a
clean Python 3.10+ installation without ``pip install``.

Invocation
----------

.. code-block:: bash

    # Default run (paths default to acceleration/data/):
    python3 acceleration/scripts/classify_prs.py

    # Stat summary printed to stdout in addition to the structured log:
    python3 acceleration/scripts/classify_prs.py --report-stats

    # Override paths (useful in tests):
    python3 acceleration/scripts/classify_prs.py \\
        --prs path/to/prs.jsonl \\
        --issues path/to/issues.jsonl

Integration with the pipeline
-----------------------------

- Runs AFTER ``extract_github.py`` (which produces ``prs.jsonl``)
  and ``extract_issues.py`` (which produces ``issues.jsonl``).
- Runs BEFORE ``compute_metrics.py`` (which reads the annotated
  ``prs.jsonl`` for Metric 6).
- The canonical ordering is encoded in
  ``run_acceleration_analysis.py``.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Public constants
# ---------------------------------------------------------------------------

# AAP §0.3.4 — Conventional-commit prefix → work_type mapping.
#
# The 12 accepted types are enforced verbatim by
# ``.github/workflows/semantic-pull-requests.yml`` (the
# ``amannn/action-semantic-pull-request`` ``types:`` list). The 13th
# entry, ``security``, is recognised additionally because AAP §0.3.4
# names it explicitly in the priority order even though the workflow
# does not enforce it — the absence of enforcement does not preclude
# its presence in a historical PR title.
#
# Mapping rationale:
#
# - ``feat`` → ``feature``: the conventional-commits literal for new
#   product capability.
# - ``fix`` → ``defect``: a PR titled ``fix:`` is, by convention, a
#   defect repair.
# - ``revert`` → ``defect``: a revert is the rollback half of a
#   broken-change event and counts as defect work for Metric 6
#   (this matches the Flow Framework's classification of unplanned
#   work).
# - ``security`` → ``risk_compliance``: explicit governance / risk
#   work per AAP §0.3.4.
# - ``chore``, ``docs``, ``style``, ``refactor``, ``perf``, ``test``,
#   ``build``, ``ci``, ``ossgg`` → ``tech_debt``: these are
#   maintenance / infrastructure / quality-improvement categories
#   that do not introduce new product capability and are not defect
#   repairs. They are aggregated under ``tech_debt`` so Metric 6's
#   four-bucket distribution (feature / defect / risk_compliance /
#   tech_debt) remains stable.
# - ``ossgg``: a Formbricks-specific prefix observed in the
#   ``types:`` list of ``semantic-pull-requests.yml`` for the
#   "OSS Gathering" administrative track; bucketed as
#   ``tech_debt`` because the work it covers is typically
#   organisational rather than product-feature.
CONVENTIONAL_TO_WORK_TYPE: dict[str, str] = {
    "feat":     "feature",
    "fix":      "defect",
    "chore":    "tech_debt",
    "docs":     "tech_debt",
    "style":    "tech_debt",
    "refactor": "tech_debt",
    "perf":     "tech_debt",
    "test":     "tech_debt",
    "build":    "tech_debt",
    "ci":       "tech_debt",
    "revert":   "defect",
    "security": "risk_compliance",
    "ossgg":    "tech_debt",  # observed in semantic-pull-requests.yml types: list
}

# AAP §0.3.4 — Linked-issue label → work_type mapping.
#
# Iteration order matters: Python 3.7+ guarantees insertion order on
# ``dict``, and :func:`classify_by_linked_issues` walks this mapping
# top-to-bottom and returns the first hit. The order below puts the
# most-specific bucket-defining labels (``feat``, ``bug``,
# ``security``) first so a PR that links to an issue carrying both
# ``bug`` and ``docs`` is classified as ``defect`` rather than
# ``tech_debt``.
#
# Both ``feat`` and ``feature`` are recognised because
# ``feature_request.yml`` declares ``type: feature`` while many
# repositories also use the conventional-commits-style ``feat``
# label. ``bug`` is the auto-applied label from
# ``bug_report.yml``. ``tech-debt`` (kebab-case) is the common
# GitHub label form; ``tech_debt`` (snake_case) is recognised for
# parity with the output value so a label that mirrors the work-type
# name is not mis-classified.
ISSUE_LABEL_TO_WORK_TYPE: dict[str, str] = {
    "feat":          "feature",
    "feature":       "feature",
    "enhancement":   "feature",
    "bug":           "defect",
    "regression":    "defect",
    "incident":      "defect",
    "defect":        "defect",
    "security":      "risk_compliance",
    "compliance":    "risk_compliance",
    "vulnerability": "risk_compliance",
    "chore":         "tech_debt",
    "refactor":      "tech_debt",
    "tech-debt":     "tech_debt",
    "tech_debt":     "tech_debt",
    "performance":   "tech_debt",
    "docs":          "tech_debt",
    "documentation": "tech_debt",
}

# AAP §0.3.4 — Keyword matching against PR title + body.
#
# Iteration order matters here too: the first ``(work_type,
# patterns)`` pair to produce any regex match wins. Patterns inside
# a single tuple are tried left-to-right and the first match within
# them also wins. The four buckets mirror the Metric 6 output set.
#
# Pattern-construction principles:
#
# - All patterns use ``\\b`` word-boundary anchors so a keyword
#   nested inside an identifier or filename does not produce a
#   false positive (e.g. ``\\bbug\\b`` will not match
#   ``debugger`` or ``snapbug.ts``).
# - Verb conjugations are folded into a single pattern with
#   non-capturing alternation
#   (``\\bfix(?:ing|ed|es)?\\b`` covers fix, fixing, fixed, fixes).
# - All matching is performed against a lower-cased copy of the
#   text (see :func:`classify_by_keyword`), so the patterns
#   themselves do not need to repeat lower-case alternatives; the
#   acronyms ``CVE`` / ``GDPR`` / ``SOC 2`` are written in
#   upper-case here purely for human readability.
KEYWORD_TO_WORK_TYPE: list[tuple[str, tuple[str, ...]]] = [
    (
        "feature",
        (
            r"\bfeature\b",
            r"\bnew capability\b",
            r"\bnew endpoint\b",
            r"\bintroduce\b",
        ),
    ),
    (
        "defect",
        (
            r"\bbug\b",
            r"\bregression\b",
            r"\bcrash\b",
            r"\bcrashes\b",
            r"\bincorrect\b",
            r"\bfix(?:ing|ed|es)?\b",
        ),
    ),
    (
        "risk_compliance",
        (
            r"\bsecurity\b",
            r"\bvulnerability\b",
            r"\bcve\b",
            r"\bgdpr\b",
            r"\bcompliance\b",
            r"\bsoc[\s-]?2\b",
        ),
    ),
    (
        "tech_debt",
        (
            r"\brefactor\b",
            r"\bcleanup\b",
            r"\bclean[- ]up\b",
            r"\btech debt\b",
            r"\bmigrate\b",
            r"\bdocs\b",
            r"\bdependencies\b",
        ),
    ),
]

# Regex: linked-issue references.
#
# Matches the GitHub-recognised "closes-issue" verbs (``Fix`` /
# ``Fixes`` / ``Fixed`` / ``Close`` / ``Closes`` / ``Closed`` /
# ``Resolve`` / ``Resolves`` / ``Resolved``) followed by ``#N`` with
# optional whitespace between the verb and the hash. The match is
# case-insensitive (``re.IGNORECASE``); the captured group ``\\1`` is
# the numeric issue ID.
#
# AAP §0.3.4 names ``Fixes #N`` / ``Closes #N`` explicitly; the
# additional verb conjugations (``Resolves``, ``Closed``, etc.) are
# included because GitHub's own "issue closing keywords"
# documentation accepts them and the Formbricks PR corpus contains
# instances of each.
LINKED_ISSUE_RE: re.Pattern[str] = re.compile(
    r"\b(?:fix(?:es|ed)?|close[sd]?|resolve[sd]?)\s+#(\d+)\b",
    re.IGNORECASE,
)

# Regex: conventional-commit prefix on PR title.
#
# Matches the leading ``type:`` / ``type(scope):`` token on a PR
# title. The captured group ``\\1`` is the bare type (without the
# scope and without the trailing colon). The pattern is anchored to
# the start of the string with ``^``; callers must pass a
# pre-stripped title or call ``.strip()`` first.
#
# Examples that match (capture in parentheses):
#
# - ``"feat: add survey templates"``         → ``(feat)``
# - ``"fix(database): handle null row"``      → ``(fix)``
# - ``"chore(ci): bump action versions"``     → ``(chore)``
#
# Examples that do not match:
#
# - ``"Add survey templates"``  (no colon, no prefix)
# - ``"WIP: experimental"``     (the captured token ``WIP`` is not
#                                in :data:`CONVENTIONAL_TO_WORK_TYPE`,
#                                so the second-priority strategy
#                                returns ``None`` and the keyword
#                                strategy is tried next)
CONVENTIONAL_PREFIX_RE: re.Pattern[str] = re.compile(r"^(\w+)(?:\([^)]*\))?:")


# ---------------------------------------------------------------------------
# JSONL I/O helpers
# ---------------------------------------------------------------------------


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    """Read a JSONL file and return one ``dict`` per non-empty line.

    Missing files yield an empty list (not an exception). Malformed
    lines are silently skipped so a single corrupted record from an
    upstream extractor does not abort the entire classification run.

    The function never raises for routine input problems; reading
    from a path that is not a regular file (e.g. a directory) is the
    one case where :class:`OSError` may propagate, but that is a
    pipeline-setup defect rather than a data defect and is left to
    the caller to surface.

    Parameters
    ----------
    path : Path
        The JSONL file to read.

    Returns
    -------
    list[dict[str, Any]]
        Parsed records in source-file order. Empty list when the
        file does not exist or contains only blank lines.
    """

    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                out.append(json.loads(stripped))
            except json.JSONDecodeError:
                # Skip malformed lines rather than abort the entire
                # classification pass — a single corrupted record from
                # an upstream extractor should not block annotation of
                # the other 99.9% of records.
                continue
    return out


def write_jsonl_atomic(path: Path, records: list[dict[str, Any]]) -> None:
    """Rewrite ``path`` from ``records`` atomically.

    The write is staged through a sibling temp file
    (``path.suffix + ".tmp"``) and then promoted via
    :meth:`Path.replace`, which is an atomic rename on POSIX and an
    atomic ``MoveFileEx`` on Windows. A crashed or signalled run
    therefore leaves either the original file or the new file fully
    intact — never a half-written hybrid.

    ``json.dumps`` is invoked with ``ensure_ascii=False`` so that
    non-ASCII characters in PR titles (the Formbricks corpus contains
    German and other Latin-1-extended characters) are preserved
    rather than escaped, and ``default=str`` so that any
    non-JSON-native value an upstream extractor may have injected
    (e.g. a ``datetime``) is coerced to its string form rather than
    raising :class:`TypeError`.

    Parameters
    ----------
    path : Path
        The destination JSONL path. Must be writable and reside in a
        directory the current process owns.
    records : list[dict[str, Any]]
        The records to serialise, one per output line, in iteration
        order.
    """

    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False, default=str))
            f.write("\n")
    tmp.replace(path)


def index_issues_by_number(
    issues: list[dict[str, Any]],
) -> dict[int, dict[str, Any]]:
    """Build an ``{issue_number: issue}`` lookup table.

    Records missing the ``number`` key are silently dropped; records
    whose ``number`` is not coercible to ``int`` are silently dropped
    via the surrounding ``try``/``except`` so a corrupted upstream
    file cannot abort the entire pipeline.

    Parameters
    ----------
    issues : list[dict[str, Any]]
        Issue records as produced by ``extract_issues.py``.

    Returns
    -------
    dict[int, dict[str, Any]]
        Map from integer issue number to the originating record.
        Later-occurring duplicates overwrite earlier ones.
    """

    indexed: dict[int, dict[str, Any]] = {}
    for issue in issues:
        if "number" not in issue:
            continue
        try:
            number = int(issue["number"])
        except (TypeError, ValueError):
            # An upstream extractor that occasionally writes a null or
            # non-numeric ``number`` field should not crash this pass.
            continue
        indexed[number] = issue
    return indexed


# ---------------------------------------------------------------------------
# Per-PR classification (priority order)
# ---------------------------------------------------------------------------


def extract_linked_issue_numbers(pr_body_and_title: str) -> list[int]:
    """Return every issue number referenced by a closes-issue keyword.

    Scans ``pr_body_and_title`` using :data:`LINKED_ISSUE_RE` and
    extracts the captured integer from each match. Duplicates are
    preserved in source order so callers that care about
    multiplicity see it; callers that want a unique set can wrap the
    return value in :class:`set`.

    Parameters
    ----------
    pr_body_and_title : str
        Concatenated PR title + body. May be empty.

    Returns
    -------
    list[int]
        Issue numbers in source order. Empty when no references are
        present or ``pr_body_and_title`` is empty.
    """

    return [int(match.group(1)) for match in LINKED_ISSUE_RE.finditer(pr_body_and_title)]


def classify_by_linked_issues(
    pr: dict[str, Any],
    issues_by_number: dict[int, dict[str, Any]],
) -> tuple[str | None, str | None]:
    """Try to classify ``pr`` from the labels on the issues it closes.

    Algorithm:

    1. Concatenate the PR's title and body.
    2. Extract every linked issue number via
       :func:`extract_linked_issue_numbers`.
    3. Look up each issue in ``issues_by_number``; collect the union
       of every resolved issue's labels (lower-cased).
    4. Walk :data:`ISSUE_LABEL_TO_WORK_TYPE` in declaration order;
       return the first label that appears in the collected set.

    Iteration over the mapping (not over the label set) makes the
    priority deterministic: a PR linked to both a ``bug``-labelled
    issue and a ``docs``-labelled issue will always classify as
    ``defect`` because ``bug`` precedes ``docs`` in the mapping.

    Parameters
    ----------
    pr : dict[str, Any]
        A PR record from ``prs.jsonl``. Must contain at least the
        ``title`` field; the description body is read from ``body``
        when present, with ``merge_body`` (the body of the
        squash-merge commit message produced by ``extract_git.py``)
        used as a fallback. Either source may be ``None``. The
        ``body`` field takes precedence because, when populated by
        ``extract_github.py``, it carries the API-fetched PR
        description, which is the highest-fidelity signal. The
        ``merge_body`` fallback preserves priority-1 classification
        in the graceful-degradation codepath (AAP §0.8.2) where no
        ``GITHUB_TOKEN`` is supplied and ``extract_github.py`` is
        skipped, so only the git-derived squash-merge body is
        available — that body still carries the ``Fixes #N`` /
        ``Closes #N`` references that priority-1 keys on.
    issues_by_number : dict[int, dict[str, Any]]
        Lookup table from :func:`index_issues_by_number`.

    Returns
    -------
    tuple[str | None, str | None]
        ``(work_type, classification_source)`` on a hit, or
        ``(None, None)`` when no linked issue was found, no
        referenced issue resolved to a known record, or none of the
        resolved labels matched a mapping entry.
    """

    # AAP §0.8.2 graceful-degradation: prefer the API-derived ``body``
    # when available (highest fidelity, populated by extract_github.py),
    # but fall back to the git-derived ``merge_body`` so the priority-1
    # path remains functional when ``GITHUB_TOKEN`` is unavailable and
    # only ``extract_git.py`` has run. The ``or`` short-circuits as
    # soon as a non-empty source is found, preserving API primacy.
    text = " ".join(
        [
            pr.get("title") or "",
            pr.get("body") or pr.get("merge_body") or "",
        ]
    )
    issue_numbers = extract_linked_issue_numbers(text)
    if not issue_numbers:
        return None, None
    labels_collected: set[str] = set()
    for number in issue_numbers:
        issue = issues_by_number.get(number)
        if issue is None:
            continue
        for label in issue.get("labels") or []:
            if isinstance(label, str):
                labels_collected.add(label.lower())
    if not labels_collected:
        return None, None
    for label, work_type in ISSUE_LABEL_TO_WORK_TYPE.items():
        if label in labels_collected:
            return work_type, f"linked-issue label '{label}'"
    return None, None


def classify_by_pr_title_prefix(
    pr: dict[str, Any],
) -> tuple[str | None, str | None]:
    """Try to classify ``pr`` from its conventional-commits prefix.

    The PR title is stripped of leading/trailing whitespace and then
    matched against :data:`CONVENTIONAL_PREFIX_RE`. The captured
    type (without scope, without the trailing colon) is lower-cased
    and looked up in :data:`CONVENTIONAL_TO_WORK_TYPE`. A captured
    type not in the mapping (e.g. ``"wip"``) results in
    ``(None, None)`` so the next strategy in the priority order can
    run.

    Parameters
    ----------
    pr : dict[str, Any]
        A PR record from ``prs.jsonl``. The ``title`` key may be
        ``None`` or missing.

    Returns
    -------
    tuple[str | None, str | None]
        ``(work_type, classification_source)`` on a hit, or
        ``(None, None)`` when the title does not start with a
        recognised conventional-commits prefix.
    """

    title = pr.get("title") or ""
    match = CONVENTIONAL_PREFIX_RE.match(title.strip())
    if not match:
        return None, None
    prefix = match.group(1).lower()
    work_type = CONVENTIONAL_TO_WORK_TYPE.get(prefix)
    if work_type is None:
        return None, None
    return work_type, f"conventional-commit prefix '{prefix}:'"


def classify_by_keyword(pr: dict[str, Any]) -> tuple[str | None, str | None]:
    """Try to classify ``pr`` from keyword matches on its title + body.

    The PR's title and body are concatenated and lower-cased once;
    every regex in :data:`KEYWORD_TO_WORK_TYPE` is then matched
    against the resulting string. The first ``(work_type, pattern)``
    pair to produce a match wins. Walking the list rather than a
    dict keeps the priority deterministic and easy to audit.

    Parameters
    ----------
    pr : dict[str, Any]
        A PR record from ``prs.jsonl``. Both the ``title`` and the
        body source (``body``, falling back to ``merge_body``) may be
        ``None`` or missing. The ``body`` field is preferred when
        populated by ``extract_github.py`` (API-derived PR
        description); ``merge_body`` (the squash-merge commit
        message produced by ``extract_git.py``) is the
        graceful-degradation fallback per AAP §0.8.2 so this
        keyword-matching path stays functional when no
        ``GITHUB_TOKEN`` is supplied.

    Returns
    -------
    tuple[str | None, str | None]
        ``(work_type, classification_source)`` on a hit, or
        ``(None, None)`` when no keyword matched.
    """

    # Same body source-preference order as :func:`classify_by_linked_issues`:
    # API-derived ``body`` first (highest fidelity), git-derived
    # ``merge_body`` as the graceful-degradation fallback (AAP §0.8.2).
    text = " ".join(
        [
            pr.get("title") or "",
            pr.get("body") or pr.get("merge_body") or "",
        ]
    )
    text_lower = text.lower()
    for work_type, patterns in KEYWORD_TO_WORK_TYPE:
        for pattern in patterns:
            if re.search(pattern, text_lower):
                return work_type, f"keyword match: {pattern}"
    return None, None


def classify_pr(
    pr: dict[str, Any],
    issues_by_number: dict[int, dict[str, Any]],
) -> tuple[str, str]:
    """Apply the four-step priority order to a single PR.

    Strategies are tried in this order:

    1. :func:`classify_by_linked_issues`
    2. :func:`classify_by_pr_title_prefix`
    3. :func:`classify_by_keyword`

    The first strategy whose return tuple is not ``(None, None)``
    wins. When all three return ``(None, None)``, the result is
    ``("unknown", "no classification matched")`` — a sentinel value
    that ``compute_metrics.py`` uses to enforce the AAP §0.3.4
    > 20%-unknown-rate confidence downgrade rule for Metric 6.

    Parameters
    ----------
    pr : dict[str, Any]
        A PR record from ``prs.jsonl``.
    issues_by_number : dict[int, dict[str, Any]]
        Lookup table from :func:`index_issues_by_number`.

    Returns
    -------
    tuple[str, str]
        ``(work_type, classification_source)``. ``work_type`` is one
        of ``feature`` / ``defect`` / ``risk_compliance`` /
        ``tech_debt`` / ``unknown``. ``classification_source`` is a
        human-readable string identifying which strategy fired and,
        where applicable, the matched label / prefix / pattern.
    """

    # Each strategy is wrapped in a zero-arg lambda so the priority
    # order is expressed as data and the evaluation is short-circuit:
    # the loop stops as soon as a non-``(None, None)`` result is
    # returned.
    strategies = (
        lambda: classify_by_linked_issues(pr, issues_by_number),
        lambda: classify_by_pr_title_prefix(pr),
        lambda: classify_by_keyword(pr),
    )
    for strategy in strategies:
        work_type, source = strategy()
        if work_type is not None and source is not None:
            return work_type, source
    return "unknown", "no classification matched"


# ---------------------------------------------------------------------------
# Argparse and main entrypoint
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the script's command-line arguments.

    The function is a public API (re-exported via the schema) so the
    orchestrator's integration tests can drive it without spawning a
    subprocess.

    Parameters
    ----------
    argv : list[str] or None
        The argument vector excluding the program name. ``None`` (the
        default) instructs :mod:`argparse` to read :data:`sys.argv`.

    Returns
    -------
    argparse.Namespace
        Parsed arguments with the following fields:

        ``prs`` — :class:`Path` to the PRs JSONL file. Default:
        ``acceleration/data/prs.jsonl``.

        ``issues`` — :class:`Path` to the issues JSONL file.
        Default: ``acceleration/data/issues.jsonl``.

        ``report_stats`` — ``bool``. When set, the script also
        prints a JSON object summarising the classification counts,
        source breakdown, and unknown rate to stdout AFTER the
        structured log lines.
    """

    parser = argparse.ArgumentParser(
        description=(
            "Annotate prs.jsonl with work_type using the four-step priority "
            "order (linked-issue labels → PR-title prefix → keyword → unknown)."
        ),
    )
    parser.add_argument(
        "--prs",
        type=Path,
        default=Path("acceleration/data/prs.jsonl"),
        help=(
            "Path to the PRs JSONL produced by extract_github.py "
            "(default: acceleration/data/prs.jsonl)."
        ),
    )
    parser.add_argument(
        "--issues",
        type=Path,
        default=Path("acceleration/data/issues.jsonl"),
        help=(
            "Path to the issues JSONL produced by extract_issues.py "
            "(default: acceleration/data/issues.jsonl)."
        ),
    )
    parser.add_argument(
        "--report-stats",
        action="store_true",
        help=(
            "After writing the annotated prs.jsonl, print a JSON summary "
            "of classification counts, source breakdown, and unknown rate "
            "to stdout."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Read PRs + issues, classify, and atomically rewrite PRs.

    The function never raises for routine data problems. Empty inputs
    return ``0`` with a log line describing the absence; malformed
    individual records are silently skipped by :func:`load_jsonl`.

    Logger configuration is best-effort: the script tries to import
    the canonical structured JSON logger via a deferred import that
    extends ``sys.path`` to the repository root, and falls back to
    stdlib :mod:`logging` (configured via ``logging.basicConfig``)
    when the import fails for any reason. Either way the script
    remains runnable.

    Parameters
    ----------
    argv : list[str] or None
        The argument vector excluding the program name. ``None`` (the
        default) instructs :func:`parse_args` to read
        :data:`sys.argv`.

    Returns
    -------
    int
        ``0`` always. Non-zero return codes are intentionally avoided
        so the orchestrator can decide whether an empty
        classification (no PRs to classify) is acceptable for the
        run as a whole.
    """

    args = parse_args(argv)

    # Configure the structured JSON logger if the module is
    # importable; otherwise fall back to stdlib logging so the
    # operator still sees output even on a broken install. The
    # try/except guards the import to satisfy AAP Rule 1
    # (Observability) graceful degradation under any working
    # directory.
    try:
        # The script lives at acceleration/scripts/classify_prs.py;
        # parents[2] is the repository root, which we add to
        # ``sys.path`` so the namespace package import resolves
        # without requiring an ``__init__.py``.
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from acceleration.observability.logger import (  # noqa: WPS433
            generate_run_id,
            get_logger,
        )

        run_id = os.environ.get("ACCEL_RUN_ID") or generate_run_id()
        log = get_logger("acceleration.scripts.classify_prs", run_id=run_id)
    except Exception:  # pragma: no cover - exercised only on broken installs
        # ``logging`` is imported lazily here so a clean import of
        # this module does not pull in the stdlib ``logging`` module
        # unless the deferred import above failed. The ``basicConfig``
        # call honours ``ACCEL_LOG_LEVEL`` for parity with the
        # canonical logger.
        import logging

        logging.basicConfig(
            level=os.environ.get("ACCEL_LOG_LEVEL", "INFO"),
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
        )
        log = logging.getLogger("acceleration.scripts.classify_prs")

    log.info("Loading PRs from %s", args.prs)
    prs = load_jsonl(args.prs)
    if not prs:
        # The orchestrator may run this script in --skip-network mode
        # or against a clean ``acceleration/data/`` directory where
        # ``extract_github.py`` was unable to retrieve any PRs. The
        # right behaviour is to exit cleanly so downstream
        # ``compute_metrics.py`` can mark Metric 6 as ``Insufficient
        # signal — no PRs to classify`` per AAP §0.3.4 / §0.8.2.
        log.warning(
            "No PR records found in %s; skipping classification "
            "(Metric 6 will be marked as insufficient signal downstream).",
            args.prs,
        )
        return 0

    log.info("Loading issues from %s", args.issues)
    issues = load_jsonl(args.issues)
    issues_by_number = index_issues_by_number(issues)
    log.info(
        "Classifying %d PRs using %d linkable issues",
        len(prs),
        len(issues_by_number),
    )

    counts: dict[str, int] = {}
    source_counts: dict[str, int] = {}
    for pr in prs:
        work_type, source = classify_pr(pr, issues_by_number)
        pr["work_type"] = work_type
        pr["classification_source"] = source
        counts[work_type] = counts.get(work_type, 0) + 1
        # The source string is bucketed by its leading token so the
        # per-strategy distribution stays compact in the summary
        # (e.g. all keyword matches roll up under ``keyword`` rather
        # than producing one bucket per matched pattern).
        if source:
            bucket = source.split(":", 1)[0].split()[0]
        else:
            bucket = "unknown"
        source_counts[bucket] = source_counts.get(bucket, 0) + 1

    write_jsonl_atomic(args.prs, prs)
    log.info("prs.jsonl updated in place: %s", args.prs)

    total = sum(counts.values()) or 1
    unknown_rate = counts.get("unknown", 0) / total
    log.info(
        "Classification summary: counts=%s sources=%s",
        counts,
        source_counts,
    )
    log.info("Unknown rate: %.2f%%", unknown_rate * 100)
    if unknown_rate > 0.20:
        # AAP §0.3.4: when the unknown rate for Metric 6 exceeds 20%,
        # the metric's confidence is downgraded to ``Low``. The
        # classifier emits the rate; ``compute_metrics.py`` enforces
        # the downgrade at render time. Surface the warning here so
        # an operator notices before the report is generated.
        log.warning(
            "Unknown classification rate %.2f%% exceeds 20%%; "
            "Metric 6 (Flow Distribution) will be downgraded to Low confidence "
            "per AAP §0.3.4.",
            unknown_rate * 100,
        )

    if args.report_stats:
        # The summary block is written to stdout AFTER the structured
        # log so a caller that pipes stdout into ``jq`` can extract
        # the final JSON object regardless of how many log lines
        # preceded it. ``indent=2`` keeps the block human-readable
        # when the operator runs the script interactively.
        summary = {
            "counts": counts,
            "source_counts": source_counts,
            "unknown_rate": unknown_rate,
        }
        print(json.dumps(summary, indent=2, default=str))
    return 0


# ---------------------------------------------------------------------------
# Module surface
# ---------------------------------------------------------------------------
# Re-export the symbols required by the file schema so static analysers
# see them as used. ``Any`` is exported alongside the type-using
# helpers for parity with how the rest of the pipeline's modules
# expose their typing imports.

__all__ = [
    "Any",
    "CONVENTIONAL_PREFIX_RE",
    "CONVENTIONAL_TO_WORK_TYPE",
    "ISSUE_LABEL_TO_WORK_TYPE",
    "KEYWORD_TO_WORK_TYPE",
    "LINKED_ISSUE_RE",
    "classify_by_keyword",
    "classify_by_linked_issues",
    "classify_by_pr_title_prefix",
    "classify_pr",
    "extract_linked_issue_numbers",
    "index_issues_by_number",
    "load_jsonl",
    "main",
    "parse_args",
    "write_jsonl_atomic",
]


if __name__ == "__main__":
    sys.exit(main())
