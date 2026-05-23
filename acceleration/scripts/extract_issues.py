#!/usr/bin/env python3
"""
acceleration.scripts.extract_issues
===================================

Issue-tracker extractor for the Development Acceleration Analysis pipeline.

The script pulls every bug- / regression- / incident- / defect-labelled
GitHub Issue on ``owner/repo`` and, in parallel, performs a filesystem
probe for an SLA-source document under the repository. Both operations
are read-only: HTTP calls are restricted to ``GET`` against the GitHub
REST API and the filesystem is only ever read (never written outside
the supplied ``--output-dir``).

Outputs (under ``acceleration/data/`` by default)
-------------------------------------------------

``issues.jsonl``
    One JSON object per line, one line per bug-labelled issue. Each
    record carries the fields downstream metrics need:

    - ``number`` — issue number (int).
    - ``title`` — issue title.
    - ``body`` — issue body (empty string when null on the API).
    - ``state`` — ``open`` / ``closed``.
    - ``created_at`` — ISO 8601 creation timestamp.
    - ``closed_at`` — ISO 8601 close timestamp, or ``None`` when open.
    - ``updated_at`` — ISO 8601 last-update timestamp.
    - ``labels`` — list of label names attached to the issue.
    - ``assignees`` — list of assignee logins.
    - ``user`` — login of the issue opener.
    - ``html_url`` — browser-facing issue URL.
    - ``is_defect`` — precomputed boolean: ``True`` when any label
      (case-insensitively) matches :data:`DEFECT_LABELS`. The
      precomputation here avoids re-evaluating label intersection in
      ``compute_metrics.py`` and reduces coupling between the
      extractor and the downstream metric calculators.

    Empty file when ``--skip-network`` is supplied or when the GitHub
    API rejects every page (e.g. invalid token, rate-limited, network
    error). An empty file is the correct, non-fabricated outcome per
    AAP §0.7.2.1 (read-only / no fabrication).

``sla_source.json``
    SLA-source discovery manifest. Two shapes are possible:

    Success (an SLA-policy document was located):

    .. code-block:: json

        {
          "found": true,
          "source": "repository_file",
          "path": "docs/SLA.md",
          "evidence": ["SLA", "respond within 24 hours", ...],
          "tried": [...]
        }

    Failure (no SLA-policy document was located, which is the expected
    outcome for the Formbricks repository per AAP §0.2.3):

    .. code-block:: json

        {
          "found": false,
          "source": null,
          "evidence": [],
          "tried": [{"path": "SLA.md", "exists": false}, ...],
          "needed": "An SLA policy document at the repository root ..."
        }

    The manifest is consumed by ``compute_metrics.py`` as the
    confidence gate for Metric 12 (Defects Out of SLA): when
    ``found`` is ``false`` Metric 12 returns ``Insufficient signal —
    no SLA source`` per AAP §0.3.4 and §0.8.2.

Authority
---------

- AAP §0.4.1 enumerates ``acceleration/scripts/extract_issues.py`` as
  a CREATE target.
- AAP §0.3.2.2 — Issue Extractor description: *"Pulls bug-labeled
  issues plus SLA-source discovery; rationale: Metric 12 is
  issue-scoped, not PR-scoped."*
- AAP §0.3.4 — Defects out of SLA and Problem Records implementation
  details.
- AAP §0.8.2 — Agent Latitude: graceful degradation to
  ``Insufficient signal — <reason>`` when a metric is unmeasurable.
- Source: ``.github/ISSUE_TEMPLATE/bug_report.yml`` applies
  ``labels: ["bug"]`` so the ``bug`` label is the primary defect
  signal in this repository.

Read-only discipline (AAP §0.7.2.1, §0.8.7, §0.8.8)
---------------------------------------------------

- HTTP method: ``GET`` only. No ``POST`` / ``PUT`` / ``PATCH`` /
  ``DELETE`` ever appears in this module.
- Filesystem writes: confined to ``issues.jsonl`` and
  ``sla_source.json`` under ``--output-dir``. The SLA probe reads
  candidate paths but never modifies them.
- No ``git`` write commands, no GitHub API write verbs, no external
  state mutation.

Stdlib-only by design (AAP §0.6.1, §0.8.8). All HTTP calls are
issued via :mod:`urllib.request`, so the pipeline runs on a clean
Python 3.10+ installation without ``pip install``.

Graceful degradation (AAP §0.3.4, §0.8.2)
-----------------------------------------

- ``--skip-network`` writes an empty ``issues.jsonl`` and still
  performs the SLA probe; exit code remains ``0``.
- A missing ``GITHUB_TOKEN`` does NOT block the run: the script
  attempts the API anonymously (which succeeds for small public repos
  on the unauthenticated quota) and falls through on the first
  non-200 response.
- Network / transport errors are logged as warnings and terminate
  the issue-iteration loop early; whatever pages were retrieved
  before the failure are preserved on disk.
- The SLA probe is filesystem-only and therefore unaffected by
  network conditions.

Invocation
----------

.. code-block:: bash

    # Full run with API access:
    python3 acceleration/scripts/extract_issues.py \\
        --owner formbricks --repo formbricks \\
        --output-dir acceleration/data

    # Offline run (SLA probe only; useful in air-gapped CI):
    python3 acceleration/scripts/extract_issues.py --skip-network

Integration with the pipeline
-----------------------------

- Order in orchestrator: AFTER ``extract_github.py`` (which sets up
  the GitHub access manifest), but the two are independent; this
  script can run in isolation.
- Outputs consumed by:

  - ``classify_prs.py`` — reads ``issues.jsonl`` for linked-issue
    label lookups when classifying PR work-type for Metric 6 (Flow
    Distribution).
  - ``compute_metrics.py`` — reads ``issues.jsonl`` for Metric 8
    (Problem Records) and Metric 12 (Defects Out of SLA); reads
    ``sla_source.json`` for the Metric 12 confidence gate.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator

# ---------------------------------------------------------------------------
# Public constants
# ---------------------------------------------------------------------------
# The GitHub REST API base. Overridable via ``--api-base`` / ``GITHUB_API``
# environment variable for GitHub Enterprise Server installations (e.g.
# ``https://github.example.com/api/v3``).
GITHUB_API_BASE = "https://api.github.com"

# User-Agent string per GitHub API documentation
# (https://docs.github.com/en/rest/overview/resources-in-the-rest-api#user-agent-required).
# Identifies this script as the acceleration-analysis pipeline; matches the
# convention used by ``extract_github.py`` so log aggregation by UA works.
USER_AGENT = "acceleration-analysis-pipeline/1.0"

# Labels that mark an issue as a defect / incident / regression. The set is
# case-insensitive on the lookup side (see :func:`normalize_issue`'s
# ``is_defect`` computation). ``bug`` is the primary signal for the
# Formbricks repository per ``.github/ISSUE_TEMPLATE/bug_report.yml``;
# ``regression`` / ``incident`` / ``defect`` are included so that
# repositories with richer taxonomies are picked up automatically without
# code changes. These are also the values supplied to GitHub's
# ``labels=`` query filter when iterating the API (see
# :func:`iter_issues`).
DEFECT_LABELS: tuple[str, ...] = ("bug", "regression", "incident", "defect")

# Page size for paginated GitHub list endpoints. 100 is the maximum value
# GitHub accepts for ``per_page`` — using the largest possible value
# minimises HTTP round-trips and stays well within the authenticated
# 5,000 requests/hour budget for any realistic repository.
PAGE_SIZE = 100

# Soft upper bound on HTTP requests issued by a single invocation. Sized
# conservatively well below GitHub's authenticated 5,000 requests/hour
# quota so that an accidentally runaway loop (e.g. a pagination cursor
# that fails to advance) cannot exhaust the token's budget for downstream
# extractors. For Formbricks-shaped repositories — a few hundred
# bug-labelled issues at most — the actual request count is in the low
# tens.
MAX_REQUESTS_PER_RUN = 1500

# SLA-source candidates: filesystem paths under ``--repo-root`` that may
# contain an SLA policy. The list is ordered by descending specificity so
# that a dedicated ``SLA.md`` is preferred over a tangentially-related
# ``SECURITY.md`` if both exist. AAP §0.3.4 makes the absence of an SLA
# source the trigger for Metric 12 returning
# ``Insufficient signal — no SLA source``; this list is the exhaustive
# inventory of where the probe looks before returning ``found: false``.
SLA_FILE_CANDIDATES: tuple[str, ...] = (
    "SLA.md",
    "sla.md",
    "docs/SLA.md",
    "docs/sla.md",
    "docs/support/SLA.md",
    "docs/support/sla.md",
    "docs/policies/SLA.md",
    "docs/policies/sla.md",
    "SECURITY.md",        # may contain disclosure-window numbers
    "SUPPORT.md",
    "docs/SUPPORT.md",
    ".github/SUPPORT.md",
)

# Regex hints used when grepping each SLA candidate file for the kind
# of language that signals an actual policy (as opposed to a passing
# mention). The four patterns capture the most common SLA-document
# vocabulary:
#
# 1. The literal ``SLA`` keyword or ``service-level agreement`` phrase.
# 2. Response- or resolution-window declarations
#    (``respond within 24 hours``, ``resolve within 5 business days``).
# 3. Severity tier declarations (``Severity 1``, ``Severity 3``).
# 4. Priority tier declarations (``P0:``, ``P1 — 24h``, ``P2-72``).
#
# A file is treated as an SLA source if ANY pattern produces ANY match;
# the union maximises recall without sacrificing specificity, because
# all four patterns require structural language that is rare outside
# actual policy documents.
SLA_HINT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(SLA|service[\s-]?level[\s-]?agreement)\b", re.IGNORECASE),
    re.compile(
        r"\b(?:respond|resolve)\s+within\s+\d+\s*(?:business\s+)?(?:hour|day)s?\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bsever(?:e|ity)\s+\d\b", re.IGNORECASE),
    re.compile(r"\b(?:P0|P1|P2|P3)\b\s*(?::|–|—|-)?\s*\d+", re.IGNORECASE),
)


# ---------------------------------------------------------------------------
# HTTP client (stdlib-only GET, with rate-limit awareness)
# ---------------------------------------------------------------------------


@dataclass
class GithubClient:
    """Minimal GitHub REST client built from :mod:`urllib.request`.

    The client is a :func:`dataclass`-based container holding the bearer
    token, a request counter (capped by :data:`MAX_REQUESTS_PER_RUN`),
    the API base URL (overridable for GitHub Enterprise Server installs),
    and the HTTP status of the most recent call (used by :func:`main` to
    decide whether an empty ``issues.jsonl`` is the result of an
    inaccessible endpoint vs. a genuinely empty result set).

    The client is **GET-only**: no method on this class issues
    ``POST``/``PUT``/``PATCH``/``DELETE``. This is enforced by inspection,
    not by configuration — the class exposes a single transport method
    (:meth:`get_json`) whose underlying :class:`urllib.request.Request`
    hard-codes ``method="GET"``. The read-only contract is therefore a
    structural property of the code, satisfying AAP §0.7.2.1 (read-only
    operations) and §0.8.7 (process-specific constraints).

    Attributes
    ----------
    token : str or None
        Personal Access Token, fine-grained PAT, GitHub App installation
        token, or ``None`` for unauthenticated calls. Unauthenticated
        calls succeed against public repositories but are rate-limited
        to 60 requests/hour per source IP; supplying a token raises the
        ceiling to 5,000 requests/hour.
    request_count : int
        Number of HTTP requests issued so far in this run. Incremented
        by :meth:`get_json`. Used as a safety cap via
        :data:`MAX_REQUESTS_PER_RUN`.
    api_base : str
        The REST API base URL (no trailing slash). Default
        :data:`GITHUB_API_BASE`. Overridable for GitHub Enterprise
        Server installations.
    last_status : int
        HTTP status code returned by the most recent :meth:`get_json`
        call. Initialised to ``0``. Used by :func:`main` to record
        endpoint accessibility into the structured log stream.
    """

    token: str | None
    request_count: int = 0
    api_base: str = GITHUB_API_BASE
    last_status: int = 0

    def headers(self) -> dict[str, str]:
        """Compose the request headers for a GitHub REST API call.

        Includes the conventional ``Accept`` and ``User-Agent`` headers
        plus the API version pin (``X-GitHub-Api-Version: 2022-11-28``).
        When :attr:`token` is non-empty, a ``Bearer`` ``Authorization``
        header is added; otherwise the call is unauthenticated and
        subject to GitHub's lower unauthenticated rate limit.

        Returns
        -------
        dict[str, str]
            Header name → header value mapping ready for
            :class:`urllib.request.Request`.
        """

        hdrs: dict[str, str] = {
            "Accept": "application/vnd.github+json",
            "User-Agent": USER_AGENT,
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            hdrs["Authorization"] = f"Bearer {self.token}"
        return hdrs

    def get_json(
        self,
        url: str,
        params: dict[str, Any] | None = None,
    ) -> tuple[int, Any, dict[str, str]]:
        """Issue a single HTTP **GET** to the supplied URL.

        Parameters
        ----------
        url : str
            Absolute URL. The caller is responsible for constructing
            the URL against :attr:`api_base` for endpoint-bound
            requests, or for passing through a ``Link: rel="next"``
            URL during pagination.
        params : dict[str, Any] or None
            Optional query parameters to URL-encode and append to
            ``url``. Pass-through-pagination callers should already
            have parameters baked into the URL and supply ``None``
            here.

        Returns
        -------
        tuple[int, Any, dict[str, str]]
            A tuple ``(status_code, body, headers)`` where ``body`` is
            the parsed JSON value when the response decodes
            successfully and the raw string otherwise. ``headers`` is
            a dict with lower-cased keys for case-insensitive lookup.

        Raises
        ------
        RuntimeError
            When :attr:`request_count` has already reached
            :data:`MAX_REQUESTS_PER_RUN`. This is a fail-fast guard
            against pathological pagination loops; the caller's loop
            catches it so partial results survive.
        """

        if self.request_count >= MAX_REQUESTS_PER_RUN:
            raise RuntimeError(
                f"Exceeded MAX_REQUESTS_PER_RUN={MAX_REQUESTS_PER_RUN}"
            )
        self.request_count += 1
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers=self.headers(), method="GET")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                self.last_status = resp.status
                body = resp.read().decode("utf-8", errors="replace")
                hdrs = {k.lower(): v for k, v in resp.headers.items()}
                try:
                    return resp.status, json.loads(body), hdrs
                except json.JSONDecodeError:
                    # The body is not JSON (e.g., a 304 with empty body
                    # or an HTML error page from a reverse proxy). Pass
                    # the raw string through; the caller's status-code
                    # check will short-circuit the iteration.
                    return resp.status, body, hdrs
        except urllib.error.HTTPError as exc:
            # 4xx / 5xx HTTPError carries a response body and headers;
            # we surface them so the caller can record the error code
            # in the run log. This is the normal path for 403/404 on
            # endpoints requiring elevated scopes or on missing repos.
            self.last_status = exc.code
            body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
            hdrs = {k.lower(): v for k, v in (exc.headers or {}).items()}
            try:
                return exc.code, json.loads(body), hdrs
            except (json.JSONDecodeError, ValueError):
                return exc.code, body, hdrs
        except urllib.error.URLError as exc:
            # URLError covers network-level failures (DNS, connection
            # refused, timeout). The caller treats ``status == 0`` as
            # "endpoint not reachable" and records the endpoint as
            # inaccessible in the structured log.
            self.last_status = 0
            return 0, str(exc), {}

    def respect_rate_limit(self, hdrs: dict[str, str]) -> None:
        """Sleep, if necessary, to respect the primary GitHub rate limit.

        When the most recent response indicates ≤ 2 remaining requests
        before the reset (``x-ratelimit-remaining`` header), the
        caller is paused until ``x-ratelimit-reset`` + 2 seconds. The
        sleep is clamped to a minimum of 5 seconds (to avoid tight
        retry loops on unsynchronised clocks) and a maximum of 120
        seconds (to avoid accidentally pausing forever on a
        misformatted reset timestamp).

        Parameters
        ----------
        hdrs : dict[str, str]
            Response headers from the most recent :meth:`get_json`.
            Keys are expected to be lower-cased (which
            :meth:`get_json` does automatically).
        """

        remaining = hdrs.get("x-ratelimit-remaining")
        reset = hdrs.get("x-ratelimit-reset")
        if remaining and reset:
            try:
                if int(remaining) <= 2:
                    sleep_for = max(5, int(reset) - int(time.time()) + 2)
                    time.sleep(min(sleep_for, 120))
            except ValueError:
                # If either header is unparseable, do not block the
                # run; just continue and let the next request return
                # 403 if the limit was truly exhausted.
                return



# ---------------------------------------------------------------------------
# Pagination helper (RFC 5988 Link header)
# ---------------------------------------------------------------------------


def parse_link_header(value: str) -> dict[str, str]:
    """Parse an HTTP ``Link`` header into a ``{rel: url}`` mapping.

    GitHub uses the standard RFC 5988 ``Link`` header for pagination
    of list endpoints. A typical value looks like:

    .. code-block:: text

        <https://api.github.com/repos/o/r/issues?page=2>; rel="next",
        <https://api.github.com/repos/o/r/issues?page=42>; rel="last"

    The parser extracts every ``rel`` token (``"next"``, ``"prev"``,
    ``"first"``, ``"last"``) and the URL it points to. Callers
    typically consume only the ``"next"`` link, but exposing the full
    map keeps the function reusable from outside this module.

    Parameters
    ----------
    value : str
        Raw ``Link`` header value. May be empty.

    Returns
    -------
    dict[str, str]
        Mapping from the ``rel`` token to the corresponding URL.
        Empty when the header is empty or unparseable.

    Examples
    --------
    >>> parse_link_header('<https://x/1>; rel="next", <https://x/9>; rel="last"')
    {'next': 'https://x/1', 'last': 'https://x/9'}
    """

    out: dict[str, str] = {}
    if not value:
        return out
    for part in value.split(","):
        part = part.strip()
        match = re.match(r'<([^>]+)>;\s*rel="([^"]+)"', part)
        if match:
            out[match.group(2)] = match.group(1)
    return out


# ---------------------------------------------------------------------------
# Issues iteration (paginated GitHub REST GET)
# ---------------------------------------------------------------------------


def iter_issues(
    client: GithubClient,
    owner: str,
    repo: str,
    labels: Iterable[str],
) -> Iterator[dict[str, Any]]:
    """Yield every issue with ANY of the supplied labels.

    Calls
    ``GET /repos/{owner}/{repo}/issues?labels=<labels>&state=all&sort=created&direction=asc&per_page=100``
    and follows the ``Link: rel="next"`` pagination header until
    exhausted. Stops cleanly on the first non-200 response so that
    partial results survive a mid-stream rate-limit hit or network
    error.

    GitHub's REST API treats Issues and Pull Requests equivalently on
    the ``/issues`` endpoint — a PR will appear in the listing with
    its ``pull_request`` key populated. This iterator filters those
    out so downstream consumers receive only true issues. The
    filtering is critical for Metric 8 (Problem Records), which
    counts defects and would otherwise double-count when a bug-labelled
    issue and its fix-PR (also bug-labelled) both surface here.

    The ``labels=`` query parameter applies an OR across the
    comma-separated values: ``labels=bug,regression`` returns issues
    that carry ``bug`` OR ``regression`` (not the intersection). This
    matches the desired semantics — any defect signal qualifies.

    Parameters
    ----------
    client : GithubClient
        Configured HTTP client. The client's request counter is
        incremented for each page fetched.
    owner : str
        Repository owner (user or organisation slug).
    repo : str
        Repository name.
    labels : Iterable[str]
        Label names to filter on. The values are joined with commas
        for the ``labels=`` query parameter. Empty iterable is legal
        and results in an unfiltered listing (rarely useful for this
        script; the orchestrator always supplies
        :data:`DEFECT_LABELS`).

    Yields
    ------
    dict[str, Any]
        Raw issue record from the GitHub API, with the
        ``pull_request`` filter already applied. Callers should pass
        each yielded item through :func:`normalize_issue` to obtain
        the downstream-friendly shape.

    Notes
    -----
    Ordering is created-ascending so downstream consumers can rely on
    the streaming order matching the temporal-windowing in
    ``compute_metrics.py`` without an additional sort pass.
    """

    label_param = ",".join(labels)
    base = f"{client.api_base}/repos/{owner}/{repo}/issues"
    params: dict[str, Any] = {
        "state": "all",
        "per_page": PAGE_SIZE,
        "sort": "created",
        "direction": "asc",
    }
    if label_param:
        # Only attach the labels filter when the caller supplied at
        # least one label — passing an empty string would silently
        # return the entire issue list, which would explode the
        # extraction time and produce a flood of irrelevant records.
        params["labels"] = label_param

    next_url: str | None = f"{base}?{urllib.parse.urlencode(params)}"
    while next_url:
        status, data, hdrs = client.get_json(next_url)
        client.respect_rate_limit(hdrs)
        if status != 200 or not isinstance(data, list):
            # Terminating the generator on a non-200 response
            # preserves whatever pages have already been yielded. The
            # caller logs the early termination via the structured
            # logger so the run remains observable.
            return
        for item in data:
            if not isinstance(item, dict):
                continue
            # GitHub's /issues endpoint returns both Issues and PRs;
            # the ``pull_request`` key disambiguates. Skip PRs — they
            # belong to ``extract_github.py``.
            if item.get("pull_request"):
                continue
            yield item
        next_url = parse_link_header(hdrs.get("link", "")).get("next")


# ---------------------------------------------------------------------------
# Issue normalisation
# ---------------------------------------------------------------------------


def normalize_issue(raw: dict[str, Any]) -> dict[str, Any]:
    """Project a raw issue record into a stable, downstream-friendly shape.

    The projection picks the minimum field set that downstream scripts
    require — ``compute_metrics.py`` (Metrics 8 and 12) and
    ``classify_prs.py`` (Metric 6 linked-issue label lookups) — and
    omits the API's noisy nested objects (``user.*`` blob, ``milestone``,
    ``reactions``) that bloat the JSONL output without adding signal.

    The function also pre-computes :attr:`is_defect`: a boolean that
    is ``True`` when any of the issue's labels (compared
    case-insensitively) appears in :data:`DEFECT_LABELS`. Pre-computing
    this here means ``compute_metrics.py`` does not need to repeat the
    label-set intersection for every metric — reducing coupling and
    keeping the metric calculators focused on aggregation rather than
    classification.

    Parameters
    ----------
    raw : dict[str, Any]
        A raw issue record as returned by
        ``GET /repos/{owner}/{repo}/issues``.

    Returns
    -------
    dict[str, Any]
        Normalised issue record with the following keys:

        ``number``     — Issue number (int).
        ``title``      — Issue title.
        ``body``       — Issue body (empty string when null).
        ``state``      — ``open`` / ``closed``.
        ``created_at`` — ISO 8601 creation timestamp.
        ``closed_at``  — ISO 8601 close timestamp, or null.
        ``updated_at`` — ISO 8601 last-update timestamp.
        ``labels``     — List of label name strings attached to the
                         issue.
        ``assignees``  — List of assignee login strings.
        ``user``       — Login of the issue opener, or null when
                         GitHub anonymised the author (deleted
                         account).
        ``html_url``   — Browser-facing issue URL.
        ``is_defect``  — Pre-computed boolean: ``True`` when any
                         label appears (case-insensitively) in
                         :data:`DEFECT_LABELS`.
    """

    # Extract the label-name list while filtering out the noisy
    # ``{"id": ..., "node_id": ..., "color": ...}`` metadata GitHub
    # attaches to each label. We only need the name.
    labels: list[str] = [
        label.get("name")
        for label in (raw.get("labels") or [])
        if isinstance(label, dict) and label.get("name")
    ]
    # Same projection for assignees — keep the logins; drop the
    # ``avatar_url``, ``gravatar_id``, etc.
    assignees: list[str] = [
        assignee.get("login")
        for assignee in (raw.get("assignees") or [])
        if isinstance(assignee, dict) and assignee.get("login")
    ]
    user_block = raw.get("user") or {}
    user = user_block.get("login") if isinstance(user_block, dict) else None

    # The defect predicate compares case-insensitively against the
    # :data:`DEFECT_LABELS` tuple. A small ``frozenset`` is built once
    # per call from the lower-cased defect tuple; the resulting
    # membership test is O(1) per label.
    defect_set = frozenset(label.lower() for label in DEFECT_LABELS)
    is_defect = any(label.lower() in defect_set for label in labels)

    return {
        "number": raw.get("number"),
        "title": raw.get("title"),
        "body": raw.get("body") or "",
        "state": raw.get("state"),
        "created_at": raw.get("created_at"),
        "closed_at": raw.get("closed_at"),
        "updated_at": raw.get("updated_at"),
        "labels": labels,
        "assignees": assignees,
        "user": user,
        "html_url": raw.get("html_url"),
        "is_defect": is_defect,
    }



# ---------------------------------------------------------------------------
# SLA-source probe (filesystem-only)
# ---------------------------------------------------------------------------


def probe_sla_source(repo_root: Path) -> dict[str, Any]:
    """Scan candidate filesystem paths for an SLA-policy document.

    The function walks :data:`SLA_FILE_CANDIDATES` in order and, for
    every file that exists, grep-matches each of the
    :data:`SLA_HINT_PATTERNS` against the file contents. The first
    candidate to produce ANY match is reported as the SLA source.
    Files that exist but do not match any pattern are recorded as
    ``"exists": true, "matches": []`` in the ``tried`` list so the
    decision trail is auditable.

    This routine NEVER fabricates or estimates: when no candidate
    matches, the returned manifest carries ``found: false`` together
    with the explicit list of paths probed and an actionable
    ``needed`` field. ``compute_metrics.py`` consumes that manifest
    as the confidence gate for Metric 12 (Defects Out of SLA): when
    ``found`` is ``false`` the metric returns
    ``Insufficient signal — no SLA source`` per AAP §0.3.4 and §0.8.2.

    Parameters
    ----------
    repo_root : Path
        Repository root under which the candidates are resolved. The
        caller is expected to pass an absolute, pre-resolved path so
        the manifest's ``path`` field reflects the relative-to-repo
        location.

    Returns
    -------
    dict[str, Any]
        SLA-source manifest. Two shapes are produced:

        Success::

            {
              "found": true,
              "source": "repository_file",
              "path": <relative-to-repo path that matched>,
              "evidence": [<up-to-5 match strings>],
              "tried": [<every attempt so far, including the match>]
            }

        Failure::

            {
              "found": false,
              "source": None,
              "evidence": [],
              "tried": [<every attempt>],
              "needed": <human-readable description of what would
                         unblock Metric 12>
            }
    """

    tried: list[dict[str, Any]] = []
    for candidate in SLA_FILE_CANDIDATES:
        path = repo_root / candidate
        # The ``exists`` field is captured unconditionally so the
        # ``tried`` list documents every attempted lookup, not just
        # the ones that found a file. This is essential for an
        # auditable decision trail per AAP §0.7.2.2 Rule 1 (Data
        # Provenance) and §0.7.2.4 Quality Gates (Insufficient signal
        # justification).
        attempt: dict[str, Any] = {"path": candidate, "exists": path.exists()}
        if path.exists() and path.is_file():
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                # Unreadable file (permissions, broken symlink). Record
                # the attempt as exists-but-empty and continue.
                text = ""
            matches: list[str] = []
            # Iterate the patterns in declared order. Each pattern is
            # capped at 5 matches per file and the overall match list
            # is capped at 5 — the cap keeps the manifest's JSON size
            # bounded even on files that mention "SLA" hundreds of
            # times.
            for pattern in SLA_HINT_PATTERNS:
                for match in pattern.finditer(text):
                    matches.append(match.group(0))
                    if len(matches) >= 5:
                        break
                if len(matches) >= 5:
                    break
            attempt["matches"] = matches
            if matches:
                return {
                    "found": True,
                    "source": "repository_file",
                    "path": candidate,
                    "evidence": matches,
                    "tried": tried + [attempt],
                }
        tried.append(attempt)
    return {
        "found": False,
        "source": None,
        "evidence": [],
        "tried": tried,
        "needed": (
            "An SLA policy document at the repository root (e.g., SLA.md) or "
            "under docs/ with explicit severity tiers and "
            "response/resolution windows, OR an issue-tracker SLA field "
            "(not present in GitHub Issues by default)."
        ),
    }


# ---------------------------------------------------------------------------
# Argparse and main entrypoint
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the script's command-line arguments.

    The function is exposed as a public API so the orchestrator's
    integration tests can drive it without spawning a subprocess.

    Parameters
    ----------
    argv : list[str] or None
        The argument vector excluding the program name. ``None`` (the
        default) instructs :mod:`argparse` to read :data:`sys.argv`.

    Returns
    -------
    argparse.Namespace
        Parsed arguments. The fields are:

        ``owner`` — repository owner (default ``$REPO_OWNER`` or
        ``"formbricks"``).
        ``repo`` — repository name (default ``$REPO_NAME`` or
        ``"formbricks"``).
        ``output_dir`` — directory to write outputs into (default
        ``acceleration/data``).
        ``repo_root`` — local repository root for the SLA probe
        (default ``.``).
        ``api_base`` — GitHub REST API base URL (default
        ``$GITHUB_API`` or :data:`GITHUB_API_BASE`).
        ``skip_network`` — when set, write an empty
        ``issues.jsonl`` and skip the API calls entirely (still
        performs the SLA probe).
        ``labels`` — comma-separated label filter (default
        ``"bug,regression,incident,defect"``).
    """

    parser = argparse.ArgumentParser(
        description=(
            "Extract bug-labelled GitHub issues and probe for an SLA-source "
            "document. Outputs issues.jsonl and sla_source.json under "
            "--output-dir."
        ),
    )
    parser.add_argument(
        "--owner",
        default=os.environ.get("REPO_OWNER", "formbricks"),
        help="Repository owner (default: $REPO_OWNER or 'formbricks').",
    )
    parser.add_argument(
        "--repo",
        default=os.environ.get("REPO_NAME", "formbricks"),
        help="Repository name (default: $REPO_NAME or 'formbricks').",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("acceleration/data"),
        help="Directory to write issues.jsonl and sla_source.json (default: acceleration/data).",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path("."),
        help="Local repository root for the SLA-source filesystem probe (default: '.').",
    )
    parser.add_argument(
        "--api-base",
        default=os.environ.get("GITHUB_API", GITHUB_API_BASE),
        help="GitHub REST API base URL (default: $GITHUB_API or https://api.github.com).",
    )
    parser.add_argument(
        "--skip-network",
        action="store_true",
        help="Skip GitHub API calls; still perform the SLA-source probe and write an empty issues.jsonl.",
    )
    parser.add_argument(
        "--labels",
        default=",".join(DEFECT_LABELS),
        help=(
            "Comma-separated label filter (default: 'bug,regression,incident,defect'). "
            "GitHub treats the list as an OR filter on the issue's label set."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint: probe SLA source, then fetch bug-labelled issues.

    Execution order is deliberate: the SLA probe runs first because
    it is filesystem-only and cannot fail in a way that aborts the
    rest of the run. The API-driven issue fetch runs second so that
    a network failure or rate-limit hit does not block the SLA
    manifest from reaching disk.

    The function never raises. Every error path is caught and
    surfaced through the structured log stream; whichever outputs
    were already on disk are preserved.

    Parameters
    ----------
    argv : list[str] or None
        The argument vector excluding the program name. ``None``
        (the default) instructs :func:`parse_args` to read
        :data:`sys.argv`.

    Returns
    -------
    int
        ``0`` always. Non-zero return codes are intentionally
        avoided so the orchestrator can decide whether
        ``found: false`` on the SLA manifest is acceptable for the
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
        # The script lives at acceleration/scripts/extract_issues.py;
        # parents[2] is the repository root, which we add to
        # ``sys.path`` so the namespace package import resolves
        # without requiring an ``__init__.py``.
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from acceleration.observability.logger import (  # noqa: WPS433
            generate_run_id,
            get_logger,
        )

        run_id = os.environ.get("ACCEL_RUN_ID") or generate_run_id()
        log = get_logger("acceleration.scripts.extract_issues", run_id=run_id)
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
        log = logging.getLogger("acceleration.scripts.extract_issues")

    # Ensure the output directory exists. ``parents=True`` is needed
    # for the default ``acceleration/data`` path when the orchestrator
    # is invoked from a clone that has not yet committed the
    # ``.gitkeep`` placeholder; ``exist_ok=True`` is needed because
    # the typical run finds the directory already in place.
    args.output_dir.mkdir(parents=True, exist_ok=True)
    issues_path: Path = args.output_dir / "issues.jsonl"
    sla_path: Path = args.output_dir / "sla_source.json"

    # -- SLA-source probe (filesystem-only, runs first) --------------------
    resolved_repo_root = args.repo_root.resolve()
    log.info(
        "Probing SLA source under %s (%d candidate paths)",
        resolved_repo_root,
        len(SLA_FILE_CANDIDATES),
    )
    sla = probe_sla_source(resolved_repo_root)
    sla_path.write_text(json.dumps(sla, indent=2, default=str), encoding="utf-8")
    log.info(
        "SLA-source manifest written: %s  found=%s  source=%s",
        sla_path,
        sla.get("found"),
        sla.get("source"),
    )
    if not sla.get("found"):
        log.info(
            "SLA source not found — Metric 12 will report "
            "'Insufficient signal — no SLA source' per AAP §0.3.4."
        )

    # -- Issues extraction (network) ---------------------------------------
    if args.skip_network:
        log.info("--skip-network supplied; writing empty issues.jsonl")
        issues_path.write_text("", encoding="utf-8")
        return 0

    token = os.environ.get("GITHUB_TOKEN")
    labels = tuple(part.strip() for part in args.labels.split(",") if part.strip())
    client = GithubClient(token=token, api_base=args.api_base)
    log.info(
        "Fetching issues for %s/%s with labels=%s  token=%s",
        args.owner,
        args.repo,
        labels,
        "present" if token else "absent",
    )

    count = 0
    with issues_path.open("w", encoding="utf-8") as out_fp:
        try:
            for raw in iter_issues(client, args.owner, args.repo, labels):
                rec = normalize_issue(raw)
                # ``ensure_ascii=False`` preserves non-ASCII labels and
                # titles (Formbricks history contains German /
                # accented characters) without escaping them; the file
                # is UTF-8 by design.
                out_fp.write(json.dumps(rec, ensure_ascii=False, default=str))
                out_fp.write("\n")
                count += 1
        except RuntimeError as exc:
            # Raised by :meth:`GithubClient.get_json` when the
            # request budget is exhausted. Whatever was written
            # before is preserved.
            log.warning(
                "Issue extraction terminated early at %d records: %s: %s",
                count,
                type(exc).__name__,
                exc,
            )
        except Exception as exc:  # pragma: no cover - defensive
            # Any other unexpected error (e.g. malformed JSON the
            # transport layer let through). Log and continue cleanup;
            # do NOT raise — the read-only contract requires this
            # function never to crash the orchestrator.
            log.warning(
                "Issue extraction failed at %d records: %s: %s",
                count,
                type(exc).__name__,
                exc,
            )

    log.info("Wrote %d issue records to %s", count, issues_path)
    log.info(
        "GitHub API requests this run: %d (cap: %d)  last_status=%d",
        client.request_count,
        MAX_REQUESTS_PER_RUN,
        client.last_status,
    )
    return 0


# ---------------------------------------------------------------------------
# Module surface
# ---------------------------------------------------------------------------
# Re-export the symbols required by the file schema so static analysers
# see them as used. ``field`` and ``asdict`` are imported alongside
# ``dataclass`` per the schema as a forward-compatibility convenience
# for any future :class:`GithubClient` subclass that needs a default
# factory or a serialiser; ``Iterable`` / ``Iterator`` are the
# documented type hints for :func:`iter_issues`'s ``labels`` parameter
# and return type.

__all__ = [
    "DEFECT_LABELS",
    "GITHUB_API_BASE",
    "GithubClient",
    "Iterable",
    "Iterator",
    "MAX_REQUESTS_PER_RUN",
    "PAGE_SIZE",
    "SLA_FILE_CANDIDATES",
    "SLA_HINT_PATTERNS",
    "USER_AGENT",
    "asdict",
    "field",
    "iter_issues",
    "main",
    "normalize_issue",
    "parse_args",
    "parse_link_header",
    "probe_sla_source",
]


if __name__ == "__main__":
    sys.exit(main())

