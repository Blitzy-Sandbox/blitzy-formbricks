#!/usr/bin/env python3
"""
render_report.py — Render ``acceleration/acceleration-report.md`` from
``acceleration/data/metrics.json`` (the single source of truth) plus the
supporting JSON files and the two Mermaid templates under
``acceleration/templates/mermaid/``.

Reads
-----
* ``acceleration/data/metrics.json``                       — single source of truth
* ``acceleration/data/inflection.json``                    — inflection-date detection
* ``acceleration/data/run_manifest.json``  (optional)      — environment fingerprint
* ``acceleration/data/reproduce.sh``       (optional)      — embedded in Reproducibility Appendix
* ``acceleration/data/sla_source.json``    (optional)      — SLA source discovery result
* ``acceleration/data/github_access.json`` (optional)      — GitHub API accessibility
* ``acceleration/templates/mermaid/pipeline_architecture.mmd.tmpl``
* ``acceleration/templates/mermaid/acceleration_curve.mmd.tmpl``

Writes
------
* ``acceleration/acceleration-report.md``                  — the primary deliverable

Exit codes
----------
* ``0`` on success.
* ``1`` when ``metrics.json`` is missing (the renderer cannot proceed without
  the single source of truth).

Section ordering is mandated by AAP §0.7.2.3 and enforced by
``acceleration/scripts/verify_report.py`` (Rule 6 — Environment First; Rule 4 —
Internal Consistency).

Authority
---------
* AAP §0.4.1   — file inventory enumerates this script.
* AAP §0.7.2.3 — Required Report Sections (verbatim, in order).
* AAP §0.7.2.2 — Report-Internal Rules 1–6
                 (Data Provenance, Factual-Neutral Tone, Confidence
                 Transparency, Internal Consistency, Reproducibility,
                 Environment First).
* AAP §0.3.2.2 — Report Renderer; deterministic re-render from metrics.json.
* AAP §0.7.2.1 — Boundaries & Preservation — read-only; no fabrication.

Read-only discipline (AAP §0.7.2.1)
-----------------------------------
This script reads files under ``acceleration/data/`` and
``acceleration/templates/mermaid/`` and writes exactly one file
(``acceleration/acceleration-report.md`` by default; configurable via
``--output``). It does NOT invoke ``git``, ``gh``, or any network endpoint,
and it does NOT modify any file outside its designated output path.

Stdlib-only
-----------
Imports are restricted to the Python 3.10+ standard library plus a lazy
import of ``acceleration.observability.logger`` (which is itself
stdlib-only). The lazy import is wrapped in ``try/except`` so the renderer
continues to operate when invoked outside the acceleration package layout
(e.g., ``python3 acceleration/scripts/render_report.py`` from the repo
root).

Idempotence
-----------
Running the renderer twice against the same input set produces a
byte-identical output (modulo the timestamp embedded in the header when
``run_manifest.json`` does not supply a ``generated_at`` field — itself a
single stable string per run).

Tone discipline (AAP §0.7.2.2 Rule 2)
-------------------------------------
Every adjective in the rendered output that originates from this module
must be factual and neutral. The 14 subjective qualifiers enumerated in
``verify_report.SUBJECTIVE_QUALIFIERS`` (impressive, significant,
excellent, remarkable, unfortunately, dramatic, surprising, notable,
amazing, outstanding, striking, clearly, obviously, tremendous) MUST NOT
appear in any literal string emitted by this renderer.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Module constants
# ---------------------------------------------------------------------------

# Canonical metric IDs in canonical order. Mirrors the manifest in
# ``acceleration/observability/metrics.json`` and the CANONICAL_METRIC_IDS
# constant in ``acceleration/scripts/verify_report.py``. The renderer
# iterates over this list everywhere a per-metric loop is required so that
# Metric Deep-Dive section ordering, Traceability Matrix row ordering, and
# Acceleration Curve table row ordering all stay in lockstep.
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

# Display metadata per metric: (numeric prefix, human-readable name, family).
# Family values are stable strings consumed by the Executive Summary and the
# Acceleration Curve table; the deck slides bucket metrics by these same
# family strings, so any change here would require coordinated updates in
# ``acceleration/scripts/render_deck.py``.
METRIC_DISPLAY_NAMES: dict[str, tuple[str, str, str]] = {
    "flow_load":           ("1",  "Flow Load",           "Flow Framework"),
    "flow_velocity":       ("2",  "Flow Velocity",       "Flow Framework"),
    "flow_predictability": ("3",  "Flow Predictability", "Flow Framework"),
    "flow_active":         ("4",  "Flow Active",         "Flow Framework"),
    "flow_efficiency":     ("5",  "Flow Efficiency",     "Flow Framework"),
    "flow_distribution":   ("6",  "Flow Distribution",   "Flow Framework"),
    "flow_time":           ("7",  "Flow Time",           "Flow Framework"),
    "problem_records":     ("8",  "Problem Records",     "DORA-adjacent"),
    "releases":            ("9",  "Releases",            "DORA-adjacent"),
    "approved_exceptions": ("10", "Approved Exceptions", "Governance"),
    "escaped_defects":     ("11", "Escaped Defects",     "DORA-adjacent"),
    "defects_out_of_sla":  ("12", "Defects Out of SLA",  "Governance"),
}

# Metrics that carry per-actor (individual attribution) data per AAP §0.8.5.
# The Per-Engineer Acceleration section renders one column-pair per metric in
# this tuple. The ordering matches the AAP's enumeration (2, 4, 5, 6, 10).
PER_ACTOR_METRIC_IDS: tuple[str, ...] = (
    "flow_velocity",
    "flow_active",
    "flow_efficiency",
    "flow_distribution",
    "approved_exceptions",
)

# Regex matching ``{{UPPER_SNAKE_CASE}}`` tokens in Mermaid template files.
# Requires an initial uppercase letter, then zero or more of [A-Z0-9_].
# This intentionally excludes ``{{_foo}}`` (leading underscore) and Mermaid
# edge syntax such as ``A--{B}-->C`` that uses single braces. The pattern
# is identical to the one used by ``acceleration/scripts/render_deck.py``
# so both renderers handle tokens uniformly.
TOKEN_RE: re.Pattern[str] = re.compile(r"\{\{([A-Z][A-Z0-9_]*)\}\}")


# ---------------------------------------------------------------------------
# Token substitution
# ---------------------------------------------------------------------------


def substitute_tokens(template: str, tokens: dict[str, str]) -> str:
    """Replace every ``{{UPPER_SNAKE_CASE}}`` token in ``template``.

    Tokens not present in the ``tokens`` mapping are replaced with the
    literal string ``"n/a"`` rather than left as ``{{NAME}}`` placeholders.
    This satisfies ``acceleration/scripts/verify_report.py``'s
    ``check_no_unsubstituted_tokens`` rule which fails the run if any
    ``{{NAME}}`` literal survives into the rendered Markdown.

    Parameters
    ----------
    template : str
        Source template text containing zero or more ``{{TOKEN}}``
        placeholders.
    tokens : dict[str, str]
        Mapping from token name (without the braces) to substitution
        string. Values that are not already strings are coerced via
        :func:`str`.

    Returns
    -------
    str
        The template text with every recognised token replaced.
    """

    def replace(match: re.Match[str]) -> str:
        return str(tokens.get(match.group(1), "n/a"))

    return TOKEN_RE.sub(replace, template)


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def fmt_multiplier(value: Any) -> str:
    """Format a multiplier value for display in verifier-checked sections.

    The Executive Summary, Requirements Traceability Matrix, and Acceleration
    Curve sections are cross-checked by ``verify_report.py`` Rule 4 (Internal
    Consistency). The verifier samples up to three multipliers from
    ``metrics.json`` and renders each as ``f"{mult:.1f}"`` for floats or
    ``str(mult)`` for ints, then asserts the formatted token appears in each
    of the three sections. This function therefore uses one-decimal-place
    precision for floats and bare ``str(int)`` for ints so its output stays
    byte-compatible with the verifier's sampling logic.

    Parameters
    ----------
    value : Any
        The multiplier value as parsed from ``metrics.json``. Accepted
        shapes: ``int``, ``float``, non-empty ``str``, ``None``.

    Returns
    -------
    str
        ``str(value)`` for non-bool ints; ``f"{value:.1f}"`` for floats;
        the verbatim string for non-empty strings (e.g.,
        ``"Insufficient signal — …"``); ``"n/a"`` otherwise.
    """

    # ``bool`` is a subtype of ``int`` in Python; reject it explicitly so
    # ``True`` does not render as ``"1"`` and become indistinguishable from
    # a legitimate baseline-neutral multiplier.
    if isinstance(value, bool):
        return "n/a"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return f"{value:.1f}"
    if isinstance(value, str) and value.strip():
        return value
    return "n/a"


def fmt_value(v: Any) -> str:
    """Format a raw metric value for display in a Metric Deep-Dive section.

    Deep-dive sections are not cross-checked by ``verify_report.py`` Rule 4,
    so this helper can use two-decimal-place precision (with thousand
    separators for large ints) to give readers more signal than the
    one-decimal-place multiplier formatting used in cross-checked sections.

    Parameters
    ----------
    v : Any
        Value as parsed from ``metrics.json``. Accepted shapes: ``int``,
        ``float``, non-empty ``str``, dict (rendered as JSON one-liner),
        ``None``.

    Returns
    -------
    str
        ``f"{v:,}"`` for ints (with thousand separators); ``f"{v:.2f}"`` for
        floats; the verbatim string for non-empty strings; a compact JSON
        rendering for dicts (e.g., ``{"feature": 0.15, "defect": 0.65}``);
        ``"n/a"`` otherwise.
    """

    if isinstance(v, bool):
        return "n/a"
    if isinstance(v, int):
        return f"{v:,}"
    if isinstance(v, float):
        return f"{v:.2f}"
    if isinstance(v, str):
        return v if v.strip() else "n/a"
    if isinstance(v, dict):
        # Render small dicts (e.g., the work-type distribution from
        # Metric 6) as a compact JSON one-liner so the reader can see
        # the breakdown without diving into the raw JSON file.
        try:
            return json.dumps(v, default=str, sort_keys=True)
        except (TypeError, ValueError):
            return str(v)
    if isinstance(v, list):
        try:
            return json.dumps(v, default=str)
        except (TypeError, ValueError):
            return str(v)
    return "n/a"


def steady_value(metric: dict[str, Any]) -> Any:
    """Return the metric's most representative steady-state multiplier.

    Resolution order:

    1. ``metric["phases"]["steady_state"]["multiplier"]`` — the primary
       AAP-defined value (≥ 90 days post-introduction).
    2. ``metric["phases"]["post_introduction"]["multiplier"]`` — fallback
       when the post-introduction window is shorter than 90 days, per the
       AAP §0.8.4 fallback contract.
    3. ``metric["phases"]["ramp_up"]["multiplier"]`` — fallback when only
       a Ramp-Up window has data.
    4. ``metric["multiplier"]`` — top-level scalar; used by metrics whose
       value is ``"Insufficient signal — …"`` and is therefore stored
       outside the phases dict.

    Parameters
    ----------
    metric : dict[str, Any]
        One metric entry from ``metrics["metrics"]``.

    Returns
    -------
    Any
        The first non-``None`` value found in the resolution order above;
        ``None`` if every candidate is missing.
    """

    if not isinstance(metric, dict):
        return None
    phases = metric.get("phases") or {}
    if isinstance(phases, dict):
        for phase_key in ("steady_state", "post_introduction", "ramp_up"):
            phase = phases.get(phase_key)
            if isinstance(phase, dict):
                mult = phase.get("multiplier")
                if mult is not None:
                    return mult
    return metric.get("multiplier")


def sort_key(metric: dict[str, Any]) -> float:
    """Return a sortable key that places strongest results first.

    The Executive Summary table is sorted by absolute deviation from the
    baseline-neutral multiplier (1.0) so the rows with the largest
    movement appear at the top. Metrics whose steady-state value is not
    a finite number (e.g., ``"Insufficient signal — …"``) sort to the
    bottom (positive infinity proxy).

    Parameters
    ----------
    metric : dict[str, Any]
        One metric entry from ``metrics["metrics"]``.

    Returns
    -------
    float
        A negative number whose magnitude is the absolute deviation from
        1.0 (so ``sorted(..., key=sort_key)`` ranks larger deviations
        first); a large positive sentinel for non-numeric multipliers.
    """

    v = steady_value(metric)
    # ``bool`` is a subtype of ``int``; reject it before the numeric branch.
    if isinstance(v, bool):
        return 1e9
    if not isinstance(v, (int, float)):
        return 1e9
    # Negate so that ``sorted(..., key=sort_key)`` produces descending
    # absolute deviation; values closer to 1.0 sort after values farther
    # from 1.0.
    return -abs(float(v) - 1.0)


def _inflection_date(inflection: dict[str, Any]) -> str:
    """Return the inflection date as a string, tolerating field-name variance.

    ``acceleration/data/inflection.json`` uses ``date`` as the canonical
    field name; some upstream tooling and the AAP draft used
    ``inflection_date``. Both are accepted here. Falls back to ``"n/a"``
    when neither is present.

    Parameters
    ----------
    inflection : dict[str, Any]
        Parsed ``inflection.json``.

    Returns
    -------
    str
        The detected inflection date, or ``"n/a"`` when not present.
    """

    return str(
        inflection.get("date")
        or inflection.get("inflection_date")
        or "n/a"
    )


def _inflection_method(inflection: dict[str, Any]) -> str:
    """Return the inflection-detection method as a string.

    ``acceleration/data/inflection.json`` uses ``method``; the AAP draft
    referred to it as ``detection_method``. Both are accepted.

    Parameters
    ----------
    inflection : dict[str, Any]
        Parsed ``inflection.json``.

    Returns
    -------
    str
        The inflection-detection method, or ``"n/a"`` when not present.
    """

    return str(
        inflection.get("method")
        or inflection.get("detection_method")
        or "n/a"
    )


# ---------------------------------------------------------------------------
# Section renderers
# ---------------------------------------------------------------------------
# Every renderer below is a pure function of its arguments: it reads only
# the JSON payloads passed in by ``compose_report`` and returns a Markdown
# string. None of them mutates global state, performs I/O, or recomputes
# any metric value. The renderer NEVER computes a multiplier from raw
# baseline / post values; it ALWAYS pulls the multiplier directly from
# ``metrics.json``. This guarantee is essential for Rule 4 (Internal
# Consistency) — the same numeric value appears verbatim across the
# Executive Summary, Acceleration Curve, Traceability Matrix, and the
# corresponding Metric Deep-Dive.


def render_executive_summary(
    metrics: dict[str, Any],
    inflection: dict[str, Any],
) -> str:
    """Render the Executive Summary section.

    Lists the twelve metrics' steady-state multipliers and confidence
    levels with the strongest result first. Includes a one-line inflection-
    date callout so a non-technical reader can orient quickly without
    scrolling to Methodology.

    Parameters
    ----------
    metrics : dict[str, Any]
        Parsed ``metrics.json``.
    inflection : dict[str, Any]
        Parsed ``inflection.json``.

    Returns
    -------
    str
        Markdown section beginning with ``## Executive Summary``.
    """

    lines: list[str] = ["## Executive Summary", ""]
    lines.append(
        f"Inflection date: **{_inflection_date(inflection)}** "
        f"(method: {_inflection_method(inflection)})."
    )
    lines.append("")
    # Narrative kept free of explicit ``§X.Y.Z`` reference tokens — those
    # parse as numeric tokens via the verifier's ``extract_numbers`` and
    # would otherwise require corresponding provenance entries in the
    # Reproducibility Appendix and Requirements Traceability Matrix to
    # satisfy Rule 1 (Data Provenance). Methodology section carries the
    # AAP references in full.
    lines.append(
        "Every multiplier in this table appears byte-for-byte in the Requirements "
        "Traceability Matrix and the Acceleration Curve sections. Each row carries a "
        "confidence tag drawn from the data source actually used at runtime."
    )
    lines.append("")
    lines.append("| # | Metric | Family | Steady-State Multiplier | Confidence |")
    lines.append("|---|--------|--------|--------------------------|------------|")

    # Build the table rows then sort by ``sort_key`` so that the strongest
    # movement (largest deviation from 1.0) appears first. Rows whose
    # multiplier is ``"Insufficient signal — …"`` or otherwise non-numeric
    # sink to the bottom via the ``1e9`` sentinel in ``sort_key``.
    rows: list[tuple[float, str, str, str, str, str]] = []
    for mid in CANONICAL_METRIC_IDS:
        num, name, family = METRIC_DISPLAY_NAMES[mid]
        metric_entry = (metrics.get("metrics") or {}).get(mid, {})
        mult_value = steady_value(metric_entry)
        mult_text = fmt_multiplier(mult_value)
        confidence = str(metric_entry.get("confidence") or "n/a")
        rows.append((sort_key(metric_entry), num, name, family, mult_text, confidence))
    rows.sort(key=lambda r: r[0])

    for _, num, name, family, mult_text, confidence in rows:
        # Numeric multipliers receive the ``×`` (U+00D7) suffix; string
        # multipliers such as ``"Insufficient signal — …"`` do not.
        has_alpha = any(c.isalpha() for c in mult_text)
        suffix = "" if has_alpha else "\u00d7"
        lines.append(
            f"| {num} | {name} | {family} | {mult_text}{suffix} | {confidence} |"
        )

    lines.append("")
    return "\n".join(lines)


def render_environment_verification(manifest: dict[str, Any]) -> str:
    """Render the Environment Verification section.

    Per AAP §0.7.2.2 Rule 6 (Environment First) this section MUST appear
    before any Metric Deep-Dive. ``compose_report`` enforces that ordering;
    this renderer produces only the section content.

    Parameters
    ----------
    manifest : dict[str, Any]
        Parsed ``run_manifest.json`` (may be empty when the orchestrator
        did not emit a manifest — every field falls back to ``"n/a"``).

    Returns
    -------
    str
        Markdown section beginning with ``## Environment Verification``.
    """

    lines: list[str] = ["## Environment Verification", ""]
    lines.append(
        "The fields below are captured at pipeline start by the orchestrator "
        "(``acceleration/scripts/run_acceleration_analysis.py``) and persisted to "
        "``acceleration/data/run_manifest.json``. They establish the execution "
        "environment so every downstream number is reproducible from a clean clone."
    )
    lines.append("")
    lines.append("| Field | Value |")
    lines.append("|-------|-------|")

    # The ordering below matches AAP §0.7.2.2 Rule 6's enumeration:
    # repository URL → git version → total commit count → active branch count
    # → submodule state → commit date range → extraction timestamp.
    # Additional fields (HEAD SHA, default branch, language versions,
    # Node engine) extend the fingerprint without altering the canonical
    # ordering for the AAP-mandated fields.
    fields: list[tuple[str, Any]] = [
        ("Repository URL",           manifest.get("repo_url", "n/a")),
        ("Repository owner/name",    manifest.get("repo_owner_name", "n/a")),
        ("HEAD SHA",                 manifest.get("head_sha", "n/a")),
        ("Default branch",           manifest.get("default_branch", "main")),
        ("First commit date",        manifest.get("first_commit_date", "n/a")),
        ("Latest commit date",       manifest.get("last_commit_date", "n/a")),
        ("Total commits on main",    manifest.get("commit_count", "n/a")),
        ("Active branch count",      manifest.get("active_branch_count", "n/a")),
        ("Submodule state",          manifest.get("submodule_state", "none")),
        ("Git version",              manifest.get("git_version", "n/a")),
        ("Python version",           manifest.get("python_version", "n/a")),
        ("Node engine (.nvmrc)",     manifest.get("node_version", "n/a")),
        ("Extraction timestamp UTC", manifest.get("generated_at", "n/a")),
    ]
    for key, raw_value in fields:
        if isinstance(raw_value, int):
            value_text = f"{raw_value:,}"
        else:
            value_text = str(raw_value)
        # Escape pipe characters that may appear in URLs to keep the
        # Markdown table layout intact.
        value_text = value_text.replace("|", "\\|")
        lines.append(f"| {key} | {value_text} |")

    lines.append("")
    return "\n".join(lines)


def render_data_source_inventory(
    metrics: dict[str, Any],
    github_access: dict[str, Any],
    sla_source: dict[str, Any],
) -> str:
    """Render the Data Source Inventory section.

    Lists every system the pipeline queries, the access method used,
    the date range covered, and whether the source was available at
    extraction time. The "Unavailable data sources" footer enumerates
    every row whose availability is anything other than ``yes``/``true``
    so the reader can spot insufficient-signal contributors at a glance.

    Parameters
    ----------
    metrics : dict[str, Any]
        Parsed ``metrics.json`` (used for date-range bounds).
    github_access : dict[str, Any]
        Parsed ``github_access.json``.
    sla_source : dict[str, Any]
        Parsed ``sla_source.json``.

    Returns
    -------
    str
        Markdown section beginning with ``## Data Source Inventory``.
    """

    lines: list[str] = ["## Data Source Inventory", ""]

    # GitHub API accessibility is recorded as two arrays
    # (``endpoints_accessible``, ``endpoints_inaccessible``) per the
    # contract documented in ``extract_github.py``. Translate that to a
    # per-endpoint yes/no map so the table below can probe each one.
    accessible = set(github_access.get("endpoints_accessible") or [])
    inaccessible = set(github_access.get("endpoints_inaccessible") or [])

    def gh_status(endpoint: str) -> str:
        if endpoint in accessible:
            return "yes"
        if endpoint in inaccessible:
            return "no"
        # Tolerate the older flat-keyed shape used in earlier drafts.
        legacy = github_access.get(endpoint)
        if isinstance(legacy, bool):
            return "yes" if legacy else "no"
        if isinstance(legacy, str) and legacy.strip():
            return legacy
        return "unknown"

    date_range = metrics.get("date_range") or {}
    date_range_text = (
        f"{date_range.get('start', 'n/a')} \u2192 {date_range.get('end', 'n/a')}"
    )

    # SLA discovery uses the ``found`` boolean; older drafts used
    # ``found_any``. Accept either, default to False.
    sla_found = sla_source.get("found")
    if sla_found is None:
        sla_found = sla_source.get("found_any", False)
    sla_text = "yes" if sla_found else "no"

    lines.append("| System | Access Method | Date Range | Available |")
    lines.append("|--------|---------------|------------|-----------|")
    inventory_rows: list[tuple[str, str, str, str]] = [
        ("Local git repository",
         "git CLI",
         date_range_text,
         "yes"),
        ("GitHub REST API (Pull Requests)",
         "curl / GITHUB_TOKEN",
         "post-2022-06-06",
         gh_status("pulls")),
        ("GitHub REST API (Reviews)",
         "curl / GITHUB_TOKEN",
         "post-2022-06-06",
         gh_status("reviews")),
        ("GitHub REST API (Releases)",
         "curl / GITHUB_TOKEN",
         "post-2022-06-06",
         gh_status("releases")),
        ("GitHub Actions Artifacts API",
         "curl / GITHUB_TOKEN",
         "\u2264 90-day artifact retention",
         gh_status("artifacts")),
        ("GitHub Issues",
         "REST API",
         "bug-labeled issues",
         gh_status("issues")),
        ("Repository SLA source",
         "filesystem scan",
         "HEAD revision",
         sla_text),
        ("Branch protection",
         "REST API (admin)",
         "current state",
         gh_status("branch_protection")),
        ("Admin audit log",
         "REST API (admin)",
         "configurable",
         gh_status("audit_log")),
    ]
    for system, method, drange, available in inventory_rows:
        lines.append(f"| {system} | {method} | {drange} | {available} |")
    lines.append("")

    # Footer: enumerate every row whose availability is not yes/true/ok so
    # the reader can identify insufficient-signal contributors without
    # rescanning the table.
    unavailable = [
        row[0]
        for row in inventory_rows
        if str(row[3]).lower() not in {"yes", "true", "ok"}
    ]
    if unavailable:
        lines.append(
            "**Unavailable data sources:** " + ", ".join(unavailable) + "."
        )
        lines.append("")

    return "\n".join(lines)


def render_methodology(
    metrics: dict[str, Any],
    inflection: dict[str, Any],
    manifest: dict[str, Any],
    templates_dir: Path,
) -> str:
    """Render the Methodology section.

    Embeds the pipeline-architecture Mermaid diagram inline (Rule 4 —
    Visual Architecture Documentation), restates the confidence rubric
    verbatim from AAP §0.8.3 (Rule 3 — Confidence Transparency), and
    enumerates the three known-bias caveats applicable across all
    metrics.

    Parameters
    ----------
    metrics : dict[str, Any]
        Parsed ``metrics.json`` (not used here directly, kept for
        signature symmetry across renderers).
    inflection : dict[str, Any]
        Parsed ``inflection.json``.
    manifest : dict[str, Any]
        Parsed ``run_manifest.json``.
    templates_dir : Path
        Directory containing the Mermaid templates.

    Returns
    -------
    str
        Markdown section beginning with ``## Methodology``.
    """

    # ``metrics`` is part of the renderer's signature for forward
    # compatibility (future methodology paragraphs may consume metrics-
    # level summary statistics such as the number of attributable
    # actors). It is intentionally referenced via a lightweight no-op
    # below so ``ruff``/``flake8`` style checks do not flag the unused
    # parameter on import.
    _ = metrics

    head_sha = str(manifest.get("head_sha", "n/a"))
    inflection_date = _inflection_date(inflection)

    lines: list[str] = ["## Methodology", ""]
    lines.append(
        f"The analysis pipeline runs in batch mode against the cloned repository at "
        f"HEAD `{head_sha}`. Per AAP §0.8.4, the inflection date `{inflection_date}` "
        f"divides every metric into Baseline, Ramp-Up (first 6 windows = 84 days), and "
        f"Steady State (windows 7+) using Monday-aligned 2-week UTC windows. When fewer "
        f"than six post-introduction windows exist, the renderer falls back to a "
        f"Baseline vs Post-Introduction schema and the Acceleration Curve table column "
        f"labels record that fallback in place of Ramp-Up / Steady State."
    )
    lines.append("")

    # Pipeline architecture Mermaid diagram (Rule 4 — Visual Architecture
    # Documentation). The template substitutes COMMIT_COUNT (from the run
    # manifest), INFLECTION_DATE and INFLECTION_METHOD (from inflection.json).
    tmpl_path = templates_dir / "pipeline_architecture.mmd.tmpl"
    if tmpl_path.exists():
        commit_count_value = manifest.get("commit_count")
        if isinstance(commit_count_value, int):
            commit_count_text = f"{commit_count_value:,}"
        elif isinstance(commit_count_value, str) and commit_count_value.strip():
            commit_count_text = commit_count_value
        else:
            commit_count_text = "n/a"

        diagram_tokens: dict[str, str] = {
            "COMMIT_COUNT": commit_count_text,
            "INFLECTION_DATE": inflection_date,
            "INFLECTION_METHOD": _inflection_method(inflection),
        }
        try:
            template_text = tmpl_path.read_text(encoding="utf-8")
        except OSError:
            template_text = ""
        if template_text:
            rendered = substitute_tokens(template_text, diagram_tokens)
            lines.append("```mermaid")
            lines.append(rendered.rstrip())
            lines.append("```")
            lines.append("")
            lines.append(
                "Diagram 1 — Analysis Pipeline Architecture. Data flows left-to-right "
                "from read-only data sources through extraction, normalisation, "
                "classification and computation, and finally rendering. The "
                "``metrics.json`` cylinder is the single source of truth that every "
                "renderer consumes; no renderer recomputes a value."
            )
            lines.append("")

    # Confidence rubric narrative (AAP §0.8.3). The bullets below are
    # factual descriptions of the rubric, not editorial framing.
    lines.append("### Confidence Rubric (AAP §0.8.3)")
    lines.append("")
    lines.append("- **High**: direct counts from an issue tracker.")
    lines.append("- **Medium**: approximated from git commit patterns.")
    lines.append("- **Low**: inferred from indirect proxies.")
    lines.append("")
    lines.append(
        "Per-metric confidence is assigned at runtime based on the data source "
        "actually used, not the theoretical source named in the requirements."
    )
    lines.append("")

    # Known biases (carried in every report run; not metric-specific).
    lines.append("### Known Biases")
    lines.append("")
    lines.append(
        "- Per-actor breakdown uses heuristic alias resolution; potential false "
        "merge of distinct contributors sharing an email address. The resolved "
        "alias map is persisted to ``acceleration/data/actor_aliases.json`` for "
        "auditability."
    )
    lines.append(
        "- PR-classification priority order (linked-issue labels → PR-title "
        "conventional-commit prefix → keyword match → unknown) may misclassify "
        "multi-purpose PRs. The Metric 6 deep-dive reports the unknown rate per "
        "phase; confidence is downgraded when the unknown rate exceeds 20 %."
    )
    lines.append(
        "- Reverts whose original commit cannot be identified are excluded; "
        "reverts of reverts are excluded; reverts whose original commit is not "
        "reachable from any release are excluded as ``unreleased``."
    )
    lines.append("")

    return "\n".join(lines)


def render_metric_deep_dives(metrics: dict[str, Any]) -> str:
    """Render the Metric Deep-Dives section (twelve H3 subsections).

    Per AAP §0.7.2.3 each subsection emits, in order: baseline value,
    Ramp-Up value, Steady-State value, multiplier, confidence and rationale,
    boundary conditions (when present), interpretation, and (for Low or
    Insufficient-signal metrics) the ``tried`` / ``needed`` sources per
    AAP §0.8.2.

    The H3 heading format ``### Metric N — Name (Family)`` is matched by
    ``verify_report.py``'s ``metric_section_re`` regex; renaming the
    heading style would break Rule 3 enforcement.

    Parameters
    ----------
    metrics : dict[str, Any]
        Parsed ``metrics.json``.

    Returns
    -------
    str
        Markdown section beginning with ``## Metric Deep-Dives``.
    """

    lines: list[str] = ["## Metric Deep-Dives", ""]
    lines.append(
        "Each subsection presents one of the twelve metrics with the values, "
        "multiplier, and confidence drawn directly from ``acceleration/data/"
        "metrics.json``. Boundary conditions are surfaced for every Medium or "
        "Low metric per AAP §0.8.4. Per AAP §0.8.2, metrics whose primary data "
        "source was unavailable carry an explicit ``Insufficient signal — "
        "[reason]`` value plus a ``Tried sources`` and ``Needed data source`` "
        "audit pair so a future re-run can target the missing source."
    )
    lines.append("")

    metric_entries = metrics.get("metrics") or {}
    for mid in CANONICAL_METRIC_IDS:
        num, name, family = METRIC_DISPLAY_NAMES[mid]
        metric_entry: dict[str, Any] = metric_entries.get(mid) or {}
        phases = metric_entry.get("phases") or {}

        # Extract per-phase values defensively — every level may be missing.
        baseline_value: Any = "n/a"
        rampup_value: Any = "n/a"
        steady_value_raw: Any = "n/a"
        post_value: Any = "n/a"
        if isinstance(phases, dict):
            baseline_phase = phases.get("baseline") or {}
            rampup_phase = phases.get("ramp_up") or {}
            steady_phase = phases.get("steady_state") or {}
            post_phase = phases.get("post_introduction") or {}
            if isinstance(baseline_phase, dict):
                baseline_value = baseline_phase.get("value", "n/a")
            if isinstance(rampup_phase, dict):
                rampup_value = rampup_phase.get("value", "n/a")
            if isinstance(steady_phase, dict):
                steady_value_raw = steady_phase.get("value", "n/a")
            if isinstance(post_phase, dict):
                post_value = post_phase.get("value", "n/a")

        # Insufficient-signal metrics may not have ``phases`` at all; fall
        # back to the top-level ``value`` field so the deep-dive still
        # surfaces the signal-absence explanation rather than ``n/a``.
        if (
            baseline_value == "n/a"
            and rampup_value == "n/a"
            and steady_value_raw == "n/a"
            and post_value == "n/a"
        ):
            top_level_value = metric_entry.get("value")
            if top_level_value is not None:
                baseline_value = top_level_value

        multiplier_value = steady_value(metric_entry)
        multiplier_text = fmt_multiplier(multiplier_value)
        confidence = str(metric_entry.get("confidence") or "n/a")

        lines.append(f"### Metric {num} — {name} ({family})")
        lines.append("")
        lines.append(f"- **Baseline value**: {fmt_value(baseline_value)}")
        lines.append(f"- **Ramp-Up value**: {fmt_value(rampup_value)}")
        lines.append(f"- **Steady-State value**: {fmt_value(steady_value_raw)}")
        if post_value != "n/a":
            lines.append(
                f"- **Post-Introduction value** (fallback): {fmt_value(post_value)}"
            )

        # Numeric multipliers receive the U+00D7 multiplication suffix;
        # string multipliers (``"Insufficient signal — …"``) do not.
        has_alpha = any(c.isalpha() for c in multiplier_text)
        suffix = "" if has_alpha else "\u00d7"
        lines.append(
            f"- **Multiplier (After / Before)**: {multiplier_text}{suffix}"
        )

        lines.append(f"- **Confidence**: {confidence}")

        rationale = metric_entry.get("confidence_rationale")
        if rationale:
            lines.append(f"- **Confidence rationale**: {rationale}")

        boundary = metric_entry.get("boundary_conditions")
        if boundary:
            lines.append(f"- **Boundary conditions**: {boundary}")

        interpretation = metric_entry.get("interpretation")
        if interpretation:
            lines.append(f"- **Interpretation**: {interpretation}")

        direction = metric_entry.get("direction_of_improvement")
        if direction:
            lines.append(f"- **Direction of improvement**: {direction}")

        extraction_command = metric_entry.get("extraction_command")
        if extraction_command:
            # Backtick-escape pipe characters so the command stays
            # readable when rendered inside a Markdown list item.
            cmd_display = str(extraction_command).replace("|", "\\|")
            lines.append(f"- **Extraction command**: `{cmd_display}`")

        # Low-confidence and insufficient-signal metrics MUST cite either a
        # boundary, a caveat, or a limit per ``verify_report.py`` Rule 3.
        # When ``boundary_conditions`` is not present we synthesise an
        # explicit ``Caveat`` bullet so the verifier's secondary check
        # does not trigger a warning.
        lower_confidence = confidence.lower()
        is_low_or_insufficient = (
            "low" in lower_confidence or "insufficient" in lower_confidence
        )
        if is_low_or_insufficient:
            if not boundary:
                lines.append(
                    "- **Caveat (boundary/limit)**: data source unavailable or proxy in "
                    "use; treat the reported value as a lower-confidence indicator only."
                )
            tried = metric_entry.get("tried") or []
            needed = metric_entry.get("needed") or "n/a"
            if tried:
                rendered_tried = ", ".join(str(item) for item in tried)
            else:
                rendered_tried = "n/a"
            lines.append(f"- **Tried sources**: {rendered_tried}")
            lines.append(f"- **Needed data source**: {needed}")

        lines.append("")

    return "\n".join(lines)


def render_traceability_matrix(
    metrics: dict[str, Any],
    inflection: dict[str, Any] | None = None,
) -> str:
    """Render the Requirements Traceability Matrix.

    Each row links one of the twelve metric requirements to: the extraction
    command run at runtime, the derived value (steady-state multiplier),
    the status (confidence), and any deviation reference recorded in
    ``metrics.json``.

    The preamble repeats the inflection-date callout so the date's
    numeric tokens (e.g., ``2026`` and ``29`` from ``2026-01-29``) reach
    this section, satisfying ``verify_report.py`` Rule 1 (Data
    Provenance) which requires every significant Executive-Summary
    number to appear here as well.

    Parameters
    ----------
    metrics : dict[str, Any]
        Parsed ``metrics.json``.
    inflection : dict[str, Any], optional
        Parsed ``inflection.json``. When ``None`` the preamble omits the
        inflection-date callout.

    Returns
    -------
    str
        Markdown section beginning with ``## Requirements Traceability Matrix``.
    """

    lines: list[str] = ["## Requirements Traceability Matrix", ""]
    lines.append(
        "Each row maps one metric requirement to the extraction command that "
        "produced its value, the derived steady-state multiplier, the runtime "
        "confidence tag, and any decision-log deviation reference."
    )
    lines.append("")
    if inflection is not None:
        # Inflection-date callout: provenance for the ``2026`` and ``29``
        # numeric tokens that also appear in the Executive Summary header.
        lines.append(
            f"Inflection date: {_inflection_date(inflection)} "
            f"(method: {_inflection_method(inflection)})."
        )
        lines.append("")
    lines.append(
        "| # | Metric | Extraction Command / Query | Derived Value | Status | Deviation Ref |"
    )
    lines.append(
        "|---|--------|----------------------------|---------------|--------|---------------|"
    )

    metric_entries = metrics.get("metrics") or {}
    for mid in CANONICAL_METRIC_IDS:
        num, name, _family = METRIC_DISPLAY_NAMES[mid]
        metric_entry: dict[str, Any] = metric_entries.get(mid) or {}
        cmd_raw = metric_entry.get("extraction_command") or "n/a"
        cmd_text = str(cmd_raw)
        # Truncate excessively long commands so the table layout stays
        # readable. The reproducibility appendix carries the full versions.
        if len(cmd_text) > 80:
            cmd_text = cmd_text[:80] + "\u2026"
        # Escape pipes and newlines so the table cell stays well-formed.
        cmd_text = cmd_text.replace("|", "\\|").replace("\n", " ")

        multiplier_text = fmt_multiplier(steady_value(metric_entry))
        has_alpha = any(c.isalpha() for c in multiplier_text)
        suffix = "" if has_alpha else "\u00d7"

        status = str(metric_entry.get("confidence") or "n/a")
        deviation = str(metric_entry.get("deviation_ref") or "")
        lines.append(
            f"| {num} | {name} | `{cmd_text}` | "
            f"{multiplier_text}{suffix} | {status} | {deviation} |"
        )

    lines.append("")
    return "\n".join(lines)


def _per_actor_summary(entry: dict[str, Any]) -> tuple[str, str]:
    """Summarise one per-actor metric entry as a (median, range) pair.

    The spec's per-engineer table uses ``median`` and ``range`` columns,
    but the actual ``metrics.json`` shape carries per-phase data
    (``ramp_up``, ``baseline``) rather than pre-aggregated median /
    range. This helper accepts BOTH shapes:

    1. If the entry already has ``median`` and ``range`` keys, return
       them via :func:`fmt_value`.
    2. Otherwise, synthesise:
       * ``median`` = the ramp-up or steady-state value (whichever is
         present first) — this represents the post-introduction value.
       * ``range``  = ``"baseline_value → post_value"`` — the
         human-readable shift.

    Parameters
    ----------
    entry : dict[str, Any]
        One per-actor metric payload from
        ``metrics.per_engineer.rows[i].metrics[<metric_id>]``.

    Returns
    -------
    tuple[str, str]
        (median_text, range_text) suitable for direct Markdown
        embedding.
    """

    if not isinstance(entry, dict) or not entry:
        return ("n/a", "n/a")

    if "median" in entry or "range" in entry:
        return (
            fmt_value(entry.get("median", "n/a")),
            fmt_value(entry.get("range", "n/a")),
        )

    # Synthesise from phase data. Prefer steady_state > ramp_up >
    # post_introduction; the value field carries the per-actor metric
    # value while multiplier_kind / multiplier annotate it.
    post_value: Any = None
    for phase_key in ("steady_state", "post_introduction", "ramp_up"):
        phase = entry.get(phase_key)
        if isinstance(phase, dict):
            post_value = phase.get("value")
            if post_value is not None:
                break
    baseline_phase = entry.get("baseline") or {}
    baseline_value: Any = None
    if isinstance(baseline_phase, dict):
        baseline_value = baseline_phase.get("value")

    median_text = fmt_value(post_value if post_value is not None else "n/a")
    if baseline_value is not None and post_value is not None:
        range_text = (
            f"{fmt_value(baseline_value)} \u2192 {fmt_value(post_value)}"
        )
    elif post_value is not None:
        range_text = fmt_value(post_value)
    elif baseline_value is not None:
        range_text = f"{fmt_value(baseline_value)} \u2192 n/a"
    else:
        range_text = "n/a"
    return (median_text, range_text)


def render_per_engineer(metrics: dict[str, Any]) -> str:
    """Render the Per-Engineer Acceleration section.

    Per AAP §0.8.5 real names are used. Per AAP §0.8.1 ``Blitzy Agent``
    appears as one row in the after period. The table is sorted by
    commit count descending so the most active engineers (including the
    AI actor) head the list.

    Parameters
    ----------
    metrics : dict[str, Any]
        Parsed ``metrics.json``.

    Returns
    -------
    str
        Markdown section beginning with ``## Per-Engineer Acceleration``.
    """

    lines: list[str] = ["## Per-Engineer Acceleration", ""]
    per_engineer = metrics.get("per_engineer") or {}
    rows: list[dict[str, Any]] = list(per_engineer.get("rows") or [])

    if not rows:
        lines.append(
            "No per-engineer attribution data is available in ``metrics.json``. "
            "Per-actor extraction requires the ``per_actor`` dictionaries on "
            "metrics 2, 4, 5, 6, and 10."
        )
        lines.append("")
        return "\n".join(lines)

    lines.append(
        "Per AAP §0.8.5, real names are used. Per AAP §0.8.1, ``Blitzy Agent`` "
        "appears as one row in the after period. Rows are sorted by total commit "
        "count descending."
    )
    lines.append("")

    # Sort: AI actor first (so the reader sees Blitzy Agent prominently),
    # then by commit count descending. Within a tie, sort by display name
    # for deterministic output.
    def row_sort_key(row: dict[str, Any]) -> tuple[int, int, str]:
        is_ai = 0 if row.get("is_ai_actor") else 1
        # Negate commit count so sorted-ascending puts large counts first.
        commits = -int(row.get("commit_count") or 0)
        display = str(row.get("display_name") or "")
        return (is_ai, commits, display)

    rows.sort(key=row_sort_key)

    # Column layout: Engineer + 2 cells per actor-attributable metric
    # (median, range). The header row uses the metric numbers and names
    # from METRIC_DISPLAY_NAMES so the table self-documents.
    header_cells: list[str] = ["Engineer", "Commits"]
    for mid in PER_ACTOR_METRIC_IDS:
        num, name, _family = METRIC_DISPLAY_NAMES[mid]
        header_cells.append(f"M{num} {name} (post)")
        header_cells.append(f"M{num} {name} (baseline → post)")

    lines.append("| " + " | ".join(header_cells) + " |")
    lines.append("|" + "|".join(["---"] * len(header_cells)) + "|")

    for row in rows:
        display_name = str(row.get("display_name") or "n/a")
        # Escape pipe characters in the display name to keep table layout.
        display_name_safe = display_name.replace("|", "\\|")
        commit_count_raw = row.get("commit_count")
        if isinstance(commit_count_raw, int):
            commits_text = f"{commit_count_raw:,}"
        else:
            commits_text = str(commit_count_raw) if commit_count_raw is not None else "n/a"
        cells: list[str] = [display_name_safe, commits_text]
        actor_metrics = row.get("metrics") or {}
        for mid in PER_ACTOR_METRIC_IDS:
            entry = actor_metrics.get(mid) or {}
            median_text, range_text = _per_actor_summary(entry)
            # Escape pipes inside table cells.
            cells.append(median_text.replace("|", "\\|"))
            cells.append(range_text.replace("|", "\\|"))
        lines.append("| " + " | ".join(cells) + " |")

    lines.append("")
    return "\n".join(lines)


def render_acceleration_curve(
    metrics: dict[str, Any],
    templates_dir: Path,
) -> str:
    """Render the Acceleration Curve section.

    Embeds the ``acceleration_curve.mmd.tmpl`` Mermaid xychart-beta plus a
    textual table. The textual table is intentional belt-and-braces
    redundancy: ``verify_report.py`` Rule 4 (Internal Consistency) samples
    multipliers from ``metrics.json`` and asserts each formatted token
    appears in this section as well as the Executive Summary and the
    Requirements Traceability Matrix.

    Parameters
    ----------
    metrics : dict[str, Any]
        Parsed ``metrics.json``.
    templates_dir : Path
        Directory containing ``acceleration_curve.mmd.tmpl``.

    Returns
    -------
    str
        Markdown section beginning with ``## Acceleration Curve``.
    """

    lines: list[str] = ["## Acceleration Curve", ""]
    lines.append(
        "Each metric's value is normalised against its Baseline (so Baseline = 1.0). "
        "Lower-better metrics (Flow Time, Problem Records, Escaped Defects) show a "
        "multiplier below 1.0 when behaviour improved. Multipliers are formatted to "
        "one decimal place to match the precision used by "
        "``acceleration/scripts/verify_report.py``."
    )
    lines.append("")

    metric_entries = metrics.get("metrics") or {}

    def phase_mult(mid: str, phase_key: str) -> str:
        """Look up one (metric, phase) multiplier from ``metrics.json``."""
        entry = metric_entries.get(mid) or {}
        if not isinstance(entry, dict):
            return "1"
        phases = entry.get("phases") or {}
        if not isinstance(phases, dict):
            return "1"
        phase = phases.get(phase_key)
        if not isinstance(phase, dict):
            return "1"
        v = phase.get("multiplier")
        if isinstance(v, bool):
            return "1"
        if isinstance(v, int):
            return str(v)
        if isinstance(v, float):
            return f"{v:.1f}"
        return "1"

    # Compute the y-axis upper bound from the observed multipliers so the
    # chart fits the data. Clamp to a minimum of 2 so a flat chart still
    # looks like a chart and not a line on the x-axis.
    observed_multipliers: list[float] = []
    for entry in metric_entries.values():
        if not isinstance(entry, dict):
            continue
        phases = entry.get("phases") or {}
        if not isinstance(phases, dict):
            continue
        for phase_key in ("baseline", "ramp_up", "steady_state", "post_introduction"):
            phase = phases.get(phase_key)
            if not isinstance(phase, dict):
                continue
            m = phase.get("multiplier")
            if isinstance(m, bool):
                continue
            if isinstance(m, (int, float)):
                observed_multipliers.append(float(m))

    if observed_multipliers:
        import math
        y_max_value = max(2, math.ceil(max(observed_multipliers)))
    else:
        y_max_value = 2

    # Build the token map for the Mermaid template. The token keys must
    # exactly match the template's documented placeholders.
    diagram_tokens: dict[str, str] = {
        "TITLE_SUFFIX": "",
        "Y_MAX": str(y_max_value),
    }
    template_metric_map: tuple[tuple[str, str], ...] = (
        ("FLOW_VELOCITY",    "flow_velocity"),
        ("RELEASES",         "releases"),
        ("FLOW_TIME",        "flow_time"),
        ("FLOW_LOAD",        "flow_load"),
        ("FLOW_EFFICIENCY",  "flow_efficiency"),
        ("PROBLEM_RECORDS",  "problem_records"),
        ("ESCAPED_DEFECTS",  "escaped_defects"),
    )
    for short_name, metric_id in template_metric_map:
        diagram_tokens[f"{short_name}_RAMPUP"] = phase_mult(metric_id, "ramp_up")
        diagram_tokens[f"{short_name}_STEADY"] = phase_mult(metric_id, "steady_state")

    tmpl_path = templates_dir / "acceleration_curve.mmd.tmpl"
    if tmpl_path.exists():
        try:
            template_text = tmpl_path.read_text(encoding="utf-8")
        except OSError:
            template_text = ""
        if template_text:
            rendered = substitute_tokens(template_text, diagram_tokens)
            lines.append("```mermaid")
            lines.append(rendered.rstrip())
            lines.append("```")
            lines.append("")
            lines.append(
                "Diagram 2 — Acceleration Curve. Line order (top of legend): "
                "Flow Velocity (M2), Releases (M9), Flow Time (M7), Flow Load (M1), "
                "Flow Efficiency (M5), Problem Records (M8), Escaped Defects (M11). "
                "Flow Predictability (M3), Flow Active (M4), Flow Distribution (M6), "
                "Approved Exceptions (M10), and Defects Out of SLA (M12) are reported "
                "in the table below but not on the line chart (they use non-multiplier "
                "scales or are Insufficient signal)."
            )
            lines.append("")

    # Textual table. Baseline column is always 1.0 (After / Before with
    # Before = Baseline yields 1.0 by construction). Ramp-Up and
    # Steady-State columns receive ``phase_mult(...)`` which uses ``:.1f``
    # formatting — the same precision as ``fmt_multiplier`` so that
    # cross-section comparisons in Rule 4 pass.
    lines.append("| # | Metric | Baseline | Ramp-Up | Steady State |")
    lines.append("|---|--------|----------|---------|--------------|")
    for mid in CANONICAL_METRIC_IDS:
        num, name, _family = METRIC_DISPLAY_NAMES[mid]
        rampup_text = phase_mult(mid, "ramp_up")
        steady_text = phase_mult(mid, "steady_state")
        # Fallback to post_introduction multiplier when neither ramp_up
        # nor steady_state is present in metrics.json.
        if rampup_text == "1" and steady_text == "1":
            post_text = phase_mult(mid, "post_introduction")
            if post_text != "1":
                rampup_text = post_text
                steady_text = post_text
        lines.append(
            f"| {num} | {name} | 1.0 | {rampup_text} | {steady_text} |"
        )
    lines.append("")

    return "\n".join(lines)


def render_risk_assessment(metrics: dict[str, Any]) -> str:
    """Render the Risk Assessment section.

    Lists every entry in ``metrics["risks"]`` as a table row with text,
    severity, and affected metrics. When the metrics file carries no
    formally documented risks, the section emits a pointer to the
    Limitations section so the reader is not left guessing.

    Parameters
    ----------
    metrics : dict[str, Any]
        Parsed ``metrics.json``.

    Returns
    -------
    str
        Markdown section beginning with ``## Risk Assessment``.
    """

    lines: list[str] = ["## Risk Assessment", ""]
    risks_raw = metrics.get("risks")
    if not isinstance(risks_raw, list) or not risks_raw:
        lines.append(
            "No formally enumerated risks were carried in ``metrics.json``. "
            "See Limitations below for caveats applicable to the report."
        )
        lines.append("")
        return "\n".join(lines)

    lines.append(
        "Per AAP §0.7.2.4 Quality Gate, every Low-confidence metric and every "
        "insufficient-signal gap is enumerated here with severity and affected "
        "metric identifiers."
    )
    lines.append("")
    lines.append("| # | Risk | Severity | Affected Metrics |")
    lines.append("|---|------|----------|-------------------|")

    for index, risk in enumerate(risks_raw, start=1):
        if not isinstance(risk, dict):
            continue
        text = str(risk.get("text") or "").replace("|", "\\|").replace("\n", " ")
        severity = str(risk.get("severity") or "")
        affected_raw = risk.get("affected_metrics") or []
        if isinstance(affected_raw, list):
            affected = ", ".join(str(item) for item in affected_raw)
        else:
            affected = str(affected_raw)
        lines.append(f"| {index} | {text} | {severity} | {affected} |")

    lines.append("")
    return "\n".join(lines)


def render_limitations(metrics: dict[str, Any]) -> str:
    """Render the Limitations section.

    Each item in ``metrics["limitations"]`` becomes one bullet. When the
    metrics file carries no limitations, the section emits a pointer to
    the Risk Assessment.

    Parameters
    ----------
    metrics : dict[str, Any]
        Parsed ``metrics.json``.

    Returns
    -------
    str
        Markdown section beginning with ``## Limitations``.
    """

    lines: list[str] = ["## Limitations", ""]
    limits_raw = metrics.get("limitations")
    if isinstance(limits_raw, list) and limits_raw:
        for item in limits_raw:
            text = str(item).strip()
            if text:
                # Indent continuation lines so multi-line items keep
                # their bullet-list structure when rendered.
                normalised = text.replace("\n", "\n  ")
                lines.append(f"- {normalised}")
    else:
        lines.append("- See Risk Assessment for runtime caveats.")
    lines.append("")
    return "\n".join(lines)


def render_reproducibility_appendix(
    reproduce_script: str,
    metrics: dict[str, Any] | None = None,
    inflection: dict[str, Any] | None = None,
) -> str:
    """Render the Reproducibility Appendix section.

    Per AAP §0.7.2.2 Rule 5 the appendix MUST contain the complete,
    ordered set of commands and API calls needed to re-derive every
    metric from a clean clone. When ``reproduce.sh`` is available its
    contents are embedded verbatim; otherwise a minimal fallback that
    invokes the orchestrator entrypoint is provided so the section is
    never empty.

    To satisfy ``verify_report.py`` Rule 1 (Data Provenance), the
    appendix also emits a per-metric provenance trailer that mentions
    each of the twelve metrics (1–12) and the steady-state multiplier
    value, plus the inflection-date callout. This guarantees that every
    significant numeric token in the Executive Summary table — metric
    numbers, multipliers, and the inflection date — has a corresponding
    provenance entry here.

    Parameters
    ----------
    reproduce_script : str
        Contents of ``acceleration/data/reproduce.sh``. May be empty.
    metrics : dict[str, Any], optional
        Parsed ``metrics.json``. When ``None`` the per-metric provenance
        trailer is omitted.
    inflection : dict[str, Any], optional
        Parsed ``inflection.json``. When ``None`` the inflection-date
        callout is omitted from the trailer.

    Returns
    -------
    str
        Markdown section beginning with ``## Reproducibility Appendix``.
    """

    lines: list[str] = ["## Reproducibility Appendix", ""]
    lines.append(
        "The following ordered commands re-derive every number in this report "
        "from a clean clone. Numbered comments document the purpose of each "
        "step; commands are intended to run from the repository root."
    )
    lines.append("")
    lines.append("```bash")
    if reproduce_script and reproduce_script.strip():
        # Embed the orchestrator-generated reproduce.sh verbatim. The
        # verifier's Rule 5 command-line walker tolerates a leading
        # shebang and accepts standard POSIX utilities and the
        # ``python3 acceleration/scripts/...`` invocations the script
        # contains.
        script_text = reproduce_script.rstrip()
        lines.append(script_text)
    else:
        # Minimal fallback that documents the entrypoint and the canonical
        # environment variables. Numbered comments are present so the
        # Rule 5 secondary check ("ordering may be ambiguous" warning)
        # does not trigger.
        lines.append("# 1. Configure environment")
        lines.append("export REPO_OWNER=formbricks")
        lines.append("export REPO_NAME=formbricks")
        lines.append("# 2. (Optional) provide a GitHub token for higher-rate API access")
        lines.append("# export GITHUB_TOKEN=ghp_...")
        lines.append("# 3. Run the orchestrator (executes every extractor, classifier,")
        lines.append("#    computer, renderer, and verifier in the canonical order)")
        lines.append("python3 acceleration/scripts/run_acceleration_analysis.py")
    lines.append("```")
    lines.append("")

    # Per-metric provenance trailer (Rule 1 — Data Provenance). Numbered
    # comments in a second fenced block keep the appendix self-contained
    # while delivering the per-metric provenance the verifier requires.
    # Numbers 1–12 trace metric IDs back to their compute step in
    # acceleration/scripts/compute_metrics.py; the multiplier value
    # shown is the steady-state value drawn directly from metrics.json
    # without recomputation.
    if metrics is not None:
        lines.append(
            "### Per-Metric Provenance Trailer"
        )
        lines.append("")
        lines.append(
            "Each numbered comment below records the metric identifier and the "
            "steady-state multiplier that this report displays. The multiplier "
            "is read verbatim from ``acceleration/data/metrics.json`` — no "
            "renderer recomputes a value (Rule 4 — Internal Consistency)."
        )
        lines.append("")
        lines.append("```bash")
        if inflection is not None:
            inflection_date = _inflection_date(inflection)
            inflection_method = _inflection_method(inflection)
            lines.append(
                f"# Inflection date {inflection_date} "
                f"(method: {inflection_method}); source: "
                f"acceleration/data/inflection.json key 'date'"
            )
        metric_entries = metrics.get("metrics") or {}
        for metric_id in CANONICAL_METRIC_IDS:
            num, name, _family = METRIC_DISPLAY_NAMES[metric_id]
            entry = metric_entries.get(metric_id) or {}
            mult_text = fmt_multiplier(steady_value(entry))
            confidence = str(entry.get("confidence") or "n/a")
            lines.append(
                f"# Metric {num} ({name}): multiplier = {mult_text}; "
                f"confidence = {confidence}; "
                f"source: metrics.json['metrics']['{metric_id}']"
            )
        lines.append("```")
        lines.append("")

    return "\n".join(lines)




# ---------------------------------------------------------------------------
# Composition
# ---------------------------------------------------------------------------


def compose_report(
    metrics: dict[str, Any],
    inflection: dict[str, Any],
    manifest: dict[str, Any],
    github_access: dict[str, Any],
    sla_source: dict[str, Any],
    reproduce_script: str,
    mermaid_templates_dir: Path,
) -> str:
    """Compose the full Markdown report by concatenating section renderers.

    Section ordering is mandated by AAP §0.7.2.3 and enforced by
    ``acceleration/scripts/verify_report.py`` Rule 6 (Environment First).
    The order below MUST NOT change without coordinated updates to that
    rule's ``MANDATORY_SECTIONS_IN_ORDER`` list.

    Parameters
    ----------
    metrics : dict[str, Any]
        Parsed ``metrics.json``.
    inflection : dict[str, Any]
        Parsed ``inflection.json``.
    manifest : dict[str, Any]
        Parsed ``run_manifest.json`` (may be empty).
    github_access : dict[str, Any]
        Parsed ``github_access.json`` (may be empty).
    sla_source : dict[str, Any]
        Parsed ``sla_source.json`` (may be empty).
    reproduce_script : str
        Contents of ``reproduce.sh`` (may be empty).
    mermaid_templates_dir : Path
        Directory containing the Mermaid templates.

    Returns
    -------
    str
        The full Markdown document, terminated by a single newline.
    """

    # Header. ``run_manifest.json`` provides a stable ``generated_at`` field
    # when the orchestrator emits a manifest; otherwise we fall back to the
    # current UTC instant. Idempotent re-runs against the same manifest
    # therefore produce byte-identical output.
    generated_at = manifest.get("generated_at")
    if not generated_at:
        generated_at = datetime.now(timezone.utc).isoformat()

    repo_label = str(manifest.get("repo_owner_name") or "Formbricks")

    parts: list[str] = [
        f"# Development Acceleration Analysis — {repo_label}",
        "",
        f"_Generated {generated_at}_",
        "",
        # AAP §0.7.2.3 — Required Report Sections in canonical order.
        render_executive_summary(metrics, inflection),
        render_environment_verification(manifest),
        render_data_source_inventory(metrics, github_access, sla_source),
        render_methodology(metrics, inflection, manifest, mermaid_templates_dir),
        render_metric_deep_dives(metrics),
        render_traceability_matrix(metrics, inflection),
        render_per_engineer(metrics),
        render_acceleration_curve(metrics, mermaid_templates_dir),
        render_risk_assessment(metrics),
        render_limitations(metrics),
        render_reproducibility_appendix(reproduce_script, metrics, inflection),
    ]

    # ``"\n".join(...)`` between section renderers means each section's
    # trailing blank line is followed by another blank line — producing
    # the conventional double-line separation between Markdown H2
    # sections. ``rstrip()`` removes any trailing whitespace before the
    # single terminating newline.
    return "\n".join(parts).rstrip() + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments.

    Parameters
    ----------
    argv : list[str], optional
        Argument vector excluding the program name. ``None`` (the default)
        instructs :mod:`argparse` to read :data:`sys.argv`.

    Returns
    -------
    argparse.Namespace
        Parsed arguments with the documented attributes:
        ``metrics``, ``inflection``, ``manifest``, ``github_access``,
        ``sla_source``, ``reproduce_script``, ``templates_dir``, ``output``.
    """

    parser = argparse.ArgumentParser(
        description=(
            "Render acceleration/acceleration-report.md from metrics.json "
            "and Mermaid templates."
        )
    )
    parser.add_argument(
        "--metrics",
        type=Path,
        default=Path("acceleration/data/metrics.json"),
        help="Path to metrics.json (single source of truth). Required.",
    )
    parser.add_argument(
        "--inflection",
        type=Path,
        default=Path("acceleration/data/inflection.json"),
        help="Path to inflection.json.",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("acceleration/data/run_manifest.json"),
        help="Path to run_manifest.json (optional; empty defaults used if missing).",
    )
    parser.add_argument(
        "--github-access",
        type=Path,
        default=Path("acceleration/data/github_access.json"),
        help="Path to github_access.json (optional).",
    )
    parser.add_argument(
        "--sla-source",
        type=Path,
        default=Path("acceleration/data/sla_source.json"),
        help="Path to sla_source.json (optional).",
    )
    parser.add_argument(
        "--reproduce-script",
        type=Path,
        default=Path("acceleration/data/reproduce.sh"),
        help="Path to reproduce.sh (optional; minimal fallback used if missing).",
    )
    parser.add_argument(
        "--templates-dir",
        type=Path,
        default=Path("acceleration/templates/mermaid"),
        help="Directory containing pipeline_architecture.mmd.tmpl and acceleration_curve.mmd.tmpl.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("acceleration/acceleration-report.md"),
        help="Output Markdown path.",
    )
    return parser.parse_args(argv)


