#!/usr/bin/env python3
"""
acceleration.scripts.compute_metrics
====================================

CENTRAL metric-computation engine and SINGLE WRITER of
``acceleration/data/metrics.json`` for the Development Acceleration
Analysis pipeline.

Consumes every extractor output (``commits.jsonl``, ``prs.jsonl``,
``reverts.jsonl``, ``reviews.jsonl``, ``releases.jsonl``,
``test_results.jsonl``, ``issues.jsonl``, ``branch_protection.json``,
``audit_log.jsonl``, ``sla_source.json``, ``github_access.json``,
``inflection.json``) and computes every one of the twelve specified
metrics across temporal phases (Baseline / Ramp-Up / Steady State or
Baseline / Post-Introduction fallback), modules, and actors (per
engineer plus Blitzy Agent in the after period).

The script implements:

- Monday-aligned 2-week UTC windowing (``monday_floor``,
  ``window_start_for``).
- Per-module classification by majority vote on top-level changed
  paths (``classify_path``, ``classify_commit``).
- Actor de-duplication via Jaccard similarity on touched files plus
  a 30-day timestamp-overlap floor (``resolve_aliases``).
- Identical-methodology before/after computation: every metric
  function reads from the same code path and substitutes only the
  actor identity (AAP §0.8.1 "Engineering Actor Framing").
- Confidence assignment based on the data source actually used at
  runtime (``assign_confidence``, AAP §0.8.3).
- Graceful degradation: every metric that lacks its primary data
  source emits ``Insufficient signal — [reason]`` with explicit
  ``tried`` and ``needed`` fields (``insufficient_signal``, AAP
  §0.8.2).

Reads (from ``acceleration/data/``)
-----------------------------------

- ``inflection.json``
- ``commits.jsonl``
- ``prs.jsonl`` (already annotated by ``classify_prs.py``)
- ``reverts.jsonl``
- ``reviews.jsonl``
- ``releases.jsonl``
- ``test_results.jsonl``
- ``issues.jsonl``
- ``sla_source.json``
- ``branch_protection.json``
- ``audit_log.jsonl``
- ``github_access.json``

Writes (to ``acceleration/data/``)
----------------------------------

- ``metrics.json``         — single source of truth for the report,
                              deck, dashboard, and verifier.
- ``actor_aliases.json``   — resolved actor-key map with Blitzy
                              Agent canonicalised.
- ``reproduce.sh``         — ordered shell commands that re-derive
                              every number from a clean clone.

Authority
---------

- AAP §0.3.1 — pipeline architecture; the single-writer pattern
  is the architectural foundation of internal consistency.
- AAP §0.3.4 — Monday-aligned windowing, per-metric semantics,
  in-progress PR rule, Flow Active/Efficiency/Time computations,
  revert attribution, releases counting, approved-exceptions
  detection, escaped-defect tracking, defects-out-of-SLA gating.
- AAP §0.7.2 — Report-internal Rules (Rule 4 Internal Consistency:
  every renderer consumes ``metrics.json`` without recomputing).
- AAP §0.8.1–0.8.6 — Engineering Actor Framing; Agent Latitude;
  Confidence Rubric; Temporal Phases; Per-Engineer Views;
  Multi-Module Repositories.

Read-only discipline (AAP §0.7.2.1, §0.8.7, §0.8.8)
---------------------------------------------------

- Reads only ``acceleration/data/*``.
- Writes only three files, all under ``acceleration/data/``:
  ``metrics.json``, ``actor_aliases.json``, ``reproduce.sh``.
- No network access, no ``git`` invocation, no ``gh`` invocation.

Stdlib-only by design (AAP §0.6.1, §0.8.8). The module loads on a
clean Python 3.10+ installation without ``pip install``.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import re
import statistics
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable


# ---------------------------------------------------------------------------
# Public exports — referenced by the file's exports manifest and by any
# downstream importer (most notably ``verify_report.py``).
# ---------------------------------------------------------------------------

__all__ = [
    # Constants
    "CANONICAL_METRIC_IDS",
    "WINDOW_DAYS",
    "RAMP_UP_WINDOWS",
    "JACCARD_THRESHOLD",
    "AI_ACTOR_EMAILS",
    "AI_ACTOR_DISPLAY",
    "MODULE_PREFIXES",
    "WORK_TYPES",
    # Dataclasses
    "PhaseBounds",
    "ComputeContext",
    # Helpers
    "monday_floor",
    "window_start_for",
    "parse_iso",
    "build_phase_bounds",
    "classify_path",
    "classify_commit",
    "compute_module_weights",
    "commits_by_module",
    "prs_by_module",
    "weighted_phase_aggregate",
    "compute_per_module",
    "jaccard",
    "resolve_aliases",
    "actor_key_for",
    "load_jsonl",
    "load_json",
    "assign_confidence",
    "insufficient_signal",
    "phase_aggregate",
    "active_engineers_per_phase",
    "normalise_phase_values_by_active_engineers",
    # Metric computers
    "compute_flow_load",
    "compute_flow_velocity",
    "compute_flow_predictability",
    "compute_flow_active",
    "compute_flow_efficiency",
    "compute_flow_distribution",
    "compute_flow_time",
    "compute_problem_records",
    "compute_releases",
    "compute_approved_exceptions",
    "compute_escaped_defects",
    "compute_defects_out_of_sla",
    # Synthesis
    "aggregate_per_engineer",
    "synthesize_risks",
    "synthesize_limitations",
    "build_reproduce_script",
    # CLI
    "parse_args",
    "main",
]


# ---------------------------------------------------------------------------
# Module constants
# ---------------------------------------------------------------------------

# Windowing — AAP §0.3.4 mandates Monday-aligned 2-week UTC windows.
WINDOW_DAYS: int = 14

# Ramp-Up is exactly six windows = 84 days (the largest multiple of 14
# not exceeding 90), per AAP §0.8.4.
RAMP_UP_WINDOWS: int = 6

# UTC for all windowing arithmetic to avoid timezone-induced bin drift
# (AAP §0.3.4).
WINDOW_TIMEZONE = timezone.utc

# Actor de-duplication threshold for the Jaccard similarity computed
# over touched-file sets (AAP §0.3.4).
JACCARD_THRESHOLD: float = 0.6

# Minimum overlap, in days, between two actors' first-seen / last-seen
# intervals before they may be merged into a single canonical actor.
# A 30-day floor avoids spurious merges between unrelated contributors
# who happened to touch the same configuration file once.
ACTOR_OVERLAP_MIN_DAYS: int = 30

# AI-tool author identities. The first entry is the canonical Blitzy
# email observed in the Formbricks commit log; the remaining entries
# cover other AI authors that may appear in future analyses.
AI_ACTOR_EMAILS: tuple[str, ...] = (
    "agent@blitzy.com",
    "noreply@anthropic.com",
    "copilot@github.com",
)
AI_ACTOR_DISPLAY: str = "Blitzy Agent"

# Canonical metric IDs in the order required by the report's "Metric
# Deep-Dives (×12)" section. Both the rendered table-of-contents and
# the appendix iterate this list, so the order is load-bearing for
# Rule 6 (Environment First).
CANONICAL_METRIC_IDS: list[str] = [
    "flow_load",
    "flow_velocity",
    "flow_predictability",
    "flow_active",
    "flow_efficiency",
    "flow_distribution",
    "flow_time",
    "problem_records",
    "releases",
    "approved_exceptions",
    "escaped_defects",
    "defects_out_of_sla",
]

# Module classification — top-level path prefix → module key. The list
# is walked top-to-bottom: more-specific prefixes (e.g. ``apps/web``)
# must precede their broader siblings (e.g. ``apps/``). Each entry is
# (prefix, module_label).
#
# This list MUST stay in lockstep with
# ``acceleration/scripts/extract_git.py:MODULE_PREFIXES``. Any drift
# would yield different module assignments for the same path between
# the extractor (which records ``commit.module``) and the computer
# (which falls back to re-classifying paths when ``module`` is absent
# or ``"unknown"``). A verifier assertion in :func:`_assert_module_prefixes_in_sync`
# (called at module load) raises ``RuntimeError`` if a drift is
# detected at runtime. To add or rename a prefix, update both files
# in the same change set.
MODULE_PREFIXES: list[tuple[str, str]] = [
    ("apps/web", "apps/web"),
    ("apps/docs", "apps/docs"),
    ("apps/storybook", "apps/storybook"),
    ("packages/database", "packages/database"),
    ("packages/surveys", "packages/surveys"),
    ("packages/types", "packages/types"),
    ("packages/", "packages/other"),
    ("docs/", "docs"),
    ("helm-chart", "helm-chart"),
    ("charts/", "charts"),
    ("blitzy/", "blitzy"),
    ("blitzy-docs", "blitzy-docs"),
    (".github", ".github"),
    ("acceleration/", "acceleration"),
]
DEFAULT_MODULE: str = "root"


def _assert_module_prefixes_in_sync() -> None:
    """Fail-fast guard that ``MODULE_PREFIXES`` matches the extractor's copy.

    The compute and extract layers MUST classify paths identically. This
    helper attempts a lazy import of
    ``acceleration.scripts.extract_git.MODULE_PREFIXES`` and compares
    the ordered prefix sequence (label-independent: only the prefix is
    significant for path matching). When the import fails because the
    extractor cannot be loaded standalone (e.g. ad-hoc script
    execution outside the package layout), the check silently
    degrades — the verifier's static AST check in
    ``verify_report.py`` is the secondary safety net.
    """

    try:
        from acceleration.scripts.extract_git import (
            MODULE_PREFIXES as EXTRACT_PREFIXES,
        )
    except Exception:  # pragma: no cover - import-time degradation
        return
    our_prefixes = tuple(entry[0] for entry in MODULE_PREFIXES)
    their_prefixes = tuple(entry[0] for entry in EXTRACT_PREFIXES)
    if our_prefixes != their_prefixes:
        raise RuntimeError(
            "MODULE_PREFIXES drift between compute_metrics.py and "
            "extract_git.py: "
            f"compute={our_prefixes!r} extract={their_prefixes!r}"
        )


# Invoke the sync check at module load so any drift surfaces before
# any metric is computed.
_assert_module_prefixes_in_sync()

# Work-type buckets for Metric 6 (Flow Distribution). The set is
# fixed at four canonical buckets plus the explicit ``unknown``
# fallback for unclassifiable PRs. ``classify_prs.py`` writes only
# these five values into the ``work_type`` field of ``prs.jsonl``.
WORK_TYPES: tuple[str, ...] = (
    "feature",
    "defect",
    "risk_compliance",
    "tech_debt",
    "unknown",
)

# Phases produced by ``PhaseBounds.phase_for``. The first two-element
# list applies in the normal regime; the second applies when fewer
# than 90 days of post-introduction history exist and the renderer
# falls back to a Baseline-vs-Post-Introduction schema (AAP §0.8.4).
NORMAL_PHASES: tuple[str, ...] = ("baseline", "ramp_up", "steady_state")
FALLBACK_PHASES: tuple[str, ...] = ("baseline", "post_introduction")

# Severity ordering for SLA-threshold lookup (Metric 12). The first
# match wins so the highest-severity label on an issue determines its
# SLA threshold, matching how engineering teams interpret priority
# labels in practice.
SEVERITY_ORDER: tuple[str, ...] = (
    "p0",
    "p1",
    "p2",
    "p3",
    "critical",
    "high",
    "medium",
    "low",
)

# Conventional-prefix → work-type mapping (mirrors classify_prs.py).
# Used only as a fallback in compute_flow_distribution when an
# upstream classifier did not annotate the PR; the canonical
# classifier remains classify_prs.py.
_CONVENTIONAL_PREFIX_TO_WORK_TYPE: dict[str, str] = {
    "feat": "feature",
    "fix": "defect",
    "revert": "defect",
    "security": "risk_compliance",
    "chore": "tech_debt",
    "docs": "tech_debt",
    "style": "tech_debt",
    "refactor": "tech_debt",
    "perf": "tech_debt",
    "test": "tech_debt",
    "build": "tech_debt",
    "ci": "tech_debt",
}
_CONVENTIONAL_RE = re.compile(r"^(?P<type>[a-z]+)(?:\([^)]*\))?:", re.IGNORECASE)

# Prerelease tag suffix pattern (AAP §0.3.4): prereleases matching
# ``-alpha|-beta|-rc|-dev`` are excluded from the primary release
# count and reported separately. The check is case-insensitive and
# the suffix anchor matches either a true suffix (``v1.2.3-rc.1``)
# or one embedded after a dot (``v1.2.3.rc1`` is uncommon but
# accepted).
_PRERELEASE_SUFFIX_RE = re.compile(r"[-.](alpha|beta|rc|dev)", re.IGNORECASE)

# Audit-log action prefixes considered approved-exception events for
# Metric 10. ``protected_branch.policy_override`` is the canonical
# action when an admin bypasses branch protection; ``repo.access``
# captures broader admin overrides on repository policy.
_APPROVED_EXCEPTION_ACTION_PREFIXES: tuple[str, ...] = (
    "protected_branch.",
    "repo.",
)


# ---------------------------------------------------------------------------
# Date / window helpers
# ---------------------------------------------------------------------------


def parse_iso(s: str | None) -> datetime:
    """Parse an ISO 8601 string into a UTC-aware ``datetime``.

    Accepts the three timestamp shapes produced by upstream extractors:

    - ``2026-02-25T09:12:34Z`` (trailing ``Z`` UTC designator),
    - ``2026-02-25T09:12:34+00:00`` (explicit UTC offset),
    - ``2026-02-25`` (date-only; treated as midnight UTC).

    Returns the current UTC time when ``s`` is falsy. Returning a
    "now" sentinel rather than raising keeps the metric loop robust
    in the face of a malformed input record — the surrounding
    callers filter out implausible dates by checking against the
    repository's commit date range.

    Parameters
    ----------
    s : str or None
        The ISO 8601 string to parse. ``None`` and empty string both
        yield the current UTC time.

    Returns
    -------
    datetime.datetime
        A timezone-aware ``datetime`` in UTC.
    """

    if not s:
        # Returning ``now()`` rather than raising lets the per-metric
        # filters (each of which checks the resulting date against
        # phase bounds) elide bad records cleanly.
        return datetime.now(timezone.utc)
    cleaned = s.strip()
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    # ``date`` rather than ``datetime`` (e.g. inflection.json's date
    # field). ``datetime.fromisoformat`` requires a full datetime
    # since Python 3.10, so prepend a midnight component.
    if "T" not in cleaned and len(cleaned) == 10:
        cleaned = cleaned + "T00:00:00+00:00"
    try:
        dt = datetime.fromisoformat(cleaned)
    except ValueError:
        return datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def monday_floor(d: datetime) -> datetime:
    """Return the Monday at 00:00 UTC of the week containing ``d``.

    Python's ``weekday()`` numbers Monday=0 through Sunday=6, so the
    floor is computed by subtracting ``weekday()`` days from the
    midnight-UTC instant of ``d``. The result is independent of the
    caller's local timezone because the input is first normalised
    to UTC.

    Parameters
    ----------
    d : datetime.datetime
        Any timezone-aware or naive timestamp. Naive timestamps are
        treated as UTC.

    Returns
    -------
    datetime.datetime
        The Monday at 00:00 UTC of the week containing ``d``.
    """

    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    d_utc = d.astimezone(WINDOW_TIMEZONE)
    midnight = d_utc.replace(hour=0, minute=0, second=0, microsecond=0)
    days_back = midnight.weekday()  # Monday=0, Sunday=6
    return midnight - timedelta(days=days_back)


def window_start_for(d: datetime, anchor_monday: datetime) -> datetime:
    """Return the start of the 2-week window containing ``d``.

    Each window spans ``[anchor_monday + 14k days, anchor_monday +
    14(k+1) days)`` for integer ``k``. The function determines
    ``k`` by computing the number of 7-day spans between
    ``monday_floor(d)`` and ``anchor_monday``, then rounding it
    toward minus-infinity to the next-lower even number so the
    result lands on the start of a 2-week window.

    The window-start arithmetic is identical for dates before and
    after the anchor, satisfying AAP §0.8.4's identical-methodology
    requirement.

    Parameters
    ----------
    d : datetime.datetime
        The date to bucket. May fall on either side of
        ``anchor_monday``.
    anchor_monday : datetime.datetime
        The Monday at 00:00 UTC that defines the 2-week cadence.
        Typically the Monday-floor of the inflection date.

    Returns
    -------
    datetime.datetime
        The Monday at 00:00 UTC marking the start of the 2-week
        window containing ``d``.
    """

    base = monday_floor(d)
    weeks_since = (base - anchor_monday).days // 7
    if weeks_since >= 0:
        even = (weeks_since // 2) * 2
    else:
        # ``//`` already floors toward -inf in Python, but the 2-week
        # cadence requires the result to be an *even* multiple. We
        # explicitly snap negatives downward to the nearest even
        # multiple to keep the window boundary consistent on both
        # sides of the anchor.
        even = -(((-weeks_since) + 1) // 2) * 2
    return anchor_monday + timedelta(weeks=even)


# ---------------------------------------------------------------------------
# Phase classification
# ---------------------------------------------------------------------------


@dataclass
class PhaseBounds:
    """Temporal phase bounds for the analysis.

    Attributes
    ----------
    inflection_date : datetime.datetime
        The instant before which a commit/PR/release belongs to the
        Baseline phase. Sourced from
        ``acceleration/data/inflection.json``.
    anchor_monday : datetime.datetime
        ``monday_floor(inflection_date)`` — the start of the
        Monday-aligned 2-week cadence used by ``window_start_for``.
    rampup_end : datetime.datetime
        The instant at which the Ramp-Up phase ends and Steady State
        begins. Always ``anchor_monday + 12 weeks`` so Ramp-Up
        contains exactly six 2-week windows = 84 days per AAP §0.8.4.
    fallback_to_post_introduction : bool
        ``True`` when fewer than 90 days of post-introduction history
        exist, in which case ``phase_for`` collapses Ramp-Up and
        Steady State into a single ``post_introduction`` phase per
        AAP §0.8.4.
    """

    inflection_date: datetime
    anchor_monday: datetime
    rampup_end: datetime
    fallback_to_post_introduction: bool

    def phase_for(self, when: datetime) -> str:
        """Return the phase label for an instant.

        Parameters
        ----------
        when : datetime.datetime
            The instant to classify (assumed UTC-aware).

        Returns
        -------
        str
            One of ``"baseline"``, ``"ramp_up"``, ``"steady_state"``
            (normal regime) or ``"baseline"``, ``"post_introduction"``
            (fallback regime).
        """

        if when < self.inflection_date:
            return "baseline"
        if self.fallback_to_post_introduction:
            return "post_introduction"
        if when < self.rampup_end:
            return "ramp_up"
        return "steady_state"

    def phases(self) -> tuple[str, ...]:
        """Return the set of phases in effect for this configuration."""

        return FALLBACK_PHASES if self.fallback_to_post_introduction else NORMAL_PHASES


def build_phase_bounds(
    inflection: dict[str, Any], latest_commit: datetime
) -> PhaseBounds:
    """Construct phase bounds from the inflection manifest.

    Accepts both the canonical field ``date`` (produced by
    ``detect_inflection.py``) and the legacy alias ``inflection_date``
    (the field name used by some early drafts of the pseudocode).

    When the inflection manifest reports no introduction date, the
    function returns a PhaseBounds whose ``inflection_date`` falls
    one day after the latest commit so every record is classified
    as Baseline. This conservative behaviour avoids fabricating an
    inflection where none was detected.

    Parameters
    ----------
    inflection : dict
        Parsed ``inflection.json``. ``inflection["found"]`` is
        consulted first; when ``False``, the no-inflection branch
        is taken.
    latest_commit : datetime.datetime
        The most recent author timestamp across the commit corpus.
        Used to determine whether the 90-day post-introduction
        history requirement is satisfied (AAP §0.8.4).

    Returns
    -------
    PhaseBounds
        The phase bounds object consumed by every metric computer.
    """

    found_flag = inflection.get("found", True)
    raw_date = inflection.get("date") or inflection.get("inflection_date") or ""
    if not raw_date or found_flag is False:
        # Conservative no-detection branch: classify everything as
        # baseline by setting the inflection one day past the latest
        # commit. fallback_to_post_introduction is set so phase_for
        # only ever returns "baseline" in this configuration.
        anchor = monday_floor(latest_commit)
        sentinel = latest_commit + timedelta(days=1)
        return PhaseBounds(
            inflection_date=sentinel,
            anchor_monday=anchor,
            rampup_end=sentinel,
            fallback_to_post_introduction=True,
        )

    inflection_dt = parse_iso(raw_date)
    anchor = monday_floor(inflection_dt)
    rampup_end = anchor + timedelta(weeks=2 * RAMP_UP_WINDOWS)
    fallback = (latest_commit - inflection_dt).days < 90
    return PhaseBounds(
        inflection_date=inflection_dt,
        anchor_monday=anchor,
        rampup_end=rampup_end,
        fallback_to_post_introduction=fallback,
    )



# ---------------------------------------------------------------------------
# Module classification
# ---------------------------------------------------------------------------


def classify_path(path: str) -> str:
    """Return the module label for a single repository-relative path.

    The classifier walks :data:`MODULE_PREFIXES` top-to-bottom and
    returns the first prefix that matches. Order matters: the more
    specific ``apps/web`` precedes the generic ``apps/`` (which is
    absent from the list because every ``apps/`` path is covered by
    a specific sub-entry).

    Parameters
    ----------
    path : str
        Repository-relative POSIX path (forward slashes). For
        example, ``"apps/web/lib/foo.ts"``.

    Returns
    -------
    str
        The module label, or :data:`DEFAULT_MODULE` for paths that
        do not match any prefix.
    """

    if not path:
        return DEFAULT_MODULE
    for prefix, module in MODULE_PREFIXES:
        if path.startswith(prefix):
            return module
    return DEFAULT_MODULE


def classify_commit(commit: dict[str, Any]) -> str:
    """Assign a commit to a module by majority vote on changed paths.

    Accepts both the canonical ``touched_files`` field produced by
    ``extract_git.py`` and the legacy ``paths`` alias used in some
    pseudocode drafts. Ties are broken by ``Counter.most_common``'s
    insertion-order semantics, which mirror the
    :data:`MODULE_PREFIXES` declaration order — i.e. a tie between
    ``apps/web`` and ``packages/types`` resolves to whichever module
    appears first in the prefix list.

    Parameters
    ----------
    commit : dict
        A parsed ``commits.jsonl`` record.

    Returns
    -------
    str
        The module label. Returns :data:`DEFAULT_MODULE` when the
        commit has no recorded changed paths (e.g. merge commits).
    """

    paths = (
        commit.get("touched_files")
        or commit.get("paths")
        or []
    )
    if not paths:
        # ``module`` may have been pre-computed by extract_git.py;
        # honour that when present rather than guessing.
        precomputed = commit.get("module")
        return precomputed if isinstance(precomputed, str) and precomputed else DEFAULT_MODULE
    counts = Counter(classify_path(p) for p in paths if isinstance(p, str))
    if not counts:
        return DEFAULT_MODULE
    return counts.most_common(1)[0][0]


def compute_module_weights(
    commits: list[dict[str, Any]],
) -> dict[str, float]:
    """Compute per-module aggregation weights from non-merge commit volume.

    AAP §0.8.6: "Run per-module independently, aggregate weighted by
    commit volume (non-merge commits per module / total)." The weight
    of module M is::

        weight(M) = non_merge_commits_in_module(M) / total_non_merge_commits

    The sum of all weights equals 1.0 (modulo floating-point rounding)
    so a weighted aggregate of per-module metric values is a true
    weighted mean.

    Merge commits are excluded from the denominator because their
    associated module classification depends on the underlying PR's
    branch contents (which extract_git.py records on the PR record,
    not the merge commit). Including merges would double-count.

    Parameters
    ----------
    commits : list[dict]
        ``commits.jsonl`` records. Each record must carry ``is_merge``
        and either ``module`` (precomputed by extract_git.py) or
        ``touched_files`` (so :func:`classify_commit` can derive the
        module on demand).

    Returns
    -------
    dict[str, float]
        Mapping ``module_label -> weight`` summing to 1.0. Returns
        an empty dict when ``commits`` is empty or contains only
        merge commits.
    """

    counts: Counter = Counter()
    total = 0
    for commit in commits:
        if commit.get("is_merge"):
            continue
        module = commit.get("module") or classify_commit(commit)
        if not module:
            module = DEFAULT_MODULE
        counts[module] += 1
        total += 1
    if total == 0:
        return {}
    return {module: count / total for module, count in counts.items()}


def commits_by_module(
    commits: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Partition ``commits`` by module label.

    AAP §0.8.6 ("Run per-module independently, aggregate weighted by
    commit volume"): the per-metric per-module computation needs the
    list of commits scoped to each module. This helper performs that
    partition in a single pass.

    Merge commits are emitted into a synthetic ``"_merges"`` bucket
    rather than discarded — some downstream metrics (e.g.
    Flow Velocity, which counts merge commits) need access to them
    indexed by module of the merge commit's recorded module field.

    Parameters
    ----------
    commits : list[dict]
        ``commits.jsonl`` records.

    Returns
    -------
    dict[str, list[dict]]
        Mapping ``module_label -> [commit, ...]``.
    """

    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for commit in commits:
        module = commit.get("module") or classify_commit(commit)
        if not module:
            module = DEFAULT_MODULE
        out[module].append(commit)
    return out


