#!/usr/bin/env python3
"""
render_deck.py
==============

Render ``acceleration/executive-presentation.html`` from
``acceleration/data/metrics.json`` (the single source of truth) plus the
seventeen ``slide_*.html.tmpl`` files and ``theme.css`` under
``acceleration/templates/deck/``.

The output is a SELF-CONTAINED single HTML file. The only external
network references are the three CDN-pinned libraries
(reveal.js 5.1.0, Mermaid 11.15.0, Lucide 0.460.0) and Google Fonts.
The Mermaid pin is intentionally raised from the AAP §0.6.1 literal
``11.4.0`` to ``11.15.0`` per ``decision-log.md`` D-016 (CVE-2026-41148,
CVE-2026-41149, CVE-2026-41150).

Reads
-----
* ``acceleration/data/metrics.json``       — single source of truth.
* ``acceleration/data/inflection.json``    — inflection-date detection.
* ``acceleration/data/run_manifest.json``  — optional; provides commit
  count, HEAD SHA, generated_at.
* ``acceleration/templates/deck/theme.css``                — inlined verbatim.
* ``acceleration/templates/deck/slide_*.html.tmpl``  (17 files) — concatenated.

Writes
------
* ``acceleration/executive-presentation.html`` — the rendered deck.

Exit codes
----------
* ``0`` on success.
* ``1`` on missing inputs (metrics.json, theme.css, any slide template).

Authority
---------
* AAP §0.7.1 Rule 5 — Executive Presentation (12–18 slides, CDN-pinned
  libraries, four slide types, Blitzy brand palette, no emoji, no fenced
  code blocks inside slides).
* AAP §0.4.1 — file inventory enumerates this script and its sibling
  templates.
* AAP §0.3.2.2 — Deck Renderer; reads the same source-of-truth as the
  report; cannot diverge by construction (Rule 4 — Internal Consistency).
* AAP §0.7.2.1 — Read-only discipline.

Read-only discipline
--------------------
This script reads files under ``acceleration/data/`` and
``acceleration/templates/`` and writes exactly one file
(``acceleration/executive-presentation.html``). It does NOT invoke
``git``, ``gh``, or any network endpoint, and it does NOT modify any
file outside its designated output path.

Stdlib-only
-----------
Imports are restricted to the Python 3.10+ standard library plus a
lazy import of ``acceleration.observability.logger`` (which is itself
stdlib-only). The lazy import is wrapped in ``try/except`` so the
renderer continues to work when invoked outside the acceleration
package layout (e.g. ``python3 acceleration/scripts/render_deck.py``
run from the repository root).

Idempotence
-----------
Running the renderer twice against the same input set produces a
byte-identical output (modulo the ``GENERATED_TIMESTAMP`` token, which
is sourced from ``run_manifest.json`` when available — itself a single
stable string per run).
"""

from __future__ import annotations

import argparse
import html
import json
import logging
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Public surface — module constants
# ---------------------------------------------------------------------------
# These constants implement the AAP §0.7.1 Rule 5 contract (CDN pins,
# brand-typography fonts, reveal.js configuration, the canonical slide
# ordering) and are exported as ``CDN_REVEAL``, ``CDN_MERMAID``,
# ``CDN_LUCIDE``, ``GOOGLE_FONTS_URL``, ``REVEAL_CONFIG``,
# ``SLIDE_FILENAMES``, ``TOKEN_RE``, and ``HTML_SHELL``. Other modules
# (in particular ``acceleration/scripts/verify_report.py``) cross-check
# the rendered HTML against the pinned versions and the brand palette,
# so the values below MUST NOT be loosened without coordinated updates.

# AAP §0.7.1 Rule 5 — CDN-pinned versions. ``verify_report.py`` greps
# the rendered HTML for ``reveal.js@5.1.0``, ``mermaid@11.15.0``, and
# ``lucide@0.460.0`` substrings; the strings below must produce those
# substrings verbatim.
#
# The Mermaid pin is intentionally raised from the AAP §0.6.1 literal
# ``11.4.0`` to ``11.15.0`` per ``acceleration/decision-log.md`` D-016
# to address CVE-2026-41148, CVE-2026-41149, and CVE-2026-41150
# (HTML/CSS injection and Gantt-chart DoS). Any drift between this
# constant, ``acceleration/scripts/verify_report.py:PINNED_MERMAID_VERSION``,
# and the rendered ``acceleration/executive-presentation.html`` import URL
# is a regression.
CDN_REVEAL: str = "https://cdn.jsdelivr.net/npm/reveal.js@5.1.0"
CDN_MERMAID: str = "https://cdn.jsdelivr.net/npm/mermaid@11.15.0/dist/mermaid.esm.min.mjs"
CDN_LUCIDE: str = "https://cdn.jsdelivr.net/npm/lucide@0.460.0/dist/umd/lucide.min.js"

# AAP §0.7.1 Rule 5 — typography stack: Inter (body), Space Grotesk
# (display), Fira Code (monospace eyebrow). Weights chosen to cover
# the regular/medium/semibold/bold range used by ``theme.css``.
GOOGLE_FONTS_URL: str = (
    "https://fonts.googleapis.com/css2"
    "?family=Inter:wght@400;500;600;700"
    "&family=Space+Grotesk:wght@500;600;700"
    "&family=Fira+Code:wght@400;500"
    "&display=swap"
)

# AAP §0.7.1 Rule 5 — reveal.js init configuration verbatim:
#   hash: true            — preserve slide URL anchor for deep-linking
#   transition: 'slide'   — horizontal slide transition (AAP-prescribed)
#   controlsTutorial: false — suppress the first-visit controls overlay
#   width: 1920, height: 1080 — 16:9 presentation canvas
REVEAL_CONFIG: dict[str, Any] = {
    "hash": True,
    "transition": "slide",
    "controlsTutorial": False,
    "width": 1920,
    "height": 1080,
}

# Slide template ordering. The seventeen entries below are the
# positional sequence in which slides are concatenated into
# ``<div class="slides">``. The numbering matches the filename prefix
# (``slide_01_*`` → first, ``slide_17_*`` → last). The four slide
# types (Title, Section Divider, Content, Closing) are interleaved per
# AAP §0.7.1 Rule 5: Title → Section Divider → Content+ → Section
# Divider → Content+ → … → Closing.
SLIDE_FILENAMES: list[str] = [
    "slide_01_title.html.tmpl",
    "slide_02_divider_what.html.tmpl",
    "slide_03_kpis.html.tmpl",
    "slide_04_inflection.html.tmpl",
    "slide_05_divider_why.html.tmpl",
    "slide_06_context.html.tmpl",
    "slide_07_divider_arch.html.tmpl",
    "slide_08_architecture.html.tmpl",
    "slide_09_flow_metrics.html.tmpl",
    "slide_10_dora.html.tmpl",
    "slide_11_governance.html.tmpl",
    "slide_12_engineers.html.tmpl",
    "slide_13_divider_risks.html.tmpl",
    "slide_14_risks.html.tmpl",
    "slide_15_divider_onboard.html.tmpl",
    "slide_16_onboarding.html.tmpl",
    "slide_17_closing.html.tmpl",
]