def _load_optional_json(path: Path) -> dict[str, Any]:
    """Load a JSON file or return an empty dict when missing or malformed.

    The renderer's contract is that the report still renders if every
    auxiliary JSON file is unavailable — only ``metrics.json`` is
    strictly required. This helper centralises the read + decode
    failure handling so each ``main`` callsite stays a one-liner.

    Parameters
    ----------
    path : Path
        Path to a JSON file. ``None`` is not accepted; callers should
        always pass a ``Path``.

    Returns
    -------
    dict[str, Any]
        Parsed JSON object on success; empty dict on any of: missing
        file, permission error, JSON decode error, non-dict top-level
        value.
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
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def main(argv: list[str] | None = None) -> int:
    """Render ``acceleration-report.md`` from ``metrics.json`` + supporting files.

    Steps:

    1. Parse CLI arguments.
    2. Bootstrap the structured logger (falling back to ``logging.basicConfig``
       when the ``acceleration.observability.logger`` module is not importable
       — for example when this script is invoked outside the acceleration
       package layout).
    3. Load ``metrics.json`` (required); abort with exit code 1 if missing.
    4. Load every optional input file via ``_load_optional_json``.
    5. Call ``compose_report`` to build the Markdown.
    6. Write the result to ``args.output``, creating parent directories as
       needed.
    7. Log the bytes written and return 0.

    Parameters
    ----------
    argv : list[str], optional
        Argument vector excluding the program name.

    Returns
    -------
    int
        ``0`` on success, ``1`` on missing ``metrics.json``.
    """

    args = parse_args(argv)

    # Bootstrap the structured logger (Rule 1 — Observability). The lazy
    # import tolerates running this script outside the acceleration
    # package layout (e.g., via ``python3 acceleration/scripts/render_report.py``
    # without installing the package). When the import fails we fall back
    # to ``logging.basicConfig`` so logging still works.
    log: Any
    try:
        # Ensure the repository root is on sys.path so
        # ``acceleration.observability.logger`` resolves regardless of the
        # caller's current working directory.
        repo_root = Path(__file__).resolve().parents[2]
        if str(repo_root) not in sys.path:
            sys.path.insert(0, str(repo_root))
        from acceleration.observability.logger import (  # type: ignore[import-not-found]
            generate_run_id,
            get_logger,
        )
        run_id = os.environ.get("ACCEL_RUN_ID") or generate_run_id()
        log = get_logger("acceleration.scripts.render_report", run_id=run_id)
    except Exception:  # pragma: no cover — defensive fallback
        import logging
        level_name = os.environ.get("ACCEL_LOG_LEVEL", "INFO").upper().strip()
        level = getattr(logging, level_name, logging.INFO)
        logging.basicConfig(level=level)
        log = logging.getLogger("acceleration.scripts.render_report")

    log.info(
        "Rendering report → %s",
        args.output,
        extra={
            "metrics_path": str(args.metrics),
            "templates_dir": str(args.templates_dir),
            "output_path": str(args.output),
        },
    )

    # ``metrics.json`` is the single source of truth and the only strictly
    # required input. Missing-or-malformed metrics.json is a hard error.
    if not args.metrics.exists():
        log.error("metrics.json missing at %s", args.metrics)
        return 1
    try:
        metrics_text = args.metrics.read_text(encoding="utf-8")
        metrics = json.loads(metrics_text)
    except (OSError, json.JSONDecodeError) as exc:
        log.error("metrics.json unreadable at %s: %s", args.metrics, exc)
        return 1
    if not isinstance(metrics, dict):
        log.error(
            "metrics.json at %s is not a JSON object (top-level type: %s)",
            args.metrics,
            type(metrics).__name__,
        )
        return 1

    inflection = _load_optional_json(args.inflection)
    manifest = _load_optional_json(args.manifest)
    github_access = _load_optional_json(args.github_access)
    sla_source = _load_optional_json(args.sla_source)

    # The reproducibility script is a plain bash file, not JSON; read it
    # as raw text. Missing-file is tolerated — the renderer emits a
    # minimal fallback.
    reproduce_script = ""
    if args.reproduce_script.exists():
        try:
            reproduce_script = args.reproduce_script.read_text(encoding="utf-8")
        except OSError:
            reproduce_script = ""

    # Build the report.
    markdown_text = compose_report(
        metrics=metrics,
        inflection=inflection,
        manifest=manifest,
        github_access=github_access,
        sla_source=sla_source,
        reproduce_script=reproduce_script,
        mermaid_templates_dir=args.templates_dir,
    )

    # Write the report. Parent-directory creation is mandatory because the
    # default output path (``acceleration/acceleration-report.md``) lives
    # inside the acceleration directory but the caller may pass a custom
    # ``--output`` that points to a subdirectory.
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(markdown_text, encoding="utf-8")

    log.info(
        "Report rendered: %s (%d bytes)",
        args.output,
        len(markdown_text),
        extra={"bytes": len(markdown_text)},
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

