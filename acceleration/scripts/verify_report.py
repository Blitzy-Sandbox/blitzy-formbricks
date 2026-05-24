#!/usr/bin/env python3
"""
verify_report.py — Automated enforcement of report-internal Rules 1–6.

Purpose
-------
Last-step gate of the Development Acceleration Analysis pipeline. Parses
the rendered Markdown report and HTML executive deck, cross-checks them
against ``acceleration/data/metrics.json`` (the single source of truth),
and reports pass/fail per rule.

Reads
-----
* ``acceleration/acceleration-report.md``           — primary deliverable.
* ``acceleration/executive-presentation.html``      — reveal.js deck.
* ``acceleration/data/metrics.json``                — single source of truth.

Writes
------
* ``acceleration/data/verification_results.json`` — single JSON object
  summarising pass/fail/warn per rule, with a top-level
  ``overall_status`` field.

Exit code
---------
* ``0`` — every required rule passes (warnings are tolerated).
* ``1`` — one or more rules fail, **and** ``--exit-on-fail`` is in effect
  (the default).

Authority
---------
* AAP §0.7.2.2 — Report-Internal Rules 1–6 (verbatim verification criteria).
* AAP §0.7.1   Rule 5 — Executive Presentation (slide count, CDN pins,
  brand palette, no emoji, no fenced code in slides).
* AAP §0.7.2.3 — mandatory report section ordering.
* AAP §0.7.2.4 — Quality Gates (all 12 metrics populated or marked
  ``Insufficient signal`` with deviation; confidence tags present).

Read-only discipline (AAP §0.7.2.1)
-----------------------------------
This script reads files under ``acceleration/`` and writes one file —
``acceleration/data/verification_results.json``. It does NOT call
``git``, ``gh``, or any network endpoint, and it does NOT modify any
file outside ``acceleration/data/``.

Stdlib-only
-----------
Imports are restricted to the Python 3.10+ standard library plus a lazy
import of ``acceleration.observability.logger`` (which is itself
stdlib-only). No third-party packages are required at any point.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Module-level constants (verbatim from the AAP)
# ---------------------------------------------------------------------------

# AAP §0.7.2.2 Rule 2 — subjective qualifiers forbidden in the report body.
# The five terms explicitly enumerated by the AAP are joined here by the
# nine additional qualifiers listed in the user prompt's
# Boundaries & Preservation block. Verification is whole-word and
# case-insensitive (see ``check_rule_2_factual_neutral``), so longer
# inflected forms such as ``significantly`` and ``noticeable`` do NOT
# match these stems.
SUBJECTIVE_QUALIFIERS: tuple[str, ...] = (
    "impressive",
    "significant",
    "excellent",
    "remarkable",
    "unfortunately",
    "dramatic",
    "surprising",
    "notable",
    "amazing",
    "outstanding",
    "striking",
    "clearly",
    "obviously",
    "tremendous",
)

# AAP §0.7.1 Rule 5 — pinned CDN versions. Each value MUST appear verbatim
# in ``acceleration/executive-presentation.html`` to satisfy the
# self-contained, reproducible-build constraint for the deck.
#
# The Mermaid pin is intentionally raised from the AAP §0.6.1 literal
# ``11.4.0`` to ``11.15.0`` per ``acceleration/decision-log.md`` D-016 to
# address CVE-2026-41148, CVE-2026-41149, and CVE-2026-41150 (HTML/CSS
# injection and Gantt-chart DoS). The verifier MUST stay in lockstep with
# ``acceleration/scripts/render_deck.py:CDN_MERMAID`` and the generated
# ``acceleration/executive-presentation.html`` import URL; any drift
# between these three locations is a regression.
PINNED_REVEAL_VERSION: str = "5.1.0"
PINNED_MERMAID_VERSION: str = "11.15.0"
PINNED_LUCIDE_VERSION: str = "0.460.0"

# AAP §0.7.1 Rule 5 — Blitzy brand identity. The four pairs below MUST
# appear as CSS custom-property declarations (``--brand-X: #VALUE``) in
# the deck's inlined ``<style>`` block. The verifier matches the
# declaration form ``--brand-primary: #5B39F3`` (whitespace tolerant,
# case-insensitive).
REQUIRED_BRAND_PROPERTIES: tuple[tuple[str, str], ...] = (
    ("--brand-primary", "#5B39F3"),
    ("--brand-dark", "#2D1C77"),
    ("--brand-teal", "#94FAD5"),
    ("--brand-navy", "#1A105F"),
)

# AAP §0.7.2.3 — mandatory report sections, in the exact required order.
# The twelve Metric Deep-Dives appear between "Methodology" and
# "Requirements Traceability Matrix" but are matched by ``check_rule_3``
# via H3 headings (varying titles), not by H2 anchor, so they are not
# enumerated here.
MANDATORY_SECTIONS_IN_ORDER: list[str] = [
    "Executive Summary",
    "Environment Verification",
    "Data Source Inventory",
    "Methodology",
    "Requirements Traceability Matrix",
    "Per-Engineer Acceleration",
    "Acceleration Curve",
    "Risk Assessment",
    "Limitations",
    "Reproducibility Appendix",
]

# Canonical metric identifiers in canonical order. Mirrors the static
# manifest at ``acceleration/observability/metrics.json`` and is used
# both by ``check_quality_gates`` (which asserts every ID is present)
# and by ``check_rule_4_internal_consistency`` (which samples three
# metrics from ``metrics.json``).
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

# Emoji Unicode ranges sufficient for the AAP §0.7.1 Rule 5
# "zero emoji" guarantee. The list covers the commonly-used pictograph,
# emoticon, transport, dingbat, and supplemental symbol blocks. Codepoints
# inside these ranges that are legitimately required by the deck (for
# example, basic geometric arrows used as iconography) MUST be replaced
# with a Lucide SVG instead — the deck is allowed exactly ZERO emoji.
EMOJI_RANGES: list[tuple[int, int]] = [
    (0x1F300, 0x1F5FF),  # symbols & pictographs
    (0x1F600, 0x1F64F),  # emoticons
    (0x1F680, 0x1F6FF),  # transport & map
    (0x1F700, 0x1F77F),  # alchemical
    (0x1F780, 0x1F7FF),  # geometric extended
    (0x1F800, 0x1F8FF),  # supplemental arrows-C
    (0x1F900, 0x1F9FF),  # supplemental symbols & pictographs
    (0x1FA00, 0x1FA6F),  # chess symbols
    (0x1FA70, 0x1FAFF),  # symbols and pictographs extended-A
    (0x2600, 0x26FF),    # miscellaneous symbols
    (0x2700, 0x27BF),    # dingbats
]

# Binaries the reproducibility appendix is permitted to invoke. The list
# is exhaustive for AAP §0.7.2.1's read-only data-source contract:
# ``git``/``gh`` for repository introspection, ``curl`` for the GitHub
# REST/GraphQL API, ``python``/``python3`` for the pipeline itself, and
# common POSIX text-processing utilities. Lines that begin with an
# environment-variable assignment (``FOO=bar python …``) or a relative
# script invocation (``./acceleration/scripts/foo.py``) are accepted
# without consulting this list — see ``check_rule_5_reproducibility``.
RECOGNISED_BINARIES: tuple[str, ...] = (
    "git",
    "curl",
    "python3",
    "python",
    "jq",
    "gh",
    "find",
    "grep",
    "awk",
    "sed",
    "head",
    "tail",
    "tee",
    "sort",
    "uniq",
    "wc",
    "cat",
    "echo",
    "mkdir",
    "cd",
    "test",
    "exit",
    "set",
    "export",
    "bash",
    "sh",
    "rm",
    "mv",
    "cp",
    "ls",
    "tr",
    "xargs",
    "date",
    "env",
    "true",
    "false",
    "uname",
    "diff",
    "hostname",
    "whoami",
    "uniq",
    "basename",
    "dirname",
    "realpath",
    "printf",
    "read",
)


# ---------------------------------------------------------------------------
# RuleResult dataclass
# ---------------------------------------------------------------------------


@dataclass
class RuleResult:
    """Outcome of a single verifier rule.

    Attributes
    ----------
    rule_id : str
        Short stable identifier (for example ``"rule_1"``, ``"deck"``).
    rule_name : str
        Human-readable rule name surfaced in the summary JSON and log
        output.
    status : str
        One of ``"pass"``, ``"warn"``, ``"fail"``. Initialised to
        ``"pass"`` by the caller; transitions are monotonic — calling
        :meth:`fail` sets the status to ``"fail"`` even if a previous
        call to :meth:`warn` had already escalated it to ``"warn"``.
    findings : list[str]
        Ordered list of human-readable findings emitted by ``fail`` or
        ``warn`` calls. An empty list means the rule passed with no
        observations.
    """

    rule_id: str
    rule_name: str
    status: str
    findings: list[str] = field(default_factory=list)

    def fail(self, msg: str) -> None:
        """Record a failing observation and force the status to ``fail``.

        Parameters
        ----------
        msg : str
            Human-readable description of the failure.
        """

        self.status = "fail"
        self.findings.append(msg)

    def warn(self, msg: str) -> None:
        """Record a warning observation, promoting the status to ``warn``.

        A warning never overrides a prior failure: if :attr:`status` is
        already ``"fail"``, the warning is recorded but the status
        remains ``"fail"``.

        Parameters
        ----------
        msg : str
            Human-readable description of the warning.
        """

        if self.status == "pass":
            self.status = "warn"
        self.findings.append(msg)


# ---------------------------------------------------------------------------
# Loader helpers
# ---------------------------------------------------------------------------


def load_text(path: Path) -> str:
    """Return the UTF-8 text contents of ``path``.

    Parameters
    ----------
    path : Path
        Filesystem path to a UTF-8 encoded text file. The caller is
        responsible for verifying existence before invocation — the
        :class:`FileNotFoundError` is allowed to propagate so that the
        orchestrator surfaces an actionable error.

    Returns
    -------
    str
        The full file contents decoded as UTF-8.
    """

    return path.read_text(encoding="utf-8")


def load_json(path: Path) -> dict[str, Any]:
    """Load and return the JSON document at ``path`` as a Python ``dict``.

    The verifier treats the payload as loosely-typed: every consumer
    inside this module narrows the field it cares about with explicit
    ``.get(...)`` calls rather than relying on a schema. This keeps
    the verifier robust to additive evolution of ``metrics.json``.

    Parameters
    ----------
    path : Path
        Filesystem path to a UTF-8 encoded JSON document whose top-level
        value is an object.

    Returns
    -------
    dict[str, Any]
        The parsed JSON document.
    """

    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Markdown section / number extraction helpers
# ---------------------------------------------------------------------------


def extract_section(markdown: str, section_title: str) -> str:
    """Return the text of a Markdown H2 section identified by its title.

    The H2 heading is matched case-insensitively. An optional numeric
    prefix (for example ``## 1. Executive Summary`` or ``## 12 Reproducibility
    Appendix``) is accepted to accommodate both numbered and unnumbered
    section schemes — the verifier checks structure and ordering, not
    typographic accidentals such as the presence or absence of a section
    number.

    Parameters
    ----------
    markdown : str
        Full Markdown document.
    section_title : str
        Target H2 heading (case-insensitive).

    Returns
    -------
    str
        Body text between the matching H2 heading (exclusive) and the
        next H2 heading or end-of-document. Returns the empty string
        when no matching heading is found.
    """

    # Match ``## [<optional number>.] <title>`` — anchored at line start,
    # case-insensitive, trailing whitespace tolerated.
    title_pattern = rf"^##\s+(?:\d+(?:\.\d+)*\.?\s+)?{re.escape(section_title)}\s*$"
    lines = markdown.splitlines()
    start: int | None = None
    end = len(lines)
    for i, line in enumerate(lines):
        if re.match(title_pattern, line, re.IGNORECASE):
            start = i + 1
            break
    if start is None:
        return ""
    # End at the next H2 heading. ``^##\s+\S`` matches any H2 with at
    # least one non-whitespace character after the marker; this excludes
    # the H3 (``###``) Metric Deep-Dive headings nested inside the
    # report's Section 5.
    for j in range(start, len(lines)):
        if re.match(r"^##\s+\S", lines[j]):
            end = j
            break
    return "\n".join(lines[start:end])


def extract_numbers(text: str) -> set[str]:
    """Return every numeric token in ``text`` as a normalised string.

    Numeric tokens are integer or decimal sequences with optional
    thousand-separator commas (for example ``1,234``). After extraction
    the commas are stripped so ``"1,234"`` and ``"1234"`` compare equal.
    Punctuation immediately following the number — multiplication
    suffixes (``×``, ``x``), percent signs (``%``), parentheses — is
    NOT captured.

    Parameters
    ----------
    text : str
        Source text from which numeric tokens are extracted.

    Returns
    -------
    set[str]
        De-duplicated set of normalised numeric tokens.
    """

    raw = re.findall(r"\d+(?:[,]\d{3})*(?:\.\d+)?", text)
    return {tok.replace(",", "") for tok in raw}


def strip_blockquotes(markdown: str) -> str:
    """Remove every Markdown blockquote line from ``markdown``.

    Blockquote lines (those whose first non-whitespace character is
    ``>``) host quoted prompt text and other source material that must
    NOT be searched for subjective qualifiers — the AAP allows a
    quoted prompt to contain any words at all.

    Parameters
    ----------
    markdown : str
        Source Markdown document.

    Returns
    -------
    str
        The document with every blockquote line removed (the rest of
        the document, including non-blockquote lines that share a
        section with blockquotes, is preserved).
    """

    return "\n".join(
        line for line in markdown.splitlines() if not line.lstrip().startswith(">")
    )


def has_emoji(text: str) -> tuple[bool, str | None]:
    """Return ``(True, "U+XXXX")`` if ``text`` contains any emoji codepoint.

    The check sweeps every character in ``text`` once. The first
    matching codepoint short-circuits the loop and is returned in the
    canonical ``U+XXXX`` form (zero-padded to at least four hex digits).

    Parameters
    ----------
    text : str
        Source text to scan.

    Returns
    -------
    tuple[bool, str | None]
        ``(True, "U+XXXX")`` for the first emoji codepoint encountered,
        otherwise ``(False, None)``.
    """

    for ch in text:
        cp = ord(ch)
        for lo, hi in EMOJI_RANGES:
            if lo <= cp <= hi:
                return True, f"U+{cp:04X}"
    return False, None


# ---------------------------------------------------------------------------
# Rule checks
# ---------------------------------------------------------------------------


def check_rule_1_data_provenance(markdown: str) -> RuleResult:
    """Rule 1 (AAP §0.7.2.2) — Data Provenance.

    Every numeric value in the Executive Summary MUST appear in the
    Reproducibility Appendix and in the Requirements Traceability
    Matrix. Single-digit numbers (``0`` and ``1``) are exempted because
    they are common in headings, footnotes, and ratio anchors that
    typically do not require their own appendix entry.

    Parameters
    ----------
    markdown : str
        Full Markdown document.

    Returns
    -------
    RuleResult
        ``rule_id="rule_1"``. ``status`` is ``"pass"`` when every
        significant Executive-Summary number is reachable from both
        cross-reference sections.
    """

    result = RuleResult(rule_id="rule_1", rule_name="Data Provenance", status="pass")
    exec_summary = extract_section(markdown, "Executive Summary")
    appendix = extract_section(markdown, "Reproducibility Appendix")
    matrix = extract_section(markdown, "Requirements Traceability Matrix")

    if not exec_summary.strip():
        result.fail("Executive Summary section is missing or empty.")
        return result
    if not appendix.strip():
        result.fail("Reproducibility Appendix section is missing or empty.")
    if not matrix.strip():
        result.fail("Requirements Traceability Matrix section is missing or empty.")

    exec_nums = extract_numbers(exec_summary)
    appendix_nums = extract_numbers(appendix)
    matrix_nums = extract_numbers(matrix)

    # Require numbers ≥ 2 OR containing a decimal point to be traceable.
    # This filter avoids spurious failures on headings ("Section 1.")
    # and ratio anchors ("1.0 baseline").
    significant = {
        n for n in exec_nums if "." in n or (n.isdigit() and int(n) >= 2)
    }

    missing_in_appendix = significant - appendix_nums
    missing_in_matrix = significant - matrix_nums
    if missing_in_appendix:
        result.fail(
            "Numbers in Executive Summary missing from Reproducibility Appendix: "
            f"{sorted(missing_in_appendix)}"
        )
    if missing_in_matrix:
        result.fail(
            "Numbers in Executive Summary missing from Requirements Traceability Matrix: "
            f"{sorted(missing_in_matrix)}"
        )
    return result


def check_rule_2_factual_neutral(markdown: str) -> RuleResult:
    """Rule 2 (AAP §0.7.2.2) — Factual-Neutral Tone.

    Every subjective qualifier listed in :data:`SUBJECTIVE_QUALIFIERS`
    is forbidden in the report body. Blockquote content is exempted
    because it may contain quoted prompt text.

    The match is whole-word and case-insensitive, so longer inflected
    forms (``significantly``, ``noticeable``) do NOT match the listed
    stems (``significant``, ``notable``).

    Parameters
    ----------
    markdown : str
        Full Markdown document.

    Returns
    -------
    RuleResult
        ``rule_id="rule_2"``. Each forbidden qualifier found produces a
        single failure finding with the match count.
    """

    result = RuleResult(
        rule_id="rule_2", rule_name="Factual-Neutral Tone", status="pass"
    )
    body = strip_blockquotes(markdown)
    body_lower = body.lower()
    for term in SUBJECTIVE_QUALIFIERS:
        # Whole-word match: assert no alphabetic character immediately
        # before or after the term. This deliberately tolerates trailing
        # punctuation, commas, and end-of-sentence markers.
        matches = re.findall(
            rf"(?<![a-z]){re.escape(term)}(?![a-z])",
            body_lower,
        )
        if matches:
            result.fail(
                f"Subjective qualifier '{term}' found {len(matches)} time(s) in report body."
            )
    return result


def check_rule_3_confidence_transparency(
    markdown: str, metrics: dict[str, Any]
) -> RuleResult:
    """Rule 3 (AAP §0.7.2.2) — Confidence Transparency.

    Every Metric Deep-Dive section MUST carry a confidence tag (one of
    High, Medium, Low, or "Insufficient signal"). A Low-confidence or
    Insufficient-signal metric MUST additionally cite a caveat,
    boundary condition, or explicit limitation in the section body —
    failure of this secondary check emits a warning, not a hard fail,
    so the pipeline is not blocked on a documentation-quality gap.

    The check is scoped to H3 headings that appear inside the "Metric
    Deep-Dives" H2 section, so unrelated subsection headings such as
    ``### 4.1 Inflection Detection`` (under Methodology) are not
    treated as metric sections.

    Parameters
    ----------
    markdown : str
        Full Markdown document.
    metrics : dict[str, Any]
        Parsed ``metrics.json`` — used only for context; the primary
        signal for this rule is the rendered Markdown.

    Returns
    -------
    RuleResult
        ``rule_id="rule_3"``. Hard-fails when fewer than 12 Metric
        Deep-Dive sections are found or when any section is missing a
        confidence tag.
    """

    result = RuleResult(
        rule_id="rule_3", rule_name="Confidence Transparency", status="pass"
    )

    # Restrict the search to the "Metric Deep-Dives" H2 body so that
    # subsection headings inside other H2 sections (Executive Summary,
    # Methodology, Per-Engineer Acceleration, etc.) are not mis-detected
    # as metric deep-dives. ``extract_section`` tolerates optional
    # numeric prefixes such as ``## 5. Metric Deep-Dives``.
    deep_dives_body = extract_section(markdown, "Metric Deep-Dives")
    if not deep_dives_body.strip():
        result.fail("Metric Deep-Dives H2 section is missing or empty.")
        return result

    # Within the Metric Deep-Dives body, every H3 heading is a metric.
    metric_section_re = re.compile(r"^###\s+(?P<heading>\S[^\n]*)$", re.MULTILINE)
    sections = list(metric_section_re.finditer(deep_dives_body))
    if len(sections) < 12:
        result.fail(
            f"Found only {len(sections)} Metric Deep-Dive sections; expected at least 12."
        )

    # Slice the section body between consecutive H3 anchors so each
    # metric body is checked independently.
    bounds = [s.start() for s in sections] + [len(deep_dives_body)]
    # The renderer is permitted multiple confidence-tag styles:
    #   ``Confidence: Medium``
    #   ``**Confidence:** Medium``
    #   ``Confidence. Low.``           (period instead of colon)
    #   ``**Confidence.** Low``
    #   ``Confidence - High``
    # The regex below tolerates markdown bold (``**``) on either side
    # of the label, any of ``:``/``.``/``-`` as the separator, and any
    # whitespace before the value.
    confidence_re = re.compile(
        r"\*{0,2}\s*Confidence\s*\*{0,2}\s*[:\.\-]\s*\*{0,2}\s*"
        r"(High|Medium|Low|Insufficient[\s\-]signal)",
        re.IGNORECASE,
    )
    for i, m in enumerate(sections):
        body = deep_dives_body[bounds[i]:bounds[i + 1]]
        conf_m = confidence_re.search(body)
        heading = m.group("heading").strip()
        if not conf_m:
            result.fail(f"Metric section '{heading}' is missing Confidence tag.")
            continue
        conf_value = conf_m.group(1).lower()
        if "low" in conf_value or "insufficient" in conf_value:
            if not re.search(r"(caveat|boundary|limit)", body, re.IGNORECASE):
                result.warn(
                    f"Low-confidence metric '{heading}' lacks an explicit caveat."
                )

    # Cross-check that every canonical metric ID has at least a
    # confidence entry in metrics.json. A metric present in the manifest
    # but missing a ``confidence`` key indicates a broken extractor.
    entries = metrics.get("metrics", {}) if isinstance(metrics, dict) else {}
    for mid in CANONICAL_METRIC_IDS:
        m_entry = entries.get(mid)
        if not isinstance(m_entry, dict):
            # Quality-gates check handles the absent-metric case; only
            # warn here to avoid double-reporting.
            result.warn(
                f"Metric '{mid}' missing from metrics.json; cannot verify Confidence transparency."
            )
            continue
        conf = m_entry.get("confidence")
        if conf is None or (isinstance(conf, str) and not conf.strip()):
            result.fail(f"Metric '{mid}' has no confidence tag in metrics.json.")

    return result


def check_rule_4_internal_consistency(
    markdown: str, metrics: dict[str, Any]
) -> RuleResult:
    """Rule 4 (AAP §0.7.2.2) — Internal Consistency.

    For a sample of metrics drawn from ``metrics.json`` (the single
    source of truth), assert that the multiplier value appears
    verbatim — after thousand-separator normalisation — in the
    Executive Summary, the Requirements Traceability Matrix, and the
    Acceleration Curve section.

    Multipliers are sampled across the first three metrics that expose
    a finite steady-state multiplier; when fewer than three are
    available the verifier falls back to ramp-up multipliers and finally
    to baseline values. This guarantees the rule exercises at least one
    cross-section comparison even on partially-populated metrics.

    Parameters
    ----------
    markdown : str
        Full Markdown document.
    metrics : dict[str, Any]
        Parsed ``metrics.json``.

    Returns
    -------
    RuleResult
        ``rule_id="rule_4"``. Each missing cross-reference produces one
        failure finding.
    """

    result = RuleResult(
        rule_id="rule_4", rule_name="Internal Consistency", status="pass"
    )
    metric_entries = metrics.get("metrics", {}) if isinstance(metrics, dict) else {}
    if not metric_entries:
        result.fail("metrics.json has no 'metrics' key or is empty.")
        return result

    # Pick up to three deterministic samples. Prefer steady-state
    # multipliers (largest signal); fall back to ramp-up multipliers
    # when steady-state is unavailable for a metric.
    samples: list[tuple[str, str]] = []
    for mid in CANONICAL_METRIC_IDS:
        if len(samples) >= 3:
            break
        m_entry = metric_entries.get(mid)
        if not isinstance(m_entry, dict):
            continue
        phases = m_entry.get("phases") or {}
        for phase_key in ("steady_state", "ramp_up"):
            phase = phases.get(phase_key) if isinstance(phases, dict) else None
            if not isinstance(phase, dict):
                continue
            mult = phase.get("multiplier")
            if isinstance(mult, bool):
                # ``bool`` is a subtype of ``int`` in Python; reject it
                # to avoid treating True/False as a numeric multiplier.
                continue
            if isinstance(mult, (int, float)):
                # Render to a string with one decimal place for floats
                # so that comparisons are robust to the formatting the
                # renderer applied (``3.2``) — full precision (``3.1893``)
                # would never match.
                formatted = (
                    f"{mult:.1f}" if isinstance(mult, float) else str(mult)
                )
                samples.append((f"{mid}/{phase_key}", formatted))
                break

    if not samples:
        result.warn(
            "metrics.json contains no finite multipliers to cross-check; "
            "rule_4 has no samples to verify."
        )
        return result

    # Cross-section assertion.
    sections_to_check = (
        "Executive Summary",
        "Requirements Traceability Matrix",
        "Acceleration Curve",
    )
    for sample_id, num in samples:
        for section in sections_to_check:
            section_text = extract_section(markdown, section)
            section_nums = extract_numbers(section_text)
            # ``num`` is already normalised (no thousand commas) by the
            # construction loop above.
            if num.replace(",", "") not in section_nums:
                result.fail(
                    f"Sample {sample_id} multiplier {num} not found in section '{section}'."
                )

    return result


def check_rule_5_reproducibility(markdown: str) -> RuleResult:
    """Rule 5 (AAP §0.7.2.2) — Reproducibility.

    The Reproducibility Appendix MUST contain at least one fenced code
    block whose **command-leading** lines invoke only recognised
    binaries (or shell-builtin operations such as environment-variable
    assignment). Numbered section comments (e.g., ``# 1. Detect
    inflection``) are expected but not strictly required — their
    absence emits a warning.

    The check is multi-line aware:

    * Lines that continue a previous command — pipe continuations
      (``| jq ...``), redirect continuations (``> file``), URL
      continuations (lines that start with a quoted URL), and lines
      following a trailing backslash on the prior line — are NOT
      treated as new commands.
    * Heredoc bodies (between ``<<TOKEN`` / ``<<-TOKEN`` / ``<<'TOKEN'``
      and the matching delimiter) are SKIPPED entirely because they
      are language-specific content (Python, SQL, JSON), not shell
      commands.

    Parameters
    ----------
    markdown : str
        Full Markdown document.

    Returns
    -------
    RuleResult
        ``rule_id="rule_5"``. Hard-fails when the appendix is missing,
        contains no fenced blocks, or contains no executable lines.
        Unrecognised binaries are flagged as warnings to avoid false
        positives on novel pipeline tooling.
    """

    result = RuleResult(
        rule_id="rule_5", rule_name="Reproducibility", status="pass"
    )
    appendix = extract_section(markdown, "Reproducibility Appendix")
    if not appendix.strip():
        result.fail("Reproducibility Appendix section is empty.")
        return result

    # Extract every fenced code block whose info-string is empty, bash,
    # or sh. Other info-strings (e.g., ```json) are deliberately
    # ignored — they are appropriate for embedding example payloads
    # next to commands, not for executable steps.
    blocks = re.findall(
        r"```(?:bash|sh)?[^\n]*\n(.+?)```", appendix, re.DOTALL
    )
    if not blocks:
        result.fail("Reproducibility Appendix contains no fenced code blocks.")
        return result

    # Walk every line of every block, building a list of command-leading
    # lines (i.e., the first line of each shell statement) while
    # skipping continuation lines and heredoc bodies.
    command_lines: list[str] = []
    heredoc_re = re.compile(r"<<-?\s*['\"]?(?P<tok>[A-Za-z_][A-Za-z0-9_]*)['\"]?")
    for blk in blocks:
        in_heredoc = False
        heredoc_token = ""
        prev_continued = False
        for raw_line in blk.splitlines():
            stripped = raw_line.rstrip()
            lstripped = stripped.lstrip()

            # Inside a heredoc body — every line is opaque content
            # until the closing delimiter appears alone on its line.
            if in_heredoc:
                if lstripped == heredoc_token or stripped == heredoc_token:
                    in_heredoc = False
                    heredoc_token = ""
                    prev_continued = False
                continue

            # Blank lines and comment lines never lead a command.
            if not stripped or lstripped.startswith("#"):
                prev_continued = False
                continue

            # Continuation of the previous line — pipes, redirects,
            # bare URLs that wrapped, or any line following a trailing
            # backslash on the previous line.
            if prev_continued or lstripped.startswith(
                ("|", ">", "&", ")", '"', "'", "&&", "||")
            ):
                prev_continued = stripped.endswith("\\")
                continue

            # Track whether the current line ends with a continuation
            # so that the next iteration knows to skip it.
            prev_continued = stripped.endswith("\\")

            # Detect a heredoc opener on this line. The body that
            # follows must be skipped.
            heredoc_m = heredoc_re.search(stripped)
            if heredoc_m:
                in_heredoc = True
                heredoc_token = heredoc_m.group("tok")
                # The opener line itself still counts as a command and
                # should be validated for the recognised binary.

            command_lines.append(stripped)

    if not command_lines:
        result.fail(
            "Reproducibility Appendix code blocks contain no executable lines."
        )
        return result

    # Validate each command-leading line.
    for ln in command_lines:
        head_token = ln.lstrip().split()[0] if ln.strip() else ""
        # Strip leading numbering markers like ``1.``, ``01.``, ``$``,
        # parenthesis or paren-close from a here-doc context, or list
        # bullets.
        head = re.sub(r"^[\$\d\.\)\(\\]+", "", head_token)
        if not head:
            continue

        # Accept environment-variable assignments such as ``GITHUB_TOKEN=…``.
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", head):
            continue
        # Accept relative script invocations.
        if head.startswith("./") or head.startswith("../"):
            continue
        # Accept absolute paths to executables.
        if head.startswith("/"):
            continue
        if head in RECOGNISED_BINARIES:
            continue
        result.warn(
            f"Reproducibility line uses non-standard binary '{head}': {ln!r}"
        )

    # Numbered comments are expected (Rule 5: "ordered sequentially").
    numbered_blocks = sum(
        1 for blk in blocks if re.search(r"#\s*\d+[\.\)]", blk)
    )
    if numbered_blocks == 0:
        result.warn(
            "No numbered comments found in any Reproducibility code block; "
            "ordering may be ambiguous."
        )

    return result


def check_rule_6_environment_first(markdown: str) -> RuleResult:
    """Rule 6 (AAP §0.7.2.2) — Environment First.

    The mandatory sections enumerated in
    :data:`MANDATORY_SECTIONS_IN_ORDER` MUST appear in the report and
    in that order. The Environment Verification section MUST precede
    every Metric Deep-Dive (enforced indirectly by requiring
    "Environment Verification" to precede "Methodology", which
    immediately precedes the Metric Deep-Dives block).

    Parameters
    ----------
    markdown : str
        Full Markdown document.

    Returns
    -------
    RuleResult
        ``rule_id="rule_6"``. Fails on any missing section or any
        ordering inversion.
    """

    result = RuleResult(
        rule_id="rule_6", rule_name="Environment First", status="pass"
    )
    positions: list[tuple[str, int]] = []
    for section in MANDATORY_SECTIONS_IN_ORDER:
        # Tolerate optional numeric prefix the same way ``extract_section``
        # does.
        pat = rf"^##\s+(?:\d+(?:\.\d+)*\.?\s+)?{re.escape(section)}\s*$"
        m = re.search(pat, markdown, re.MULTILINE | re.IGNORECASE)
        if not m:
            result.fail(f"Mandatory section '{section}' missing from report.")
            continue
        positions.append((section, m.start()))

    if result.status == "fail":
        return result

    # Validate ordering.
    section_names = [s for s, _ in positions]
    offsets = [p for _, p in positions]
    if offsets != sorted(offsets):
        # Build a precise message identifying the first inversion.
        for i in range(1, len(offsets)):
            if offsets[i] < offsets[i - 1]:
                result.fail(
                    f"Section '{section_names[i]}' appears before "
                    f"'{section_names[i - 1]}' in the report; required order is: "
                    + ", ".join(MANDATORY_SECTIONS_IN_ORDER)
                )
                break
        else:  # pragma: no cover — defensive; the for-else should not execute
            result.fail(
                "Mandatory sections are not in the required order: "
                + ", ".join(MANDATORY_SECTIONS_IN_ORDER)
            )

    return result


def check_no_unsubstituted_tokens(markdown: str) -> RuleResult:
    """Verify the rendered report contains no ``{{TOKEN}}`` placeholders.

    Templates under ``acceleration/templates/`` use the ``{{NAME}}``
    token style. If any survive into the rendered output it means the
    renderer skipped a substitution — a defect that the verifier
    surfaces immediately.

    Parameters
    ----------
    markdown : str
        Full Markdown document.

    Returns
    -------
    RuleResult
        ``rule_id="tokens"``. Hard-fails on any leftover token.
    """

    result = RuleResult(
        rule_id="tokens", rule_name="Token Substitution", status="pass"
    )
    leftover = re.findall(r"\{\{[A-Z_][A-Z0-9_]*\}\}", markdown)
    if leftover:
        result.fail(
            f"Report contains unsubstituted template tokens: {sorted(set(leftover))}"
        )
    return result


def check_mermaid_block_syntax(markdown: str) -> RuleResult:
    """Verify every ``\u0060\u0060\u0060mermaid`` fenced block uses parser-safe syntax.

    This check closes the historical verifier blind spot in which the
    verifier reported PASS even though one of the embedded Mermaid
    diagrams would fail to render in Mermaid 11.15.0.

    Anti-patterns detected:

    1. **Bare ``%%`` comment lines** — a line containing exactly two
       percent signs (after optional trailing whitespace stripping)
       triggers a hard parse error in Mermaid 11.15.0's flowchart
       lexer because the lexer concatenates the next directive token
       onto the bare ``%%`` and rejects the result. The minimal
       reproducer ``%%\\nflowchart LR\\n A --> B`` raises the verbatim
       error ``Parse error on line 1: %%flowchart LR ^ Expecting
       'NEWLINE', 'SPACE', 'GRAPH', got 'NODE_STRING'`` (upstream issue
       `mermaid-js/mermaid#4137`). The ``xychart-beta`` parser tolerates
       the same pattern in Mermaid 11.15.0, but parser tolerance is
       undocumented and may regress; this check requires both
       templates to remain free of bare ``%%`` lines so renderer
       behaviour stays parser-agnostic.

       The accepted comment forms — ``%% explanatory text``,
       ``%% ---``, and any line whose ``%%`` prefix is followed by at
       least one non-whitespace character — are preserved by the
       check. Only the empty form is rejected.

    Authority
    ---------
    AAP §0.7.1 Rule 4 — Visual Architecture Documentation. A rendered
    Markdown report whose embedded Mermaid blocks fail to render in
    the pinned Mermaid 11.15.0 violates the rule even though the
    source text is present, because a documentation consumer cannot
    see the diagram.

    Parameters
    ----------
    markdown : str
        Full Markdown document.

    Returns
    -------
    RuleResult
        ``rule_id="mermaid_syntax"``. Hard-fails on any bare ``%%``
        comment line inside a fenced ``\u0060\u0060\u0060mermaid`` block.
    """

    result = RuleResult(
        rule_id="mermaid_syntax",
        rule_name="Mermaid Block Syntax (Rule 4)",
        status="pass",
    )

    # Capture each fenced ```mermaid ... ``` block's body. The non-greedy
    # match ensures we never span across separate Mermaid blocks even
    # when several are embedded in the same Markdown file.
    mermaid_blocks = re.findall(
        r"```mermaid\n(.*?)\n```", markdown, flags=re.DOTALL
    )
    if not mermaid_blocks:
        # No Mermaid blocks at all is unusual but not a Rule 4 violation
        # per se — Rule 4's check is owned by ``check_deck`` and by the
        # Visual Architecture Documentation requirement on the report,
        # both of which surface their own findings.
        return result

    for block_index, body in enumerate(mermaid_blocks):
        offending_lines: list[tuple[int, str]] = []
        for line_no, line in enumerate(body.splitlines(), start=1):
            # ``rstrip()`` accepts both ``"%%"`` and ``"%%   "`` as
            # bare-comment forms — Mermaid strips trailing whitespace
            # before lexing so both shapes trigger the same upstream
            # bug. ``%% ---``, ``%% (text)`` and similar non-empty
            # forms remain accepted.
            if line.rstrip() == "%%":
                offending_lines.append((line_no, line))
        if offending_lines:
            preview_line_nos = ", ".join(
                str(ln) for ln, _ in offending_lines[:9]
            )
            if len(offending_lines) > 9:
                preview_line_nos += f", … (+{len(offending_lines) - 9} more)"
            result.fail(
                f"Mermaid block #{block_index} contains "
                f"{len(offending_lines)} bare '%%' empty-comment "
                f"line(s) at block-relative line(s) {preview_line_nos}. "
                f"Mermaid 11.15.0's flowchart parser rejects bare '%%' "
                f"with 'Parse error: Expecting NEWLINE/SPACE/GRAPH, "
                f"got NODE_STRING'. Replace each bare '%%' with "
                f"'%% ---' (or any non-empty comment text) in the "
                f"originating template under "
                f"acceleration/templates/mermaid/."
            )

    return result


def check_deck(html_path: Path) -> RuleResult:
    """Verify the executive presentation HTML against AAP §0.7.1 Rule 5.

    Checks:

    1. ``12 ≤ count(<section>) ≤ 18``.
    2. Zero emoji codepoints in the entire HTML document.
    3. CDN URLs reference the pinned reveal.js / Mermaid / Lucide
       versions.
    4. All four mandatory Blitzy brand custom properties are declared
       in the inlined ``<style>`` block.
    5. Every ``<section>`` contains at least one non-text visual element
       (Mermaid diagram, Lucide icon, table, or KPI block).
    6. No fenced code blocks (``<pre><code>``) appear inside slides.
    7. No unsubstituted ``{{TOKEN}}`` placeholders remain.

    Parameters
    ----------
    html_path : Path
        Filesystem path to the rendered executive deck HTML file.

    Returns
    -------
    RuleResult
        ``rule_id="deck"``. Hard-fails on any violation.
    """

    result = RuleResult(
        rule_id="deck",
        rule_name="Executive Presentation (Rule 5)",
        status="pass",
    )
    if not html_path.exists():
        result.fail(f"Executive presentation not found at {html_path}")
        return result
    html = load_text(html_path)

    # 1. Slide count.
    sections = re.findall(r"<section\b", html)
    if not (12 <= len(sections) <= 18):
        result.fail(
            f"Deck has {len(sections)} sections; Rule 5 requires 12–18."
        )

    # 2. Zero emoji.
    has_em, codepoint = has_emoji(html)
    if has_em:
        result.fail(
            f"Deck contains emoji codepoint {codepoint}; Rule 5 forbids emoji."
        )

    # 3. CDN pins. The verifier looks for ``<pkg>@<version>`` substrings
    # rather than reconstructing the full URL — this tolerates both
    # ``cdn.jsdelivr.net``, ``unpkg.com``, and any other CDN host while
    # still pinning the version.
    if f"reveal.js@{PINNED_REVEAL_VERSION}" not in html:
        result.fail(
            f"reveal.js CDN URL not pinned to {PINNED_REVEAL_VERSION}."
        )
    if f"mermaid@{PINNED_MERMAID_VERSION}" not in html:
        result.fail(
            f"Mermaid CDN URL not pinned to {PINNED_MERMAID_VERSION}."
        )
    if f"lucide@{PINNED_LUCIDE_VERSION}" not in html:
        result.fail(
            f"Lucide CDN URL not pinned to {PINNED_LUCIDE_VERSION}."
        )

    # 4. Mandatory brand custom properties.
    for prop, value in REQUIRED_BRAND_PROPERTIES:
        # Whitespace tolerant, case-insensitive comparison of the
        # ``--prop: #VALUE`` declaration.
        if not re.search(
            rf"{re.escape(prop)}\s*:\s*{re.escape(value)}",
            html,
            re.IGNORECASE,
        ):
            result.fail(
                f"Brand property {prop} = {value} not present in inline CSS."
            )

    # 5. Every section must contain ≥1 non-text visual marker.
    section_blocks = re.split(r"<section\b", html)[1:]
    for idx, blk in enumerate(section_blocks, start=1):
        end = blk.find("</section>")
        section_html = blk[:end] if end != -1 else blk
        markers = (
            '<pre class="mermaid"',
            "data-lucide=",
            "<table",
            'class="kpi-',
            'class="kpi"',
        )
        has_visual = any(marker in section_html for marker in markers)
        if not has_visual:
            result.fail(f"Section {idx} has no non-text visual element.")

    # 6. No fenced code blocks inside slides.
    if re.search(r"<pre>\s*<code", html):
        result.fail(
            "Deck contains a fenced code block (<pre><code>); Rule 5 forbids fenced code in slides."
        )

    # 7. Unsubstituted template tokens.
    leftover = re.findall(r"\{\{[A-Z_][A-Z0-9_]*\}\}", html)
    if leftover:
        result.fail(
            f"Deck contains unsubstituted template tokens: {sorted(set(leftover))}"
        )

    return result


def check_quality_gates(metrics: dict[str, Any]) -> RuleResult:
    """Quality Gates (AAP §0.7.2.4).

    Asserts:

    * Every canonical metric ID is present in ``metrics.json``.
    * Every metric carries a confidence tag drawn from
      {``High``, ``Medium``, ``Low``, ``Insufficient signal``}.
    * Metrics marked ``Insufficient signal`` ship a ``tried`` list and
      a ``needed`` field (warning only — these are documentation
      hygiene fields, not hard requirements).

    Parameters
    ----------
    metrics : dict[str, Any]
        Parsed ``metrics.json``.

    Returns
    -------
    RuleResult
        ``rule_id="gates"``. Fails on missing metric or invalid
        confidence tag.
    """

    result = RuleResult(
        rule_id="gates",
        rule_name="Quality Gates (AAP §0.7.2.4)",
        status="pass",
    )
    entries = metrics.get("metrics", {}) if isinstance(metrics, dict) else {}
    if not entries:
        result.fail("metrics.json has no 'metrics' key.")
        return result

    missing = [mid for mid in CANONICAL_METRIC_IDS if mid not in entries]
    if missing:
        result.fail(f"Missing metric IDs in metrics.json: {missing}")

    valid_confidences = {
        "high",
        "medium",
        "low",
        "insufficient_signal",
        "insufficient signal",
        "insufficient-signal",
    }
    for mid in CANONICAL_METRIC_IDS:
        m = entries.get(mid)
        if not isinstance(m, dict):
            continue  # already reported by the missing check above
        conf_raw = m.get("confidence") or ""
        conf = conf_raw.lower() if isinstance(conf_raw, str) else ""
        if conf not in valid_confidences:
            result.fail(
                f"Metric {mid} has invalid confidence tag {conf_raw!r}."
            )
        is_insufficient = conf in {
            "insufficient_signal",
            "insufficient signal",
            "insufficient-signal",
        }
        if is_insufficient and not m.get("tried"):
            result.warn(
                f"Metric {mid} marked Insufficient signal without 'tried' list."
            )
        if is_insufficient and not m.get("needed"):
            result.warn(
                f"Metric {mid} marked Insufficient signal without 'needed' field."
            )

    return result


# ---------------------------------------------------------------------------
# CLI surface
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments for the verifier.

    Parameters
    ----------
    argv : list[str] | None
        Optional argument vector (excluding the program name). When
        ``None``, :func:`argparse.ArgumentParser.parse_args` reads
        ``sys.argv[1:]``.

    Returns
    -------
    argparse.Namespace
        Parsed arguments with attributes ``report``, ``deck``,
        ``metrics``, ``output``, and ``exit_on_fail``.
    """

    parser = argparse.ArgumentParser(
        prog="verify_report",
        description=(
            "Enforce report-internal Rules 1–6 (AAP §0.7.2.2) plus the "
            "executive deck Rule 5 (§0.7.1)."
        ),
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("acceleration/acceleration-report.md"),
        help=(
            "Path to the rendered acceleration-report.md "
            "(default: acceleration/acceleration-report.md)."
        ),
    )
    parser.add_argument(
        "--deck",
        type=Path,
        default=Path("acceleration/executive-presentation.html"),
        help=(
            "Path to the rendered executive-presentation.html "
            "(default: acceleration/executive-presentation.html)."
        ),
    )
    parser.add_argument(
        "--metrics",
        type=Path,
        default=Path("acceleration/data/metrics.json"),
        help=(
            "Path to the metrics.json single source of truth "
            "(default: acceleration/data/metrics.json)."
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("acceleration/data/verification_results.json"),
        help=(
            "Where to write the JSON summary "
            "(default: acceleration/data/verification_results.json)."
        ),
    )
    parser.add_argument(
        "--exit-on-fail",
        action="store_true",
        default=True,
        help="Exit 1 if any rule fails (default).",
    )
    parser.add_argument(
        "--no-exit-on-fail",
        dest="exit_on_fail",
        action="store_false",
        help="Always exit 0 (use for debugging only).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Verifier entrypoint.

    Parameters
    ----------
    argv : list[str] | None
        Optional argument vector forwarded to :func:`parse_args`.

    Returns
    -------
    int
        Exit code: ``0`` on overall pass (or warn) and on overall
        fail when ``--no-exit-on-fail`` was supplied; ``1`` on overall
        fail with the default ``--exit-on-fail`` enabled.
    """

    args = parse_args(argv)

    # Lazy import of the structured logger so that this script also
    # works when invoked standalone, e.g. ``python3 verify_report.py``
    # from a clean shell without ``acceleration/`` on ``PYTHONPATH``.
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from acceleration.observability.logger import (  # noqa: WPS433
            generate_run_id,
            get_logger,
        )

        run_id = os.environ.get("ACCEL_RUN_ID") or generate_run_id()
        log = get_logger("acceleration.scripts.verify_report", run_id=run_id)
    except Exception:  # pragma: no cover — exercised only when import fails
        import logging

        logging.basicConfig(
            level=os.environ.get("ACCEL_LOG_LEVEL", "INFO"),
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
        )
        log = logging.getLogger("verify_report")

    log.info("Starting report verification")
    log.info(
        "Inputs: report=%s deck=%s metrics=%s output=%s",
        args.report,
        args.deck,
        args.metrics,
        args.output,
    )

    # Pre-flight existence checks. The verifier writes a summary even
    # when these fail so downstream consumers (the orchestrator,
    # dashboards) can still find a JSON payload at the expected path.
    pre_flight_failures: list[str] = []
    if not args.report.exists():
        msg = f"Report not found at {args.report}"
        log.error(msg)
        pre_flight_failures.append(msg)
    if not args.metrics.exists():
        msg = f"metrics.json not found at {args.metrics}"
        log.error(msg)
        pre_flight_failures.append(msg)

    if pre_flight_failures:
        # Emit a minimal failure summary so the orchestrator picks up
        # the failure via verification_results.json.
        summary = {
            "results": [
                {
                    "rule_id": "preflight",
                    "rule_name": "Pre-flight",
                    "status": "fail",
                    "findings": pre_flight_failures,
                }
            ],
            "overall_status": "fail",
        }
        try:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(summary, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError as exc:
            log.error("Could not write verification summary: %s", exc)
        return 1 if args.exit_on_fail else 0

    markdown = load_text(args.report)
    try:
        metrics = load_json(args.metrics)
    except json.JSONDecodeError as exc:
        log.error("metrics.json is not valid JSON: %s", exc)
        summary = {
            "results": [
                {
                    "rule_id": "preflight",
                    "rule_name": "Pre-flight",
                    "status": "fail",
                    "findings": [f"metrics.json is not valid JSON: {exc}"],
                }
            ],
            "overall_status": "fail",
        }
        try:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(summary, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError as os_exc:
            log.error("Could not write verification summary: %s", os_exc)
        return 1 if args.exit_on_fail else 0

    # Run every check. Each check is independent and surfaces its own
    # findings; ordering here matches the AAP rule numbering for
    # readability of the JSON summary and the log output.
    #
    # ``check_mermaid_block_syntax`` follows the token-substitution
    # check because both checks operate on the rendered Markdown's
    # embedded template output and surface text-level defects that
    # would otherwise reach a documentation consumer silently.
    results: list[RuleResult] = [
        check_rule_1_data_provenance(markdown),
        check_rule_2_factual_neutral(markdown),
        check_rule_3_confidence_transparency(markdown, metrics),
        check_rule_4_internal_consistency(markdown, metrics),
        check_rule_5_reproducibility(markdown),
        check_rule_6_environment_first(markdown),
        check_no_unsubstituted_tokens(markdown),
        check_mermaid_block_syntax(markdown),
        check_deck(args.deck),
        check_quality_gates(metrics),
    ]

    overall_status = (
        "fail"
        if any(r.status == "fail" for r in results)
        else "warn"
        if any(r.status == "warn" for r in results)
        else "pass"
    )

    summary = {
        "results": [asdict(r) for r in results],
        "overall_status": overall_status,
        "metadata": {
            "report_path": str(args.report),
            "deck_path": str(args.deck),
            "metrics_path": str(args.metrics),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    log.info("Wrote verification summary to %s", args.output)

    # Emit a human-readable rundown to the log so the orchestrator's
    # consolidated console output stays useful.
    for r in results:
        log.info("  [%s] %s", r.status.upper(), r.rule_name)
        for finding in r.findings:
            log.info("      %s", finding)
    log.info("Overall: %s", overall_status.upper())

    if args.exit_on_fail and overall_status == "fail":
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