# Token-substitution regex. Tokens are ``{{UPPER_SNAKE_CASE}}`` with at
# least two characters (initial letter + at least one more) — the
# pattern below requires an initial uppercase letter, then zero or more
# of [A-Z0-9_]. This intentionally excludes ``{{_FOO}}`` (leading
# underscore) and Mermaid edge syntax such as ``A--{B}-->C`` that uses
# single braces. The regex is reused by ``substitute_tokens`` and by
# the verifier's leftover-token scan.
TOKEN_RE: re.Pattern[str] = re.compile(r"\{\{([A-Z][A-Z0-9_]*)\}\}")

# Matcher for the body of a Mermaid block (``<pre class="mermaid">…</pre>``).
# Substitution inside this block intentionally does NOT HTML-escape token
# values because Mermaid parses the block content as Mermaid DSL, not HTML;
# inserting ``&quot;`` or ``&amp;`` would corrupt the chart. Mermaid-safe
# sanitisation is therefore applied at the token-source level in
# :func:`build_tokens` (e.g. ``METRIC_LABEL`` strips quotes; ``ENG_LABELS``
# and ``ENG_VALUES`` are JSON-encoded; date tokens are constrained to
# ``YYYY-MM-DD`` by :func:`_iso_date`). The pattern tolerates extra
# attributes on the ``<pre>`` tag and is case-insensitive.
MERMAID_BLOCK_RE: re.Pattern[str] = re.compile(
    r"<pre\b[^>]*\bclass\s*=\s*[\"']?[^\"']*\bmermaid\b[^\"']*[\"']?[^>]*>"
    r".*?</pre\s*>",
    re.DOTALL | re.IGNORECASE,
)

# HTML-comment matcher used by ``load_slides`` to strip the lengthy
# provenance comments from the head of each slide template before
# concatenation. The verifier (``verify_report.py``) counts
# ``<section\b`` matches across the whole document, which would
# overcount when slide templates carry HTML comments containing the
# literal substring ``<section`` in their author-facing documentation.
# Stripping the comments yields exactly the seventeen ``<section>``
# elements in the rendered HTML, satisfying Rule 5's 12–18 slide gate
# without sacrificing comment value at the template-source level.
COMMENT_RE: re.Pattern[str] = re.compile(r"<!--.*?-->", re.DOTALL)

# Unicode multiplication sign (U+00D7) appended to numeric multiplier
# tokens. The slide templates and ``verify_report.py`` both require
# the multiplier symbol to be the Unicode character, NOT the ASCII
# letter ``x``. Holding it as a module-level constant avoids any
# accidental substitution and makes the intent explicit.
MULTIPLIER_SIGN: str = "\u00d7"

# Mapping of canonical metric IDs (the keys used in metrics.json) to
# the abbreviated tokens used in the slide templates. M1–M7 are the
# Flow Framework metrics (slide 09), M8/M9/M11 are DORA-adjacent
# (slide 10), and M10/M12 are governance (slide 11). The mapping is
# stable across re-runs because it is keyed by metric_id, not by
# numeric position in the metrics.json file.
METRIC_ID_TO_KEY: dict[str, str] = {
    "flow_load": "M1",
    "flow_velocity": "M2",
    "flow_predictability": "M3",
    "flow_active": "M4",
    "flow_efficiency": "M5",
    "flow_distribution": "M6",
    "flow_time": "M7",
    "problem_records": "M8",
    "releases": "M9",
    "approved_exceptions": "M10",
    "escaped_defects": "M11",
    "defects_out_of_sla": "M12",
}

# HTML shell template. The shell embeds the inlined ``theme.css`` body
# and the concatenated slide HTML, and bootstraps reveal.js / Mermaid /
# Lucide per AAP §0.7.1 Rule 5. The shell uses Python str.format
# placeholders ({GOOGLE_FONTS_URL}, {CDN_REVEAL}, {CDN_MERMAID},
# {CDN_LUCIDE}, {THEME_CSS}, {SLIDES}, {REVEAL_CONFIG_JSON}); literal
# curly braces in the embedded JavaScript are escaped as ``{{`` / ``}}``
# per str.format conventions.
HTML_SHELL: str = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Development Acceleration Analysis &mdash; Formbricks</title>
<meta name="viewport" content="width=1920, initial-scale=1.0">
<meta name="generator" content="acceleration/scripts/render_deck.py">
<meta name="theme-color" content="#5B39F3">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="{GOOGLE_FONTS_URL}">
<link rel="stylesheet" href="{CDN_REVEAL}/dist/reveal.css">
<link rel="stylesheet" href="{CDN_REVEAL}/dist/theme/white.css" id="theme">
<style>
{THEME_CSS}
</style>
</head>
<body>
<div class="reveal">
<div class="slides">
{SLIDES}
</div>
</div>
<script type="module">
import Reveal from "{CDN_REVEAL}/dist/reveal.esm.js";
import mermaid from "{CDN_MERMAID}";

// Mermaid initialisation — AAP §0.7.1 Rule 5 requires startOnLoad:false
// with explicit mermaid.run() invocation after each slidechanged event
// so that diagrams inside hidden slides render on first display.
mermaid.initialize({{
  startOnLoad: false,
  theme: "base",
  themeVariables: {{
    primaryColor: "#5B39F3",
    primaryTextColor: "#FFFFFF",
    primaryBorderColor: "#2D1C77",
    lineColor: "#1A105F",
    secondaryColor: "#94FAD5",
    tertiaryColor: "#FAFAFA",
    background: "#FFFFFF",
    mainBkg: "#5B39F3",
    secondBkg: "#94FAD5",
    fontFamily: "Inter, system-ui, sans-serif"
  }},
  gantt: {{
    useMaxWidth: true,
    fontSize: 11
  }},
  flowchart: {{
    useMaxWidth: true,
    htmlLabels: true,
    curve: "basis"
  }}
}});

const deck = new Reveal({REVEAL_CONFIG_JSON});

function renderVisuals() {{
  // Render Lucide icons if the UMD bundle has loaded.
  if (window.lucide && typeof window.lucide.createIcons === "function") {{
    window.lucide.createIcons();
  }}
  // Render Mermaid diagrams. ``mermaid.run`` is the idempotent API
  // introduced in Mermaid 10+; calling it on every slidechanged event
  // is safe because already-rendered <pre class="mermaid"> blocks are
  // marked processed by Mermaid itself and skipped on re-invocation.
  try {{
    mermaid.run();
  }} catch (err) {{
    // Defensive: do not let a Mermaid rendering failure crash the deck.
    console.warn("Mermaid render failed:", err);
  }}
}}

deck.initialize().then(() => {{
  renderVisuals();
}});