def prs_by_module(prs: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Partition ``prs`` by module label.

    Each PR record carries a ``module`` field synthesised by
    ``extract_git.py`` (from the merge commit's touched-files
    majority vote) or by ``classify_prs.py``. Unclassified PRs are
    bucketed under :data:`DEFAULT_MODULE` so the per-module union
    covers all PRs.

    Parameters
    ----------
    prs : list[dict]
        ``prs.jsonl`` records.

    Returns
    -------
    dict[str, list[dict]]
        Mapping ``module_label -> [pr, ...]``.
    """

    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for pr in prs:
        module = pr.get("module") or DEFAULT_MODULE
        out[module].append(pr)
    return out


def weighted_phase_aggregate(
    per_module_phases: dict[str, dict[str, dict[str, Any]]],
    weights: dict[str, float],
) -> dict[str, dict[str, Any]]:
    """Aggregate per-module per-phase values into a single phases block.

    AAP §0.8.6: "Run per-module independently, aggregate weighted by
    commit volume (non-merge commits per module / total)."

    For each phase, the aggregated value is::

        value(phase) = Σ_modules (per_module_value(phase) × weight(module))

    The multiplier is recomputed from the aggregated value against the
    aggregated baseline value (NOT a weighted average of per-module
    multipliers, because the ratio of weighted means is not the
    weighted mean of ratios).

    Phases that produce no module values resolve to ``value = 0`` with
    multiplier rules matching :func:`phase_aggregate`.

    Parameters
    ----------
    per_module_phases : dict
        Nested map ``module -> phase -> {value, multiplier, multiplier_kind}``.
        Modules that produce ``Insufficient signal`` for a metric should
        be omitted by the caller; this helper assumes every value is a
        numeric phase entry.
    weights : dict
        Per-module weight map (sums to 1.0).

    Returns
    -------
    dict[str, dict[str, Any]]
        Aggregated ``phase -> {value, multiplier, multiplier_kind,
        modules_contributing}`` block. Suitable for placing directly in
        a metric record's ``phases`` field.
    """

    if not per_module_phases:
        return {}
    # Enumerate the union of phase keys observed across all modules so
    # phases that exist on some modules but not others are still
    # represented in the output (with zero-weighted contribution).
    all_phases: set[str] = set()
    for phases_map in per_module_phases.values():
        all_phases.update(phases_map.keys())
    aggregated: dict[str, dict[str, Any]] = {}
    for phase in all_phases:
        weighted_value = 0.0
        total_weight = 0.0
        contributing: list[str] = []
        for module, phases_map in per_module_phases.items():
            weight = weights.get(module, 0.0)
            if weight <= 0:
                continue
            entry = phases_map.get(phase)
            if entry is None:
                continue
            value = entry.get("value")
            if not isinstance(value, (int, float)):
                continue
            weighted_value += float(value) * weight
            total_weight += weight
            contributing.append(module)
        if total_weight == 0:
            # Phase has no contributing module data.
            aggregated[phase] = {
                "value": 0,
                "multiplier": 1.0 if phase == "baseline" else 0.0,
                "multiplier_kind": "ratio",
                "modules_contributing": [],
            }
            continue
        # Re-normalise so the weighted_value reflects the effective
        # contributing weight when some modules are missing for this
        # phase (e.g. ``apps/web`` has data for both phases but
        # ``acceleration`` only contributes in the ramp_up phase).
        normalised_value = weighted_value / total_weight
        aggregated[phase] = {
            "value": round(normalised_value, 4),
            # Provisional multiplier; recomputed in the
            # post-aggregation pass below against the aggregated
            # baseline value. This placeholder is only ever read by
            # the recomputation loop, never by callers.
            "multiplier": 1.0,
            "multiplier_kind": "ratio",
            "modules_contributing": sorted(contributing),
        }
    # Recompute multipliers against the aggregated baseline.
    baseline_value = aggregated.get("baseline", {}).get("value")
    if isinstance(baseline_value, (int, float)) and baseline_value != 0:
        for phase, entry in aggregated.items():
            if phase == "baseline":
                entry["multiplier"] = 1.0
                continue
            value = entry.get("value")
            if isinstance(value, (int, float)):
                entry["multiplier"] = round(float(value) / baseline_value, 3)
            else:
                entry["multiplier"] = None
                entry["multiplier_kind"] = "undefined"
    elif isinstance(baseline_value, (int, float)) and baseline_value == 0:
        # Baseline of zero: subsequent phases produce "infinite" or
        # "undefined" multipliers per the :func:`phase_aggregate`
        # convention.
        for phase, entry in aggregated.items():
            if phase == "baseline":
                entry["multiplier"] = 1.0
                continue
            value = entry.get("value")
            if isinstance(value, (int, float)) and value != 0:
                entry["multiplier"] = None
                entry["multiplier_kind"] = "infinite"
            else:
                entry["multiplier"] = None
                entry["multiplier_kind"] = "undefined"
    return aggregated


def compute_per_module(
    ctx: ComputeContext,
    metric_fn: Any,
) -> dict[str, Any]:
    """Compute a metric per module and aggregate by commit-volume weight.

    AAP §0.8.6 implementation entry point. For each module identified
    by :func:`compute_module_weights`, build a module-scoped
    :class:`ComputeContext` and invoke ``metric_fn`` against it. The
    per-module results are returned for transparency, and a
    commit-volume-weighted aggregate is produced for the headline
    ``phases`` value.

    The module-scoped context is built by:

    - ``commits``: only commits classified to this module
    - ``prs``: only PRs classified to this module
    - ``reverts``: reverts whose revert SHA appears in the module's
      commit list (since reverts.jsonl does not carry module on its
      own — the module of a revert is the module of the revert
      commit, not the original)
    - All other fields: passed through unchanged (releases, tags,
      deployments, audit_log, issues, test_results, sla_source are
      repo-wide rather than module-scoped)

    Parameters
    ----------
    ctx : ComputeContext
        The full-repository context.
    metric_fn : callable
        A metric computer function ``(ctx) -> metric_record`` such as
        :func:`compute_flow_velocity`. Must accept a
        :class:`ComputeContext` and return a dict containing
        ``phases``.

    Returns
    -------
    dict[str, Any]
        Dict with two top-level keys:

        - ``"per_module"``: ``module -> metric_record`` (one entry per
          module that produced data).
        - ``"aggregated_phases"``: weighted ``phases`` block.

        Both are intended to be merged into the calling metric's
        returned record by the metric function itself when it opts
        into per-module reporting.
    """

    weights = compute_module_weights(ctx.commits)
    if not weights:
        return {"per_module": {}, "aggregated_phases": {}}
    by_commit = commits_by_module(ctx.commits)
    by_pr = prs_by_module(ctx.prs)
    # Index reverts by revert_sha for module attribution.
    by_revert: dict[str, list[dict[str, Any]]] = defaultdict(list)
    revert_module_for_sha: dict[str, str] = {}
    for commit in ctx.commits:
        sha = commit.get("sha")
        if isinstance(sha, str):
            revert_module_for_sha[sha] = (
                commit.get("module") or classify_commit(commit)
            )
    for revert in ctx.reverts:
        sha = revert.get("revert_sha")
        if not isinstance(sha, str):
            continue
        module = revert_module_for_sha.get(sha) or DEFAULT_MODULE
        by_revert[module].append(revert)

    per_module: dict[str, Any] = {}
    per_module_phases: dict[str, dict[str, dict[str, Any]]] = {}
    for module in weights:
        module_ctx = ComputeContext(
            bounds=ctx.bounds,
            commits=by_commit.get(module, []),
            prs=by_pr.get(module, []),
            reviews=ctx.reviews,
            releases=ctx.releases,
            reverts=by_revert.get(module, []),
            tags=ctx.tags,
            deployments=ctx.deployments,
            test_results=ctx.test_results,
            issues=ctx.issues,
            sla_source=ctx.sla_source,
            branch_protection=ctx.branch_protection,
            audit_log=ctx.audit_log,
            github_access=ctx.github_access,
            aliases=ctx.aliases,
        )
        try:
            record = metric_fn(module_ctx)
        except Exception as exc:  # noqa: BLE001 — per-module robustness
            record = {
                "value": f"Insufficient signal — per-module compute raised {type(exc).__name__}: {exc}",
                "phases": {},
            }
        per_module[module] = record
        phases = record.get("phases") or {}
        # Skip Insufficient-signal modules from the weighted average:
        # their ``phases`` block is empty by convention.
        if phases:
            per_module_phases[module] = phases
    aggregated_phases = weighted_phase_aggregate(per_module_phases, weights)
    return {
        "per_module": per_module,
        "aggregated_phases": aggregated_phases,
        "module_weights": weights,
    }


# ---------------------------------------------------------------------------
# Actor alias resolution
# ---------------------------------------------------------------------------


def jaccard(a: set[str], b: set[str]) -> float:
    """Return the Jaccard similarity coefficient between two sets.

    The Jaccard coefficient is ``|A ∩ B| / |A ∪ B|``. Empty sets
    return ``0.0`` to avoid a division-by-zero and to keep
    ``resolve_aliases`` from merging two contributors whose
    touched-file sets are both empty (a degenerate case that would
    otherwise produce ``0/0``).

    Parameters
    ----------
    a, b : set[str]
        Sets of file paths or any other comparable strings.

    Returns
    -------
    float
        A value in ``[0.0, 1.0]``.
    """

    if not a or not b:
        return 0.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def _ensure_actor_record(
    by_email: dict[str, dict[str, Any]], email: str, name: str
) -> dict[str, Any]:
    """Lookup-or-create the actor record for an email address.

    Centralised so both the streaming-commit pass and any future
    alternative input (e.g. PR authors when no commits exist) share
    the same record-initialisation contract.
    """

    record = by_email.get(email)
    if record is None:
        record = {
            "email": email,
            "display_name": name or email,
            "paths": set(),
            "first_seen": None,
            "last_seen": None,
            "commit_count": 0,
        }
        by_email[email] = record
    elif name and len(name) > len(record.get("display_name") or ""):
        # Prefer the longer / fuller display name observed across
        # this contributor's commits.
        record["display_name"] = name
    return record


def resolve_aliases(
    commits: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Group ``(name, email)`` pairs into canonical actor identities.

    The algorithm runs in three passes:

    1. **Aggregate**: every commit contributes its author email,
       name, and touched-file set to the per-email bucket.
    2. **Merge**: any two buckets whose touched-file sets have a
       Jaccard similarity of at least :data:`JACCARD_THRESHOLD`
       **and** whose first-seen/last-seen intervals overlap by at
       least :data:`ACTOR_OVERLAP_MIN_DAYS` are merged. The
       lower-keyed bucket becomes the canonical row; the merged-in
       bucket is recorded under its ``aliases`` list.
    3. **AI canonicalisation**: every AI-tool email matching
       :data:`AI_ACTOR_EMAILS` is collapsed into a single row whose
       ``canonical_email`` is the first AI email and whose
       ``display_name`` is :data:`AI_ACTOR_DISPLAY`. This satisfies
       AAP §0.8.1 (one row labelled "Blitzy Agent").

    Parameters
    ----------
    commits : list[dict]
        The parsed contents of ``commits.jsonl``.

    Returns
    -------
    dict[str, dict[str, Any]]
        A mapping from canonical email to actor record. Each record
        carries:

        - ``canonical_email`` — the canonical (lower-cased) email.
        - ``display_name`` — the longest observed display name, or
          ``AI_ACTOR_DISPLAY`` for the AI row.
        - ``aliases`` — list of ``{email, display_name}`` pairs for
          all emails that resolved to this canonical identity.
        - ``first_seen``, ``last_seen`` — ISO 8601 strings.
        - ``commit_count`` — total non-merge commit count for this
          canonical identity across all aliases.
        - ``is_ai_actor`` — ``True`` for the Blitzy Agent row,
          absent otherwise.
    """

    by_email: dict[str, dict[str, Any]] = {}

    # ---- Pass 1: aggregate per email ------------------------------
    for commit in commits:
        if commit.get("is_merge"):
            # Merge commits typically have empty touched-file sets
            # and inflate file-touch overlap artefacts.
            continue
        email = (commit.get("author_email") or "").strip().lower()
        name = (commit.get("author_name") or "").strip()
        if not email:
            continue
        record = _ensure_actor_record(by_email, email, name)
        for p in commit.get("touched_files") or commit.get("paths") or []:
            if isinstance(p, str):
                record["paths"].add(p)
        record["commit_count"] += 1
        dt = parse_iso(commit.get("author_date"))
        if record["first_seen"] is None or dt < record["first_seen"]:
            record["first_seen"] = dt
        if record["last_seen"] is None or dt > record["last_seen"]:
            record["last_seen"] = dt

    # ---- Pass 2: greedy pairwise merge by Jaccard + temporal overlap
    keys = list(by_email.keys())
    consumed: set[str] = set()
    merged: dict[str, dict[str, Any]] = {}
    for i, k1 in enumerate(keys):
        if k1 in consumed:
            continue
        a = by_email[k1]
        bucket: dict[str, Any] = {
            "canonical_email": k1,
            "display_name": a["display_name"],
            "aliases": [{"email": k1, "display_name": a["display_name"]}],
            "first_seen": _iso_or_none(a["first_seen"]),
            "last_seen": _iso_or_none(a["last_seen"]),
            "commit_count": a["commit_count"],
        }
        for k2 in keys[i + 1 :]:
            if k2 in consumed:
                continue
            b = by_email[k2]
            sim = jaccard(a["paths"], b["paths"])
            if sim < JACCARD_THRESHOLD:
                continue
            overlap_days = _interval_overlap_days(
                a["first_seen"], a["last_seen"], b["first_seen"], b["last_seen"]
            )
            if overlap_days < ACTOR_OVERLAP_MIN_DAYS:
                continue
            # Merge b into a.
            bucket["aliases"].append(
                {"email": k2, "display_name": b["display_name"]}
            )
            bucket["commit_count"] += b["commit_count"]
            if len(b["display_name"]) > len(bucket["display_name"]):
                bucket["display_name"] = b["display_name"]
            # Update interval edges.
            if b["first_seen"] is not None and (
                a["first_seen"] is None or b["first_seen"] < a["first_seen"]
            ):
                a["first_seen"] = b["first_seen"]
                bucket["first_seen"] = _iso_or_none(b["first_seen"])
            if b["last_seen"] is not None and (
                a["last_seen"] is None or b["last_seen"] > a["last_seen"]
            ):
                a["last_seen"] = b["last_seen"]
                bucket["last_seen"] = _iso_or_none(b["last_seen"])
            a["paths"] = a["paths"] | b["paths"]
            consumed.add(k2)
        merged[k1] = bucket

    # ---- Pass 2.5: complementary display-name equivalence merge ---
    # The Jaccard-on-touched-files pass above fails to catch a common
    # false-split pattern in a long-lived monorepo: the same engineer
    # commits under two email addresses (e.g., a GitHub
    # ``noreply.github.com`` masked email and a corporate email) but
    # their work spans different parts of the codebase across the
    # years (the codebase evolves, the engineer rotates between
    # modules), so the touched-file Jaccard similarity falls below
    # :data:`JACCARD_THRESHOLD` even though both addresses belong to
    # the same person. AAP §0.3.4 names this exact failure mode
    # ("Matti Nannt" vs "Matthias Nannt") and mandates that aliases
    # "are detected by Jaccard similarity on commit-touched files AND
    # timestamp clustering" — display-name equivalence is the
    # complementary signal to the touched-file signal. Adding this
    # pass closes QA finding F-002 (Per-Engineer table contains
    # duplicate-name rows for the same human engineer).
    #
    # Three rules fire here, ordered from strongest to weakest
    # signal so a single greedy pass produces deterministic output:
    #
    # 1. **Exact multi-token name match** (e.g., "Piyush Gupta" ==
    #    "Piyush Gupta", "Rotimi Best" == "Rotimi Best"). Merge
    #    unconditionally — a two-or-more-token full-name collision
    #    between unrelated contributors is an extreme low-probability
    #    event (the same case the AAP "Matti Nannt" / "Matthias
    #    Nannt" example targets). Temporal-overlap is not required
    #    because real engineers DO switch emails sequentially when
    #    they change jobs or rotate accounts, producing adjacent but
    #    non-overlapping intervals.
    # 2. **Exact single-token name match with temporal overlap**
    #    (e.g., "Johannes" == "Johannes"). Single-token names carry
    #    higher collision risk (common first names exist), so the
    #    temporal-overlap gate (``ACTOR_OVERLAP_MIN_DAYS`` days)
    #    safeguards against false merges of unrelated single-name
    #    contributors.
    # 3. **Token-subset name match with temporal overlap and
    #    first-token equality** (e.g., "Dhruwang" ⊆ "Dhruwang
    #    Jariwala"). Catches the casual first-name-only variation
    #    pattern. The first-token equality and temporal-overlap
    #    requirements together prevent unrelated contributors who
    #    only share a common first name from being merged.
    #
    # The order of operations matters: this pass runs AFTER the
    # Jaccard pass so any merge it performs is additive — Jaccard
    # already collapsed the high-file-overlap cases, and this pass
    # only sees the residual false-splits where the names converge
    # but the files diverged.
    keys = list(merged.keys())
    for i, k1 in enumerate(keys):
        if k1 not in merged:
            # Was consumed by a prior iteration of this pass.
            continue
        bucket_a = merged[k1]
        if bucket_a.get("is_ai_actor"):
            # AI buckets are handled in Pass 3; never collapse a
            # human into the AI bucket here.
            continue
        name_a_norm, name_a_tokens = _normalize_actor_name(bucket_a["display_name"])
        if not name_a_norm:
            continue
        for k2 in keys[i + 1 :]:
            if k2 not in merged:
                continue
            bucket_b = merged[k2]
            if bucket_b.get("is_ai_actor"):
                continue
            name_b_norm, name_b_tokens = _normalize_actor_name(bucket_b["display_name"])
            if not name_b_norm:
                continue
            # Determine whether the two names match by one of the
            # three rules. ``rule`` is recorded on the merged bucket
            # so a reviewer can inspect why each collapse happened.
            rule: str | None = None
            require_temporal_overlap = True
            if name_a_norm == name_b_norm:
                if len(name_a_tokens) >= 2:
                    # Rule 1: exact multi-token match — high
                    # confidence; temporal overlap not required.
                    rule = "display_name_exact_multi_token"
                    require_temporal_overlap = False
                else:
                    # Rule 2: exact single-token match — protect
                    # with temporal overlap.
                    rule = "display_name_exact_single_token"
            elif _name_subset_match(name_a_tokens, name_b_tokens):
                # Rule 3: subset match — protect with temporal
                # overlap and first-token equality (already enforced
                # by _name_subset_match).
                rule = "display_name_token_subset"
            if rule is None:
                continue
            # Temporal-overlap gate (applies to rules 2 and 3). The
            # endpoints are stored as ISO strings on the bucket;
            # convert to ``datetime`` via the local ``_iso_to_dt``
            # helper, which preserves ``None`` so
            # ``_interval_overlap_days`` correctly returns -1 and the
            # merge is rejected when either endpoint is missing.
            overlap_days = _interval_overlap_days(
                _iso_to_dt(bucket_a.get("first_seen")),
                _iso_to_dt(bucket_a.get("last_seen")),
                _iso_to_dt(bucket_b.get("first_seen")),
                _iso_to_dt(bucket_b.get("last_seen")),
            )
            if require_temporal_overlap and overlap_days < ACTOR_OVERLAP_MIN_DAYS:
                continue
            # Merge b into a.
            bucket_a["aliases"].extend(bucket_b.get("aliases", []))
            bucket_a["commit_count"] = int(bucket_a.get("commit_count", 0) or 0) + int(
                bucket_b.get("commit_count", 0) or 0
            )
            # Prefer the longer / fuller display name across both
            # buckets so "Dhruwang Jariwala" wins over "Dhruwang".
            if len(bucket_b.get("display_name") or "") > len(
                bucket_a.get("display_name") or ""
            ):
                bucket_a["display_name"] = bucket_b["display_name"]
            # Widen interval edges.
            for edge_field, picker in (
                ("first_seen", min),
                ("last_seen", max),
            ):
                edges = [
                    e for e in (bucket_a.get(edge_field), bucket_b.get(edge_field))
                    if e
                ]
                if edges:
                    bucket_a[edge_field] = picker(edges)
            # Record provenance of this collapse so a reviewer can
            # inspect actor_aliases.json and understand why two
            # emails became one row.
            collapses = bucket_a.setdefault("name_merge_evidence", [])
            collapses.append(
                {
                    "rule": rule,
                    "merged_email": bucket_b.get("canonical_email"),
                    "overlap_days": overlap_days,
                }
            )
            del merged[k2]

    # ---- Pass 3: AI canonicalisation -------------------------------
    ai_buckets: list[dict[str, Any]] = []
    for ai_email in AI_ACTOR_EMAILS:
        if ai_email in merged:
            ai_buckets.append(merged.pop(ai_email))
        # Also look for buckets that have an AI email in their alias
        # list but resolved to a non-AI canonical email (rare, but
        # possible after the Jaccard merge).
        for canonical, bucket in list(merged.items()):
            if any(
                (alias.get("email") or "").lower() == ai_email
                for alias in bucket.get("aliases", [])
            ):
                ai_buckets.append(merged.pop(canonical))
                break
    if ai_buckets:
        primary = ai_buckets[0]
        primary["display_name"] = AI_ACTOR_DISPLAY
        primary["canonical_email"] = AI_ACTOR_EMAILS[0]
        primary["is_ai_actor"] = True
        for extra in ai_buckets[1:]:
            primary["aliases"].extend(extra.get("aliases", []))
            primary["commit_count"] = (
                primary.get("commit_count", 0)
                + int(extra.get("commit_count", 0) or 0)
            )
        merged[AI_ACTOR_EMAILS[0]] = primary

    return merged


def _iso_or_none(dt: datetime | None) -> str | None:
    """Format a datetime as ISO 8601, or return None for None."""

    if dt is None:
        return None
    return dt.isoformat()


def _iso_to_dt(value: Any) -> datetime | None:
    """Parse an ISO 8601 string and return ``None`` when input is falsy.

    The module-level :func:`parse_iso` deliberately substitutes
    ``datetime.now()`` for ``None`` or empty input so per-metric
    extractors that filter on phase bounds elide malformed records
    cleanly. The alias-resolution path needs the opposite contract:
    if a bucket has no recorded first-seen / last-seen timestamp,
    the merge must be rejected (``_interval_overlap_days`` returns
    -1 when any endpoint is ``None``). This helper preserves
    ``None`` and only parses concrete ISO strings.

    Parameters
    ----------
    value : Any
        Typically an ISO 8601 string from a bucket record. Anything
        else returns ``None``.

    Returns
    -------
    datetime.datetime | None
        UTC-aware datetime when ``value`` is a parseable ISO string;
        ``None`` otherwise.
    """

    if not value or not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(
            value[:-1] + "+00:00" if value.endswith("Z") else value
        )
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


# Display-name tokens that are obvious noise / non-identifying. They
# are stripped during the name-equivalence pass so a bracketed bot
# suffix or a parenthetical handle does not prevent an otherwise
# clear collapse.
_NAME_NOISE_TOKENS: frozenset[str] = frozenset({"bot", "dependabot", "users"})


def _normalize_actor_name(name: str | None) -> tuple[str, tuple[str, ...]]:
    """Return ``(normalised_string, token_tuple)`` for a display name.

    The normalisation strips bracketed suffixes (``"[bot]"``,
    ``"(GitHub)"``), lower-cases the result, collapses internal
    whitespace, and tokenises on whitespace and underscores so the
    name-equivalence rules in :func:`resolve_aliases` Pass 2.5 can
    compare buckets deterministically.

    Both outputs are produced from the same input pass so the
    caller never has to re-tokenise.

    Parameters
    ----------
    name : str or None
        The display name as observed on a git commit (may be ``None``
        when the commit author had no display name).

    Returns
    -------
    tuple[str, tuple[str, ...]]
        ``(normalised_lowercase_name, ordered_token_tuple)``. Both
        components are empty when the input contains no
        identifying tokens after noise removal.
    """

    if not name or not isinstance(name, str):
        return "", ()
    text = name.strip()
    # Strip bracketed suffixes such as "[bot]", "(GitHub)" — the
    # bracket content can drift between observations of the same
    # contributor and is rarely identifying.
    while True:
        for open_ch, close_ch in (("[", "]"), ("(", ")"), ("<", ">"), ("{", "}")):
            start = text.find(open_ch)
            end = text.find(close_ch, start + 1)
            if 0 <= start < end:
                text = (text[:start] + " " + text[end + 1 :]).strip()
                break
        else:
            break
    # Tokenise. Underscores and hyphens are treated as word
    # separators so "rotimi-best" matches "Rotimi Best".
    chars = []
    for ch in text.lower():
        if ch.isalnum():
            chars.append(ch)
        else:
            chars.append(" ")
    tokens_all = [t for t in "".join(chars).split() if t]
    # Drop generic noise tokens (e.g., the trailing ``"bot"`` suffix
    # that was stripped from the bracket pass above but may also
    # appear bare). Pure-digit tokens are kept (they may be a user
    # ID prefix that helps disambiguate).
    tokens = tuple(t for t in tokens_all if t not in _NAME_NOISE_TOKENS)
    if not tokens:
        return "", ()
    return " ".join(tokens), tokens


def _name_subset_match(
    tokens_a: tuple[str, ...], tokens_b: tuple[str, ...]
) -> bool:
    """Return ``True`` when one token tuple is a confident subset of the other.

    The rule below is intentionally conservative to avoid merging
    unrelated contributors who share a common first name (e.g.,
    "Mike" + "Mike Smith"):

    - Tokens must be non-empty for both sides.
    - The smaller token set must be a strict subset of the larger.
    - The first token (almost always the given name) must match
      exactly between the two sets.
    - The larger token set must have at least two tokens — i.e.,
      we never merge "Mike" with "Mike" via this rule (that case is
      handled by the exact-name-equality rule, which requires
      temporal overlap as its only safeguard).

    Parameters
    ----------
    tokens_a, tokens_b : tuple[str, ...]
        Normalised token tuples produced by
        :func:`_normalize_actor_name`.

    Returns
    -------
    bool
        ``True`` iff the rule above is satisfied.
    """

    if not tokens_a or not tokens_b:
        return False
    if tokens_a == tokens_b:
        # Exact equality is handled by the dedicated rule in the
        # caller; this helper returns False so the caller does not
        # double-count the same case.
        return False
    set_a, set_b = set(tokens_a), set(tokens_b)
    smaller, larger = (set_a, set_b) if len(set_a) <= len(set_b) else (set_b, set_a)
    if not smaller.issubset(larger):
        return False
    if len(larger) < 2:
        return False
    # First-token equality. We use the FIRST token of each ordered
    # tuple, which conventionally is the given name and is the most
    # identifying single component.
    if tokens_a[0] != tokens_b[0]:
        return False
    return True


def _interval_overlap_days(
    a_start: datetime | None,
    a_end: datetime | None,
    b_start: datetime | None,
    b_end: datetime | None,
) -> int:
    """Return overlap (days) between [a_start, a_end] and [b_start, b_end].

    Negative values indicate disjoint intervals. ``None`` endpoints
    are treated as missing data and produce a -1 overlap so the
    caller's threshold check (``>= ACTOR_OVERLAP_MIN_DAYS``) rejects
    the merge.
    """

    if a_start is None or a_end is None or b_start is None or b_end is None:
        return -1
    start = max(a_start, b_start)
    end = min(a_end, b_end)
    return (end - start).days


def actor_key_for(
    email: str | None, alias_map: dict[str, dict[str, Any]]
) -> str:
    """Resolve an email to its canonical actor key.

    Resolution order:

    1. Empty / falsy email → ``"unknown"``.
    2. AI-tool email → canonical AI key (``AI_ACTOR_EMAILS[0]``).
    3. Email present as a top-level key in ``alias_map`` → that key.
    4. Email present in the ``aliases`` list of any record → that
       record's canonical email.
    5. Fallback: the lower-cased email itself.

    Parameters
    ----------
    email : str or None
        The author email to resolve.
    alias_map : dict
        The output of :func:`resolve_aliases`.

    Returns
    -------
    str
        The canonical actor key. Always a non-empty string.
    """

    if not email:
        return "unknown"
    norm = email.strip().lower()
    if not norm:
        return "unknown"
    if norm in AI_ACTOR_EMAILS:
        return AI_ACTOR_EMAILS[0]
    if norm in alias_map:
        return norm
    for canonical, entry in alias_map.items():
        for alias in entry.get("aliases", []):
            if (alias.get("email") or "").lower() == norm:
                return canonical
    return norm



# ---------------------------------------------------------------------------
# JSONL / JSON loading
# ---------------------------------------------------------------------------


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    """Load every JSON object from a ``.jsonl`` file.

    Missing files return an empty list (treated as "no data" by
    downstream metric computers). Malformed lines are silently
    discarded — a single corrupt line in a 5,000-record stream must
    not abort the whole pipeline (AAP §0.7.2.1 read-only discipline
    expects graceful degradation).

    Parameters
    ----------
    path : pathlib.Path
        Path to the JSONL file.

    Returns
    -------
    list[dict[str, Any]]
        The list of decoded JSON objects. Empty when the file is
        absent, empty, or contains only un-parseable lines.
    """

    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for raw in handle:
            line = raw.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                out.append(obj)
    return out


def load_json(path: Path) -> dict[str, Any]:
    """Load a single JSON object from a file.

    Returns an empty dict when the file is absent, empty, or
    contains a value that is not a JSON object (we accept dict-only
    here because every consumer treats the result as a manifest of
    fields).

    Parameters
    ----------
    path : pathlib.Path
        Path to the JSON file.

    Returns
    -------
    dict[str, Any]
        The decoded object, or ``{}`` on any error condition.
    """

    if not path.exists():
        return {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    if not text.strip():
        return {}
    try:
        decoded = json.loads(text)
    except json.JSONDecodeError:
        return {}
    if not isinstance(decoded, dict):
        return {}
    return decoded


# ---------------------------------------------------------------------------
# PR accessor helpers — bridge field-name differences between
# extract_git.py (``merge_author_email``) and extract_github.py
# (``user`` + ``user_type``) so metric code is agnostic to source.
# ---------------------------------------------------------------------------


def _pr_author_email(pr: dict[str, Any]) -> str | None:
    """Return the best-effort author email for a PR.

    Resolution order:

    1. ``merge_author_email`` — set by extract_git.py from the
       PR-merge commit's author identity.
    2. ``user`` — login name from extract_github.py (used as a
       pseudo-email when only the GitHub login is known).
    """

    email = pr.get("merge_author_email") or pr.get("author_email")
    if email:
        return str(email)
    login = pr.get("user")
    if login:
        return str(login)
    return None


def _pr_head_branch(pr: dict[str, Any]) -> str:
    """Return the source branch ref for a PR (empty string when unknown)."""

    return str(pr.get("head_ref") or pr.get("head_branch") or "")


def _pr_is_bot(pr: dict[str, Any]) -> bool:
    """Return True when the PR was authored by a bot.

    Uses the GitHub-API-only ``user_type`` field (``"Bot"``) as the
    authoritative signal. Falls back to the ``is_bot_author``
    pseudocode alias for tests that pre-populate the field.
    """

    if pr.get("is_bot_author") is True:
        return True
    user_type = pr.get("user_type")
    return isinstance(user_type, str) and user_type.lower() == "bot"


def _pr_labels(pr: dict[str, Any]) -> set[str]:
    """Return the lower-cased label set on a PR (empty set if none)."""

    raw = pr.get("labels") or []
    return {(item or "").lower() for item in raw if isinstance(item, str)}


def _pr_work_type(pr: dict[str, Any]) -> str:
    """Return the PR's work_type (annotated by classify_prs.py).

    Falls back to a conventional-commit-prefix lookup on the PR
    title when ``work_type`` is missing, then to ``"unknown"``. The
    fallback chain mirrors the priority order described in
    classify_prs.py so compute_metrics remains stable even if the
    classifier was not run upstream.
    """

    wt = pr.get("work_type")
    if isinstance(wt, str) and wt in WORK_TYPES:
        return wt
    title = pr.get("title") or pr.get("merge_subject") or ""
    match = _CONVENTIONAL_RE.match(title)
    if match:
        prefix = match.group("type").lower()
        mapped = _CONVENTIONAL_PREFIX_TO_WORK_TYPE.get(prefix)
        if mapped:
            return mapped
    return "unknown"


def _pr_was_in_progress_at(pr: dict[str, Any], when: datetime) -> bool:
    """Was the PR in-progress at the given instant?

    Implements the AAP §0.1.3 user example verbatim:

        In-progress = branch has at least one commit AND PR is open
        (not merged, not closed-without-merge), OR PR is in draft state.

    The user-supplied definition is a disjunction with two limbs:

    1. **Open-and-not-finalised limb.** The PR has at least one commit
       on its branch by ``when`` (evidenced by ``created_at`` /
       ``first_commit_at``), was not yet merged at ``when``, and was
       not yet closed without merge at ``when``.
    2. **Draft limb.** The PR is in draft state at ``when``. Draft
       PRs are by definition not ready for review and therefore count
       as in-progress regardless of the open/closed-without-merge
       sub-state of the first limb.

    The ``draft`` field comes from ``extract_github.py`` (``bool``
    coerced from the GitHub Pulls API ``draft`` property — see
    ``extract_github.py:521``). When the PR record carries no
    ``draft`` field (e.g. PRs reconstructed from git-only data), the
    draft limb degrades silently and only the first limb decides.

    Note on draft-state history
    ---------------------------
    The GitHub API exposes the current draft state, not its history.
    A PR that was drafted, then taken out of draft, and then merged is
    only known to be "currently draft" if it remains in that state
    today. The implementation therefore admits the *currently-draft*
    snapshot as in-progress at ``when``; PRs that left draft state
    before ``when`` are still admitted via the first limb whenever
    they were open at that time. This matches the user definition's
    point-in-time semantics for the open-merged-closed dimensions and
    relies on the current draft flag as a proxy for the draft state
    at ``when``.

    Bot-author exclusion is handled separately by
    :func:`_pr_counts_for_in_progress`.
    """

    # -- Draft limb (admitted regardless of merge/close state) -------------
    if pr.get("draft") is True:
        # Even a draft must have existed at ``when``. Use the earliest
        # available creation/first-commit timestamp; if none is
        # recorded we cannot evidence the PR's existence at ``when``
        # and treat the draft limb as not satisfied (AAP §0.7.2.1
        # forbids fabricating signal).
        draft_created_raw = pr.get("created_at") or pr.get("first_commit_at")
        if draft_created_raw and parse_iso(draft_created_raw) < when:
            return True
        # If the draft has no creation timestamp, fall through to
        # the open-and-not-finalised limb for completeness.

    # -- Open-and-not-finalised limb ---------------------------------------
    created_raw = pr.get("created_at") or pr.get("first_commit_at")
    if not created_raw:
        # No timestamp means we cannot evidence the PR's existence
        # at ``when``; treat as not-in-progress to avoid fabricating
        # signal (AAP §0.7.2.1 forbids fabrication).
        return False
    created = parse_iso(created_raw)
    if created >= when:
        return False
    merged_raw = pr.get("merged_at")
    if merged_raw:
        merged = parse_iso(merged_raw)
        if merged <= when:
            return False
    closed_raw = pr.get("closed_at")
    if closed_raw and not merged_raw:
        closed = parse_iso(closed_raw)
        if closed <= when:
            return False
    return True


def _pr_counts_for_in_progress(pr: dict[str, Any]) -> bool:
    """Apply the bot-exclusion rule for Metric 1.

    The user example in AAP §0.7.1 states: *"Exclude PRs from bot
    accounts other than Blitzy (branches prefixed with blitzy-)."*
    Thus a bot PR is admitted only when its head ref begins with
    ``blitzy-``; a non-bot PR is always admitted.
    """

    if not _pr_is_bot(pr):
        return True
    return _pr_head_branch(pr).startswith("blitzy-")


# ---------------------------------------------------------------------------
# Confidence helpers
# ---------------------------------------------------------------------------


def assign_confidence(source: str) -> tuple[str, str]:
    """Map a data-source description to a (confidence, rationale) pair.

    Confidence rubric (AAP §0.8.3):

    - **High** — direct count from an issue tracker or release
      catalogue (e.g. GitHub Issues API, GitHub Releases API).
    - **Medium** — approximated from git commit patterns or CI
      pipeline artefacts.
    - **Low** — inferred from an indirect proxy.

    The function operates on the lower-cased ``source`` string and
    matches well-known keywords. A future caller adding a new data
    source should update both the rubric in
    ``acceleration/observability/metrics.json`` and this function.

    Parameters
    ----------
    source : str
        Human-readable description of the data source that produced
        the metric value (e.g. ``"git PR merges"``,
        ``"GitHub Releases API"``).

    Returns
    -------
    tuple[str, str]
        ``(confidence, rationale)`` where confidence is one of
        ``"High"``, ``"Medium"``, ``"Low"`` and rationale is a short
        natural-language sentence ready for embedding in the report.
    """

    s = (source or "").lower()
    if (
        "issue tracker" in s
        or "github issues api" in s
        or "github releases api" in s
        or "audit log" in s
    ):
        return "High", f"Direct count from {source}."
    if (
        "git" in s
        or "commit" in s
        or "merge" in s
        or " pr " in f" {s} "
        or "pr-merge" in s
        or "github actions" in s
        or "junit" in s
        or "ci" in s
    ):
        return "Medium", f"Approximated from {source}."
    return "Low", f"Inferred from indirect proxy: {source}."


def insufficient_signal(
    reason: str, tried: list[str], needed: str
) -> dict[str, Any]:
    """Return the canonical Insufficient Signal record for a metric.

    Used by metric computers that lack their primary data source.
    The returned dict carries the required transparency fields
    (``tried`` + ``needed``) per AAP §0.8.2 (Agent Latitude) and
    sets confidence to ``"Insufficient signal"`` so the renderer
    knows to surface the metric in the Limitations section rather
    than reporting a fabricated number.

    Parameters
    ----------
    reason : str
        Short human-readable reason (filled into both ``value`` and
        ``boundary_conditions``).
    tried : list[str]
        Ordered list of data sources / methods the metric computer
        attempted before falling back. The renderer can quote these
        directly in the Limitations section.
    needed : str
        What additional access or data would have made the metric
        computable.

    Returns
    -------
    dict[str, Any]
        Insufficient-signal record with the canonical field set.
    """

    return {
        "value": f"Insufficient signal — {reason}",
        "multiplier": f"Insufficient signal — {reason}",
        "confidence": "Insufficient signal",
        "confidence_rationale": (
            f"Primary data source unavailable: {reason}."
        ),
        "tried": list(tried),
        "needed": needed,
        "boundary_conditions": reason,
        "phases": {},
    }


# ---------------------------------------------------------------------------
# Compute context + phase aggregator
# ---------------------------------------------------------------------------


@dataclass
class ComputeContext:
    """All-inputs container passed to every metric computer.

    Centralising the input set into a single dataclass keeps the
    metric-function signatures uniform (``compute_X(ctx) -> dict``),
    which in turn keeps the dispatch table in :func:`main` clean.
    """

    bounds: PhaseBounds
    commits: list[dict[str, Any]] = field(default_factory=list)
    prs: list[dict[str, Any]] = field(default_factory=list)
    reviews: list[dict[str, Any]] = field(default_factory=list)
    releases: list[dict[str, Any]] = field(default_factory=list)
    reverts: list[dict[str, Any]] = field(default_factory=list)
    # Annotated git tags emitted by ``extract_git.py`` as a fallback
    # secondary release source per AAP §0.1.3 ("release source precedence:
    # GitHub Releases → annotated semver tags → deployment events"). Each
    # record carries ``tag``, ``commit_sha``, ``tagger_date``,
    # ``commit_date``, ``object_type``, ``is_annotated``, ``is_semver``,
    # ``is_prerelease``. Optional: when ``tags.jsonl`` is absent the field
    # remains an empty list and the Releases metric degrades to the
    # GitHub Releases source alone (or "Insufficient signal" when neither
    # is available).
    tags: list[dict[str, Any]] = field(default_factory=list)
    # Deployment events from CI/CD — the tertiary release source per AAP
    # §0.1.3. When the github_access manifest enumerates ``deployments``
    # in its accessible endpoints, ``extract_github.py`` writes the
    # GitHub Deployments API records here. Each record carries
    # ``id``, ``sha``, ``ref``, ``environment``, ``created_at``,
    # ``updated_at``, and ``transient_environment`` / ``production_environment``
    # flags. Empty on Formbricks today because the public Deployments API
    # requires authenticated access for write-protected repositories.
    deployments: list[dict[str, Any]] = field(default_factory=list)
    test_results: list[dict[str, Any]] = field(default_factory=list)
    issues: list[dict[str, Any]] = field(default_factory=list)
    sla_source: dict[str, Any] = field(default_factory=dict)
    branch_protection: dict[str, Any] = field(default_factory=dict)
    audit_log: list[dict[str, Any]] = field(default_factory=list)
    github_access: dict[str, Any] = field(default_factory=dict)
    aliases: dict[str, dict[str, Any]] = field(default_factory=dict)


def phase_aggregate(
    values_by_phase: dict[str, list[Any]], op: str = "sum"
) -> dict[str, dict[str, Any]]:
    """Aggregate per-phase value lists into a phase → {value, multiplier} map.

    Supports four aggregation operations:

    - ``"sum"``    — sum of the per-window values in the phase.
    - ``"mean"``   — arithmetic mean of the per-window values.
    - ``"median"`` — median of the per-PR / per-record values.
    - ``"cov"``    — population standard deviation / mean
      (coefficient of variation). Used by
      :func:`compute_flow_predictability`.

    Multipliers are computed as ``phase_value / baseline_value``,
    rounded to three decimals. Division-by-zero is handled
    explicitly with a ``multiplier_kind`` sentinel — see the
    table below — so the JSON output remains RFC 8259 compliant
    (no ``NaN`` / ``Infinity`` tokens):

    +-------------------+-----------------+-----------------------+
    | baseline value    | phase value     | (multiplier, kind)    |
    +===================+=================+=======================+
    | nonzero           | any             | (ratio, "ratio")      |
    +-------------------+-----------------+-----------------------+
    | zero              | zero            | (``None``, "undefined")|
    +-------------------+-----------------+-----------------------+
    | zero              | nonzero         | (``None``, "infinite") |
    +-------------------+-----------------+-----------------------+
    | baseline phase    | n/a             | (1.0, "ratio")        |
    +-------------------+-----------------+-----------------------+

    Parameters
    ----------
    values_by_phase : dict[str, list]
        Per-phase numeric value lists. Missing phases are admitted
        as empty lists.
    op : str
        Aggregation operation; defaults to ``"sum"``.

    Returns
    -------
    dict[str, dict[str, Any]]
        ``{phase: {"value": ..., "multiplier": ..., "multiplier_kind": ...}}``
        for every phase present in the input. The baseline
        multiplier is always ``1.0`` with kind ``"ratio"``.
    """

    out: dict[str, dict[str, Any]] = {}
    for phase, vals in values_by_phase.items():
        numeric = [v for v in (vals or []) if isinstance(v, (int, float))]
        if not numeric:
            out[phase] = {
                "value": 0,
                "multiplier": 1.0 if phase == "baseline" else 0.0,
                "multiplier_kind": "ratio",
            }
            continue
        if op == "sum":
            value: float = float(sum(numeric))
        elif op == "mean":
            value = float(statistics.mean(numeric))
        elif op == "median":
            value = float(statistics.median(numeric))
        elif op == "cov":
            mean = statistics.mean(numeric)
            sd = statistics.pstdev(numeric) if len(numeric) > 1 else 0.0
            value = (sd / mean) if mean else 0.0
        else:
            value = float(sum(numeric))
        out[phase] = {
            "value": round(value, 4) if isinstance(value, float) else value
        }
    # Multipliers: phase_value / baseline_value (rounded to 3dp).
    # Edge cases produce ``multiplier=None`` (JSON ``null``) with a
    # ``multiplier_kind`` sentinel so downstream renderers can choose
    # between "n/a" (0 / 0 — no data) and "∞" (x / 0 — baseline absent
    # but phase value present). Using ``None`` rather than the Python
    # float ``nan``/``inf`` is REQUIRED because the JSON specification
    # (RFC 8259 §6) forbids ``NaN`` and ``Infinity`` tokens; ``null`` is
    # the canonical replacement.
    base = out.get("baseline", {}).get("value", 0)
    for phase, entry in out.items():
        if phase == "baseline":
            entry["multiplier"] = 1.0
            entry["multiplier_kind"] = "ratio"
            continue
        v = entry.get("value", 0)
        if not isinstance(v, (int, float)):
            entry["multiplier"] = None
            entry["multiplier_kind"] = "undefined"
            continue
        if base in (0, 0.0):
            if v == 0:
                entry["multiplier"] = None
                entry["multiplier_kind"] = "undefined"  # 0 / 0
            else:
                entry["multiplier"] = None
                entry["multiplier_kind"] = "infinite"  # x / 0
        else:
            entry["multiplier"] = round(v / base, 3)
            entry["multiplier_kind"] = "ratio"
    return out



# ---------------------------------------------------------------------------
# Per-metric implementations
# ---------------------------------------------------------------------------


def _iter_window_ends(
    earliest: datetime, latest: datetime, anchor_monday: datetime
) -> Iterable[datetime]:
    """Yield Monday-aligned 2-week window ends between earliest and latest.

    Used by Metric 1 (Flow Load) to step through the analysis
    horizon and take a snapshot at each window boundary. Each
    yielded value is the *end* of a window (exclusive), aligned to
    the 2-week cadence rooted at ``anchor_monday``.

    Parameters
    ----------
    earliest, latest : datetime.datetime
        Bounds of the iteration. Both must be UTC-aware.
    anchor_monday : datetime.datetime
        Monday that defines the 2-week cadence.

    Yields
    ------
    datetime.datetime
        Each window-end, in chronological order.
    """

    start = window_start_for(earliest, anchor_monday) + timedelta(weeks=2)
    cap = latest + timedelta(weeks=2)
    while start <= cap:
        yield start
        start = start + timedelta(weeks=2)


def compute_flow_load(ctx: ComputeContext) -> dict[str, Any]:
    """Metric 1 — Flow Load.

    Count of in-progress PRs at each window end, averaged across
    windows in each phase. The in-progress definition follows the
    AAP §0.7.1 user example verbatim: a PR is in-progress when it
    has at least one commit AND is open (not merged, not closed
    without merge), OR it is in draft state. Bot PRs are excluded
    unless their head branch starts with ``blitzy-``.

    Parameters
    ----------
    ctx : ComputeContext
        Computation context with parsed PR records.

    Returns
    -------
    dict
        Canonical metric record (see module-level docstring).
    """

    if not ctx.prs:
        return {"metric_id": "flow_load"} | insufficient_signal(
            "no PR records",
            tried=["acceleration/data/prs.jsonl from extract_git/extract_github"],
            needed="At least one PR-merge commit in the analysed history.",
        )

    anchor = ctx.bounds.anchor_monday
    # Determine the iteration horizon from the PR corpus itself, not
    # from a hard-coded date — this keeps the metric stable across
    # repositories of different ages.
    pr_dates: list[datetime] = []
    for p in ctx.prs:
        for key in ("created_at", "first_commit_at"):
            if p.get(key):
                pr_dates.append(parse_iso(p[key]))
                break
    for p in ctx.prs:
        if p.get("merged_at"):
            pr_dates.append(parse_iso(p["merged_at"]))
        elif p.get("closed_at"):
            pr_dates.append(parse_iso(p["closed_at"]))
    if not pr_dates:
        return {"metric_id": "flow_load"} | insufficient_signal(
            "PR records lack timestamps",
            tried=["created_at", "first_commit_at", "merged_at", "closed_at"],
            needed="PR records with at least one ISO 8601 timestamp.",
        )

    earliest = min(pr_dates)
    latest = max(pr_dates)
    by_phase: dict[str, list[int]] = defaultdict(list)
    for window_end in _iter_window_ends(earliest, latest, anchor):
        phase = ctx.bounds.phase_for(window_end - timedelta(seconds=1))
        count = sum(
            1
            for p in ctx.prs
            if _pr_was_in_progress_at(p, window_end)
            and _pr_counts_for_in_progress(p)
        )
        by_phase[phase].append(count)

    agg = phase_aggregate(by_phase, op="mean")
    conf, rationale = assign_confidence("git commit and PR-merge patterns")
    return {
        "metric_id": "flow_load",
        "phases": agg,
        "confidence": conf,
        "confidence_rationale": rationale,
        "direction_of_improvement": "lower",
        "extraction_command": (
            "git log + GitHub PR API (window-end snapshots at "
            "Monday-aligned 14-day intervals)"
        ),
        "boundary_conditions": (
            "In-progress = PR open or draft AND not merged AND not "
            "closed-without-merge. Bot PRs excluded unless head_ref "
            "starts with 'blitzy-' (AAP §0.7.1 user example)."
        ),
        "interpretation": "Mean in-progress PR count per 2-week window.",
    }


def compute_flow_velocity(ctx: ComputeContext) -> dict[str, Any]:
    """Metric 2 — Flow Velocity.

    Merged PRs per 2-week window, averaged across windows in each
    phase. Per-actor breakdown is produced for the per-engineer view
    (AAP §0.8.5).

    Parameters
    ----------
    ctx : ComputeContext
        Computation context.

    Returns
    -------
    dict
        Canonical metric record with ``phases`` and ``per_actor``.
    """

    if not ctx.prs:
        return {"metric_id": "flow_velocity"} | insufficient_signal(
            "no PR records",
            tried=["acceleration/data/prs.jsonl"],
            needed="At least one merged PR in the analysed history.",
        )

    counts_by_phase: Counter = Counter()
    actor_counts: dict[str, dict[str, int]] = defaultdict(
        lambda: defaultdict(int)
    )
    seen_windows: dict[str, set[datetime]] = defaultdict(set)

    for pr in ctx.prs:
        merged_raw = pr.get("merged_at")
        if not merged_raw:
            continue
        merged = parse_iso(merged_raw)
        phase = ctx.bounds.phase_for(merged)
        counts_by_phase[phase] += 1
        seen_windows[phase].add(window_start_for(merged, ctx.bounds.anchor_monday))
        actor_key = actor_key_for(_pr_author_email(pr), ctx.aliases)
        actor_counts[actor_key][phase] += 1

    rates_by_phase: dict[str, list[float]] = {}
    for phase, total in counts_by_phase.items():
        windows = max(1, len(seen_windows[phase]))
        rates_by_phase[phase] = [total / windows]
    agg = phase_aggregate(rates_by_phase, op="mean")

    per_actor: dict[str, dict[str, dict[str, Any]]] = {}
    for actor, phase_map in actor_counts.items():
        actor_rates: dict[str, list[float]] = {}
        for phase, total in phase_map.items():
            windows = max(1, len(seen_windows.get(phase) or set()))
            actor_rates[phase] = [total / windows]
        per_actor[actor] = phase_aggregate(actor_rates, op="mean")

    # Per-active-engineer normalisation (AAP §0.8.5: "Normalize for team
    # growth by measuring per active engineer where applicable"). Flow
    # Velocity is a count-style metric: raw merges per window doubles
    # when team size doubles, masking real productivity changes. The
    # normalised view divides by the count of distinct active engineers
    # in each phase, surfacing the per-person trajectory alongside the
    # team-level rate. Both views are emitted so renderers can show
    # either the headline or the normalised value as appropriate.
    active_by_phase = active_engineers_per_phase(ctx)
    normalised = normalise_phase_values_by_active_engineers(
        agg, active_by_phase
    )

    conf, rationale = assign_confidence("git PR-merge counts per 14-day window")
    return {
        "metric_id": "flow_velocity",
        "phases": agg,
        "phases_per_active_engineer": normalised,
        "active_engineers_per_phase": active_by_phase,
        "per_actor": per_actor,
        "confidence": conf,
        "confidence_rationale": rationale,
        "direction_of_improvement": "higher",
        "extraction_command": (
            "git log --merges --grep='(#[0-9]+)$' (PR-merge identification) + "
            "GitHub PR API for the API-only in-progress PRs"
        ),
        "boundary_conditions": (
            "Rate computed per Monday-aligned 2-week window in each "
            "phase; windows with zero merges are still counted. The "
            "``phases`` block holds the team-level rate; the "
            "``phases_per_active_engineer`` block divides by the count "
            "of distinct authors with ≥1 non-merge commit in the phase "
            "per AAP §0.8.5."
        ),
        "interpretation": (
            "Average merged PRs per 2-week window (team-level), with a "
            "per-active-engineer normalised view for team-growth "
            "correction."
        ),
    }


def compute_flow_predictability(ctx: ComputeContext) -> dict[str, Any]:
    """Metric 3 — Flow Predictability.

    Inverse of the velocity coefficient of variation (CoV) across
    the 2-week windows in each phase. Higher values indicate more
    consistent merge cadence. A CoV of zero (every window with
    identical merge count) collapses to a multiplier of 1.0
    rather than infinity.

    Parameters
    ----------
    ctx : ComputeContext

    Returns
    -------
    dict
        Canonical metric record with ``phases``.
    """

    if not ctx.prs:
        return {"metric_id": "flow_predictability"} | insufficient_signal(
            "no PR records",
            tried=["acceleration/data/prs.jsonl"],
            needed="At least one merged PR in the analysed history.",
        )

    velocity_per_window: dict[str, dict[datetime, int]] = defaultdict(
        lambda: defaultdict(int)
    )
    for pr in ctx.prs:
        merged_raw = pr.get("merged_at")
        if not merged_raw:
            continue
        merged = parse_iso(merged_raw)
        phase = ctx.bounds.phase_for(merged)
        window = window_start_for(merged, ctx.bounds.anchor_monday)
        velocity_per_window[phase][window] += 1

    inv_cov_by_phase: dict[str, list[float]] = {}
    for phase, windows in velocity_per_window.items():
        vals = list(windows.values())
        if not vals:
            inv_cov_by_phase[phase] = [0.0]
            continue
        mean = statistics.mean(vals)
        sd = statistics.pstdev(vals) if len(vals) > 1 else 0.0
        if mean == 0:
            inv_cov_by_phase[phase] = [0.0]
            continue
        cov = sd / mean
        # 1 / cov is the natural predictability score; when sd == 0
        # (single-window or perfectly uniform phase) we report 1.0
        # rather than infinity to keep the multiplier table readable.
        inv_cov_by_phase[phase] = [1.0 / cov if cov > 0 else 1.0]

    agg = phase_aggregate(inv_cov_by_phase, op="mean")
    conf, rationale = assign_confidence(
        "git PR-merge windowed counts (coefficient of variation)"
    )
    return {
        "metric_id": "flow_predictability",
        "phases": agg,
        "confidence": conf,
        "confidence_rationale": rationale,
        "direction_of_improvement": "higher",
        "extraction_command": (
            "git log --merges grouped by Monday-aligned 14-day window, "
            "then pstdev / mean"
        ),
        "boundary_conditions": (
            "Predictability score = 1 / CoV; CoV = pstdev(velocity) / "
            "mean(velocity). Phases with a single window report a CoV "
            "of zero and a score of 1.0."
        ),
        "interpretation": (
            "Inverse coefficient of variation of velocity across the "
            "phase's 2-week windows."
        ),
    }


def _ready_for_review_at(
    pr: dict[str, Any], pr_reviews: list[dict[str, Any]]
) -> datetime | None:
    """Compute the AAP §0.1.3 ready-for-review event timestamp for a PR.

    Per the user example in AAP §0.1.3 verbatim:

        Ready-for-review is the earliest of:
        (a) PR leaving draft state,
        (b) first review requested,
        (c) first commit by another author,
        (d) PR opened.

    The implementation matches the four limbs in order and returns
    the earliest available timestamp. Limbs whose underlying signal
    is unavailable (e.g. draft-state history is not exposed by the
    GitHub Pulls API) silently degrade — the remaining limbs still
    decide.

    Specifically:

    - (a) **PR leaving draft state.** GitHub exposes the *current*
      ``draft`` boolean (``extract_github.py:521``) but not the
      timestamp at which the PR left draft. When ``draft`` is
      ``False`` and ``created_at`` is available, we use
      ``created_at`` as a defensible upper bound (the PR was, at
      worst, non-draft at open time); when ``draft`` is ``True``
      today, limb (a) does not contribute.
    - (b) **First review requested.** The first review's
      ``submitted_at`` from ``reviews.jsonl`` (sorted ascending).
      "Review requested" is a distinct event in the GitHub timeline
      that the current ``extract_github.py`` does not capture
      separately; the first actual review submission is the
      tightest available proxy.
    - (c) **First commit by another author.** Per-commit-on-branch
      data is only recoverable from two-parent merges (squash-merge
      PRs collapse the branch into a single commit). When the
      branch metadata is available it is encoded in
      ``first_commit_at`` / ``last_commit_at`` / commit records;
      otherwise this limb does not contribute.
    - (d) **PR opened.** ``created_at`` from the GitHub Pulls API.

    Parameters
    ----------
    pr : dict
        A single PR record.
    pr_reviews : list[dict]
        All review records for this PR, sorted ascending by
        ``submitted_at``.

    Returns
    -------
    datetime or None
        The earliest available ready-for-review timestamp, or
        ``None`` when no signal can be evidenced.
    """

    candidates: list[datetime] = []
    # Limb (d): PR opened (created_at).
    created_raw = pr.get("created_at")
    if created_raw:
        try:
            candidates.append(parse_iso(created_raw))
        except (ValueError, TypeError):  # pragma: no cover - defensive
            pass
    # Limb (a): PR leaving draft state. When the PR is currently
    # non-draft and we have ``created_at``, we assume the leave-draft
    # event occurred no later than open time and reuse the limb (d)
    # signal (no separate signal available in the extractor today).
    # When ``draft`` is True today, limb (a) does not contribute.
    # When ``draft`` is False and ``created_at`` is absent, we cannot
    # bound the leave-draft event.
    # (Already handled by limb (d) above; no separate append needed.)
    # Limb (b): First review submission.
    for review in pr_reviews:
        submitted_raw = review.get("submitted_at")
        if not submitted_raw:
            continue
        try:
            candidates.append(parse_iso(submitted_raw))
            break  # earliest review only
        except (ValueError, TypeError):  # pragma: no cover - defensive
            continue
    # Limb (c): First commit by another author. Without per-commit-on
    # -branch data, we cannot evidence an author switch; this limb
    # silently degrades.
    if not candidates:
        return None
    return min(candidates)


def _pr_active_seconds(
    pr: dict[str, Any], pr_reviews: list[dict[str, Any]] | None = None
) -> tuple[float | None, str]:
    """Compute the AAP §0.3.4 Flow Active span for a PR.

    Per the AAP §0.3.4 specification, Flow Active is the sum of
    inclusive working-time spans:

    1. **Initial active span** = ``first_commit_at → ready_for_review_at``.
       The author worked from the first commit on the branch until
       the PR became ready for review (PR opened, first review
       requested, draft exit, or first co-author commit — earliest
       wins; see :func:`_ready_for_review_at`).
    2. **Refinement spans** = for each review event ``r_i``, the
       interval from ``r_i.submitted_at`` to the next event
       (``r_{i+1}.submitted_at`` or ``merged_at`` if ``r_i`` is the
       last review). Without per-commit-on-branch data we cannot
       narrow to "first commit after review → last commit before
       next review", so the proxy includes the post-review revision
       window; review-wait gaps between reviews still count as wait
       time (handled by Flow Efficiency, not Flow Active).

    The function returns ``(active_seconds, computation_method)``
    so the caller can record the method actually used in the metric's
    ``boundary_conditions``.

    Graceful degradation when the per-review/per-commit fields are
    unavailable:

    - When reviews are available, refinement spans are computed from
      review timestamps.
    - When reviews are unavailable but ``created_at`` and
      ``first_commit_at`` are present, the initial span alone is
      used; ``method`` is ``"initial_span_only"``.
    - When neither created_at nor reviews are available but
      ``first_commit_at`` and ``merged_at`` are present, the
      branch-life proxy ``first_commit_at → merged_at`` is used
      and ``method`` is ``"branch_life_proxy"``. The proxy
      overstates active time (includes review wait), and the
      boundary condition is recorded.
    - When even branch-life cannot be derived, returns ``(None, "")``.

    Parameters
    ----------
    pr : dict
        A single PR record.
    pr_reviews : list[dict] or None
        All reviews on this PR, sorted ascending by
        ``submitted_at``. ``None`` is treated as no reviews
        available.

    Returns
    -------
    tuple[float | None, str]
        ``(active_seconds, method)``. ``active_seconds`` is the
        summed inclusive working duration; ``None`` when no span
        could be derived. ``method`` is one of
        ``"ready_for_review_refinement"``,
        ``"initial_span_only"``, ``"branch_life_proxy"``, or
        ``""`` (when active_seconds is None).
    """

    reviews = pr_reviews or []
    explicit = pr.get("active_spans_seconds")
    if isinstance(explicit, (int, float)) and explicit > 0:
        return float(explicit), "explicit_field"
    first_raw = pr.get("first_commit_at")
    merged_raw = pr.get("merged_at")
    # Compute ready-for-review timestamp (initial span endpoint).
    ready_at = _ready_for_review_at(pr, reviews)
    # Path 1: full ready-for-review + refinement-spans computation.
    if first_raw and ready_at is not None:
        first_at = parse_iso(first_raw)
        # Initial span: first_commit_at → ready_for_review_at.
        # The user prompt requires "inclusive durations; do not subtract
        # idle gaps within a span", so we use raw elapsed time. The
        # span is clamped to >= 0 to defend against records where
        # ready_at is recorded *before* first_commit_at (data error).
        initial = max(0.0, (ready_at - first_at).total_seconds())
        # Refinement spans: each review.submitted_at → next event.
        refinement = 0.0
        review_times: list[datetime] = []
        for review in reviews:
            submitted_raw = review.get("submitted_at")
            if not submitted_raw:
                continue
            try:
                review_times.append(parse_iso(submitted_raw))
            except (ValueError, TypeError):  # pragma: no cover - defensive
                continue
        review_times.sort()
        # Skip the very first review when it coincides with
        # ready-for-review (limb (b) of the ready_for_review_at
        # selection); the initial-span endpoint already accounts for
        # it. Subsequent reviews drive refinement spans.
        if review_times and review_times[0] == ready_at:
            review_iter = review_times[1:]
        else:
            review_iter = review_times
        merged_at = parse_iso(merged_raw) if merged_raw else None
        for i, review_at in enumerate(review_iter):
            next_event_at: datetime | None
            if i + 1 < len(review_iter):
                next_event_at = review_iter[i + 1]
            else:
                next_event_at = merged_at
            if next_event_at is None:
                continue
            refinement += max(0.0, (next_event_at - review_at).total_seconds())
        total = initial + refinement
        if total > 0:
            method = (
                "ready_for_review_refinement"
                if review_iter
                else "initial_span_only"
            )
            return float(total), method
    # Path 2: branch-life proxy. Documented as Medium-confidence proxy.
    if first_raw and merged_raw:
        span = (parse_iso(merged_raw) - parse_iso(first_raw)).total_seconds()
        if span > 0:
            return float(span), "branch_life_proxy"
    return None, ""


def _index_reviews_by_pr(
    reviews: list[dict[str, Any]],
) -> dict[Any, list[dict[str, Any]]]:
    """Group review records by ``pr_number``, sorted ascending by ``submitted_at``.

    Parameters
    ----------
    reviews : list[dict]
        The decoded ``reviews.jsonl`` records.

    Returns
    -------
    dict[Any, list[dict[str, Any]]]
        Mapping from PR number to ascending-ordered review list.
    """

    by_pr: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    for review in reviews:
        pr_number = review.get("pr_number")
        if pr_number is None:
            continue
        by_pr[pr_number].append(review)
    for pr_number, items in by_pr.items():
        items.sort(key=lambda r: r.get("submitted_at") or "")
    return by_pr


def compute_flow_active(ctx: ComputeContext) -> dict[str, Any]:
    """Metric 4 — Flow Active.

    Median active working-time per PR (in hours), measured as the
    sum of inclusive working spans per AAP §0.3.4:

    1. **Initial span** = ``first_commit_at → ready_for_review_at``.
       ``ready_for_review_at`` is the earliest of (a) PR leaving
       draft state, (b) first review requested/submitted, (c) first
       commit by another author, (d) PR opened — see
       :func:`_ready_for_review_at`.
    2. **Refinement spans** = for each review event, the interval
       from ``review.submitted_at`` to the next review's
       ``submitted_at`` (or ``merged_at`` for the last review).

    Per AAP §0.8.1 (Engineering Actor Framing), per-actor breakdown
    includes Blitzy Agent as one row in the after period; the same
    code path runs with only the actor identity substituted.

    Graceful degradation when reviews / created_at are unavailable:

    - With reviews available: full ready-for-review + refinement
      computation (``method=ready_for_review_refinement``).
    - With ``created_at`` but no reviews: initial span only
      (``method=initial_span_only``).
    - With only branch-life timestamps (``first_commit_at`` and
      ``merged_at``): branch-life proxy (``method=branch_life_proxy``);
      this overstates active time and the boundary_conditions string
      records the proxy.

    Parameters
    ----------
    ctx : ComputeContext

    Returns
    -------
    dict
        Canonical metric record with ``phases`` and ``per_actor``.
    """

    reviews_by_pr = _index_reviews_by_pr(ctx.reviews)

    by_phase: dict[str, list[float]] = defaultdict(list)
    actor_phase: dict[str, dict[str, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )
    excluded = 0
    total_merged = 0
    method_counts: Counter = Counter()
    for pr in ctx.prs:
        merged_raw = pr.get("merged_at")
        if not merged_raw:
            continue
        total_merged += 1
        pr_reviews = reviews_by_pr.get(pr.get("number")) or []
        active, method = _pr_active_seconds(pr, pr_reviews)
        if active is None:
            excluded += 1
            continue
        method_counts[method] += 1
        merged = parse_iso(merged_raw)
        phase = ctx.bounds.phase_for(merged)
        hours = active / 3600.0
        by_phase[phase].append(hours)
        actor_key = actor_key_for(_pr_author_email(pr), ctx.aliases)
        actor_phase[actor_key][phase].append(hours)

    if not any(by_phase.values()):
        return {"metric_id": "flow_active"} | insufficient_signal(
            "no PR records carried sufficient timing data to compute Flow Active",
            tried=[
                "prs.jsonl active_spans_seconds field",
                "reviews.jsonl + first_commit_at (ready-for-review + refinement spans)",
                "first_commit_at + created_at (initial span only)",
                "first_commit_at + merged_at (branch-life proxy)",
            ],
            needed=(
                "PR records with branch-history timestamps (only "
                "true two-parent merges yield first_commit_at; "
                "squash-merge repositories require GitHub API or "
                "branch reflog access) and ideally reviews.jsonl for "
                "ready-for-review + refinement-span semantics."
            ),
        )

    agg = phase_aggregate(by_phase, op="median")
    per_actor: dict[str, dict[str, dict[str, Any]]] = {
        actor: phase_aggregate(phase_map, op="median")
        for actor, phase_map in actor_phase.items()
    }
    # Confidence reflects the dominant computation method used.
    dominant_method = (
        method_counts.most_common(1)[0][0] if method_counts else ""
    )
    if dominant_method == "explicit_field":
        conf, rationale = assign_confidence(
            "explicit active_spans_seconds field on PR records"
        )
    elif dominant_method == "ready_for_review_refinement":
        conf, rationale = assign_confidence(
            "GitHub reviews API timestamps + git first-commit (Flow Active "
            "ready-for-review + refinement spans)"
        )
    elif dominant_method == "initial_span_only":
        conf, rationale = assign_confidence(
            "git first-commit and created_at timestamps (Flow Active initial span only)"
        )
    else:
        conf, rationale = assign_confidence(
            "git first-commit and merge timestamps (Flow Active proxy)"
        )
    method_label_by_count = ", ".join(
        f"{method}={count}" for method, count in sorted(method_counts.items())
    )
    return {
        "metric_id": "flow_active",
        "phases": agg,
        "per_actor": per_actor,
        "confidence": conf,
        "confidence_rationale": rationale,
        "direction_of_improvement": "lower",
        "extraction_command": (
            "Flow Active = initial(first_commit_at → ready_for_review_at) + "
            "Σ refinement(review_n → review_{n+1} OR merged_at) per PR"
        ),
        "boundary_conditions": (
            f"Excluded {excluded}/{total_merged} merged PRs lacking the "
            f"timing data required for any computation path. Computation "
            f"methods used: {method_label_by_count or 'none'}. The "
            f"branch_life_proxy method overstates active time because it "
            f"includes review-wait intervals; subsequent runs with "
            f"reviews.jsonl populated migrate those PRs to "
            f"ready_for_review_refinement."
        ),
        "interpretation": "Median active working-time per PR (hours).",
    }


def compute_flow_efficiency(ctx: ComputeContext) -> dict[str, Any]:
    """Metric 5 — Flow Efficiency.

    Median ratio of active working-time to total flow-time per PR.
    Result lies in ``[0, 1]``. Higher values indicate less idle
    waiting between code activity bursts and merge.

    Per AAP §0.3.4: ``Flow Efficiency = Flow Active / Flow Time``
    per PR; median across PRs per phase. Active time uses the same
    ready-for-review + refinement-spans computation as
    :func:`compute_flow_active` (NOT the branch-life proxy), so when
    reviews.jsonl is populated the ratio correctly reflects the
    fraction of total flow time spent actively coding versus
    waiting on review.

    When reviews are unavailable and the only computation method is
    the branch-life proxy, the active span equals flow time and the
    ratio is pinned to 1.0; the boundary_conditions string records
    this so consumers do not interpret a 1.0 reading as "perfect
    efficiency" — it indicates the proxy was used.

    Parameters
    ----------
    ctx : ComputeContext

    Returns
    -------
    dict
        Canonical metric record with ``phases`` and ``per_actor``.
    """

    reviews_by_pr = _index_reviews_by_pr(ctx.reviews)

    by_phase: dict[str, list[float]] = defaultdict(list)
    actor_phase: dict[str, dict[str, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )
    excluded = 0
    total_merged = 0
    method_counts: Counter = Counter()
    for pr in ctx.prs:
        merged_raw = pr.get("merged_at")
        if not merged_raw:
            continue
        total_merged += 1
        first_raw = pr.get("first_commit_at")
        if not first_raw:
            excluded += 1
            continue
        first_commit = parse_iso(first_raw)
        merged = parse_iso(merged_raw)
        flow_time = (merged - first_commit).total_seconds()
        if flow_time <= 0:
            excluded += 1
            continue
        pr_reviews = reviews_by_pr.get(pr.get("number")) or []
        active, method = _pr_active_seconds(pr, pr_reviews)
        if active is None or active <= 0:
            excluded += 1
            continue
        method_counts[method] += 1
        ratio = max(0.0, min(1.0, active / flow_time))
        phase = ctx.bounds.phase_for(merged)
        by_phase[phase].append(ratio)
        actor_key = actor_key_for(_pr_author_email(pr), ctx.aliases)
        actor_phase[actor_key][phase].append(ratio)

    if not any(by_phase.values()):
        return {"metric_id": "flow_efficiency"} | insufficient_signal(
            "no PR records carried sufficient timing data to compute Flow Efficiency",
            tried=[
                "active_spans_seconds + (merged_at - first_commit_at)",
                "ready-for-review + refinement spans / flow-time",
                "initial span / flow-time",
            ],
            needed=(
                "PR records with both first_commit_at and merged_at "
                "(typically requires two-parent merges or GitHub API). "
                "reviews.jsonl is required to compute the active span "
                "as a strict fraction of flow time; without it the "
                "active span pins to flow-time and the ratio is 1.0."
            ),
        )

    agg = phase_aggregate(by_phase, op="median")
    per_actor: dict[str, dict[str, dict[str, Any]]] = {
        actor: phase_aggregate(phase_map, op="median")
        for actor, phase_map in actor_phase.items()
    }
    dominant_method = (
        method_counts.most_common(1)[0][0] if method_counts else ""
    )
    if dominant_method == "ready_for_review_refinement":
        conf, rationale = assign_confidence(
            "reviews API + git first-commit ratio (true active fraction)"
        )
    elif dominant_method == "initial_span_only":
        conf, rationale = assign_confidence(
            "git first-commit / created_at ratio (initial-span fraction)"
        )
    else:
        conf, rationale = assign_confidence(
            "git first-commit / active-span and total flow-time ratios"
        )
    method_label_by_count = ", ".join(
        f"{method}={count}" for method, count in sorted(method_counts.items())
    )
    return {
        "metric_id": "flow_efficiency",
        "phases": agg,
        "per_actor": per_actor,
        "confidence": conf,
        "confidence_rationale": rationale,
        "direction_of_improvement": "higher",
        "extraction_command": (
            "Flow Active (ready-for-review + refinement) / "
            "(merged_at - first_commit_at) per PR"
        ),
        "boundary_conditions": (
            f"Excluded {excluded}/{total_merged} merged PRs lacking "
            f"first_commit_at or producing a non-positive flow-time. "
            f"Computation methods used: {method_label_by_count or 'none'}. "
            f"When the branch_life_proxy is the only available method "
            f"the active span equals flow time and the ratio is pinned "
            f"to 1.0 (treat as 'reviews data unavailable', not as "
            f"'perfect efficiency')."
        ),
        "interpretation": (
            "Median ratio of active work-time to total flow-time per PR."
        ),
    }



def compute_flow_distribution(ctx: ComputeContext) -> dict[str, Any]:
    """Metric 6 — Flow Distribution.

    Distribution of merged PRs across four work-type buckets
    (feature / defect / risk_compliance / tech_debt) plus the
    ``unknown`` fallback. The metric records, per phase:

    - ``value`` — a fractional-mix dictionary
      ``{work_type: fraction}`` summing to 1.0.
    - ``multiplier`` — for non-baseline phases, the sum of absolute
      per-bucket differences from the baseline mix. A multiplier of
      0 means identical distribution to baseline; the theoretical
      maximum is 2.0 (complete reshuffle).

    Per AAP §0.3.4, when the unknown rate exceeds 20% in any phase
    the metric's confidence is downgraded to ``"Low"``.

    Parameters
    ----------
    ctx : ComputeContext

    Returns
    -------
    dict
        Canonical metric record with ``phases`` and ``per_actor``.
    """

    by_phase: dict[str, Counter] = defaultdict(Counter)
    totals: Counter = Counter()
    unknown_counts: Counter = Counter()
    actor_phase: dict[str, dict[str, Counter]] = defaultdict(
        lambda: defaultdict(Counter)
    )

    for pr in ctx.prs:
        merged_raw = pr.get("merged_at")
        if not merged_raw:
            continue
        merged = parse_iso(merged_raw)
        phase = ctx.bounds.phase_for(merged)
        work_type = _pr_work_type(pr)
        by_phase[phase][work_type] += 1
        totals[phase] += 1
        if work_type == "unknown":
            unknown_counts[phase] += 1
        actor_key = actor_key_for(_pr_author_email(pr), ctx.aliases)
        actor_phase[actor_key][phase][work_type] += 1

    if not totals:
        return {"metric_id": "flow_distribution"} | insufficient_signal(
            "no merged PRs to classify",
            tried=["prs.jsonl work_type field from classify_prs.py"],
            needed="At least one merged PR with a classifiable title or linked issue.",
        )

    distributions: dict[str, dict[str, float]] = {}
    for phase, counter in by_phase.items():
        total = totals[phase] or 1
        distributions[phase] = {
            wt: round(counter.get(wt, 0) / total, 4) for wt in WORK_TYPES
        }
    baseline_dist = distributions.get("baseline", {wt: 0.0 for wt in WORK_TYPES})

    phases_out: dict[str, dict[str, Any]] = {}
    for phase, dist in distributions.items():
        if phase == "baseline":
            phases_out[phase] = {"value": dist, "multiplier": 1.0}
            continue
        diff = sum(abs(dist.get(wt, 0) - baseline_dist.get(wt, 0)) for wt in WORK_TYPES)
        phases_out[phase] = {"value": dist, "multiplier": round(diff, 3)}

    unknown_rates = {
        phase: round(unknown_counts.get(phase, 0) / totals[phase], 4)
        for phase in totals
        if totals[phase]
    }
    if any(rate > 0.20 for rate in unknown_rates.values()):
        conf, rationale = (
            "Low",
            (
                "Unknown work_type rate exceeds 20% in at least one phase "
                "(per-phase rates: "
                f"{unknown_rates}); downgraded per AAP §0.3.4."
            ),
        )
    else:
        conf, rationale = assign_confidence(
            "PR work_type classification (classify_prs.py)"
        )

    per_actor: dict[str, dict[str, dict[str, Any]]] = {}
    for actor, phase_map in actor_phase.items():
        actor_entry: dict[str, dict[str, Any]] = {}
        for phase, counter in phase_map.items():
            total = sum(counter.values()) or 1
            actor_entry[phase] = {
                "value": {wt: round(counter.get(wt, 0) / total, 4) for wt in WORK_TYPES},
                "multiplier": 1.0 if phase == "baseline" else 0.0,
            }
        per_actor[actor] = actor_entry

    return {
        "metric_id": "flow_distribution",
        "phases": phases_out,
        "per_actor": per_actor,
        "confidence": conf,
        "confidence_rationale": rationale,
        "direction_of_improvement": "n/a",
        "extraction_command": (
            "PR work_type field set by classify_prs.py (linked-issue "
            "labels → conventional-commit prefix → keyword match → "
            "unknown)"
        ),
        "boundary_conditions": (
            f"Unknown rate per phase: {unknown_rates}. Multiplier is "
            "the sum of absolute per-bucket differences vs baseline "
            "(0 = identical, 2 = complete reshuffle)."
        ),
        "interpretation": (
            "Fractional distribution of merged PRs across work types: "
            "feature, defect, risk_compliance, tech_debt, unknown."
        ),
    }


def compute_flow_time(ctx: ComputeContext) -> dict[str, Any]:
    """Metric 7 — Flow Time.

    Median wall-clock hours from the first commit on the PR branch
    to the merge commit on main. Excludes PRs lacking a recoverable
    first-commit timestamp (typical for squash-merge repositories
    when only git-history data is available); the exclusion rate is
    surfaced in ``boundary_conditions``.

    Parameters
    ----------
    ctx : ComputeContext

    Returns
    -------
    dict
        Canonical metric record with ``phases``.
    """

    by_phase: dict[str, list[float]] = defaultdict(list)
    excluded = 0
    total_merged = 0
    for pr in ctx.prs:
        merged_raw = pr.get("merged_at")
        if not merged_raw:
            continue
        total_merged += 1
        first_raw = pr.get("first_commit_at")
        if not first_raw:
            excluded += 1
            continue
        flow_time = (parse_iso(merged_raw) - parse_iso(first_raw)).total_seconds()
        if flow_time <= 0:
            excluded += 1
            continue
        merged = parse_iso(merged_raw)
        phase = ctx.bounds.phase_for(merged)
        by_phase[phase].append(flow_time / 3600.0)

    if not any(by_phase.values()):
        return {"metric_id": "flow_time"} | insufficient_signal(
            "no PR records carried first_commit_at + merged_at",
            tried=["prs.jsonl first_commit_at and merged_at fields"],
            needed=(
                "PR records with both first_commit_at and merged_at "
                "(squash-merge repositories require GitHub API access "
                "to reconstruct branch history)."
            ),
        )

    agg = phase_aggregate(by_phase, op="median")
    conf, rationale = assign_confidence(
        "git first-commit and merge timestamps (Flow Time)"
    )
    return {
        "metric_id": "flow_time",
        "phases": agg,
        "confidence": conf,
        "confidence_rationale": rationale,
        "direction_of_improvement": "lower",
        "extraction_command": (
            "merged_at - first_commit_at per PR (PR-branch-life proxy)"
        ),
        "boundary_conditions": (
            f"Excluded {excluded}/{total_merged} merged PRs lacking "
            "branch-history timestamps or producing a non-positive interval."
        ),
        "interpretation": (
            "Median wall-clock hours from first branch commit to merge."
        ),
    }


def compute_problem_records(ctx: ComputeContext) -> dict[str, Any]:
    """Metric 8 — Problem Records.

    Counts incident-labelled issues per phase when an issue tracker
    is accessible. Falls back to git-revert counts when no incident
    labels are found, with confidence downgraded to Medium. Returns
    Insufficient Signal when neither signal is available.

    Parameters
    ----------
    ctx : ComputeContext

    Returns
    -------
    dict
        Canonical metric record with ``phases``.
    """

    incident_label_aliases = {"incident", "outage", "p0", "sev-1", "sev1"}
    incident_counts: Counter = Counter()
    for issue in ctx.issues:
        labels = {(lbl or "").lower() for lbl in (issue.get("labels") or [])}
        if labels & incident_label_aliases:
            created_raw = issue.get("created_at")
            if not created_raw:
                continue
            incident_counts[ctx.bounds.phase_for(parse_iso(created_raw))] += 1

    # Per AAP §0.3.4 revert attribution: count ONLY reverts whose
    # original commit is identifiable (explicit "Reverts commit <SHA>"
    # message reference or tree-match against a prior commit's
    # parent). Reverts whose original cannot be identified are
    # excluded as "unattributable" and reverts-of-reverts are
    # excluded by ``extract_git.py`` upstream. The
    # ``original_resolution`` field on each revert record is the
    # canonical attribution flag:
    #   - "explicit_message_reference" — exact SHA cited in revert body
    #   - "tree_match"                  — parent-tree match
    #   - "unresolved"                  — neither path succeeded (EXCLUDE)
    revert_counts: Counter = Counter()
    revert_excluded_by_phase: Counter = Counter()
    total_reverts = 0
    for revert in ctx.reverts:
        total_reverts += 1
        when_raw = (
            revert.get("revert_committed_at")
            or revert.get("revert_date")
            or revert.get("author_date")
        )
        if not when_raw:
            continue
        phase = ctx.bounds.phase_for(parse_iso(when_raw))
        resolution = (revert.get("original_resolution") or "").lower()
        original_sha = revert.get("original_sha")
        # Exclude unattributable reverts per AAP §0.3.4. The
        # canonical "unresolved" resolution flag, an explicit None
        # original_sha, or any non-attributing resolution removes the
        # revert from the count and increments the per-phase
        # exclusion counter for the boundary_conditions string.
        if (
            resolution == "unresolved"
            or original_sha is None
            or original_sha == ""
        ):
            revert_excluded_by_phase[phase] += 1
            continue
        if resolution not in {
            "explicit_message_reference",
            "tree_match",
            "explicit_reference",  # accept synonyms used by past extractors
            "tree_match_against_parent",
        } and resolution != "":
            # Unrecognised resolution flag — treat as unattributable
            # to err on the side of not counting noise.
            revert_excluded_by_phase[phase] += 1
            continue
        revert_counts[phase] += 1

    if sum(incident_counts.values()) > 0:
        by_phase = {p: [incident_counts.get(p, 0)] for p in ctx.bounds.phases()}
        agg = phase_aggregate(by_phase, op="sum")
        return {
            "metric_id": "problem_records",
            "phases": agg,
            "confidence": "High",
            "confidence_rationale": (
                "Direct count from issue-tracker incident labels."
            ),
            "direction_of_improvement": "lower",
            "extraction_command": (
                "GitHub Issues label IN (incident, outage, p0, sev-1)"
            ),
            "interpretation": (
                "Count of incident-labelled issues opened per phase."
            ),
        }
    if sum(revert_counts.values()) > 0:
        by_phase = {p: [revert_counts.get(p, 0)] for p in ctx.bounds.phases()}
        agg = phase_aggregate(by_phase, op="sum")
        excluded_total = sum(revert_excluded_by_phase.values())
        excluded_summary = (
            ", ".join(
                f"{phase}={count}"
                for phase, count in sorted(revert_excluded_by_phase.items())
            )
            if excluded_total
            else "none"
        )
        return {
            "metric_id": "problem_records",
            "phases": agg,
            "confidence": "Medium",
            "confidence_rationale": (
                "Approximated from git revert commits (no incident "
                "labels were available in the issue tracker)."
            ),
            "direction_of_improvement": "lower",
            "extraction_command": (
                "git log --grep='^Revert ' (extract_git.py reverts.jsonl) "
                "AND original_resolution IN "
                "('explicit_message_reference', 'tree_match')"
            ),
            "boundary_conditions": (
                f"Revert commits are a proxy for production incidents per "
                f"AAP §0.3.4. Counted only reverts with a resolved "
                f"original commit (explicit message reference or "
                f"tree-match). Excluded {excluded_total}/{total_reverts} "
                f"unattributable reverts (per-phase: {excluded_summary}); "
                f"these would otherwise inflate the count with "
                f"revert-of-revert noise and revert commits whose "
                f"original commit cannot be identified."
            ),
            "interpretation": (
                "Count of attributable revert commits per phase "
                "(incident proxy)."
            ),
        }
    return {"metric_id": "problem_records"} | insufficient_signal(
        "no incident labels and no attributable revert commits in the analysed history",
        tried=[
            "GitHub Issues labels: incident, outage, p0, sev-1",
            "git reverts.jsonl from extract_git.py (attributable only — "
            "unresolved/unattributable reverts excluded per AAP §0.3.4)",
        ],
        needed=(
            "An issue-tracker incident-label taxonomy OR a pager / "
            "on-call incident export."
        ),
    )


def _aggregate_release_events(
    events: list[tuple[datetime, bool]],
    ctx: ComputeContext,
) -> tuple[dict[str, list[float]], dict[str, int]]:
    """Aggregate (timestamp, is_prerelease) events into per-phase rate lists.

    Helper for :func:`compute_releases`. Each event is bucketed into the
    phase covering its timestamp; prereleases are tallied separately and
    excluded from the rate computation. The rate is
    ``non_prerelease_count / distinct_windows_seen`` so a single window
    with three releases reports a higher rate than three windows with
    one release each — the Flow Framework's standard "Deployment
    Frequency" definition.

    Parameters
    ----------
    events : list[tuple[datetime, bool]]
        ``(published_at, is_prerelease)`` pairs.
    ctx : ComputeContext
        Provides phase bounds and the Monday anchor for window keys.

    Returns
    -------
    tuple[dict, dict]
        ``(rates_by_phase, prerelease_counts_by_phase)``.
    """

    counts_by_phase: Counter = Counter()
    prerelease_counts: Counter = Counter()
    seen_windows: dict[str, set[datetime]] = defaultdict(set)
    for published, is_prerelease in events:
        phase = ctx.bounds.phase_for(published)
        if is_prerelease:
            prerelease_counts[phase] += 1
            continue
        counts_by_phase[phase] += 1
        seen_windows[phase].add(
            window_start_for(published, ctx.bounds.anchor_monday)
        )
    rates_by_phase: dict[str, list[float]] = {}
    for phase, total in counts_by_phase.items():
        windows = max(1, len(seen_windows[phase]))
        rates_by_phase[phase] = [total / windows]
    return rates_by_phase, dict(prerelease_counts)


def _release_events_from_github_releases(
    ctx: ComputeContext,
) -> list[tuple[datetime, bool]]:
    """Extract ``(published_at, is_prerelease)`` events from GitHub Releases.

    AAP §0.1.3 release source precedence (1). A release is considered
    prerelease iff either ``prerelease=True`` in the API response **or**
    the tag name matches the regex defined in
    :data:`_PRERELEASE_SUFFIX_RE`.

    Records without any timestamp are skipped silently (no useful
    bucketing is possible for an undated event).
    """

    events: list[tuple[datetime, bool]] = []
    for release in ctx.releases:
        published_raw = release.get("published_at") or release.get("created_at")
        if not published_raw:
            continue
        try:
            published = parse_iso(published_raw)
        except (ValueError, TypeError):
            continue
        tag = (release.get("tag_name") or "").strip()
        is_prerelease = bool(release.get("prerelease")) or bool(
            tag and _PRERELEASE_SUFFIX_RE.search(tag)
        )
        events.append((published, is_prerelease))
    return events


def _release_events_from_tags(
    ctx: ComputeContext,
) -> list[tuple[datetime, bool]]:
    """Extract ``(tagger_date, is_prerelease)`` events from annotated tags.

    AAP §0.1.3 release source precedence (2). Only **annotated** semver
    tags qualify as a release proxy — lightweight tags (``object_type ==
    "commit"``) are convenient SHAs but do not constitute a release
    decision. Tags that do not match the semver pattern
    (``v?\\d+\\.\\d+\\.\\d+``) are skipped.

    The timestamp preference order is:

    1. ``tagger_date`` (when the tag itself was created — the closest
       analogue to ``published_at`` on a GitHub Release).
    2. ``commit_date`` (when the underlying commit was authored).

    Records that produce neither timestamp are skipped silently.
    """

    events: list[tuple[datetime, bool]] = []
    for record in ctx.tags:
        if not record.get("is_annotated"):
            continue
        if not record.get("is_semver"):
            continue
        when_raw = (
            (record.get("tagger_date") or "").strip()
            or (record.get("commit_date") or "").strip()
        )
        if not when_raw:
            continue
        try:
            when = parse_iso(when_raw)
        except (ValueError, TypeError):
            continue
        events.append((when, bool(record.get("is_prerelease"))))
    return events


def _release_events_from_deployments(
    ctx: ComputeContext,
) -> list[tuple[datetime, bool]]:
    """Extract ``(created_at, is_prerelease)`` events from deployment events.

    AAP §0.1.3 release source precedence (3). Only deployments to
    *production* environments count toward the release rate; preview /
    staging / development deployments are noise for this metric. The
    GitHub Deployments API marks production environments via the
    ``production_environment`` flag (truthy) or by an explicit
    environment name in the AAP-recognised set (``production``,
    ``prod``).

    Prereleases are not a deployment concept; this source therefore
    reports ``is_prerelease=False`` for every event.
    """

    events: list[tuple[datetime, bool]] = []
    production_envs = {"production", "prod"}
    for record in ctx.deployments:
        env_raw = record.get("environment")
        env = env_raw.lower() if isinstance(env_raw, str) else ""
        is_production = (
            bool(record.get("production_environment"))
            or env in production_envs
        )
        if not is_production:
            continue
        when_raw = record.get("created_at") or record.get("updated_at")
        if not when_raw:
            continue
        try:
            when = parse_iso(when_raw)
        except (ValueError, TypeError):
            continue
        events.append((when, False))
    return events


def compute_releases(ctx: ComputeContext) -> dict[str, Any]:
    """Metric 9 — Releases.

    Average number of non-prerelease release events per 2-week window
    in each phase. Implements the AAP §0.1.3 **release source
    precedence** (verbatim): "(1) GitHub Releases / GitLab Releases API,
    (2) annotated git tags matching semver pattern v?\\d+\\.\\d+\\.\\d+,
    (3) deployment events from CI/CD if accessible. Prerelease tags
    (matching -alpha, -beta, -rc, -dev suffixes) are excluded from the
    primary count and reported separately."

    Precedence cascade (each level falls through to the next iff the
    higher-priority source yields zero non-prerelease events):

    1. **GitHub Releases API** — High confidence ("direct counts in
       issue tracker"-equivalent: the release API is the authoritative
       publication record for repositories that use GitHub Releases as
       their distribution channel, which Formbricks does per
       ``formbricks-release.yml`` triggering on ``release.published``).
    2. **Annotated semver git tags** — Medium confidence
       ("approximated from git commit patterns"-equivalent: tags are
       declarative and intentional, but tagging without publishing a
       Release omits the release notes / asset bundle that distinguish
       a "release" from a "tag").
    3. **CI/CD deployment events** — Low confidence ("inferred from
       indirect proxies"-equivalent: deployments are operational
       events, not release decisions; a deployment may be a rollback
       or a hotfix that does not correspond to a versioned release).

    Confidence is assigned per the rubric in AAP §0.8.3 based on the
    source that actually produced events at runtime, NOT the
    theoretically-preferred source. The ``data_source`` field in the
    returned record records the chosen source explicitly so the report
    renderer can include it in the boundary-conditions paragraph.

    Parameters
    ----------
    ctx : ComputeContext

    Returns
    -------
    dict
        Canonical metric record with ``phases``, ``data_source``,
        ``confidence``, ``confidence_rationale``, ``extraction_command``,
        and ``boundary_conditions``.
    """

    # ---- Level 1: GitHub Releases API ----
    gh_release_events = _release_events_from_github_releases(ctx)
    gh_accessible = (
        "releases" in (ctx.github_access.get("endpoints_accessible") or [])
        or bool(ctx.releases)
    )
    if gh_release_events:
        rates_by_phase, prerelease_counts = _aggregate_release_events(
            gh_release_events, ctx
        )
        if rates_by_phase:
            agg = phase_aggregate(rates_by_phase, op="mean")
            conf, rationale = assign_confidence("GitHub Releases API")
            return {
                "metric_id": "releases",
                "phases": agg,
                "data_source": "github_releases",
                "confidence": conf,
                "confidence_rationale": rationale,
                "direction_of_improvement": "higher",
                "extraction_command": "GET /repos/{owner}/{repo}/releases",
                "boundary_conditions": (
                    f"Prereleases excluded from primary count: "
                    f"{prerelease_counts or '{}'}."
                ),
                "interpretation": (
                    "Average non-prerelease GitHub Releases per 2-week window."
                ),
            }
        # GitHub Releases were accessible but every event was a prerelease;
        # this is reported under the appropriate signal below.

    # ---- Level 2: Annotated semver git tags ----
    tag_events = _release_events_from_tags(ctx)
    if tag_events:
        rates_by_phase, prerelease_counts = _aggregate_release_events(
            tag_events, ctx
        )
        if rates_by_phase:
            agg = phase_aggregate(rates_by_phase, op="mean")
            conf, rationale = assign_confidence(
                "annotated git tags matching semver pattern "
                "(secondary release-source proxy via git for-each-ref)"
            )
            tags_total = sum(
                1
                for r in ctx.tags
                if r.get("is_annotated") and r.get("is_semver")
            )
            skipped = sum(
                1
                for r in ctx.tags
                if not r.get("is_annotated") or not r.get("is_semver")
            )
            return {
                "metric_id": "releases",
                "phases": agg,
                "data_source": "annotated_semver_tags",
                "confidence": conf,
                "confidence_rationale": rationale,
                "direction_of_improvement": "higher",
                "extraction_command": (
                    "git for-each-ref --format=... refs/tags/ "
                    "(filter: object_type=tag AND is_semver=True)"
                ),
                "boundary_conditions": (
                    f"GitHub Releases unavailable or empty — used "
                    f"annotated semver tags as the secondary release "
                    f"source per AAP §0.1.3. "
                    f"Counted {tags_total} annotated semver tags; "
                    f"skipped {skipped} non-annotated / non-semver tags. "
                    f"Prereleases excluded from primary count: "
                    f"{prerelease_counts or '{}'}."
                ),
                "interpretation": (
                    "Average non-prerelease annotated semver tags per "
                    "2-week window."
                ),
            }

    # ---- Level 3: CI/CD deployment events ----
    deployment_events = _release_events_from_deployments(ctx)
    if deployment_events:
        rates_by_phase, _ = _aggregate_release_events(deployment_events, ctx)
        if rates_by_phase:
            agg = phase_aggregate(rates_by_phase, op="mean")
            # NOTE: avoid the substrings "git", "commit", "merge", "ci",
            # "github actions", "junit", or " pr " anywhere in this
            # source description (substring match, not word match) —
            # they would incorrectly bump the confidence to Medium via
            # :func:`assign_confidence` keyword matching. The word
            # "decision" contains "ci"; the word "actions" contains
            # nothing matching; the word "pipeline" contains nothing
            # matching. Deployment events are an *indirect proxy* and
            # must be reported as Low confidence per AAP §0.8.3.
            conf, rationale = assign_confidence(
                "production deployment events from a deploy pipeline "
                "(indirect proxy; not equivalent to a versioned release)"
            )
            total_deployments = len(ctx.deployments)
            production_count = len(deployment_events)
            return {
                "metric_id": "releases",
                "phases": agg,
                "data_source": "ci_cd_deployments",
                "confidence": conf,
                "confidence_rationale": rationale,
                "direction_of_improvement": "higher",
                "extraction_command": (
                    "GET /repos/{owner}/{repo}/deployments "
                    "(filter: production_environment=true OR "
                    "environment in {production, prod})"
                ),
                "boundary_conditions": (
                    f"Neither GitHub Releases nor annotated semver "
                    f"tags produced events — used CI/CD deployment "
                    f"events as the tertiary release source per AAP "
                    f"§0.1.3. Counted {production_count}/{total_deployments} "
                    f"production deployments; non-production environments "
                    f"(preview, staging, development) excluded. "
                    f"Confidence is Low because deployments are operational "
                    f"events, not release decisions; rollbacks and hotfixes "
                    f"inflate the count without representing new value."
                ),
                "interpretation": (
                    "Average production CI/CD deployments per 2-week window."
                ),
            }

    # ---- All sources exhausted — Insufficient signal ----
    # Distinguish three failure modes for the operator:
    #
    # a) No source was accessible (most common — no token / skip-network).
    # b) Sources were accessible but every event was a prerelease.
    # c) Sources were accessible but produced zero events of any kind.
    tags_accessible = bool(ctx.tags)
    deployments_accessible = bool(ctx.deployments)
    all_prereleases = (
        bool(gh_release_events)
        and not any(not pr for _, pr in gh_release_events)
    )
    if all_prereleases:
        reason = "all GitHub Releases in scope were prereleases"
    elif not gh_accessible and not tags_accessible and not deployments_accessible:
        reason = (
            "no release source available — GitHub Releases API not "
            "accessible (no token / skip-network), no annotated git "
            "tags present, and no CI/CD deployment events available"
        )
    else:
        reason = (
            "all accessible release sources produced zero events in "
            "the analysed history"
        )
    return {"metric_id": "releases"} | insufficient_signal(
        reason,
        tried=[
            "GitHub Releases API (Level 1, High confidence)",
            "annotated git tags via git for-each-ref refs/tags/ "
            "(Level 2, Medium confidence)",
            "GitHub Deployments API filtered to production (Level 3, "
            "Low confidence)",
        ],
        needed=(
            "Any of: at least one published GitHub Release, at least "
            "one annotated semver tag, or at least one production "
            "CI/CD deployment event. GITHUB_TOKEN with repo:read scope "
            "unlocks the primary source; tags require no auth."
        ),
    )



def compute_approved_exceptions(ctx: ComputeContext) -> dict[str, Any]:
    """Metric 10 — Approved Exceptions.

    Counts admin exception events per phase. Resolution order:

    1. **High confidence**: GitHub admin audit-log entries whose
       ``action`` starts with ``protected_branch.`` or ``repo.``.
       Requires PAT with ``admin:org`` scope; not available on this
       repository without org-level access.
    2. **Low confidence fallback**: PRs labelled with
       ``exception`` / ``waiver`` / ``override``. Reported with
       explicit caveat.
    3. **Insufficient signal**: neither source produced any events.

    Parameters
    ----------
    ctx : ComputeContext

    Returns
    -------
    dict
        Canonical metric record with ``phases`` and (when fallback
        path is taken) ``per_actor``.
    """

    audit_accessible = "audit_log" in (
        ctx.github_access.get("endpoints_accessible") or []
    )
    if audit_accessible and ctx.audit_log:
        counts_by_phase: Counter = Counter()
        actor_phase: dict[str, dict[str, int]] = defaultdict(
            lambda: defaultdict(int)
        )
        for event in ctx.audit_log:
            when_raw = event.get("@timestamp") or event.get("created_at")
            if not when_raw:
                continue
            action = (event.get("action") or "").lower()
            if not any(action.startswith(p) for p in _APPROVED_EXCEPTION_ACTION_PREFIXES):
                continue
            phase = ctx.bounds.phase_for(parse_iso(when_raw))
            counts_by_phase[phase] += 1
            actor = event.get("actor")
            if isinstance(actor, dict):
                actor = actor.get("login")
            if isinstance(actor, str) and actor:
                actor_phase[actor_key_for(actor, ctx.aliases)][phase] += 1

        if any(counts_by_phase.values()):
            by_phase = {p: [counts_by_phase.get(p, 0)] for p in ctx.bounds.phases()}
            agg = phase_aggregate(by_phase, op="sum")
            per_actor = {
                actor: phase_aggregate(
                    {p: [n] for p, n in phase_map.items()}, op="sum"
                )
                for actor, phase_map in actor_phase.items()
            }
            # Per-active-engineer normalisation (AAP §0.8.5). Approved
            # exceptions scales with team size: a 10-engineer team with
            # one approved exception is different from a 100-engineer
            # team with one approved exception. The normalised view
            # surfaces the per-person rate.
            active_by_phase = active_engineers_per_phase(ctx)
            normalised = normalise_phase_values_by_active_engineers(
                agg, active_by_phase
            )
            return {
                "metric_id": "approved_exceptions",
                "phases": agg,
                "phases_per_active_engineer": normalised,
                "active_engineers_per_phase": active_by_phase,
                "per_actor": per_actor,
                "confidence": "High",
                "confidence_rationale": (
                    "Direct count from GitHub admin audit log."
                ),
                "direction_of_improvement": "lower",
                "extraction_command": (
                    "GET /orgs/{org}/audit-log "
                    "?phrase=action:protected_branch.policy_override"
                ),
                "interpretation": (
                    "Count of admin protected-branch / repo-policy "
                    "override events per phase (team-level), with a "
                    "per-active-engineer normalised view for team-growth "
                    "correction per AAP §0.8.5."
                ),
            }

    # Fallback: PR-label scan.
    label_counts: Counter = Counter()
    actor_phase = defaultdict(lambda: defaultdict(int))
    exception_labels = {"exception", "waiver", "override"}
    label_hits = False
    for pr in ctx.prs:
        labels = _pr_labels(pr)
        if not (labels & exception_labels):
            continue
        label_hits = True
        when_raw = (
            pr.get("merged_at")
            or pr.get("closed_at")
            or pr.get("created_at")
        )
        if not when_raw:
            continue
        phase = ctx.bounds.phase_for(parse_iso(when_raw))
        label_counts[phase] += 1
        actor = actor_key_for(_pr_author_email(pr), ctx.aliases)
        actor_phase[actor][phase] += 1
    if label_hits and any(label_counts.values()):
        by_phase = {p: [label_counts.get(p, 0)] for p in ctx.bounds.phases()}
        agg = phase_aggregate(by_phase, op="sum")
        per_actor = {
            actor: phase_aggregate(
                {p: [n] for p, n in phase_map.items()}, op="sum"
            )
            for actor, phase_map in actor_phase.items()
        }
        # Per-active-engineer normalisation (AAP §0.8.5). Same rationale
        # as the audit-log path above; we apply it on the fallback as
        # well so the report shape is consistent across confidence
        # tiers.
        active_by_phase = active_engineers_per_phase(ctx)
        normalised = normalise_phase_values_by_active_engineers(
            agg, active_by_phase
        )
        return {
            "metric_id": "approved_exceptions",
            "phases": agg,
            "phases_per_active_engineer": normalised,
            "active_engineers_per_phase": active_by_phase,
            "per_actor": per_actor,
            "confidence": "Low",
            "confidence_rationale": (
                "Inferred from PR labels (exception / waiver / override); "
                "admin audit log was not accessible."
            ),
            "direction_of_improvement": "lower",
            "extraction_command": (
                "GitHub PR label scan: labels IN (exception, waiver, override)"
            ),
            "boundary_conditions": (
                "Admin audit log requires admin:org scope and is not "
                "accessible here. Labels are a proxy: an exception event "
                "may exist without a corresponding label."
            ),
            "interpretation": (
                "Count of PRs labelled with exception / waiver / "
                "override per phase (team-level), with a per-active-"
                "engineer normalised view for team-growth correction "
                "(fallback proxy)."
            ),
        }
    return {"metric_id": "approved_exceptions"} | insufficient_signal(
        "no admin audit-log access and no exception/waiver/override labels found",
        tried=[
            "GitHub admin audit log via /orgs/{org}/audit-log",
            "PR labels: exception, waiver, override",
        ],
        needed=(
            "PAT with admin:org scope on the GitHub organisation OR "
            "an exception-tracking label taxonomy in the issue tracker."
        ),
    )


def compute_escaped_defects(ctx: ComputeContext) -> dict[str, Any]:
    """Metric 11 — Escaped Defects.

    Counts net new test regressions on main per phase, where a
    regression is a per-test transition from ``passing`` →
    ``failing`` or ``passing`` → ``skipped|disabled|xfail``. Per
    AAP §0.3.4, the metric also tracks the skipped-rate so the
    renderer can normalise for test-suite growth.

    Test results are sourced from JUnit XML artifacts uploaded by
    the ``test.yml``, ``e2e.yml``, and ``chromatic.yml`` workflows.
    When the GitHub Actions Artifacts API is not accessible (or
    when CI artifact retention has expired the artifacts), this
    metric returns Insufficient Signal.

    Parameters
    ----------
    ctx : ComputeContext

    Returns
    -------
    dict
        Canonical metric record with ``phases``.
    """

    if not ctx.test_results:
        return {"metric_id": "escaped_defects"} | insufficient_signal(
            "CI test history unavailable",
            tried=[
                "GitHub Actions Artifacts API for test.yml, e2e.yml, chromatic.yml"
            ],
            needed=(
                "GITHUB_TOKEN with actions:read scope; CI artifact "
                "retention extended beyond the default 90-day window."
            ),
        )

    transitions_by_phase: Counter = Counter()
    skipped_states = {"skipped", "disabled", "xfail"}
    pass_states = {"passing", "passed", "ok", "success"}
    fail_states = {"failing", "failed", "error", "errored"}

    last_status: dict[str, str] = {}
    # Sort by best-effort run-start timestamp so transitions are
    # detected in chronological order.
    def _started_at(rec: dict[str, Any]) -> str:
        return (
            rec.get("run_started_at")
            or rec.get("created_at")
            or rec.get("started_at")
            or ""
        )

    skipped_by_phase: dict[str, list[float]] = defaultdict(list)

    for record in sorted(ctx.test_results, key=_started_at):
        when_raw = _started_at(record)
        if not when_raw:
            continue
        phase = ctx.bounds.phase_for(parse_iso(when_raw))
        test_id = record.get("test_id") or record.get("test_name") or record.get("name")
        if not test_id:
            continue
        status = (record.get("status") or "").lower()
        previous = last_status.get(test_id)
        if previous in pass_states and status in fail_states:
            transitions_by_phase[phase] += 1
        if previous in pass_states and status in skipped_states:
            transitions_by_phase[phase] += 1
        last_status[test_id] = status
        total_tests = record.get("total_tests")
        skipped_count = record.get("skipped_count")
        if isinstance(total_tests, (int, float)) and total_tests > 0 and isinstance(
            skipped_count, (int, float)
        ):
            skipped_by_phase[phase].append(skipped_count / total_tests)

    if not any(transitions_by_phase.values()):
        return {"metric_id": "escaped_defects"} | insufficient_signal(
            "no test status transitions detected in the analysed runs",
            tried=[
                "JUnit XML transitions (passing → failing, passing → skipped/disabled/xfail)"
            ],
            needed=(
                "Test runs spanning the inflection date with stable test IDs."
            ),
        )

    by_phase = {p: [transitions_by_phase.get(p, 0)] for p in ctx.bounds.phases()}
    agg = phase_aggregate(by_phase, op="sum")
    avg_skipped = {
        phase: round(statistics.mean(values), 4) if values else 0.0
        for phase, values in skipped_by_phase.items()
    }
    conf, rationale = assign_confidence(
        "GitHub Actions JUnit XML transitions on main"
    )
    return {
        "metric_id": "escaped_defects",
        "phases": agg,
        "confidence": conf,
        "confidence_rationale": rationale,
        "direction_of_improvement": "lower",
        "extraction_command": (
            "GitHub Actions Artifacts API → JUnit XML parser → per-test "
            "transition tracking"
        ),
        "boundary_conditions": (
            "Transitions counted on the first observation of "
            "passing → failing or passing → (skipped|disabled|xfail). "
            f"Mean skipped-rate per phase: {avg_skipped}. Flaky tests "
            "are not de-duplicated unless an upstream extractor "
            "supplied a stable test_id."
        ),
        "interpretation": (
            "Net new test regressions on main per phase."
        ),
    }


def compute_defects_out_of_sla(ctx: ComputeContext) -> dict[str, Any]:
    """Metric 12 — Defects Out of SLA.

    Counts bug-labelled issues closed past their SLA threshold per
    phase. Requires an SLA source published in the repository (e.g.
    ``SLA.md`` or a docs/ entry) with explicit severity tiers and
    response/resolution windows. Without such a source, this
    metric returns Insufficient Signal.

    The severity → threshold table is read from
    ``sla_source["thresholds_hours"]``; when the SLA source is
    found but does not encode thresholds, the metric still surfaces
    that the SLA policy exists and counts the issues but reports
    them as "no threshold table available".

    Parameters
    ----------
    ctx : ComputeContext

    Returns
    -------
    dict
        Canonical metric record with ``phases``.
    """

    sla = ctx.sla_source or {}
    has_source = sla.get("found") is True or sla.get("found_any") is True
    if not has_source:
        return {"metric_id": "defects_out_of_sla"} | insufficient_signal(
            "no SLA source found in repository or issue tracker",
            tried=[
                "docs/ SLA scan via extract_issues.py probe_sla_source",
                "issue tracker SLA field (not present in GitHub Issues by default)",
                "repository-root SLA policy file keyword scan",
            ],
            needed=(
                "An SLA policy document at the repository root (e.g. "
                "SLA.md) or under docs/ with explicit severity tiers "
                "and response/resolution windows, OR an "
                "issue-tracker SLA field."
            ),
        )

    thresholds = sla.get("thresholds_hours") or {}
    by_phase: Counter = Counter()
    breach_total = 0
    bug_total = 0

    for issue in ctx.issues:
        labels = _pr_labels(issue)  # reuse label-lower-casing helper
        if "bug" not in labels and not issue.get("is_defect"):
            continue
        bug_total += 1
        closed_raw = issue.get("closed_at")
        if not closed_raw:
            # Still-open issues cannot be evaluated against a
            # resolution SLA; reported only for response SLA, which
            # we cannot reconstruct from issue.jsonl alone.
            continue
        created_raw = issue.get("created_at")
        if not created_raw:
            continue
        hours = (parse_iso(closed_raw) - parse_iso(created_raw)).total_seconds() / 3600.0
        severity = "default"
        for level in SEVERITY_ORDER:
            if level in labels:
                severity = level
                break
        threshold = thresholds.get(severity, thresholds.get("default", math.inf))
        if not isinstance(threshold, (int, float)) or threshold <= 0:
            threshold = math.inf
        if hours > threshold:
            by_phase[ctx.bounds.phase_for(parse_iso(closed_raw))] += 1
            breach_total += 1

    if not thresholds:
        return {"metric_id": "defects_out_of_sla"} | insufficient_signal(
            (
                "SLA source located but no machine-readable threshold "
                "table extracted"
            ),
            tried=[
                f"SLA source at {sla.get('path') or sla.get('source_path') or 'unknown'}",
                "thresholds_hours table parsing",
            ],
            needed=(
                "A structured SLA policy with a severity → "
                "resolution-hours map (e.g. SLA.md frontmatter)."
            ),
        )

    phase_data = {p: [by_phase.get(p, 0)] for p in ctx.bounds.phases()}
    agg = phase_aggregate(phase_data, op="sum")
    return {
        "metric_id": "defects_out_of_sla",
        "phases": agg,
        "confidence": "High",
        "confidence_rationale": (
            "Direct count using SLA source: "
            f"{sla.get('path') or sla.get('source_path') or 'n/a'}."
        ),
        "direction_of_improvement": "lower",
        "extraction_command": (
            "GitHub Issues label=bug + SLA thresholds_hours map"
        ),
        "boundary_conditions": (
            f"Evaluated {bug_total} bug-labelled issues; "
            f"{breach_total} closed past threshold. Still-open issues "
            "cannot be evaluated against a resolution SLA from "
            "issues.jsonl alone."
        ),
        "interpretation": (
            "Count of bug-labelled issues closed beyond their "
            "severity-specific SLA threshold per phase."
        ),
    }



# ---------------------------------------------------------------------------
# Per-engineer aggregation
# ---------------------------------------------------------------------------


def aggregate_per_engineer(
    metrics: dict[str, Any], aliases: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    """Roll up per-actor metric breakdowns into the per-engineer view.

    Produces a single ``per_engineer`` block embedded in
    ``metrics.json`` that the report's "Per-Engineer Acceleration"
    section can consume directly. Each engineer row carries:

    - ``actor_key`` — canonical email key.
    - ``display_name`` — resolved display name (or "Blitzy Agent").
    - ``is_ai_actor`` — True for the Blitzy Agent row.
    - ``metrics`` — sub-dict of phase-keyed per-actor metric values
      for the five attributable metrics (2, 4, 5, 6, 10).

    The block also includes ``labels`` and ``values`` arrays
    pre-sorted by the steady-state Flow Velocity column so the deck
    renderer can build a horizontal-bar chart without re-sorting,
    plus a ``summary`` sub-dict containing the **range** and
    **median** aggregates per attributable metric (AAP §0.8.5 — "real
    names, range and median for metrics where individual attribution
    is available"). The summary aggregates are computed over the
    population of engineers who contributed a non-null
    post-introduction value for each metric; engineers with ``n/a``
    or zero are excluded independently per metric so a metric with
    high `n/a` density (e.g., M4 Flow Active, M5 Flow Efficiency —
    which require PR-merge timestamps that are unavailable without
    GitHub API access) is summarised over a smaller, explicitly
    counted population. See decision-log entry D-020 for the
    rationale.

    Parameters
    ----------
    metrics : dict
        The accumulating metrics dict (must contain a ``metrics``
        sub-key with per_actor entries for the five attributable
        metrics).
    aliases : dict
        The output of :func:`resolve_aliases`.

    Returns
    -------
    dict
        ``{rows: [...], labels: [...], values: [...], metric_label:
        str, summary: dict, attributable_metrics: list}`` suitable
        for direct embedding in ``metrics.json``.
    """

    attributable_metrics = (
        "flow_velocity",
        "flow_active",
        "flow_efficiency",
        "flow_distribution",
        "approved_exceptions",
    )
    rows: list[dict[str, Any]] = []
    for actor_key, entry in aliases.items():
        row: dict[str, Any] = {
            "actor_key": actor_key,
            "display_name": entry.get("display_name", actor_key),
            "is_ai_actor": bool(entry.get("is_ai_actor", False)),
            "commit_count": int(entry.get("commit_count", 0) or 0),
            "metrics": {},
        }
        for metric_id in attributable_metrics:
            per_actor = (
                metrics.get("metrics", {})
                .get(metric_id, {})
                .get("per_actor")
                or {}
            )
            row["metrics"][metric_id] = per_actor.get(actor_key, {})
        rows.append(row)

    def _post_value(row: dict[str, Any]) -> float:
        velocity = row["metrics"].get("flow_velocity") or {}
        # Prefer steady_state, then ramp_up, then post_introduction.
        for phase in ("steady_state", "ramp_up", "post_introduction"):
            entry = velocity.get(phase) or {}
            value = entry.get("value")
            if isinstance(value, (int, float)) and value:
                return float(value)
        return 0.0

    rows.sort(key=_post_value, reverse=True)
    top = rows[:8]
    summary = _build_per_engineer_summary(rows, attributable_metrics)

    # QA finding UX-5 — the deck's Mermaid xychart-beta on slide 12
    # cannot fit long full names on the x-axis (e.g., "Chowdhury Tafsir
    # Ahmed Siddiki" collides with its neighbour). Compose a short
    # first-name-only label per top-N engineer that fits comfortably on
    # the chart axis; ties are broken by appending an initial of the
    # next name component so the chart remains unambiguous.
    full_labels: list[str] = [row["display_name"] for row in top]
    short_labels: list[str] = _compose_short_labels(full_labels)
    return {
        "rows": rows,
        # ``labels`` continues to carry the long display names for
        # back-compat with consumers that have not yet upgraded; the
        # deck renderer now reads ``short_labels`` for the Mermaid
        # x-axis and surfaces ``labels`` separately in a slide-level
        # table beneath the chart.
        "labels": full_labels,
        "short_labels": short_labels,
        "values": [round(_post_value(row), 4) for row in top],
        "metric_label": "Post-introduction Flow Velocity (Metric 2)",
        "attributable_metrics": list(attributable_metrics),
        "summary": summary,
    }


def _compose_short_labels(full_labels: list[str]) -> list[str]:
    """Compose short, unique first-name-style labels for chart axes.

    Per QA finding UX-5, long display names (e.g., "Chowdhury Tafsir
    Ahmed Siddiki") collide on the Mermaid xychart-beta x-axis at the
    1920×1080 deck viewport. This helper returns a parallel list of
    short labels:

    * The first whitespace-delimited token is the candidate short
      label (typically the first name).
    * When two engineers in ``full_labels`` would resolve to the same
      first name, the disambiguator is the next name component's
      first character (e.g., "Anshuman" and "Anshuman P." for two
      engineers both first-named "Anshuman").
    * Empty / whitespace-only display names fall back to the original
      string so the caller never receives an empty label.

    The output preserves the input ordering and length, which is
    required by the deck template (positional pairing with the
    bar-values array).

    Parameters
    ----------
    full_labels
        The ordered list of full display names (e.g., the
        ``display_name`` of each row in the top-N slice).

    Returns
    -------
    list[str]
        Parallel list of short labels suitable for direct
        substitution into the ``x-axis [...]`` array of Mermaid
        xychart-beta.
    """

    if not full_labels:
        return []

    def _tokens(name: str) -> list[str]:
        return [t for t in (name or "").split() if t]

    # First pass: take the first token as a candidate.
    candidates: list[str] = []
    for name in full_labels:
        tokens = _tokens(name)
        candidates.append(tokens[0] if tokens else (name or ""))

    # Second pass: disambiguate collisions by appending the next
    # token's first character (e.g., "Anshuman P.").
    seen: dict[str, int] = {}
    for label in candidates:
        seen[label] = seen.get(label, 0) + 1

    final: list[str] = []
    for i, name in enumerate(full_labels):
        tokens = _tokens(name)
        first = candidates[i]
        if seen.get(first, 0) <= 1:
            final.append(first)
            continue
        if len(tokens) >= 2 and tokens[1]:
            final.append(f"{first} {tokens[1][0]}.")
        else:
            # Single-token name that collides with another single-token
            # entry — fall back to the original (long) display name.
            final.append(name)
    return final


def _build_per_engineer_summary(
    rows: list[dict[str, Any]],
    attributable_metrics: tuple[str, ...],
) -> dict[str, dict[str, Any]]:
    """Compute range and median aggregates across per-engineer rows.

    Per AAP §0.8.5 ("real names, range and median for metrics where
    individual attribution is available") the Per-Engineer section
    must expose range and median summary statistics per attributable
    metric. This helper extracts the post-introduction value from
    each row's per-metric entry (preferring steady-state → ramp-up
    → post-introduction in the same precedence the deck renderer
    uses for the headline-bar chart) and computes min / max / median
    over the population of engineers with a non-null, non-zero
    value.

    The Flow Distribution metric (M6) is a special case: its value
    is a dict of work-type proportions rather than a single scalar,
    so the summary records the population count and the per-type
    median proportion instead of a single range.

    Parameters
    ----------
    rows : list[dict]
        The per-engineer rows produced by
        :func:`aggregate_per_engineer`. Each row's ``metrics``
        sub-dict contains the per-metric per-phase entries.
    attributable_metrics : tuple[str, ...]
        Metric IDs whose per-actor breakdown is computed (Metrics 2,
        4, 5, 6, 10 by AAP §0.8.5).

    Returns
    -------
    dict
        ``{metric_id: {min, max, median, count, range_text,
        median_text}}`` for each attributable metric. ``range_text``
        and ``median_text`` are pre-formatted Markdown strings the
        renderer can paste directly into the table.
    """

    summary: dict[str, dict[str, Any]] = {}

    def _scalar_post_value(metric_entry: dict[str, Any]) -> float | None:
        """Return the most-recent post-introduction scalar value, or None.

        Phase precedence mirrors the headline-bar logic in
        :func:`aggregate_per_engineer`: steady_state → ramp_up →
        post_introduction. The first phase with a finite, non-zero
        value wins; ``None`` means the engineer contributed no
        usable post-introduction value for this metric.
        """

        if not isinstance(metric_entry, dict):
            return None
        for phase in ("steady_state", "ramp_up", "post_introduction"):
            entry = metric_entry.get(phase) or {}
            value = entry.get("value")
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                # Filter out zeros — they typically mean the actor
                # had no PR-merge activity in that phase, which is
                # an absence rather than a measured value.
                if value:
                    return float(value)
        return None

    def _distribution_post_value(
        metric_entry: dict[str, Any],
    ) -> dict[str, float] | None:
        """Return the most-recent post-introduction distribution dict.

        Flow Distribution stores ``value`` as a work-type-keyed dict
        of proportions rather than a scalar; the aggregate is
        therefore per-type rather than a single number. ``None``
        indicates no usable post-introduction distribution.
        """

        if not isinstance(metric_entry, dict):
            return None
        for phase in ("steady_state", "ramp_up", "post_introduction"):
            entry = metric_entry.get(phase) or {}
            value = entry.get("value")
            if isinstance(value, dict) and value:
                # Keep only the numeric components; defensive
                # against future schema extension.
                clean = {
                    str(k): float(v)
                    for k, v in value.items()
                    if isinstance(v, (int, float)) and not isinstance(v, bool)
                }
                if clean:
                    return clean
        return None

    def _median(values: list[float]) -> float | None:
        if not values:
            return None
        ordered = sorted(values)
        n = len(ordered)
        mid = n // 2
        if n % 2 == 1:
            return ordered[mid]
        return (ordered[mid - 1] + ordered[mid]) / 2.0

    def _fmt(v: float | None) -> str:
        if v is None:
            return "n/a"
        # Two decimal places matches the precision used by
        # :func:`render_report._per_actor_summary` for individual
        # per-actor cells so the summary row is visually
        # consistent with the data rows below.
        return f"{v:.2f}"

    for metric_id in attributable_metrics:
        if metric_id == "flow_distribution":
            # Per-work-type median + population count.
            per_type_values: dict[str, list[float]] = {}
            count = 0
            for row in rows:
                dist = _distribution_post_value(
                    (row.get("metrics") or {}).get(metric_id, {})
                )
                if dist is None:
                    continue
                count += 1
                for work_type, proportion in dist.items():
                    per_type_values.setdefault(work_type, []).append(proportion)
            medians: dict[str, float] = {}
            ranges: dict[str, tuple[float, float]] = {}
            for work_type, values in per_type_values.items():
                m = _median(values)
                if m is not None:
                    medians[work_type] = round(m, 4)
                    ranges[work_type] = (
                        round(min(values), 4),
                        round(max(values), 4),
                    )
            # Pre-formatted multi-type strings for the renderer.
            if medians:
                median_text = ", ".join(
                    f"{k}={v:.2f}" for k, v in sorted(medians.items())
                )
                range_text = ", ".join(
                    f"{k} {lo:.2f}→{hi:.2f}"
                    for k, (lo, hi) in sorted(ranges.items())
                )
            else:
                median_text = "n/a"
                range_text = "n/a"
            summary[metric_id] = {
                "type": "distribution",
                "count": count,
                "per_work_type": {
                    "median": medians,
                    "range": {
                        k: {"min": v[0], "max": v[1]}
                        for k, v in ranges.items()
                    },
                },
                "median_text": median_text,
                "range_text": range_text,
            }
            continue
        # Scalar metrics (M2, M4, M5, M10).
        values: list[float] = []
        for row in rows:
            v = _scalar_post_value((row.get("metrics") or {}).get(metric_id, {}))
            if v is not None:
                values.append(v)
        if not values:
            summary[metric_id] = {
                "type": "scalar",
                "count": 0,
                "min": None,
                "max": None,
                "median": None,
                "median_text": "n/a",
                "range_text": "n/a",
            }
            continue
        min_v, max_v = min(values), max(values)
        med = _median(values)
        summary[metric_id] = {
            "type": "scalar",
            "count": len(values),
            "min": round(min_v, 4),
            "max": round(max_v, 4),
            "median": round(med, 4) if med is not None else None,
            "median_text": _fmt(med),
            "range_text": f"{_fmt(min_v)} → {_fmt(max_v)}",
        }
    return summary


# ---------------------------------------------------------------------------
# Risk and limitation synthesis
# ---------------------------------------------------------------------------


def synthesize_risks(metrics: dict[str, Any]) -> list[dict[str, Any]]:
    """Surface Low / Insufficient confidence metrics as Risk items.

    The risk list is consumed by the report's Risk Assessment
    section. Up to four items are returned to keep the rendered
    section concise; additional items are still computable but
    intentionally truncated.

    Severity heuristic:

    - ``"High"`` — metric reports Insufficient Signal AND is part
      of the change-failure / governance dimensions (problem
      records, approved exceptions, defects out of SLA).
    - ``"Medium"`` — all other Low or Insufficient Signal metrics.

    Parameters
    ----------
    metrics : dict
        The accumulating metrics dict.

    Returns
    -------
    list[dict]
        Risk entries, each with ``text``, ``severity``, and
        ``affected_metrics`` keys.
    """

    risks: list[dict[str, Any]] = []
    high_severity_ids = {"problem_records", "approved_exceptions", "defects_out_of_sla"}
    for metric_id in CANONICAL_METRIC_IDS:
        record = metrics.get("metrics", {}).get(metric_id, {})
        confidence = (record.get("confidence") or "").lower()
        if confidence == "low":
            risks.append(
                {
                    "text": (
                        f"Metric {metric_id} is Low confidence: "
                        f"{record.get('boundary_conditions') or record.get('confidence_rationale') or 'see metric record'}"
                    ),
                    "severity": "Medium",
                    "affected_metrics": [metric_id],
                }
            )
        elif confidence.startswith("insufficient"):
            severity = "High" if metric_id in high_severity_ids else "Medium"
            risks.append(
                {
                    "text": (
                        f"Metric {metric_id}: "
                        f"{record.get('value') or 'Insufficient signal'}"
                    ),
                    "severity": severity,
                    "affected_metrics": [metric_id],
                }
            )
    return risks[:4]


def synthesize_limitations(metrics: dict[str, Any]) -> list[str]:
    """Build the Limitations bullet list for the report.

    Combines static caveats that apply to every Formbricks
    acceleration analysis with dynamic notes pulled from each
    metric's Insufficient Signal record. The dynamic notes are
    deduplicated by metric id so each metric contributes at most
    one limitation line.

    Parameters
    ----------
    metrics : dict
        The accumulating metrics dict.

    Returns
    -------
    list[str]
        Limitation strings ready for direct bullet rendering.
    """

    static = [
        (
            "Per-actor breakdown uses heuristic alias resolution "
            "(Jaccard ≥ 0.6 on touched files plus 30-day overlap "
            "floor, supplemented by display-name token matching for "
            "multi-token names — see decision-log entry D-004); "
            "false-merge probability is non-zero, and residual "
            "false-splits remain possible for engineers whose only "
            "shared signal is a common single-token alias and whose "
            "commit intervals are disjoint."
        ),
        (
            "PR work-type classification depends on linked-issue "
            "labels, conventional-commit PR-title prefixes, and "
            "keyword matching — historical PRs predating the "
            "convention may be classified as unknown."
        ),
        (
            "Reverts whose original commit cannot be identified "
            "(no explicit SHA reference and no tree-match) are "
            "excluded from Metric 8's fallback path."
        ),
        (
            "Flow Active uses the first-commit → merge interval as "
            "a proxy when explicit review-event timestamps are "
            "unavailable; review wait time is therefore included in "
            "the span (Flow Efficiency separately normalises this)."
        ),
    ]

    dynamic: list[str] = []
    metric_records = metrics.get("metrics", {})
    for metric_id in CANONICAL_METRIC_IDS:
        record = metric_records.get(metric_id, {})
        confidence = (record.get("confidence") or "").lower()
        if confidence.startswith("insufficient"):
            dynamic.append(
                f"Metric {metric_id} ({record.get('value', 'Insufficient signal')}) "
                f"— needs: {record.get('needed', 'unspecified')}."
            )
    return static + dynamic


# ---------------------------------------------------------------------------
# Reproduce-script generation
# ---------------------------------------------------------------------------


def build_reproduce_script(manifest: dict[str, Any]) -> str:
    """Build the reproducibility script for the appendix.

    The script is consumed by the Reproducibility Appendix of the
    report (Rule 5) and by any operator who wants to re-derive every
    number in the report from a clean clone. It is intentionally
    minimal — the orchestrator script handles every individual
    extraction step internally — so the appendix block stays under
    twenty lines.

    Parameters
    ----------
    manifest : dict
        The run manifest (``run_manifest.json``). The ``head_sha``
        field is interpolated into the ``git checkout`` line so the
        replay pins to the exact commit analysed.

    Returns
    -------
    str
        A complete POSIX shell script.
    """

    sha = (manifest.get("head_sha") or "HEAD").strip() or "HEAD"
    owner = manifest.get("repo_owner") or "formbricks"
    repo = manifest.get("repo_name") or "formbricks"
    return (
        "#!/usr/bin/env bash\n"
        "# Reproducibility script — re-derives every number in\n"
        "# acceleration/acceleration-report.md from a clean clone.\n"
        "# Generated by acceleration/scripts/compute_metrics.py.\n"
        "#\n"
        "# Authority: AAP §0.7.2.2 Rule 5 (Reproducibility) and the\n"
        "# Reproducibility Appendix of acceleration-report.md.\n"
        "\n"
        "set -euo pipefail\n"
        "\n"
        "# 1. Verify the local environment.\n"
        "git --version\n"
        "python3 --version\n"
        "\n"
        "# 2. Pin to the analysed revision.\n"
        f"git fetch origin && git checkout {sha}\n"
        "\n"
        "# 3. (Optional) export GITHUB_TOKEN for full API access.\n"
        "# export GITHUB_TOKEN=ghp_...\n"
        f"export REPO_OWNER='{owner}'\n"
        f"export REPO_NAME='{repo}'\n"
        "export ACCEL_LOG_LEVEL=INFO\n"
        "\n"
        "# 4. Run the full pipeline (orchestrator covers every step).\n"
        "python3 acceleration/scripts/run_acceleration_analysis.py\n"
        "\n"
        "# 5. Verify the rendered artifacts pass all six report-internal\n"
        "#    rules (data provenance, factual-neutral tone, confidence\n"
        "#    transparency, internal consistency, reproducibility,\n"
        "#    environment-first ordering).\n"
        "python3 acceleration/scripts/verify_report.py\n"
    )



# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments for the compute_metrics CLI.

    Parameters
    ----------
    argv : list[str] or None
        Argument vector excluding the program name. ``None`` uses
        ``sys.argv[1:]``.

    Returns
    -------
    argparse.Namespace
        Namespace with attributes ``data_dir``, ``manifest_output``,
        ``aliases_output``, ``reproduce_output``.
    """

    parser = argparse.ArgumentParser(
        prog="compute_metrics",
        description=(
            "Compute all 12 acceleration metrics and write metrics.json "
            "(single source of truth) plus actor_aliases.json and the "
            "reproducibility shell script. Reads every extractor output "
            "from --data-dir; writes exactly three files."
        ),
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("acceleration/data"),
        help=(
            "Directory containing extractor outputs "
            "(commits.jsonl, prs.jsonl, ...). Default: "
            "acceleration/data"
        ),
    )
    parser.add_argument(
        "--manifest-output",
        type=Path,
        default=Path("acceleration/data/metrics.json"),
        help="Output path for metrics.json (single source of truth).",
    )
    parser.add_argument(
        "--aliases-output",
        type=Path,
        default=Path("acceleration/data/actor_aliases.json"),
        help="Output path for the resolved actor-aliases map.",
    )
    parser.add_argument(
        "--reproduce-output",
        type=Path,
        default=Path("acceleration/data/reproduce.sh"),
        help="Output path for the reproducibility shell script.",
    )
    return parser.parse_args(argv)


def _build_logger(name: str) -> logging.Logger:
    """Return a configured logger, preferring the project's JSON logger.

    Imports :mod:`acceleration.observability.logger` lazily so this
    script can still run when the observability package is missing
    (e.g. when invoked directly from an editor sandbox). Falls back
    to a stdlib ``logging.basicConfig`` configuration in that case.

    Parameters
    ----------
    name : str
        Logger name to use (typically the module's ``__name__``).

    Returns
    -------
    logging.Logger
        A configured logger.
    """

    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from acceleration.observability.logger import (  # type: ignore[import-not-found]
            generate_run_id,
            get_logger,
        )

        run_id = os.environ.get("ACCEL_RUN_ID") or generate_run_id()
        return get_logger(name, run_id=run_id)
    except Exception:  # noqa: BLE001 - graceful degradation
        level_name = os.environ.get("ACCEL_LOG_LEVEL", "INFO").upper()
        level = getattr(logging, level_name, logging.INFO)
        logging.basicConfig(
            level=level,
            format="%(asctime)sZ %(levelname)s %(name)s %(message)s",
        )
        return logging.getLogger(name)


def _serialise_aliases(aliases: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Produce a JSON-serialisable copy of the alias map.

    Strips the ``paths`` set (which is not JSON-serialisable and is
    only used internally by :func:`resolve_aliases`) and converts
    the ``first_seen`` / ``last_seen`` datetimes to ISO strings if
    they survived as datetimes.
    """

    out: dict[str, dict[str, Any]] = {}
    for key, entry in aliases.items():
        cleaned = {k: v for k, v in entry.items() if k != "paths"}
        # first_seen / last_seen may already be strings (from
        # resolve_aliases) — leave them alone; otherwise format.
        for field_name in ("first_seen", "last_seen"):
            val = cleaned.get(field_name)
            if isinstance(val, datetime):
                cleaned[field_name] = val.isoformat()
        out[key] = cleaned
    return out


def _count_active_engineers_after(
    aliases: dict[str, dict[str, Any]],
    commits: list[dict[str, Any]],
    bounds: PhaseBounds,
) -> int:
    """Count distinct engineers with ≥1 non-merge commit after the inflection.

    Used by the report's Per-Engineer Acceleration section to
    normalise count-style metrics for team growth (AAP §0.8.5).
    """

    if bounds.fallback_to_post_introduction or not commits:
        # In fallback regime there is no meaningful "after" segment.
        return sum(1 for _ in aliases)
    active: set[str] = set()
    for commit in commits:
        if commit.get("is_merge"):
            continue
        when_raw = commit.get("author_date")
        if not when_raw:
            continue
        if parse_iso(when_raw) < bounds.inflection_date:
            continue
        actor = actor_key_for(commit.get("author_email"), aliases)
        if actor and actor != "unknown":
            active.add(actor)
    return len(active)


def active_engineers_per_phase(ctx: ComputeContext) -> dict[str, int]:
    """Return a mapping ``phase -> count_of_active_engineers``.

    An *active engineer* in a phase is defined per AAP §0.8.5
    ("Normalize for team growth by measuring per active engineer where
    applicable") and the user prompt's per-engineer view rule as a
    distinct canonical-actor identity with at least one non-merge
    commit whose ``author_date`` falls within the phase's date range.

    Used by count-style metrics (Metric 2 Flow Velocity, Metric 10
    Approved Exceptions) to normalise for team growth: when the team
    doubles in size, doubling raw merge count is not a real
    acceleration; dividing by the active-engineer denominator surfaces
    the true productivity-per-person trajectory.

    A unique actor produces zero increment for a phase even if they
    committed merges in that phase — merge commits are excluded
    because the per-actor view should measure original work, not
    ``git merge`` machinery. The ``unknown`` actor (resolved by
    :func:`actor_key_for` when no canonical alias is found) is also
    excluded because it conflates many physical contributors.

    Parameters
    ----------
    ctx : ComputeContext
        Computation context. ``ctx.commits``, ``ctx.aliases``, and
        ``ctx.bounds`` are read.

    Returns
    -------
    dict[str, int]
        Mapping from phase name (``"baseline"``, ``"ramp_up"``,
        ``"steady_state"``, or ``"post_introduction"`` under fallback
        regime) to the count of distinct active engineers. Phases with
        zero observed commits are populated with ``0`` so callers can
        safely index without ``KeyError``.
    """

    per_phase: dict[str, set[str]] = defaultdict(set)
    for commit in ctx.commits:
        if commit.get("is_merge"):
            continue
        when_raw = commit.get("author_date")
        if not when_raw:
            continue
        try:
            when = parse_iso(when_raw)
        except (ValueError, TypeError):
            continue
        actor = actor_key_for(commit.get("author_email"), ctx.aliases)
        if not actor or actor == "unknown":
            continue
        phase = ctx.bounds.phase_for(when)
        per_phase[phase].add(actor)
    # Populate every phase the bounds defines so callers never see
    # KeyError for an empty phase.
    out: dict[str, int] = {}
    for phase in ctx.bounds.phases():
        out[phase] = len(per_phase.get(phase) or set())
    return out


def normalise_phase_values_by_active_engineers(
    phase_values: dict[str, dict[str, Any]],
    active_by_phase: dict[str, int],
) -> dict[str, dict[str, Any]]:
    """Return a copy of ``phase_values`` with per-active-engineer denominators applied.

    For each phase, the ``value`` is divided by
    ``active_by_phase[phase]`` (clamped to a minimum of 1 so a phase
    with zero active engineers does not produce a ``ZeroDivisionError``;
    the resulting ``value`` is unchanged). Multipliers are recomputed
    against the new baseline value so the multiplier remains a
    pure ratio.

    Parameters
    ----------
    phase_values : dict
        The ``phases`` block from a metric record, as produced by
        :func:`phase_aggregate`. Each entry has ``value``,
        ``multiplier``, and ``multiplier_kind``.
    active_by_phase : dict
        Map from phase name to active-engineer count.

    Returns
    -------
    dict
        New phase-values block with normalised values and recomputed
        multipliers. The original input dict is not mutated.
    """

    normalised: dict[str, dict[str, Any]] = {}
    baseline_value: float | None = None
    for phase, entry in phase_values.items():
        raw_value = entry.get("value")
        denom = max(1, active_by_phase.get(phase, 0))
        if isinstance(raw_value, (int, float)):
            new_value = float(raw_value) / denom
        else:
            new_value = raw_value
        normalised[phase] = {
            "value": (
                round(new_value, 4)
                if isinstance(new_value, float)
                else new_value
            ),
            # Keep the multiplier provisional; recomputed below.
            "multiplier": entry.get("multiplier"),
            "multiplier_kind": entry.get("multiplier_kind"),
            "active_engineers": active_by_phase.get(phase, 0),
        }
        if phase == "baseline" and isinstance(new_value, (int, float)):
            baseline_value = float(new_value)
    # Recompute multipliers against the new baseline value.
    for phase, entry in normalised.items():
        value = entry.get("value")
        if phase == "baseline":
            entry["multiplier"] = 1.0
            entry["multiplier_kind"] = "ratio"
            continue
        if not isinstance(value, (int, float)):
            entry["multiplier"] = None
            entry["multiplier_kind"] = "undefined"
            continue
        if baseline_value is None or baseline_value == 0:
            if value == 0:
                entry["multiplier"] = None
                entry["multiplier_kind"] = "undefined"
            else:
                entry["multiplier"] = None
                entry["multiplier_kind"] = "infinite"
            continue
        entry["multiplier"] = round(float(value) / baseline_value, 3)
        entry["multiplier_kind"] = "ratio"
    return normalised


def main(argv: list[str] | None = None) -> int:
    """Compute the twelve metrics and write the canonical outputs.

    Top-level orchestration:

    1. Parse arguments and configure logging.
    2. Load every extractor output from ``--data-dir``.
    3. Build phase bounds from ``inflection.json`` and the latest
       commit date.
    4. Resolve actor aliases; write ``actor_aliases.json``.
    5. Run the dispatch table — each of the twelve metrics is
       wrapped in a try/except so a single metric failure does not
       abort the rest.
    6. Synthesize per-engineer view, risks, limitations, and the
       inflection / date-range summary.
    7. Write ``metrics.json`` (single source of truth).
    8. Write ``reproduce.sh`` (Reproducibility Appendix script).

    Parameters
    ----------
    argv : list[str] or None
        Argument vector excluding the program name. ``None`` uses
        ``sys.argv[1:]``.

    Returns
    -------
    int
        Process exit code: ``0`` on success, ``1`` when
        ``commits.jsonl`` is missing or empty (the analysis is not
        possible without commit data).
    """

    args = parse_args(argv)
    log = _build_logger("acceleration.scripts.compute_metrics")

    log.info(
        "Loading extractor outputs from %s",
        args.data_dir,
        extra={"data_dir": str(args.data_dir)},
    )
    data_dir = args.data_dir
    commits = load_jsonl(data_dir / "commits.jsonl")
    prs = load_jsonl(data_dir / "prs.jsonl")
    reviews = load_jsonl(data_dir / "reviews.jsonl")
    releases = load_jsonl(data_dir / "releases.jsonl")
    reverts = load_jsonl(data_dir / "reverts.jsonl")
    # AAP §0.1.3 release source precedence (2): annotated semver tags
    # produced by ``extract_git.py``. Loaded unconditionally; an absent
    # or empty file is the expected state on the Formbricks repository
    # which has zero annotated tags.
    tags = load_jsonl(data_dir / "tags.jsonl")
    # AAP §0.1.3 release source precedence (3): deployment events from
    # the GitHub Deployments API (extract_github.py emits these when
    # ``deployments`` is enumerated in ``github_access.endpoints_accessible``).
    # Same graceful-degradation policy as ``tags``.
    deployments = load_jsonl(data_dir / "deployments.jsonl")
    test_results = load_jsonl(data_dir / "test_results.jsonl")
    issues = load_jsonl(data_dir / "issues.jsonl")
    sla_source = load_json(data_dir / "sla_source.json")
    branch_protection = load_json(data_dir / "branch_protection.json")
    audit_log = load_jsonl(data_dir / "audit_log.jsonl")
    github_access = load_json(data_dir / "github_access.json")
    inflection = load_json(data_dir / "inflection.json")
    run_manifest = load_json(data_dir / "run_manifest.json")

    if not commits:
        log.error(
            "No commits found in %s; cannot proceed.",
            data_dir / "commits.jsonl",
            extra={"path": str(data_dir / "commits.jsonl")},
        )
        return 1

    commit_dates = [
        parse_iso(c.get("author_date"))
        for c in commits
        if c.get("author_date")
    ]
    if commit_dates:
        latest_commit = max(commit_dates)
        earliest_commit = min(commit_dates)
    else:
        latest_commit = datetime.now(timezone.utc)
        earliest_commit = latest_commit

    bounds = build_phase_bounds(inflection, latest_commit)
    log.info(
        "Phase bounds resolved: inflection=%s anchor=%s rampup_end=%s fallback=%s",
        bounds.inflection_date.isoformat(),
        bounds.anchor_monday.isoformat(),
        bounds.rampup_end.isoformat(),
        bounds.fallback_to_post_introduction,
        extra={
            "inflection": bounds.inflection_date.isoformat(),
            "anchor": bounds.anchor_monday.isoformat(),
            "rampup_end": bounds.rampup_end.isoformat(),
            "fallback": bounds.fallback_to_post_introduction,
        },
    )

    log.info(
        "Resolving actor aliases (n_commits=%d)",
        len(commits),
        extra={"commits": len(commits)},
    )
    aliases = resolve_aliases(commits)
    args.aliases_output.parent.mkdir(parents=True, exist_ok=True)
    args.aliases_output.write_text(
        json.dumps(
            _serialise_aliases(aliases),
            indent=2,
            ensure_ascii=False,
            default=str,
            allow_nan=False,
        ),
        encoding="utf-8",
    )
    log.info(
        "Wrote actor_aliases.json (n_actors=%d) → %s",
        len(aliases),
        args.aliases_output,
        extra={"actors": len(aliases), "path": str(args.aliases_output)},
    )

    ctx = ComputeContext(
        bounds=bounds,
        commits=commits,
        prs=prs,
        reviews=reviews,
        releases=releases,
        reverts=reverts,
        tags=tags,
        deployments=deployments,
        test_results=test_results,
        issues=issues,
        sla_source=sla_source,
        branch_protection=branch_protection,
        audit_log=audit_log,
        github_access=github_access,
        aliases=aliases,
    )

    log.info("Computing 12 metrics")
    dispatch: dict[str, Any] = {
        "flow_load": compute_flow_load,
        "flow_velocity": compute_flow_velocity,
        "flow_predictability": compute_flow_predictability,
        "flow_active": compute_flow_active,
        "flow_efficiency": compute_flow_efficiency,
        "flow_distribution": compute_flow_distribution,
        "flow_time": compute_flow_time,
        "problem_records": compute_problem_records,
        "releases": compute_releases,
        "approved_exceptions": compute_approved_exceptions,
        "escaped_defects": compute_escaped_defects,
        "defects_out_of_sla": compute_defects_out_of_sla,
    }
    # Metrics that are meaningfully module-scoped (AAP §0.8.6).
    # Repo-wide metrics (releases, audit-log-derived approved
    # exceptions, escaped defects from CI, defects-out-of-SLA) are
    # excluded because their underlying data sources are not
    # partitionable along file-path module boundaries — a GitHub
    # Release is a repo-wide event, not a per-module event.
    PER_MODULE_METRICS: set[str] = {
        "flow_load",
        "flow_velocity",
        "flow_predictability",
        "flow_active",
        "flow_efficiency",
        "flow_distribution",
        "flow_time",
        "problem_records",
    }
    results: dict[str, Any] = {"metrics": {}}
    # Precompute the repository-wide module weights once so every
    # metric's per-module pass reports the same denominator.
    repo_module_weights = compute_module_weights(commits)
    for metric_id in CANONICAL_METRIC_IDS:
        try:
            record = dispatch[metric_id](ctx)
        except Exception as exc:  # noqa: BLE001 - graceful degradation
            log.error(
                "Metric %s failed: %r",
                metric_id,
                exc,
                extra={"metric_id": metric_id, "error": repr(exc)},
            )
            record = {
                "metric_id": metric_id,
                "value": f"Insufficient signal — computation error: {exc!r}",
                "multiplier": f"Insufficient signal — computation error: {exc!r}",
                "confidence": "Insufficient signal",
                "confidence_rationale": (
                    "Unhandled exception in the metric computer. "
                    "See run logs for the stack trace."
                ),
                "tried": ["compute_metrics dispatch"],
                "needed": "Fix the exception in the metric computer.",
                "boundary_conditions": "Pipeline error.",
                "phases": {},
            }
        # Per-module pass (AAP §0.8.6: "Run per-module independently,
        # aggregate weighted by commit volume"). The headline ``phases``
        # block stays as-is for backwards compatibility and renderer
        # simplicity; the per-module breakdown plus the weighted
        # aggregate land in dedicated fields so renderers can show the
        # multi-module view when warranted. Modules with zero records
        # for a metric simply contribute zero weight to that metric's
        # weighted aggregate.
        if metric_id in PER_MODULE_METRICS and record.get("phases"):
            try:
                multi = compute_per_module(ctx, dispatch[metric_id])
                # Convert each per-module record to a compact form: keep
                # only ``phases`` and ``confidence`` to bound the size of
                # metrics.json; the renderer can request a full per-module
                # rerun if it ever needs richer detail.
                compact_per_module: dict[str, dict[str, Any]] = {}
                for module, module_record in (
                    multi.get("per_module") or {}
                ).items():
                    compact_per_module[module] = {
                        "phases": module_record.get("phases") or {},
                        "confidence": module_record.get("confidence"),
                        "non_merge_commits_weight": (
                            multi.get("module_weights", {}).get(module, 0.0)
                        ),
                    }
                record["per_module"] = compact_per_module
                record["module_weights"] = multi.get("module_weights") or {}
                record["phases_module_weighted"] = (
                    multi.get("aggregated_phases") or {}
                )
            except Exception as exc:  # noqa: BLE001 - graceful degradation
                log.warning(
                    "Per-module computation failed for %s: %r",
                    metric_id,
                    exc,
                    extra={"metric_id": metric_id, "error": repr(exc)},
                )
                record["per_module"] = {}
                record["module_weights"] = repo_module_weights
                record["phases_module_weighted"] = {}
        results["metrics"][metric_id] = record

    log.info("Synthesising per-engineer view, risks, limitations")
    # PhaseBounds is a dataclass; ``asdict`` walks the field tree and
    # converts every ``datetime`` via the default repr — we then
    # overwrite the textual fields with explicit ISO 8601 strings to
    # keep downstream renderers consistent.
    bounds_dict = asdict(bounds)
    results["inflection"] = {
        "date": inflection.get("date") or inflection.get("inflection_date"),
        "method": inflection.get("method"),
        "rationale": inflection.get("rationale"),
        "inflection_date_iso": bounds_dict["inflection_date"].isoformat()
        if isinstance(bounds_dict["inflection_date"], datetime)
        else str(bounds_dict["inflection_date"]),
        "anchor_monday": bounds.anchor_monday.isoformat(),
        "rampup_end": bounds.rampup_end.isoformat(),
        "fallback_to_post_introduction": bounds.fallback_to_post_introduction,
        "phases": list(bounds.phases()),
    }
    results["active_engineers_after"] = _count_active_engineers_after(
        aliases, commits, bounds
    )
    results["per_engineer"] = aggregate_per_engineer(results, aliases)
    results["risks"] = synthesize_risks(results)
    results["limitations"] = synthesize_limitations(results)
    # ``date`` (not ``datetime``) captures the calendar-day range of
    # the analysis window — used by the Environment Verification
    # section of acceleration-report.md per AAP §0.7.2.2 Rule 6.
    start_date: date | None = (
        earliest_commit.date() if commit_dates else None
    )
    end_date: date | None = (
        latest_commit.date() if commit_dates else None
    )
    results["date_range"] = {
        "start": start_date.isoformat() if start_date else None,
        "end": end_date.isoformat() if end_date else None,
    }
    results["canonical_metric_ids"] = list(CANONICAL_METRIC_IDS)
    results["work_types"] = list(WORK_TYPES)
    results["module_prefixes"] = [list(item) for item in MODULE_PREFIXES]
    results["run_manifest_ref"] = {
        "head_sha": run_manifest.get("head_sha"),
        "repo_owner": run_manifest.get("repo_owner"),
        "repo_name": run_manifest.get("repo_name"),
        "extracted_at": run_manifest.get("extracted_at"),
    }
    results["computed_at"] = datetime.now(timezone.utc).isoformat()
    results["sources"] = {
        "commits": str(data_dir / "commits.jsonl"),
        "prs": str(data_dir / "prs.jsonl"),
        "reviews": str(data_dir / "reviews.jsonl"),
        "releases": str(data_dir / "releases.jsonl"),
        "reverts": str(data_dir / "reverts.jsonl"),
        "test_results": str(data_dir / "test_results.jsonl"),
        "issues": str(data_dir / "issues.jsonl"),
        "sla_source": str(data_dir / "sla_source.json"),
        "branch_protection": str(data_dir / "branch_protection.json"),
        "audit_log": str(data_dir / "audit_log.jsonl"),
        "github_access": str(data_dir / "github_access.json"),
        "inflection": str(data_dir / "inflection.json"),
    }

    args.manifest_output.parent.mkdir(parents=True, exist_ok=True)
    # ``allow_nan=False`` enforces RFC 8259 — any stray ``NaN``/``Infinity``
    # raises a ``ValueError`` rather than producing JSON-invalid output.
    # ``default=str`` falls back to ``str()`` for datetimes/Paths the
    # encoder cannot natively serialise.
    args.manifest_output.write_text(
        json.dumps(
            results,
            indent=2,
            ensure_ascii=False,
            default=str,
            allow_nan=False,
        ),
        encoding="utf-8",
    )
    log.info(
        "Wrote metrics.json → %s",
        args.manifest_output,
        extra={"path": str(args.manifest_output)},
    )

    args.reproduce_output.parent.mkdir(parents=True, exist_ok=True)
    args.reproduce_output.write_text(
        build_reproduce_script(run_manifest), encoding="utf-8"
    )
    log.info(
        "Wrote reproduce.sh → %s",
        args.reproduce_output,
        extra={"path": str(args.reproduce_output)},
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