deck.on("slidechanged", () => {{
  renderVisuals();
}});
</script>
<script src="{CDN_LUCIDE}"></script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def fmt_multiplier(value: Any) -> str:
    """Format a metric multiplier as a display-ready string WITHOUT ``×``.

    Numeric values are rendered to one decimal place (``"3.2"``).
    String values pass through verbatim, which is how the canonical
    ``"Insufficient signal — <reason>"`` phrase is preserved when a
    metric lacks a primary data source. ``None`` and empty strings
    collapse to ``"n/a"``.

    The Unicode multiplier sign U+00D7 is NOT appended here so that the
    caller (``build_tokens``) can decide per-token whether to attach
    it — numeric multipliers attract the ``×`` suffix; the literal
    ``"Insufficient signal — …"`` phrase does NOT (per AAP §0.7.2.1,
    the canonical phrase MUST render verbatim with no trailing
    multiplier symbol).

    Parameters
    ----------
    value
        The raw multiplier read from ``metrics.json``. May be a
        ``float``, ``int``, a string (the canonical Insufficient
        signal phrase or an extractor-emitted note), ``None``, or any
        other JSON-decoded scalar.

    Returns
    -------
    str
        A non-empty display-ready string. Never ``None``.
    """

    # Bool subclasses int in Python, but ``True``/``False`` aren't
    # meaningful multipliers — reject them before the numeric branch.
    if isinstance(value, bool):
        return "n/a"
    if isinstance(value, (int, float)):
        return f"{float(value):.1f}"
    if isinstance(value, str):
        stripped = value.strip()
        if stripped:
            return stripped
        return "n/a"
    return "n/a"


def fmt_display(value: Any) -> str:
    """Format a metric multiplier for slide display, appending ``×`` for numbers.

    This is the canonical helper for the ``_DISPLAY`` and ``_MULT``
    tokens consumed by the metric tables on slides 9, 10, and 11.
    Numeric values are rendered as ``"3.2×"`` (Unicode U+00D7).
    Non-numeric values (the canonical Insufficient-signal phrase or
    ``None``) pass through ``fmt_multiplier`` unchanged so that the
    deck never renders nonsensical strings like
    ``"Insufficient signal — …×"``.

    Parameters
    ----------
    value
        The raw multiplier read from ``metrics.json``.

    Returns
    -------
    str
        For numeric input: ``f"{value:.1f}×"`` (single-decimal,
        Unicode multiplier sign).
        For non-numeric input: the underlying string from
        ``fmt_multiplier`` (no suffix appended).
    """

    base = fmt_multiplier(value)
    if isinstance(value, bool):
        return base
    if isinstance(value, (int, float)):
        return f"{base}{MULTIPLIER_SIGN}"
    return base


def confidence_class(conf: Any) -> str:
    """Map a confidence label to the deck's CSS class suffix.

    The output is intentionally restricted to ``"high"`` / ``"medium"``
    / ``"low"`` because ``theme.css`` only defines three confidence
    badge styles (.confidence-high / .confidence-medium /
    .confidence-low). The fourth conceptual tier — Insufficient signal
    — borrows the ``"low"`` style and is differentiated by the
    confidence label ("Insufficient") rather than a separate badge
    color.

    Parameters
    ----------
    conf
        Confidence string from ``metrics.json``. Accepted variants
        (case-insensitive): ``"High"``, ``"Medium"``, ``"Low"``,
        ``"Insufficient signal"``. ``None`` and empty strings collapse
        to ``"low"``.

    Returns
    -------
    str
        One of ``"high"``, ``"medium"``, ``"low"``.
    """

    if not isinstance(conf, str) or not conf.strip():
        return "low"
    c = conf.lower().strip()
    if c.startswith("high"):
        return "high"
    if c.startswith("med"):
        return "medium"
    # Insufficient signal and any other label collapse to "low".
    return "low"


def confidence_label(conf: Any) -> str:
    """Map a confidence string to its display label.

    Unlike :func:`confidence_class`, this helper preserves the
    distinction between Low and Insufficient signal so that the deck
    surfaces the actual confidence tier the extractor recorded at
    runtime.

    Parameters
    ----------
    conf
        Confidence string from ``metrics.json``.

    Returns
    -------
    str
        One of ``"High"``, ``"Medium"``, ``"Low"``, ``"Insufficient"``,
        or ``"Unknown"`` when ``conf`` is missing.
    """

    if not isinstance(conf, str) or not conf.strip():
        return "Unknown"
    c = conf.lower().strip()
    if c.startswith("high"):
        return "High"
    if c.startswith("med"):
        return "Medium"
    if c.startswith("insuff"):
        return "Insufficient"
    return "Low"


def steady_multiplier(metric: dict[str, Any]) -> Any:
    """Return the most-representative multiplier for a metric.

    Resolution order, falling through on ``None``:

    1. ``metric.phases.steady_state.multiplier`` — preferred per AAP
       §0.8.4 (Steady State = 90+ days post-introduction).
    2. ``metric.phases.post_introduction.multiplier`` — used when the
       repository has fewer than six post-introduction windows and the
       analysis falls back to a single Post-Introduction phase
       (AAP §0.8.4 fallback schema).
    3. ``metric.phases.ramp_up.multiplier`` — used when the analysis
       has captured Ramp-Up data but the Steady State phase has not
       yet accumulated enough windows.
    4. ``metric.multiplier`` — top-level fallback used by Insufficient
       signal metrics, where the entire ``phases`` block is empty and
       the canonical phrase appears at the metric root.

    Parameters
    ----------
    metric
        A single metric entry from ``metrics.json["metrics"]``.

    Returns
    -------
    Any
        Whatever the chosen field contains — a number, the canonical
        Insufficient signal string, ``None``, or any other JSON
        scalar. The caller is responsible for type-aware formatting
        via :func:`fmt_display`.
    """

    if not isinstance(metric, dict):
        return None
    phases = metric.get("phases") or {}
    if isinstance(phases, dict):
        for key in ("steady_state", "post_introduction", "ramp_up"):
            phase = phases.get(key)
            if isinstance(phase, dict):
                value = phase.get("multiplier")
                if value is not None:
                    return value
    return metric.get("multiplier")


def _iso_date(value: Any) -> str:
    """Normalise a date or datetime string to ``YYYY-MM-DD``.

    Inputs may already be an ISO date (``"2026-01-29"``), a full ISO
    8601 datetime (``"2026-01-29T05:53:59+00:00"``), or contain a
    fractional/zoned suffix. The helper extracts the leading 10
    characters when they look date-like; otherwise it returns the
    input unchanged. Non-strings collapse to ``"n/a"``.

    Parameters
    ----------
    value
        The raw date string from ``inflection.json`` or
        ``metrics.json``.

    Returns
    -------
    str
        A ``YYYY-MM-DD`` string, the original input, or ``"n/a"``.
    """

    if not isinstance(value, str) or not value.strip():
        return "n/a"
    text = value.strip()
    # Fast path: already a 10-char date.
    if len(text) >= 10 and re.match(r"^\d{4}-\d{2}-\d{2}", text):
        return text[:10]
    return text


def _baseline_end(inflection: dict[str, Any]) -> str:
    """Compute the Baseline phase end date (the day before inflection).

    The Mermaid Gantt diagram on slide 04 renders three phases
    (Baseline / Ramp-Up / Steady State) using the
    ``dateFormat YYYY-MM-DD`` directive, so every date token must be
    a parseable ISO date. The inflection record stores the inflection
    date itself but does NOT carry a baseline_end field, so this
    helper derives it as ``inflection_date - 1 day``. If the date
    cannot be parsed, the function returns ``"n/a"`` and the slide
    renders the Gantt with that literal in place of the end date —
    which Mermaid surfaces as a parse error in the diagram preview,
    making the underlying data gap visible.

    Parameters
    ----------
    inflection
        The decoded ``inflection.json`` payload.

    Returns
    -------
    str
        ``YYYY-MM-DD`` string for the day before the inflection date,
        or ``"n/a"`` if the inflection date is absent or unparseable.
    """

    date_raw = inflection.get("baseline_end") or inflection.get("date")
    if not isinstance(date_raw, str) or not date_raw.strip():
        return "n/a"
    iso = _iso_date(date_raw)
    if iso == "n/a":
        return "n/a"
    try:
        dt = datetime.strptime(iso, "%Y-%m-%d")
    except ValueError:
        return iso
    # If the source field was already ``baseline_end`` (explicit), do
    # not subtract a day — the extractor recorded the intended end.
    if inflection.get("baseline_end"):
        return iso
    return (dt - timedelta(days=1)).strftime("%Y-%m-%d")


# AAP §0.8.4 — Ramp-Up = first 90 days post-introduction; in practice
# the analysis uses the largest multiple of 14 days that fits within
# the 90-day window (six 2-week Monday-aligned windows = 84 days).
# The slide-04 Mermaid Gantt diagram fails to render when this token
# resolves to ``"n/a"`` (Mermaid rejects non-date strings in the
# ``dateFormat YYYY-MM-DD`` mode), so this helper provides a
# deterministic fallback when ``inflection.json`` lacks the explicit
# field.
_RAMP_UP_WINDOW_DAYS: int = 84


def _rampup_end(inflection: dict[str, Any]) -> str:
    """Compute the Ramp-Up phase end date (``inflection + 84 days``).

    Resolution order:

    1. ``inflection.rampup_end`` — explicit field set by the
       computer when available.
    2. ``inflection.ramp_up_end`` — alternate field name.
    3. ``inflection.date + 84 days`` — deterministic fallback per
       AAP §0.8.4 (six Monday-aligned 2-week windows, the largest
       multiple of 14 that fits within the 90-day Ramp-Up bound).
    4. ``"n/a"`` — only when the inflection date itself is absent or
       unparseable.

    Parameters
    ----------
    inflection
        The decoded ``inflection.json`` payload.

    Returns
    -------
    str
        ``YYYY-MM-DD`` string for the Ramp-Up phase end date, or
        ``"n/a"`` when the inflection date is unavailable.
    """

    explicit = inflection.get("rampup_end") or inflection.get("ramp_up_end")
    if isinstance(explicit, str) and explicit.strip():
        normalised = _iso_date(explicit)
        if normalised != "n/a":
            return normalised
    # Deterministic fallback: inflection_date + 84 days.
    inflection_date = inflection.get("date") or inflection.get("inflection_date")
    if not isinstance(inflection_date, str) or not inflection_date.strip():
        return "n/a"
    iso = _iso_date(inflection_date)
    if iso == "n/a":
        return "n/a"
    try:
        dt = datetime.strptime(iso, "%Y-%m-%d")
    except ValueError:
        return "n/a"
    return (dt + timedelta(days=_RAMP_UP_WINDOW_DAYS)).strftime("%Y-%m-%d")


def _sanitise_for_mermaid_label(value: Any) -> str:
    """Return a Mermaid-block-safe label string.

    Mermaid block contexts (``<pre class="mermaid">…</pre>``) are NOT
    HTML-escaped at substitution time (see :func:`substitute_tokens`
    rationale). The renderer therefore sanitises any externally-sourced
    label string before it enters the Mermaid DSL by:

    1. Coercing non-string inputs to ``str()``.
    2. Stripping ASCII control characters (categories ``Cc``) other
       than ordinary spaces — a NUL, tab, vertical tab, form-feed, or
       newline embedded in an engineer display name would otherwise
       break the Mermaid line that the label appears on.
    3. Removing the double-quote character (``"``). Mermaid ``title``
       directives wrap the label in double quotes; an embedded quote
       terminates the label and lets the remainder of the value run as
       Mermaid DSL.
    4. Removing the backslash character (``\\``). Mermaid recognises
       certain backslash escapes; stripping them removes the smuggling
       surface.
    5. Collapsing internal whitespace runs to a single space and
       trimming leading/trailing whitespace.

    This sanitiser is intentionally lossy: a label with embedded HTML
    or DSL metacharacters renders as its plain-text equivalent, which
    is acceptable for engineer display names and metric labels.

    Parameters
    ----------
    value
        Any value supplied via ``per_engineer.labels`` or
        ``per_engineer.metric_label`` in ``metrics.json``.

    Returns
    -------
    str
        Mermaid-block-safe representation of ``value``.
    """

    text = str(value) if value is not None else ""
    if not text:
        return ""
    # Drop characters whose Unicode category is "Cc" (control) except
    # ordinary space. We process Python characters one at a time rather
    # than use a regex so the implementation is stdlib-only and obvious.
    cleaned_chars: list[str] = []
    for ch in text:
        if ch == "\u0020":
            cleaned_chars.append(ch)
            continue
        if ord(ch) < 0x20 or ord(ch) == 0x7F:
            continue
        if ch in ('"', "\\"):
            continue
        cleaned_chars.append(ch)
    cleaned = "".join(cleaned_chars)
    # Collapse repeated spaces and trim.
    return re.sub(r"\s+", " ", cleaned).strip()


def _extract_caveat(metric: dict[str, Any]) -> str:
    """Return the most informative caveat string for a metric.

    Resolution order:

    1. ``metric.boundary_conditions`` — the canonical field per AAP
       §0.7.2.2 Rule 3 (every Low or Insufficient metric MUST carry an
       explicit caveat surfaced as boundary_conditions).
    2. ``metric.caveat`` — alternate field name used by some
       extractors.
    3. ``metric.confidence_rationale`` — fallback when no caveat is
       set but a rationale is recorded.
    4. Empty string — for High-confidence metrics with no caveat.

    Parameters
    ----------
    metric
        A single metric entry from ``metrics.json["metrics"]``.

    Returns
    -------
    str
        The caveat text, or an empty string when none is available.
    """

    if not isinstance(metric, dict):
        return ""
    for field in ("boundary_conditions", "caveat", "confidence_rationale"):
        value = metric.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


# ---------------------------------------------------------------------------
# Token construction
# ---------------------------------------------------------------------------


def build_tokens(
    metrics: dict[str, Any],
    inflection: dict[str, Any],
    manifest: dict[str, Any],
) -> dict[str, str]:
    """Construct the complete token map used by every template.

    The returned dict maps every ``{{TOKEN}}`` identifier referenced by
    the seventeen slide templates to its display-ready string value.
    No template substitution is performed here; that happens in
    :func:`substitute_tokens`.

    Token categories
    ----------------
    * Title slide (01)        : DATE_RANGE_HUMAN, INFLECTION_DATE,
      INFLECTION_METHOD, GENERATED_TIMESTAMP.
    * KPI slide (03)          : REL_DISPLAY, REL_CONF, REL_CONF_LABEL,
      VEL_*, TIME_*, ACTIVE_ENG.
    * Inflection slide (04)   : BASELINE_START, BASELINE_END,
      RAMPUP_END, STEADY_END (plus INFLECTION_*).
    * Flow / DORA / Gov (09–11): M1–M12 ``_DISPLAY`` + ``_MULT`` +
      ``_CONF`` + ``_CONF_LABEL`` + ``_CAVEAT``.
    * Per-engineer (12)        : ENG_LABELS, ENG_VALUES, METRIC_LABEL.
    * Risks (14)               : RISK_n_TEXT, RISK_n_SEVERITY,
      RISK_n_CONF_CLASS for n in 1..4.
    * Closing (17)             : COMMIT_TOTAL, HEAD_SHA_SHORT.

    Insufficient-signal handling: any metric whose ``multiplier``
    field carries a string (the canonical Insufficient-signal phrase
    per AAP §0.7.2.1) is passed through verbatim without a multiplier
    suffix — see :func:`fmt_display`.

    Parameters
    ----------
    metrics
        The decoded ``metrics.json`` payload. Must contain a
        ``"metrics"`` sub-object keyed by canonical metric IDs.
    inflection
        The decoded ``inflection.json`` payload.
    manifest
        The decoded ``run_manifest.json`` payload (or an empty dict if
        the manifest is unavailable).

    Returns
    -------
    dict[str, str]
        Mapping from token identifier (uppercase, no braces) to
        display-ready string. All values are stringified before
        return.
    """

    metric_data: dict[str, Any] = metrics.get("metrics") or {}
    risks: list[Any] = metrics.get("risks") or []
    date_range: dict[str, Any] = metrics.get("date_range") or {}
    per_engineer: dict[str, Any] = metrics.get("per_engineer") or {}

    def _metric(metric_id: str) -> dict[str, Any]:
        entry = metric_data.get(metric_id)
        return entry if isinstance(entry, dict) else {}

    tokens: dict[str, str] = {}

    # -- Repository date range -----------------------------------------------
    # Prefer the run manifest when available (it carries the canonical
    # extraction-time values) and fall back to metrics.json's
    # date_range (which the metric computer populates from the
    # commits.jsonl extraction). Both are stable across re-runs that
    # use the same commit set.
    first_commit_date = _iso_date(
        manifest.get("first_commit_date")
        or date_range.get("start")
        or "n/a"
    )
    last_commit_date = _iso_date(
        manifest.get("last_commit_date")
        or date_range.get("end")
        or "n/a"
    )
    tokens["DATE_RANGE_HUMAN"] = f"{first_commit_date} \u2192 {last_commit_date}"

    # -- Inflection ---------------------------------------------------------
    # ``inflection.json`` uses ``date`` and ``method`` as the canonical
    # field names; some downstream tools use ``inflection_date`` as
    # the field name — accept either to be robust.
    #
    # SECURITY: ``INFLECTION_DATE`` and ``INFLECTION_METHOD`` are
    # interpolated into BOTH HTML text (slide 04 paragraph) AND a
    # Mermaid Gantt block (slide 04). The HTML occurrence is
    # HTML-escaped by :func:`substitute_tokens`; the Mermaid
    # occurrence is passed through verbatim, so the values that flow
    # here must be Mermaid-safe at the source. ``_iso_date`` already
    # constrains the date token to the ``YYYY-MM-DD`` character set;
    # ``_sanitise_for_mermaid_label`` does the same for the method
    # string (typically ``convergent_evidence`` / ``single_signal`` /
    # ``velocity_only``).
    inflection_date = _iso_date(
        inflection.get("date")
        or inflection.get("inflection_date")
        or "n/a"
    )
    inflection_method_raw = (
        inflection.get("method")
        or inflection.get("detection_method")
        or "n/a"
    )
    tokens["INFLECTION_DATE"] = inflection_date
    tokens["INFLECTION_METHOD"] = (
        _sanitise_for_mermaid_label(inflection_method_raw) or "n/a"
    )

    # -- Generated timestamp -----------------------------------------------
    # ``run_manifest.json["generated_at"]`` is the canonical source;
    # ``metrics.json["computed_at"]`` is the second-best source; a
    # synthesised UTC now() is the last resort. The synthesised value
    # is the only non-idempotent field across re-runs and is documented
    # as such in the file docstring.
    generated_at_raw = (
        manifest.get("generated_at")
        or manifest.get("extraction_timestamp")
        or metrics.get("computed_at")
    )
    if isinstance(generated_at_raw, str) and generated_at_raw.strip():
        tokens["GENERATED_TIMESTAMP"] = _humanise_timestamp(generated_at_raw)
    else:
        tokens["GENERATED_TIMESTAMP"] = datetime.now(timezone.utc).strftime(
            "%Y-%m-%d %H:%M UTC"
        )

    # -- Inflection-slide Gantt chart dates --------------------------------
    # Each date token must resolve to a Mermaid-parseable ISO date
    # (YYYY-MM-DD) so the slide-04 Gantt diagram renders. RAMPUP_END
    # falls back to ``inflection_date + 84 days`` per AAP §0.8.4 when
    # the explicit field is absent — see :func:`_rampup_end`.
    tokens["BASELINE_START"] = first_commit_date
    tokens["BASELINE_END"] = _baseline_end(inflection)
    tokens["RAMPUP_END"] = _rampup_end(inflection)
    tokens["STEADY_END"] = last_commit_date

    # -- Headline KPIs (slide 03) ------------------------------------------
    # The three headline KPIs are sourced from canonical metric IDs:
    #   REL  → releases (Metric 9)
    #   VEL  → flow_velocity (Metric 2)
    #   TIME → flow_time (Metric 7)
    rel_metric = _metric("releases")
    vel_metric = _metric("flow_velocity")
    time_metric = _metric("flow_time")
    tokens["REL_DISPLAY"] = fmt_display(steady_multiplier(rel_metric))
    tokens["REL_CONF"] = confidence_class(rel_metric.get("confidence"))
    tokens["REL_CONF_LABEL"] = confidence_label(rel_metric.get("confidence"))
    tokens["VEL_DISPLAY"] = fmt_display(steady_multiplier(vel_metric))
    tokens["VEL_CONF"] = confidence_class(vel_metric.get("confidence"))
    tokens["VEL_CONF_LABEL"] = confidence_label(vel_metric.get("confidence"))
    tokens["TIME_DISPLAY"] = fmt_display(steady_multiplier(time_metric))
    tokens["TIME_CONF"] = confidence_class(time_metric.get("confidence"))
    tokens["TIME_CONF_LABEL"] = confidence_label(time_metric.get("confidence"))

    # Active engineer count (count, not multiplier).
    active_eng_raw = metrics.get("active_engineers_after")
    if isinstance(active_eng_raw, (int, float)) and not isinstance(active_eng_raw, bool):
        tokens["ACTIVE_ENG"] = str(int(active_eng_raw))
    elif isinstance(active_eng_raw, str) and active_eng_raw.strip():
        tokens["ACTIVE_ENG"] = active_eng_raw.strip()
    else:
        tokens["ACTIVE_ENG"] = "n/a"

    # -- Per-metric tokens for slides 09, 10, 11 ---------------------------
    # All twelve metrics receive BOTH ``_DISPLAY`` and ``_MULT`` token
    # values because the slide templates use both conventions (slides
    # 09 and 10 use ``_DISPLAY``; slide 11 uses ``_MULT``). The display
    # string is identical for both — including the U+00D7 suffix for
    # numeric values and the canonical Insufficient-signal phrase for
    # string values.
    for metric_id, token_key in METRIC_ID_TO_KEY.items():
        metric_entry = _metric(metric_id)
        multiplier = steady_multiplier(metric_entry)
        display_value = fmt_display(multiplier)
        tokens[f"{token_key}_DISPLAY"] = display_value
        tokens[f"{token_key}_MULT"] = display_value
        tokens[f"{token_key}_CONF"] = confidence_class(
            metric_entry.get("confidence")
        )
        tokens[f"{token_key}_CONF_LABEL"] = confidence_label(
            metric_entry.get("confidence")
        )
        tokens[f"{token_key}_CAVEAT"] = _extract_caveat(metric_entry)

    # -- Per-engineer slide (12) -------------------------------------------
    # The slide's Mermaid xychart-beta consumes JSON-array literals
    # directly, so we emit JSON-encoded strings here. ``ensure_ascii``
    # is False so that engineer names with non-ASCII characters
    # (Theodór Tómas, etc.) render in their native glyphs rather than
    # ``\uXXXX`` escapes.
    #
    # SECURITY: ENG_LABELS and ENG_VALUES are emitted inside a
    # ``<pre class="mermaid">`` block (Mermaid DSL context). ``json.dumps``
    # encodes the values as JSON literals, escaping any embedded ``"``
    # / ``\`` / control characters in author display names — this is
    # the Mermaid-safe form. ``substitute_tokens`` recognises the
    # Mermaid block via :data:`MERMAID_BLOCK_RE` and does NOT apply
    # HTML escaping on top, which would corrupt the JSON literal.
    eng_labels_raw = per_engineer.get("labels") or []
    eng_values_raw = per_engineer.get("values") or []
    if not isinstance(eng_labels_raw, list):
        eng_labels_raw = []
    if not isinstance(eng_values_raw, list):
        eng_values_raw = []
    # Defensive normalisation: ensure every label is a string and every
    # value is a JSON number-or-null. Drop ASCII control characters
    # other than ordinary whitespace before JSON-encoding so a malicious
    # author display name carrying a NUL or a vertical tab cannot
    # smuggle a chart-breaking character into the Mermaid block.
    eng_labels: list[str] = [
        _sanitise_for_mermaid_label(label) for label in eng_labels_raw
    ]
    eng_values: list[Any] = []
    for value in eng_values_raw:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            eng_values.append(value)
        elif value is None:
            eng_values.append(None)
        else:
            # Non-numeric values would break the Mermaid bar definition;
            # fall back to 0 rather than render the literal string.
            eng_values.append(0)
    tokens["ENG_LABELS"] = json.dumps(eng_labels, ensure_ascii=False)
    tokens["ENG_VALUES"] = json.dumps(eng_values)
    metric_label = per_engineer.get("metric_label")
    # ``METRIC_LABEL`` is interpolated into a Mermaid ``title "…"``
    # directive (slide 12). The wrapping double quotes are part of the
    # template, so any embedded double quote in the substituted value
    # would terminate the Mermaid title literal. The sanitiser also
    # collapses control characters / newlines (which would split the
    # Mermaid line and corrupt the chart) and strips the backslash so
    # an attacker cannot smuggle a Mermaid escape sequence.
    if isinstance(metric_label, str) and metric_label.strip():
        tokens["METRIC_LABEL"] = _sanitise_for_mermaid_label(metric_label)
    else:
        tokens["METRIC_LABEL"] = "Post-Introduction Activity (Metric 2)"

    # -- Risks (slide 14) --------------------------------------------------
    # The risk slide carries exactly four risk rows. If fewer than
    # four risks are recorded in ``metrics.json``, the remaining slots
    # fall back to a neutral placeholder so the template still renders
    # without unsubstituted tokens (per the verifier's strict no-token
    # gate).
    for i in range(1, 5):
        risk = risks[i - 1] if i - 1 < len(risks) and isinstance(risks[i - 1], dict) else {}
        text = risk.get("text") or risk.get("description") or ""
        severity = risk.get("severity") or risk.get("level") or ""
        if not isinstance(text, str):
            text = str(text)
        if not isinstance(severity, str):
            severity = str(severity)
        text = text.strip()
        severity = severity.strip()
        if not text:
            text = "No additional risk recorded."
        if not severity:
            severity = "Low"
        tokens[f"RISK_{i}_TEXT"] = text
        tokens[f"RISK_{i}_SEVERITY"] = severity
        tokens[f"RISK_{i}_CONF_CLASS"] = confidence_class(severity)

    # -- Closing slide (17) ------------------------------------------------
    commit_count = manifest.get("commit_count")
    if commit_count is None:
        commit_count = metrics.get("commit_count")
    if isinstance(commit_count, (int, float)) and not isinstance(commit_count, bool):
        tokens["COMMIT_TOTAL"] = f"{int(commit_count):,}"
    elif isinstance(commit_count, str) and commit_count.strip():
        tokens["COMMIT_TOTAL"] = commit_count.strip()
    else:
        tokens["COMMIT_TOTAL"] = "n/a"

    head_sha = manifest.get("head_sha") or manifest.get("HEAD_SHA")
    if isinstance(head_sha, str) and head_sha.strip():
        tokens["HEAD_SHA_SHORT"] = head_sha.strip()[:7]
    else:
        tokens["HEAD_SHA_SHORT"] = "n/a"

    return tokens


def _humanise_timestamp(raw: str) -> str:
    """Render an ISO 8601 timestamp as ``YYYY-MM-DD HH:MM UTC``.

    Inputs may carry timezone info (``+00:00``) or microseconds
    (``.123456``). The helper normalises to UTC, drops sub-minute
    precision, and appends the literal ``" UTC"`` suffix. If the
    input cannot be parsed, the original string is returned verbatim
    so that downstream consumers can surface the raw value rather
    than a fabricated timestamp.

    Parameters
    ----------
    raw
        ISO 8601 timestamp string from
        ``metrics.json["computed_at"]`` or
        ``run_manifest.json["generated_at"]``.

    Returns
    -------
    str
        ``YYYY-MM-DD HH:MM UTC`` on success, ``raw`` on failure.
    """

    if not isinstance(raw, str) or not raw.strip():
        return ""
    text = raw.strip()
    # ``datetime.fromisoformat`` (3.11+) handles the "Z" suffix; on
    # 3.10 it doesn't — replace it manually before parsing.
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return raw
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M UTC")


# ---------------------------------------------------------------------------
# Token substitution
# ---------------------------------------------------------------------------


def substitute_tokens(template: str, tokens: dict[str, str]) -> str:
    """Replace every ``{{TOKEN}}`` occurrence with the mapped value, applying
    context-aware escaping.

    The deck template carries tokens whose substitution VALUES originate
    from runtime data (``metrics.json``, ``inflection.json``,
    ``run_manifest.json``, and indirectly from git commit messages,
    GitHub PR titles, engineer display names, label text, and risk
    text). All of those sources sit outside the trust boundary of this
    renderer — a maliciously crafted git author name, branch name, or
    issue label could, before this hardening, inject script tags or
    HTML attributes into the rendered deck (CWE-79 cross-site scripting
    via context-confusion). The trust boundary is therefore:

    Trusted   : ``acceleration/templates/deck/*.html.tmpl`` (in-repo);
                ``HTML_SHELL`` literal in this module.
    Untrusted : every string value in the ``tokens`` mapping.

    Context-aware escaping
    ----------------------
    Two output contexts coexist in the same template:

    1. **HTML text & attribute contexts.** The vast majority of tokens
       (``RISK_*``, ``M*_CAVEAT``, ``COMMIT_TOTAL``, …) render as
       inner-HTML or attribute values. Substitution applies
       :func:`html.escape` with ``quote=True`` so that ``<``, ``>``,
       ``&``, ``"`` and ``'`` are inert and cannot break out of the
       surrounding tag or attribute.
    2. **Mermaid block contexts** (inside ``<pre class="mermaid">…</pre>``).
       Mermaid parses the block as its own DSL — applying HTML escape
       would corrupt the chart (``&quot;`` is not a string literal in
       Mermaid). Substitution inside Mermaid blocks therefore passes
       the token value through verbatim. The values that flow into
       Mermaid contexts are sanitised at their source in
       :func:`build_tokens` (``ENG_LABELS``/``ENG_VALUES`` are
       :func:`json.dumps`-encoded; ``METRIC_LABEL`` has embedded
       quotes/newlines stripped; date tokens are restricted to
       ``YYYY-MM-DD`` by :func:`_iso_date`).

    Tokens not present in the ``tokens`` dict are substituted with the
    string ``"n/a"`` rather than left raw, because the verifier (see
    ``verify_report.py``) fails the deck check when any unsubstituted
    ``{{TOKEN}}`` placeholder remains in the rendered HTML.

    Parameters
    ----------
    template
        The raw template body, typically the contents of one
        ``slide_*.html.tmpl`` file.
    tokens
        Mapping from token identifier (uppercase, no braces) to
        substitution value.

    Returns
    -------
    str
        The substituted text. All ``{{UPPERCASE_TOKEN}}`` occurrences
        are replaced.

    See Also
    --------
    :data:`MERMAID_BLOCK_RE`
        The regex used to identify Mermaid block boundaries.
    :func:`build_tokens`
        Source-level sanitisation that complements the substitution
        escaping (Mermaid-safe and HTML-safe normalisation of values
        derived from external data).
    """

    def _replace_html(match: re.Match[str]) -> str:
        # HTML text & attribute context: escape so that ``<``, ``>``,
        # ``&``, single and double quotes cannot break out of the
        # surrounding HTML structure.
        key = match.group(1)
        value = tokens.get(key)
        if value is None:
            return "n/a"
        return html.escape(str(value), quote=True)

    def _replace_mermaid(match: re.Match[str]) -> str:
        # Mermaid DSL context: pass through verbatim. The values that
        # arrive here must already be Mermaid-safe per ``build_tokens``;
        # if the value is structurally a JSON literal (ENG_LABELS,
        # ENG_VALUES) it is also already JSON-encoded.
        key = match.group(1)
        value = tokens.get(key)
        if value is None:
            return "n/a"
        return str(value)

    # Walk the template, treating each ``<pre class="mermaid">…</pre>``
    # block as a Mermaid region (verbatim substitution) and every other
    # segment as an HTML region (HTML-escaped substitution).
    pieces: list[str] = []
    pos = 0
    for block in MERMAID_BLOCK_RE.finditer(template):
        # HTML region up to the start of this Mermaid block.
        if block.start() > pos:
            pieces.append(TOKEN_RE.sub(_replace_html, template[pos : block.start()]))
        # The Mermaid block itself (verbatim substitution).
        pieces.append(TOKEN_RE.sub(_replace_mermaid, block.group(0)))
        pos = block.end()
    # Final HTML region (after the last Mermaid block, if any).
    if pos < len(template):
        pieces.append(TOKEN_RE.sub(_replace_html, template[pos:]))
    return "".join(pieces)


# ---------------------------------------------------------------------------
# Slide loading
# ---------------------------------------------------------------------------


def load_slides(templates_dir: Path, tokens: dict[str, str]) -> str:
    """Concatenate slide templates in canonical order with token substitution.

    Reads each file named in :data:`SLIDE_FILENAMES` from
    ``templates_dir``, substitutes its tokens via
    :func:`substitute_tokens`, and joins the rendered fragments with a
    blank-line separator. The separator preserves source-readable
    spacing in the rendered HTML and aids downstream diff inspection.

    Parameters
    ----------
    templates_dir
        Directory containing the seventeen ``slide_*.html.tmpl``
        files plus ``theme.css``.
    tokens
        Token map returned by :func:`build_tokens`.

    Returns
    -------
    str
        The concatenated, token-substituted slide HTML — ready to be
        embedded inside ``<div class="slides">``.

    Raises
    ------
    FileNotFoundError
        When any of the seventeen required slide templates is missing.
    """

    slides: list[str] = []
    for filename in SLIDE_FILENAMES:
        path = templates_dir / filename
        if not path.exists():
            raise FileNotFoundError(
                f"Required slide template missing: {path}"
            )
        raw = path.read_text(encoding="utf-8")
        # Strip provenance HTML comments before substitution so that
        # downstream verification (count of ``<section\b`` matches)
        # reflects only the actual ``<section>`` elements rather than
        # the literal ``<section`` substrings embedded in template
        # author documentation. The comments are valuable in the
        # template source but inert at render time, so removing them
        # has no visual impact on the deck.
        stripped = COMMENT_RE.sub("", raw)
        # Collapse blank lines left behind by the comment strip so
        # the rendered HTML stays compact and diff-friendly.
        stripped = re.sub(r"\n{3,}", "\n\n", stripped).lstrip()
        slides.append(substitute_tokens(stripped, tokens))
    return "\n\n".join(slides)


# ---------------------------------------------------------------------------
# HTML shell rendering
# ---------------------------------------------------------------------------


def render_html(theme_css: str, slides_html: str) -> str:
    """Assemble the final HTML by substituting :data:`HTML_SHELL` placeholders.

    Parameters
    ----------
    theme_css
        Inlined contents of ``acceleration/templates/deck/theme.css``.
        The CSS is embedded verbatim inside a ``<style>`` block.
    slides_html
        Concatenated slide HTML as returned by :func:`load_slides`.

    Returns
    -------
    str
        The complete self-contained HTML document.
    """

    return HTML_SHELL.format(
        GOOGLE_FONTS_URL=GOOGLE_FONTS_URL,
        CDN_REVEAL=CDN_REVEAL,
        CDN_MERMAID=CDN_MERMAID,
        CDN_LUCIDE=CDN_LUCIDE,
        THEME_CSS=theme_css,
        SLIDES=slides_html,
        REVEAL_CONFIG_JSON=json.dumps(REVEAL_CONFIG),
    )


# ---------------------------------------------------------------------------
# CLI plumbing
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the command-line arguments for the deck renderer.

    The five flags accepted are:

    * ``--metrics``         Path to the single source of truth (default
      ``acceleration/data/metrics.json``).
    * ``--inflection``      Path to ``inflection.json`` (default
      ``acceleration/data/inflection.json``).
    * ``--manifest``        Path to ``run_manifest.json`` (default
      ``acceleration/data/run_manifest.json``); optional — missing
      manifest falls back to in-file timestamps.
    * ``--templates-dir``   Directory of slide templates and
      ``theme.css`` (default ``acceleration/templates/deck``).
    * ``--output``          Destination HTML path (default
      ``acceleration/executive-presentation.html``).

    Parameters
    ----------
    argv
        Argument vector excluding the program name. ``None`` (the
        default) instructs :mod:`argparse` to read :data:`sys.argv`.

    Returns
    -------
    argparse.Namespace
        Namespace with the five fields named above, each typed as
        :class:`pathlib.Path`.
    """

    parser = argparse.ArgumentParser(
        prog="render_deck",
        description=(
            "Render the executive-presentation HTML deck from "
            "metrics.json + slide templates."
        ),
    )
    parser.add_argument(
        "--metrics",
        type=Path,
        default=Path("acceleration/data/metrics.json"),
        help="Path to the metrics.json single source of truth.",
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
        help=(
            "Path to run_manifest.json (optional; provides commit "
            "counts, dates, HEAD SHA)."
        ),
    )
    parser.add_argument(
        "--templates-dir",
        type=Path,
        default=Path("acceleration/templates/deck"),
        help="Directory containing slide_*.html.tmpl + theme.css.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("acceleration/executive-presentation.html"),
        help="Destination HTML path.",
    )
    return parser.parse_args(argv)


def _bootstrap_logger() -> logging.Logger:
    """Return a configured logger, preferring the structured JSON variant.

    Attempts to import :mod:`acceleration.observability.logger` so that
    the deck renderer participates in the AAP Rule 1 observability
    contract (structured JSON, run-scoped correlation IDs). When the
    import fails (e.g. when the script is run from outside the
    acceleration package layout via ``python3 render_deck.py``),
    falls back to a minimal :class:`logging.Logger` configured via
    :func:`logging.basicConfig`. Either way the returned logger is
    safe to use without inspection by the caller.

    Returns
    -------
    logging.Logger
        A logger named ``"render_deck"``.
    """

    try:
        # Add the repository root to sys.path so the import works when
        # the script is launched directly (not via ``python -m``). The
        # repository root is two directories above this script file:
        # acceleration/scripts/render_deck.py  →  parents[2] == repo root.
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from acceleration.observability.logger import (  # noqa: WPS433
            generate_run_id,
            get_logger,
        )
        run_id = os.environ.get("ACCEL_RUN_ID") or generate_run_id()
        return get_logger("render_deck", run_id=run_id)
    except Exception:  # noqa: BLE001 - fallback to stdlib logger
        logging.basicConfig(
            level=os.environ.get("ACCEL_LOG_LEVEL", "INFO"),
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
        )
        return logging.getLogger("render_deck")


def _load_json(path: Path, optional: bool, log: logging.Logger) -> dict[str, Any]:
    """Load a JSON file, optionally tolerating absence.

    Parameters
    ----------
    path
        Path to the JSON file.
    optional
        If True, missing files yield ``{}`` and ``WARNING``-level
        diagnostics. If False, missing files raise
        :class:`FileNotFoundError`.
    log
        Logger used for diagnostics.

    Returns
    -------
    dict[str, Any]
        The decoded JSON payload, or ``{}`` for optional missing files.

    Raises
    ------
    FileNotFoundError
        If ``optional`` is False and the file is missing.
    """

    if not path.exists():
        if optional:
            log.warning("Optional input %s not found; continuing", path)
            return {}
        raise FileNotFoundError(f"Required input not found: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        log.error("Failed to parse %s: %s", path, exc)
        raise
    if not isinstance(payload, dict):
        log.error("Expected JSON object in %s, got %s", path, type(payload).__name__)
        raise TypeError(f"{path}: expected top-level object, got {type(payload).__name__}")
    return payload


def main(argv: list[str] | None = None) -> int:
    """Top-level entry point for the deck renderer.

    Orchestrates the full pipeline:

    1. Parse CLI arguments.
    2. Bootstrap the structured-JSON logger (with stdlib fallback).
    3. Load ``metrics.json`` (required), ``inflection.json`` and
       ``run_manifest.json`` (optional).
    4. Build the token map via :func:`build_tokens`.
    5. Load and inline ``theme.css``.
    6. Concatenate the seventeen slide templates via
       :func:`load_slides`, substituting tokens.
    7. Assemble the HTML shell via :func:`render_html` and write it
       to the output path.

    Parameters
    ----------
    argv
        Optional argument vector excluding the program name. ``None``
        defers to :data:`sys.argv`.

    Returns
    -------
    int
        ``0`` on success, ``1`` on any missing input or rendering
        failure (the error is logged before returning).
    """

    args = parse_args(argv)
    log = _bootstrap_logger()
    log.info("Rendering deck → %s", args.output)

    # -- Load inputs -------------------------------------------------------
    try:
        metrics = _load_json(args.metrics, optional=False, log=log)
    except FileNotFoundError as exc:
        log.error("%s", exc)
        return 1
    except (json.JSONDecodeError, TypeError):
        return 1
    inflection = _load_json(args.inflection, optional=True, log=log)
    manifest = _load_json(args.manifest, optional=True, log=log)

    # -- Build tokens ------------------------------------------------------
    tokens = build_tokens(metrics, inflection, manifest)
    log.info("Built %d tokens", len(tokens))

    # -- Load theme -------------------------------------------------------
    theme_path = args.templates_dir / "theme.css"
    if not theme_path.exists():
        log.error("theme.css missing at %s", theme_path)
        return 1
    theme_css = theme_path.read_text(encoding="utf-8")

    # -- Load and substitute slides ---------------------------------------
    try:
        slides_html = load_slides(args.templates_dir, tokens)
    except FileNotFoundError as exc:
        log.error("%s", exc)
        return 1

    # -- Render HTML and write to disk ------------------------------------
    html = render_html(theme_css, slides_html)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(html, encoding="utf-8")
    log.info(
        "Deck rendered: %s (%s bytes, %d slides)",
        args.output,
        f"{len(html):,}",
        len(SLIDE_FILENAMES),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
