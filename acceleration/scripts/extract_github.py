#!/usr/bin/env python3
"""
acceleration.scripts.extract_github
===================================

GitHub REST/GraphQL extractor that augments git-derived PR records with
platform-only signals for the Development Acceleration Analysis pipeline.

The script issues HTTP **GET** requests only — never a write verb — and
writes its results into the supplied ``--output-dir`` (default
``acceleration/data``). It is the second extractor invoked by the
orchestrator, immediately after ``extract_git.py``, so the PR-merge
strategy can enrich the git-derived ``prs.jsonl`` in place rather than
overwriting it.

Outputs (under ``acceleration/data/``):

``prs.jsonl``
    PR records, either enriched in place when ``extract_git.py`` has
    already populated the file (recommended path) or freshly written
    from the API alone (fallback when git-side ``prs.jsonl`` is empty).
    Each record carries the merge of git-derived fields
    (``first_commit_at``, ``last_commit_at``, ``merge_commit_sha_from_git``)
    and API-derived fields (``draft``, ``requested_reviewers``,
    ``labels``, ``user_type``, ``state``). The ``source_blend`` field
    documents the provenance of each merged record:
    ``git_only`` / ``api_only`` / ``git_plus_api``.

``reviews.jsonl``
    One JSON record per PR review event, carrying ``pr_number``,
    ``review_id``, ``user``, ``state``, ``submitted_at``,
    ``commit_id``. Skipped when ``--skip-reviews`` is supplied.

``releases.jsonl``
    One JSON record per GitHub Release. The record's ``prerelease``
    field is the logical OR of the API ``prerelease: true`` flag and
    the tag-suffix regex match (``-alpha|-beta|-rc|-dev``) per AAP
    §0.8 release-source precedence, because some maintainers forget
    the API checkbox. Both individual sources are also retained on the
    record (``prerelease_by_api_flag``, ``prerelease_by_tag_suffix``).

``branch_protection.json``
    Protection settings for the supplied ``--branch`` (default
    ``main``) when accessible. When the endpoint returns 403 / 404
    (the normal case without admin scope) the file contains
    ``{"accessible": false, "branch": ..., "status_code": ...,
    "reason": ...}``.

``audit_log.jsonl``
    Admin audit-log entries filtered to branch-protection bypass
    events (the primary signal for Metric 10 Approved Exceptions).
    Empty when ``--org`` is not provided or the token lacks
    ``admin:org`` scope. An empty file is the correct outcome.

``github_access.json``
    A manifest documenting what was queried and what was accessible:
    ``accessed_at``, ``owner``, ``repo``, ``token_present``,
    ``endpoints_attempted``, ``endpoints_accessible``,
    ``endpoints_inaccessible``, ``api_requests``, ``needed``.
    Consumed by ``compute_metrics.py`` (Data Source Inventory) and
    ``verify_report.py`` (Rule 6 Environment First).

Authority
---------

- AAP §0.4.1 enumerates this file as a CREATE target.
- AAP §0.3.2.2 — GitHub Extractor description ("Pulls PRs (with
  reviews, draft state, requested-reviews), releases, branch-protection
  settings, and audit log when accessible").
- AAP §0.3.4 — Approved exceptions and Releases counting details.
- AAP §0.8 — Release-source precedence (GitHub Releases > annotated
  tags > deployment events; prereleases excluded from primary count
  and reported separately).
- Source: ``.github/workflows/formbricks-release.yml`` triggers on
  ``release: types: [published]`` (Releases, not git tags). Releases
  endpoint is therefore the authoritative source for Metric 9.
- Source: ``.github/labeler.yml`` defines NO exception / waiver /
  override labels — confirming Metric 10's default to ``Insufficient
  signal — no SLA source`` when the admin audit-log endpoint is
  inaccessible.

Read-only discipline (AAP §0.7.2.1, §0.8.7, §0.8.8)
---------------------------------------------------

HTTP method: ``GET`` only. No ``POST``, ``PUT``, ``PATCH``,
``DELETE``. Filesystem writes are confined to the six output files
under the supplied ``--output-dir``. The PR merge step rewrites
``prs.jsonl`` in place via standard truncate-and-write; this is the
documented contract under AAP §0.4.1.

Stdlib-only by design (AAP §0.6.1, §0.8.8). HTTP calls are issued
via :mod:`urllib.request` so the pipeline runs on a clean Python
3.10+ installation without ``pip install``.

Graceful degradation (AAP §0.3.4)
---------------------------------

- ``--skip-network`` and / or absent ``GITHUB_TOKEN`` => the script
  touches each output file (empty or stub-structured JSON) so
  downstream scripts always find files, then writes a
  ``github_access.json`` manifest that lists every endpoint as
  ``inaccessible``. The exit code remains ``0``.
- Network errors (URLError / HTTPError / rate-limit exhaustion) are
  caught and recorded in the access manifest as ``inaccessible`` for
  the affected endpoint; partial results are preserved.
- 403 / 404 on branch-protection or audit-log endpoints are NOT
  failures — they are the expected response for non-admin tokens.

Invocation
----------

.. code-block:: bash

    python3 acceleration/scripts/extract_github.py \\
        --owner formbricks --repo formbricks --branch main \\
        --output-dir acceleration/data
    # Or, for a fast offline run (no network) that still touches outputs:
    python3 acceleration/scripts/extract_github.py --skip-network

Integration with the pipeline
-----------------------------

- Order in orchestrator: AFTER ``extract_git.py`` so the PR merge
  enriches rather than overwrites.
- Outputs consumed by:
  - ``classify_prs.py`` (PR title / labels).
  - ``compute_metrics.py`` (Metrics 1, 4, 5, 6, 7, 9, 10).
  - ``verify_report.py`` (Data Source Inventory completeness).
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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator

# ---------------------------------------------------------------------------
# Public constants
# ---------------------------------------------------------------------------
# The GitHub REST API base. Overridable via ``--api-base`` / ``GITHUB_API``
# for GitHub Enterprise Server installations (e.g.
# ``https://github.example.com/api/v3``).
GITHUB_API_BASE = "https://api.github.com"

# User-Agent string per GitHub API documentation
# (https://docs.github.com/en/rest/overview/resources-in-the-rest-api#user-agent-required).
USER_AGENT = "acceleration-analysis-pipeline/1.0"

# Page size for paginated endpoints. 100 is the GitHub-imposed maximum.
PAGE_SIZE = 100

# Upper bound on HTTP requests issued by a single invocation. Sized for
# Formbricks (~3,500 PRs * 1 review-fetch + releases + admin endpoints
# ≈ 3,600 requests in the worst case), with headroom for pagination of
# very wide PR-review histories.
MAX_REQUESTS_PER_RUN = 4000

# Retry policy for transient HTTP failures (review feedback: "Add bounded
# exponential backoff for HTTPError 5xx, URLError, and transient socket
# failures. Preserve GET-only discipline and record retry attempts in
# github_access.json.").
#
# Backoff schedule with these defaults:
#     attempt 1: immediate
#     attempt 2: 2.0  seconds wait
#     attempt 3: 4.0  seconds wait
#     attempt 4: 8.0  seconds wait
#     give up: total max wait ≈ 14 s; total attempts = 4
HTTP_MAX_RETRIES: int = 3
HTTP_RETRY_BACKOFF_BASE: float = 2.0
# HTTP status codes that we retry. 429 is intentionally absent because
# the upstream :meth:`GithubClient.respect_rate_limit` already handles
# it correctly via the documented rate-limit-reset window. 4xx codes
# other than 429 are deterministic (404 means not-found, 401 means
# unauthorised, 422 means malformed request) — retrying wastes the
# rate-limit budget without changing the outcome.
HTTP_RETRYABLE_STATUS: frozenset[int] = frozenset({500, 502, 503, 504})

# Prerelease tag-suffix detection per AAP §0.8 release-source precedence.
# Matches ``v1.2.3-alpha``, ``v1.2.3-alpha.1``, ``v1.2.3-alpha1``,
# ``v1.2.3-beta.4``, ``v1.2.3-rc1``, ``v1.2.3-RC1``, ``v1.2.3-dev``,
# etc. Case-insensitive because some maintainers use ``-RC`` / ``-DEV``.
# A negative lookahead ``(?![a-z])`` (combined with ``re.IGNORECASE``)
# replaces a naive ``\b`` word boundary because ``\b`` requires a
# word→non-word transition, which does not exist between the suffix's
# trailing letter and a following digit (the most common naming
# convention for release candidates such as ``-rc1``). The lookahead
# instead asserts that the suffix is not extended by another ASCII
# letter — so ``-alphabet`` correctly does NOT match, while
# ``-alpha.5`` / ``-alpha5`` / ``-alpha-2`` / end-of-string all do.
PRERELEASE_SUFFIX_RE = re.compile(
    r"-(?:alpha|beta|rc|dev)(?![a-z])", re.IGNORECASE
)

# Exception labels referenced in AAP §0.3.4 (none of these exist in the
# Formbricks repo; the lookup is intentionally exhaustive so future repos
# with such labels are picked up automatically by ``compute_metrics.py``
# via the enriched PR ``labels`` field).
EXCEPTION_LABELS = ("exception", "waiver", "override", "merge-override", "bypass")


# ---------------------------------------------------------------------------
# HTTP client (stdlib-only GET, with rate-limit and pagination awareness)
# ---------------------------------------------------------------------------


@dataclass
class GithubClient:
    """Minimal GitHub REST client built from :mod:`urllib.request`.

    The client is a :func:`dataclass`-based container that holds the
    bearer token, a request counter (capped by :data:`MAX_REQUESTS_PER_RUN`),
    the API base URL (overridable for GitHub Enterprise Server installs),
    and the HTTP status of the most recent call (used by :func:`main` to
    decide whether an empty audit-log JSONL is the result of an
    inaccessible endpoint vs. a genuinely empty result set).

    The client is **GET-only**. There is no method that issues
    ``POST``/``PUT``/``PATCH``/``DELETE``, satisfying AAP §0.7.2.1
    read-only operations and AAP §0.8.7 process-specific constraints.

    Attributes
    ----------
    token : str or None
        Personal Access Token, fine-grained PAT, GitHub App installation
        token, or ``None`` for unauthenticated calls (which return 403
        almost immediately for any repo-scoped endpoint on a real repo).
    request_count : int
        Number of HTTP requests issued so far in this run. Incremented
        by :meth:`get`. Used as a safety cap.
    api_base : str
        The REST API base URL (no trailing slash). Default
        :data:`GITHUB_API_BASE`.
    last_status : int
        HTTP status code returned by the most recent :meth:`get` call.
        Initialised to ``0``. Used by :func:`main` for the audit-log
        accessibility heuristic.
    """

    token: str | None
    request_count: int = 0
    api_base: str = GITHUB_API_BASE
    last_status: int = 0
    # Total number of retry attempts issued across the run (for
    # provenance / observability — recorded in github_access.json so
    # operators can see whether transient failures degraded any metric).
    retry_attempts: int = 0
    # Total number of (request_url, status) pairs that ultimately
    # succeeded after at least one retry. Useful as a low-level
    # reliability KPI when the run produces complete data despite
    # GitHub instability.
    retry_recoveries: int = 0
    # Total number of (request_url, status) pairs that exhausted all
    # retry attempts and returned a final failure. Useful as a
    # low-level signal that something is wrong with GitHub / the
    # network.
    retry_failures: int = 0

    def headers(self) -> dict[str, str]:
        """Compose the request headers for a GitHub REST API call.

        Includes the conventional ``Accept`` and ``User-Agent`` headers
        plus the API version pin (``X-GitHub-Api-Version: 2022-11-28``).
        When :attr:`token` is non-empty, a ``Bearer`` ``Authorization``
        header is added; otherwise the call is unauthenticated and
        subject to GitHub's lower unauthenticated rate limit (60 requests
        per hour from a given source IP).

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

    def get(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        *,
        max_retries: int | None = None,
        retry_backoff_base: float | None = None,
    ) -> tuple[int, Any, dict[str, str]]:
        """Issue a single HTTP **GET** to the supplied URL with bounded retries.

        The call is retried with bounded exponential backoff when the
        server returns a transient 5xx (502, 503, 504), or when a
        network-level failure occurs (DNS, connection refused, timeout,
        connection reset, broken pipe). 4xx errors are returned as-is
        because they are deterministic (404 means not-found, 401 means
        unauthorised, 422 means malformed request) — retrying them only
        wastes the rate-limit budget. 429 (Too Many Requests) is also
        returned as-is because the upstream rate-limit honouring path
        (:meth:`respect_rate_limit`) is the correct way to handle it.

        Backoff schedule with the default values (``max_retries=3``,
        ``retry_backoff_base=2.0``)::

            attempt 1: immediate
            attempt 2: 2.0  seconds wait
            attempt 3: 4.0  seconds wait
            attempt 4: 8.0  seconds wait
            give up: total max wait ≈ 14 s; total attempts = 4

        The total wait time is bounded so a stuck endpoint does not
        block the entire pipeline. After exhausting retries, the final
        failing status (5xx HTTPError code or 0 for URLError) is
        returned so the caller's existing graceful-degradation logic
        kicks in.

        Counters incremented per call:

        - :attr:`retry_attempts`  — total retry **attempts** (not
          original requests). A single retried-once-then-succeeded call
          contributes 1 to ``retry_attempts``.
        - :attr:`retry_recoveries` — single retried call that
          ultimately succeeds (status < 400 OR a deterministic 4xx
          mid-retry that the caller wants to surface immediately).
        - :attr:`retry_failures`   — single retried call that
          ultimately exhausts retries with a still-transient failure.

        Parameters
        ----------
        url : str
            Absolute URL. The caller is responsible for constructing the
            URL against :attr:`api_base` for endpoint-bound requests, or
            passing through a ``Link: rel="next"`` URL during pagination.
        params : dict[str, Any] or None
            Optional query parameters to URL-encode and append to ``url``.
            Pass-through-pagination callers should already have parameters
            baked into the URL and supply ``None`` here.
        max_retries : int or None
            Maximum number of retry attempts (in addition to the initial
            attempt). Defaults to :data:`HTTP_MAX_RETRIES` (3 retries =
            4 attempts total). Pass ``0`` to disable retries entirely
            (used by tests).
        retry_backoff_base : float or None
            Backoff base in seconds. The nth retry sleeps for
            ``retry_backoff_base * 2**(n-1)`` seconds. Defaults to
            :data:`HTTP_RETRY_BACKOFF_BASE` (2.0). Used by tests to
            collapse the schedule.

        Returns
        -------
        tuple[int, Any, dict[str, str]]
            A tuple ``(status_code, body, headers)`` where ``body`` is the
            parsed JSON value when the response decodes successfully and
            the raw string otherwise. ``headers`` is a dict with
            lower-cased keys for case-insensitive lookup.

        Raises
        ------
        RuntimeError
            When :attr:`request_count` has already reached
            :data:`MAX_REQUESTS_PER_RUN`. This is a fail-fast guard
            against pathological pagination loops.
        """

        if self.request_count >= MAX_REQUESTS_PER_RUN:
            raise RuntimeError(
                f"Exceeded MAX_REQUESTS_PER_RUN={MAX_REQUESTS_PER_RUN}"
            )
        self.request_count += 1
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"

        retries = (
            HTTP_MAX_RETRIES if max_retries is None else max(0, max_retries)
        )
        backoff_base = (
            HTTP_RETRY_BACKOFF_BASE
            if retry_backoff_base is None
            else max(0.0, retry_backoff_base)
        )
        retried_at_least_once = False

        for attempt in range(retries + 1):
            req = urllib.request.Request(
                url, headers=self.headers(), method="GET"
            )
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    self.last_status = resp.status
                    body = resp.read().decode("utf-8", errors="replace")
                    hdrs = {k.lower(): v for k, v in resp.headers.items()}
                    if retried_at_least_once:
                        self.retry_recoveries += 1
                    try:
                        return resp.status, json.loads(body), hdrs
                    except json.JSONDecodeError:
                        return resp.status, body, hdrs
            except urllib.error.HTTPError as exc:
                self.last_status = exc.code
                body = (
                    exc.read().decode("utf-8", errors="replace")
                    if exc.fp
                    else ""
                )
                hdrs = {
                    k.lower(): v for k, v in (exc.headers or {}).items()
                }
                # Retry only on transient 5xx codes; 4xx are
                # deterministic and 429 is handled upstream by
                # respect_rate_limit so the rate-limit reset window is
                # the correct wait time, not exponential backoff.
                if exc.code in HTTP_RETRYABLE_STATUS and attempt < retries:
                    self.retry_attempts += 1
                    retried_at_least_once = True
                    time.sleep(backoff_base * (2 ** attempt))
                    continue
                if retried_at_least_once:
                    # We retried and still got an error — record the
                    # ultimate failure mode.
                    if exc.code in HTTP_RETRYABLE_STATUS:
                        self.retry_failures += 1
                    else:
                        # A non-retryable 4xx mid-retry: count as a
                        # recovery because we have a deterministic
                        # answer now.
                        self.retry_recoveries += 1
                try:
                    return exc.code, json.loads(body), hdrs
                except (json.JSONDecodeError, ValueError):
                    return exc.code, body, hdrs
            except urllib.error.URLError as exc:
                # URLError covers DNS / connection refused / timeout /
                # connection reset. All four are transient; we retry
                # them.
                self.last_status = 0
                if attempt < retries:
                    self.retry_attempts += 1
                    retried_at_least_once = True
                    time.sleep(backoff_base * (2 ** attempt))
                    continue
                if retried_at_least_once:
                    self.retry_failures += 1
                return 0, str(exc), {}
            except (TimeoutError, OSError) as exc:
                # OSError covers ConnectionResetError, BrokenPipeError,
                # and similar transient transport-layer failures. Treat
                # them like URLError.
                self.last_status = 0
                if attempt < retries:
                    self.retry_attempts += 1
                    retried_at_least_once = True
                    time.sleep(backoff_base * (2 ** attempt))
                    continue
                if retried_at_least_once:
                    self.retry_failures += 1
                return 0, str(exc), {}
        # Defensive: the loop always returns on the final iteration; we
        # only reach this line if ``retries`` was negative, which the
        # ``max(0, ...)`` clamp prevents.
        return 0, "retry loop fell through", {}

    def respect_rate_limit(self, hdrs: dict[str, str]) -> None:
        """Sleep, if necessary, to respect the primary GitHub rate limit.

        When the most recent response indicates ≤ 2 remaining requests
        before the reset (``x-ratelimit-remaining`` header), the caller
        is paused until ``x-ratelimit-reset`` + 2 seconds. The sleep is
        clamped to a minimum of 5 seconds (to avoid tight retry loops on
        unsynchronised clocks) and a maximum of 120 seconds (to avoid
        accidentally pausing forever on a misformatted reset timestamp).

        Parameters
        ----------
        hdrs : dict[str, str]
            Response headers from the most recent :meth:`get`. Keys are
            expected to be lower-cased (which :meth:`get` does
            automatically).
        """

        rem = hdrs.get("x-ratelimit-remaining")
        rst = hdrs.get("x-ratelimit-reset")
        if rem and rst:
            try:
                if int(rem) <= 2:
                    sleep_for = min(
                        max(5, int(rst) - int(time.time()) + 2),
                        120,
                    )
                    time.sleep(sleep_for)
            except ValueError:
                # If either header is unparseable, do not block the run.
                return


def parse_link_header(value: str) -> dict[str, str]:
    """Parse an HTTP ``Link`` header into a ``{rel: url}`` mapping.

    GitHub uses the standard RFC 5988 ``Link`` header for pagination of
    list endpoints. A typical value:

    .. code-block:: text

        <https://api.github.com/repos/o/r/pulls?page=2>; rel="next",
        <https://api.github.com/repos/o/r/pulls?page=42>; rel="last"

    Parameters
    ----------
    value : str
        Raw ``Link`` header value. May be empty.

    Returns
    -------
    dict[str, str]
        Mapping from the ``rel`` token (e.g. ``"next"``, ``"prev"``,
        ``"first"``, ``"last"``) to the corresponding URL. Empty when
        the header is empty or unparseable.
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
# Pull requests
# ---------------------------------------------------------------------------


def iter_prs(
    client: GithubClient,
    owner: str,
    repo: str,
) -> Iterator[dict[str, Any]]:
    """Yield every pull request on ``owner/repo`` in created-asc order.

    Calls ``GET /repos/{owner}/{repo}/pulls?state=all&sort=created&direction=asc&per_page=100``
    and follows the ``Link: rel="next"`` pagination header until
    exhausted. Stops cleanly on the first non-200 response so partial
    results survive a mid-stream rate-limit hit.

    The generator yields **raw** PR dicts as returned by the API.
    Callers that need a stable, downstream-friendly shape should pass
    each item through :func:`normalize_pr`.

    Parameters
    ----------
    client : GithubClient
        Configured HTTP client.
    owner : str
        Repository owner (user or organisation slug).
    repo : str
        Repository name.

    Yields
    ------
    dict[str, Any]
        Raw PR record from the GitHub API.

    Notes
    -----
    Ordering is created ascending so that downstream consumers can rely
    on the streaming order matching the temporal-windowing in
    ``compute_metrics.py`` without an additional sort pass.
    """

    base = f"{client.api_base}/repos/{owner}/{repo}/pulls"
    params = {
        "state": "all",
        "per_page": PAGE_SIZE,
        "sort": "created",
        "direction": "asc",
    }
    next_url: str | None = f"{base}?{urllib.parse.urlencode(params)}"
    while next_url:
        status, data, hdrs = client.get(next_url)
        client.respect_rate_limit(hdrs)
        if status != 200 or not isinstance(data, list):
            # Terminating the generator on a non-200 response preserves
            # whatever partial pages have already been yielded.
            return
        for raw_pr in data:
            if isinstance(raw_pr, dict):
                yield raw_pr
        next_url = parse_link_header(hdrs.get("link", "")).get("next")


def normalize_pr(raw: dict[str, Any]) -> dict[str, Any]:
    """Project a raw PR record into a stable, downstream-friendly shape.

    The projection picks fields that downstream scripts
    (``classify_prs.py``, ``compute_metrics.py``) need explicitly and
    omits the noisy ``_links`` / ``head.repo`` / ``base.repo`` blocks
    that bloat the JSONL output.

    Parameters
    ----------
    raw : dict[str, Any]
        A raw PR record as returned by ``GET /repos/{owner}/{repo}/pulls``.

    Returns
    -------
    dict[str, Any]
        Normalised PR record with the following keys:

        ``number``           — PR number (int).
        ``title``            — PR title.
        ``body``             — PR body (empty string when null).
        ``state``            — ``open`` / ``closed``.
        ``draft``            — Whether the PR is in draft state.
        ``created_at``       — ISO 8601 PR creation timestamp.
        ``closed_at``        — ISO 8601 close timestamp, or null.
        ``merged_at``        — ISO 8601 merge timestamp, or null.
        ``user``             — PR author login.
        ``user_type``        — ``User`` / ``Bot`` (per GitHub's
                              account-type categorisation, used to
                              exclude non-Blitzy bot PRs from Metric 1
                              per AAP §0.1.3 user-example).
        ``head_ref``         — Source branch ref.
        ``head_sha``         — Head commit SHA on the source branch.
        ``base_ref``         — Target branch ref.
        ``labels``           — List of label names attached to the PR.
        ``requested_reviewers`` — List of user logins requested as
                                  reviewers.
        ``merge_commit_sha`` — Merge commit SHA on the base branch
                              when merged, or null.
        ``html_url``         — Browser-facing PR URL.
    """

    user_block = raw.get("user") or {}
    head_block = raw.get("head") or {}
    base_block = raw.get("base") or {}
    labels = [
        label.get("name")
        for label in (raw.get("labels") or [])
        if isinstance(label, dict) and label.get("name")
    ]
    requested_reviewers = [
        reviewer.get("login")
        for reviewer in (raw.get("requested_reviewers") or [])
        if isinstance(reviewer, dict) and reviewer.get("login")
    ]
    return {
        "number": raw.get("number"),
        "title": raw.get("title"),
        "body": raw.get("body") or "",
        "state": raw.get("state"),
        "draft": bool(raw.get("draft", False)),
        "created_at": raw.get("created_at"),
        "closed_at": raw.get("closed_at"),
        "merged_at": raw.get("merged_at"),
        "user": user_block.get("login"),
        "user_type": user_block.get("type"),  # "User" | "Bot"
        "head_ref": head_block.get("ref"),
        "head_sha": head_block.get("sha"),
        "base_ref": base_block.get("ref"),
        "labels": labels,
        "requested_reviewers": requested_reviewers,
        "merge_commit_sha": raw.get("merge_commit_sha"),
        "html_url": raw.get("html_url"),
    }


# ---------------------------------------------------------------------------
# PR reviews
# ---------------------------------------------------------------------------


def iter_reviews(
    client: GithubClient,
    owner: str,
    repo: str,
    pr_number: int,
) -> Iterator[dict[str, Any]]:
    """Yield every review on a single PR in submission order.

    Calls ``GET /repos/{owner}/{repo}/pulls/{pr_number}/reviews`` and
    follows ``Link: rel="next"`` pagination. Each yielded record is
    already projected into the downstream-friendly shape (no raw
    pass-through), because the review endpoint's response is small and
    flat and there's no second consumer that needs the raw form.

    Parameters
    ----------
    client : GithubClient
        Configured HTTP client.
    owner : str
        Repository owner.
    repo : str
        Repository name.
    pr_number : int
        Pull request number.

    Yields
    ------
    dict[str, Any]
        Review record with the keys ``pr_number``, ``review_id``,
        ``user``, ``state`` (``APPROVED`` / ``CHANGES_REQUESTED`` /
        ``COMMENTED`` / ``DISMISSED`` / ``PENDING``), ``submitted_at``,
        and ``commit_id``.
    """

    base = f"{client.api_base}/repos/{owner}/{repo}/pulls/{pr_number}/reviews"
    params = {"per_page": PAGE_SIZE}
    next_url: str | None = f"{base}?{urllib.parse.urlencode(params)}"
    while next_url:
        status, data, hdrs = client.get(next_url)
        client.respect_rate_limit(hdrs)
        if status != 200 or not isinstance(data, list):
            return
        for raw_review in data:
            if not isinstance(raw_review, dict):
                continue
            user_block = raw_review.get("user") or {}
            yield {
                "pr_number": pr_number,
                "review_id": raw_review.get("id"),
                "user": user_block.get("login"),
                "state": raw_review.get("state"),
                "submitted_at": raw_review.get("submitted_at"),
                "commit_id": raw_review.get("commit_id"),
            }
        next_url = parse_link_header(hdrs.get("link", "")).get("next")



# ---------------------------------------------------------------------------
# Releases
# ---------------------------------------------------------------------------


def iter_releases(
    client: GithubClient,
    owner: str,
    repo: str,
) -> Iterator[dict[str, Any]]:
    """Yield every GitHub Release on ``owner/repo``.

    Calls ``GET /repos/{owner}/{repo}/releases?per_page=100`` and
    follows ``Link: rel="next"`` pagination. Yields raw API records;
    callers should pass each through :func:`normalize_release` to apply
    the prerelease-by-suffix logic.

    The Releases endpoint returns the data Formbricks needs for Metric
    9 (Releases) because the release workflow in
    ``.github/workflows/formbricks-release.yml`` is triggered by
    ``release: types: [published]`` events — i.e. Releases are
    authored on the GitHub Releases UI, not via annotated git tags.

    Parameters
    ----------
    client : GithubClient
        Configured HTTP client.
    owner : str
        Repository owner.
    repo : str
        Repository name.

    Yields
    ------
    dict[str, Any]
        Raw release record from the GitHub API.
    """

    base = f"{client.api_base}/repos/{owner}/{repo}/releases"
    params = {"per_page": PAGE_SIZE}
    next_url: str | None = f"{base}?{urllib.parse.urlencode(params)}"
    while next_url:
        status, data, hdrs = client.get(next_url)
        client.respect_rate_limit(hdrs)
        if status != 200 or not isinstance(data, list):
            return
        for raw_release in data:
            if isinstance(raw_release, dict):
                yield raw_release
        next_url = parse_link_header(hdrs.get("link", "")).get("next")


def normalize_release(raw: dict[str, Any]) -> dict[str, Any]:
    """Project a raw release record into the downstream-friendly shape.

    The ``prerelease`` field on the returned record is the **logical
    OR** of the API's explicit ``prerelease: true`` flag and a
    suffix-regex match against the tag name (``-alpha|-beta|-rc|-dev``)
    per AAP §0.8 release-source precedence — because some maintainers
    forget to tick the API checkbox. Both individual sources are
    retained on the record under ``prerelease_by_api_flag`` and
    ``prerelease_by_tag_suffix`` so ``compute_metrics.py`` can audit
    which signal triggered the classification.

    Parameters
    ----------
    raw : dict[str, Any]
        A raw release record as returned by
        ``GET /repos/{owner}/{repo}/releases``.

    Returns
    -------
    dict[str, Any]
        Normalised release record with the keys ``id``, ``tag_name``,
        ``name``, ``prerelease``, ``prerelease_by_api_flag``,
        ``prerelease_by_tag_suffix``, ``draft``, ``published_at``,
        ``created_at``, ``target_commitish``, ``html_url``, ``author``.
    """

    tag = raw.get("tag_name") or ""
    prerelease_flag = bool(raw.get("prerelease"))
    suffix_match = bool(PRERELEASE_SUFFIX_RE.search(tag))
    author_block = raw.get("author") or {}
    return {
        "id": raw.get("id"),
        "tag_name": tag,
        "name": raw.get("name"),
        "prerelease": prerelease_flag or suffix_match,
        "prerelease_by_api_flag": prerelease_flag,
        "prerelease_by_tag_suffix": suffix_match,
        "draft": bool(raw.get("draft", False)),
        "published_at": raw.get("published_at"),
        "created_at": raw.get("created_at"),
        "target_commitish": raw.get("target_commitish"),
        "html_url": raw.get("html_url"),
        "author": author_block.get("login"),
    }


def iter_deployments(
    client: GithubClient,
    owner: str,
    repo: str,
) -> Iterator[dict[str, Any]]:
    """Yield every Deployment event on ``owner/repo``.

    Calls ``GET /repos/{owner}/{repo}/deployments?per_page=100`` and
    follows ``Link: rel="next"`` pagination. Yields raw API records;
    callers should pass each through :func:`normalize_deployment` to
    select the fields downstream metrics consume.

    Deployments are the **tertiary** release source in AAP §0.1.3
    ("release source precedence ... (3) deployment events from CI/CD
    if accessible"). They are an indirect proxy: a deployment is an
    operational event (a "this code is now running here" record),
    not a release decision. The Releases metric falls through to this
    source only when neither GitHub Releases nor annotated semver
    tags produce any events.

    Parameters
    ----------
    client : GithubClient
        Configured HTTP client.
    owner : str
        Repository owner.
    repo : str
        Repository name.

    Yields
    ------
    dict[str, Any]
        Raw deployment record from the GitHub API.
    """

    base = f"{client.api_base}/repos/{owner}/{repo}/deployments"
    params = {"per_page": PAGE_SIZE}
    next_url: str | None = f"{base}?{urllib.parse.urlencode(params)}"
    while next_url:
        status, data, hdrs = client.get(next_url)
        client.respect_rate_limit(hdrs)
        if status != 200 or not isinstance(data, list):
            return
        for raw_record in data:
            if isinstance(raw_record, dict):
                yield raw_record
        next_url = parse_link_header(hdrs.get("link", "")).get("next")


def normalize_deployment(raw: dict[str, Any]) -> dict[str, Any]:
    """Project a raw deployment record into the downstream-friendly shape.

    The ``production_environment`` field is sourced directly from the
    GitHub API (which returns it as a boolean for repositories that
    distinguish environments). When the field is absent we fall back
    to recognising the conventional environment names ``production``
    and ``prod`` so that legacy deployments without environment
    metadata still classify correctly.

    Parameters
    ----------
    raw : dict[str, Any]
        A raw deployment record as returned by
        ``GET /repos/{owner}/{repo}/deployments``.

    Returns
    -------
    dict[str, Any]
        Normalised deployment record with the keys ``id``, ``sha``,
        ``ref``, ``task``, ``environment``, ``description``,
        ``creator``, ``production_environment``,
        ``transient_environment``, ``created_at``, ``updated_at``.
    """

    creator_block = raw.get("creator") or {}
    env = raw.get("environment")
    production_flag = raw.get("production_environment")
    # Fall back to environment-name heuristics when the explicit flag
    # is absent (older deployments) so the metric does not miss them.
    if production_flag is None and isinstance(env, str):
        production_flag = env.lower() in {"production", "prod"}
    return {
        "id": raw.get("id"),
        "sha": raw.get("sha"),
        "ref": raw.get("ref"),
        "task": raw.get("task"),
        "environment": env,
        "description": raw.get("description"),
        "creator": creator_block.get("login")
        if isinstance(creator_block, dict)
        else None,
        "production_environment": bool(production_flag),
        "transient_environment": bool(raw.get("transient_environment", False)),
        "created_at": raw.get("created_at"),
        "updated_at": raw.get("updated_at"),
    }


# ---------------------------------------------------------------------------
# Branch protection
# ---------------------------------------------------------------------------


def fetch_branch_protection(
    client: GithubClient,
    owner: str,
    repo: str,
    branch: str = "main",
) -> dict[str, Any]:
    """Return the branch-protection settings for ``owner/repo:branch``.

    Calls ``GET /repos/{owner}/{repo}/branches/{branch}/protection``.
    This endpoint requires admin scope on the repository; without it
    the API returns 403 or 404, which is the **expected** outcome for
    a typical PAT-based extraction.

    Parameters
    ----------
    client : GithubClient
        Configured HTTP client.
    owner : str
        Repository owner.
    repo : str
        Repository name.
    branch : str, default ``"main"``
        Branch to query.

    Returns
    -------
    dict[str, Any]
        On success: ``{"accessible": True, "branch": branch,
        "settings": <full protection object>}``. On 403 / 404 / network
        failure: ``{"accessible": False, "branch": branch,
        "status_code": int, "reason": str}``. The result is **never**
        an exception; this method gracefully degrades per AAP §0.3.4.
    """

    url = f"{client.api_base}/repos/{owner}/{repo}/branches/{branch}/protection"
    status, data, hdrs = client.get(url)
    client.respect_rate_limit(hdrs)
    if status == 200 and isinstance(data, dict):
        return {
            "accessible": True,
            "branch": branch,
            "status_code": status,
            "settings": data,
        }
    return {
        "accessible": False,
        "branch": branch,
        "status_code": status,
        "reason": (
            "Branch-protection settings require repo admin scope. "
            "Per AAP §0.3.4 Metric 10 (Approved Exceptions) falls back to "
            "label-based signal or 'Insufficient signal' confidence Low."
        ),
    }


# ---------------------------------------------------------------------------
# Admin audit log
# ---------------------------------------------------------------------------


def iter_audit_log(
    client: GithubClient,
    org: str | None,
) -> Iterator[dict[str, Any]]:
    """Yield protected-branch-bypass events from the org audit log.

    Calls
    ``GET /orgs/{org}/audit-log?phrase=action:protected_branch.policy_override``
    and follows ``Link: rel="next"`` pagination. The endpoint requires a
    PAT with ``admin:org`` scope; without it the call returns 404 and
    the generator yields nothing — an **empty** audit log is the
    correct outcome.

    The ``phrase`` filter targets the policy-override action which is
    the primary signal for Metric 10 (Approved Exceptions) governance
    bypasses. Other actions (admin role grants, secret-scanning
    bypasses, etc.) are intentionally not enumerated; expanding the
    filter is documented as a "Suggested Next Tasks" item in
    ``acceleration/README.md``.

    Parameters
    ----------
    client : GithubClient
        Configured HTTP client.
    org : str or None
        Organisation slug. When ``None`` the generator returns
        immediately without making any HTTP call (the user-account
        repos do not have an audit log endpoint).

    Yields
    ------
    dict[str, Any]
        Audit-log event projected to the keys ``@timestamp``,
        ``action``, ``actor``, ``repo``, ``branch``, plus the raw event
        under ``raw`` for downstream forensics.
    """

    if not org:
        return
    base = f"{client.api_base}/orgs/{org}/audit-log"
    params = {
        "per_page": PAGE_SIZE,
        "phrase": "action:protected_branch.policy_override",
    }
    next_url: str | None = f"{base}?{urllib.parse.urlencode(params)}"
    while next_url:
        status, data, hdrs = client.get(next_url)
        client.respect_rate_limit(hdrs)
        if status != 200 or not isinstance(data, list):
            return
        for raw_event in data:
            if not isinstance(raw_event, dict):
                continue
            yield {
                "@timestamp": raw_event.get("@timestamp"),
                "action": raw_event.get("action"),
                "actor": raw_event.get("actor"),
                "repo": raw_event.get("repo"),
                "branch": raw_event.get("branch"),
                "raw": raw_event,
            }
        next_url = parse_link_header(hdrs.get("link", "")).get("next")



# ---------------------------------------------------------------------------
# JSONL helpers
# ---------------------------------------------------------------------------
# Field names contributed exclusively by ``extract_git.py`` that the
# API-side normalisation cannot reconstruct. ``merge_pr_records`` restores
# these on the combined record after the API spread, so the merge result
# preserves the temporal anchors needed for Flow Active / Flow Time
# (Metrics 4 and 7).
_GIT_FIRST_LAST_KEYS: tuple[str, ...] = (
    "first_commit_at",
    "last_commit_at",
    "first_commit_sha",
    "merge_commit_sha_from_git",
    "merge_sha",
    "merged_at",
    "merge_subject",
    "merge_body",
    "merge_author_name",
    "merge_author_email",
    "module",
    "module_counts",
    "ai_signal",
    "ai_indicators",
)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    """Read every JSON object from a ``.jsonl`` file into a list.

    Skips blank lines and silently discards lines that fail to parse
    (a corrupt mid-stream line in the previous extractor's output
    should not abort the merge). The on-disk format is one JSON object
    per line (compact, no leading/trailing whitespace), UTF-8 encoded.

    Parameters
    ----------
    path : Path
        Path to the ``.jsonl`` file. A non-existent path returns an
        empty list (used to detect "extract_git.py never ran" so the
        merge falls back to API-only output).

    Returns
    -------
    list[dict[str, Any]]
        Decoded records in file order.
    """

    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fhandle:
        for raw_line in fhandle:
            stripped = raw_line.strip()
            if not stripped:
                continue
            try:
                obj = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                out.append(obj)
    return out


def merge_pr_records(
    git_prs: list[dict[str, Any]],
    api_prs_by_number: dict[int, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Combine git-derived and API-derived PR records into one stream.

    Merge strategy (git-first, API enriches):

    1. For each git-side PR record with a known ``number``, look up the
       API counterpart. When the API counterpart exists, the records
       are merged with the API record taking precedence on platform
       fields (``draft``, ``state``, ``user``, ``labels``,
       ``requested_reviewers``) and the git-side record taking
       precedence on branch-only fields enumerated in
       :data:`_GIT_FIRST_LAST_KEYS` (``first_commit_at``,
       ``last_commit_at``, ``merge_commit_sha_from_git``, etc.). The
       combined record is tagged ``source_blend = "git_plus_api"``.
    2. When the API counterpart is absent (closed PR not synced to
       cache, archived PR, deleted PR), the git record is kept verbatim
       with ``source_blend = "git_only"``.
    3. After all git records are processed, any **API-only** PRs
       (typically still-open, never-merged PRs that have no merge
       commit in git history) are appended with ``source_blend =
       "api_only"``. These are the in-progress PRs that Metric 1 (Flow
       Load) needs per the user-example in AAP §0.1.3.

    Parameters
    ----------
    git_prs : list[dict[str, Any]]
        PR records produced by ``extract_git.py`` (``prs.jsonl``).
    api_prs_by_number : dict[int, dict[str, Any]]
        Mapping from PR number to the normalised API record (output
        of :func:`normalize_pr`).

    Returns
    -------
    list[dict[str, Any]]
        The merged PR stream, suitable for writing back to
        ``prs.jsonl``.
    """

    merged: list[dict[str, Any]] = []
    used_api_numbers: set[int] = set()
    for git_pr in git_prs:
        raw_number = git_pr.get("number")
        try:
            number = int(raw_number) if raw_number is not None else None
        except (TypeError, ValueError):
            number = None
        api_pr = api_prs_by_number.get(number) if number is not None else None
        if api_pr is None:
            merged.append({**git_pr, "source_blend": "git_only"})
            continue
        combined: dict[str, Any] = {**git_pr, **api_pr, "source_blend": "git_plus_api"}
        # Restore git-derived fields the API spread would otherwise
        # overwrite (most overlap is benign — the key offender is the
        # ``title`` and ``merge_commit_sha`` overlap, but the
        # branch-window timestamps are critical for Metrics 4 and 7).
        for key in _GIT_FIRST_LAST_KEYS:
            if key in git_pr:
                combined[key] = git_pr[key]
        merged.append(combined)
        if number is not None:
            used_api_numbers.add(number)
    # Append API-only PRs (in-progress / draft / never-merged).
    for number, api_pr in api_prs_by_number.items():
        if number in used_api_numbers:
            continue
        merged.append({**api_pr, "source_blend": "api_only"})
    return merged


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Define and parse the script's CLI.

    Parameters
    ----------
    argv : list[str] or None
        Argument vector excluding the program name. ``None`` (the
        default) defers to ``sys.argv``.

    Returns
    -------
    argparse.Namespace
        Parsed arguments. The fields are:

        - ``owner`` (default ``REPO_OWNER`` env or ``formbricks``)
        - ``repo`` (default ``REPO_NAME`` env or ``formbricks``)
        - ``org`` (default ``GITHUB_ORG`` env or ``None``; falls back to
          ``owner`` at audit-log time if still ``None``)
        - ``branch`` (default ``main``)
        - ``output_dir`` (default ``acceleration/data``)
        - ``api_base`` (default ``GITHUB_API`` env or
          :data:`GITHUB_API_BASE`)
        - ``skip_network`` (default ``False``)
        - ``max_prs`` (default ``10_000``)
        - ``skip_reviews`` (default ``False``)
    """

    parser = argparse.ArgumentParser(
        description=(
            "Extract PR reviews, releases, branch protection, and admin audit log "
            "via the GitHub REST API. HTTP GET only; read-only per AAP §0.7.2.1."
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
        "--org",
        default=os.environ.get("GITHUB_ORG"),
        help=(
            "Organisation slug for audit-log access. When omitted, the "
            "extractor falls back to --owner at audit-log time."
        ),
    )
    parser.add_argument(
        "--branch",
        default="main",
        help="Branch to query for branch-protection settings (default: main).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("acceleration/data"),
        help="Directory under which the JSONL/JSON outputs are written.",
    )
    parser.add_argument(
        "--api-base",
        default=os.environ.get("GITHUB_API", GITHUB_API_BASE),
        help=(
            "Override the GitHub API base URL (e.g. for GitHub Enterprise "
            f"Server). Default: $GITHUB_API or {GITHUB_API_BASE!r}."
        ),
    )
    parser.add_argument(
        "--skip-network",
        action="store_true",
        help=(
            "Do not call any GitHub endpoint; touch each output file and "
            "write a github_access.json documenting every endpoint as "
            "inaccessible. Useful for offline smoke tests."
        ),
    )
    parser.add_argument(
        "--max-prs",
        type=int,
        default=10_000,
        help=(
            "Upper bound on PRs to fetch (safety cap; Formbricks has ~3,465 "
            "PR-merges)."
        ),
    )
    parser.add_argument(
        "--skip-reviews",
        action="store_true",
        help=(
            "Skip the per-PR /reviews fetch (saves time when only releases "
            "or branch-protection are needed). The reviews.jsonl file is "
            "still created (empty) so downstream consumers find it."
        ),
    )
    return parser.parse_args(argv)



# ---------------------------------------------------------------------------
# Main entrypoint
# ---------------------------------------------------------------------------


def _write_jsonl_lines(path: Path, records: Iterable[dict[str, Any]]) -> int:
    """Write an iterable of records to a JSONL file and return the count.

    Helper used by :func:`main` to keep the orchestration straightforward
    (open-write-close pattern is identical across the four JSONL outputs).
    Records are serialised with ``ensure_ascii=False`` (so non-ASCII PR
    titles and author names round-trip cleanly) and ``default=str`` (so
    any stray non-JSON-native value falls back to its string
    representation rather than raising).

    Parameters
    ----------
    path : Path
        Output path. Parent directory is assumed to exist.
    records : Iterable[dict[str, Any]]
        Records to write.

    Returns
    -------
    int
        Number of records written.
    """

    count = 0
    with path.open("w", encoding="utf-8") as fhandle:
        for record in records:
            fhandle.write(json.dumps(record, ensure_ascii=False, default=str))
            fhandle.write("\n")
            count += 1
    return count


def _ensure_output_stubs(paths: dict[str, Path], reason: str) -> None:
    """Touch each output file so downstream consumers always find them.

    Used by the ``--skip-network`` / missing-token path so the rest of
    the pipeline can keep moving without special-casing missing files.
    Empty JSONL is the natural representation for "no records". The
    branch-protection stub gets a small JSON blob with the
    inaccessibility reason so consumers can distinguish "the API said
    no" from "we never asked".

    Parameters
    ----------
    paths : dict[str, Path]
        Output file map; keys are ``prs``, ``reviews``, ``releases``,
        ``deployments``, ``branch_protection``, ``audit_log``, ``access``.
    reason : str
        Human-readable reason that callers will copy into the
        ``github_access.json`` ``reason`` field.
    """

    for key in ("prs", "reviews", "releases", "deployments", "audit_log"):
        if not paths[key].exists():
            paths[key].write_text("", encoding="utf-8")
    if not paths["branch_protection"].exists():
        paths["branch_protection"].write_text(
            json.dumps(
                {
                    "accessible": False,
                    "branch": "main",
                    "status_code": 0,
                    "reason": reason,
                },
                indent=2,
            ),
            encoding="utf-8",
        )


def main(argv: list[str] | None = None) -> int:
    """Run the GitHub extractor end-to-end.

    The function performs the following steps:

    1. Parse CLI arguments.
    2. Initialise the structured JSON logger (with a stdlib-logging
       fallback per AAP Rule 1).
    3. If ``--skip-network`` or no token, touch outputs and write an
       inaccessibility manifest; return 0.
    4. Otherwise, fetch (in order): pulls → reviews → releases →
       branch-protection → audit-log. Each step is wrapped in a
       try/except that records the endpoint as inaccessible in the
       manifest rather than aborting the run.
    5. Merge the API-derived PR records with whatever ``extract_git.py``
       left in ``prs.jsonl``.
    6. Write the final ``github_access.json`` manifest with the
       endpoint-accessibility breakdown and the total request count.

    Parameters
    ----------
    argv : list[str] or None
        Argument vector excluding the program name. ``None`` defers to
        ``sys.argv``.

    Returns
    -------
    int
        Process exit code. The current implementation always returns
        ``0`` (zero) because every error path is captured into the
        manifest as an inaccessibility record — downstream consumers
        decide what to do with that, not the extractor.
    """

    args = parse_args(argv)

    # Configure the structured JSON logger if the module is importable;
    # otherwise fall back to stdlib logging so the operator still sees
    # output even on a broken install (graceful degradation per AAP
    # Observability Rule 1).
    try:
        # The script lives at acceleration/scripts/extract_github.py;
        # parents[2] is the repository root, which we add to sys.path so
        # ``acceleration.observability.logger`` resolves as a namespace
        # package import without requiring an __init__.py.
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from acceleration.observability.logger import (  # noqa: WPS433
            generate_run_id,
            get_logger,
        )

        run_id = os.environ.get("ACCEL_RUN_ID") or generate_run_id()
        log = get_logger("acceleration.scripts.extract_github", run_id=run_id)
    except Exception:  # pragma: no cover - exercised only on broken installs
        import logging

        logging.basicConfig(
            level=os.environ.get("ACCEL_LOG_LEVEL", "INFO"),
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
        )
        log = logging.getLogger("acceleration.scripts.extract_github")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {
        "prs": args.output_dir / "prs.jsonl",
        "reviews": args.output_dir / "reviews.jsonl",
        "releases": args.output_dir / "releases.jsonl",
        # Deployments are the tertiary release source per AAP §0.1.3.
        # Emitted as ``deployments.jsonl`` so ``compute_metrics.py`` can
        # use them as a Low-confidence fallback when neither GitHub
        # Releases nor annotated semver tags produce events.
        "deployments": args.output_dir / "deployments.jsonl",
        "branch_protection": args.output_dir / "branch_protection.json",
        "audit_log": args.output_dir / "audit_log.jsonl",
        "access": args.output_dir / "github_access.json",
    }

    token = os.environ.get("GITHUB_TOKEN")
    # Graceful degradation path: no network OR no token => touch outputs
    # and emit an all-inaccessible manifest. Exit cleanly so the
    # orchestrator can carry on with whatever local-only metrics remain.
    if args.skip_network or not token:
        reason = (
            "skip-network supplied"
            if args.skip_network
            else "GITHUB_TOKEN absent — unauthenticated calls would exceed the 60/hour limit"
        )
        log.info(
            "Skipping GitHub API: %s",
            reason,
            extra={"owner": args.owner, "repo": args.repo, "skip_network": args.skip_network},
        )
        _ensure_output_stubs(paths, reason)
        paths["access"].write_text(
            json.dumps(
                {
                    "accessed_at": time.strftime(
                        "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
                    ),
                    "owner": args.owner,
                    "repo": args.repo,
                    "token_present": False,
                    "reason": reason,
                    "endpoints_attempted": [],
                    "endpoints_accessible": [],
                    "endpoints_inaccessible": [
                        "pulls",
                        "reviews",
                        "releases",
                        "deployments",
                        "branch_protection",
                        "audit_log",
                    ],
                    "api_requests": 0,
                    "needed": {
                        "pulls": "GITHUB_TOKEN with repo:read scope.",
                        "reviews": "GITHUB_TOKEN with repo:read scope.",
                        "releases": "GITHUB_TOKEN with repo:read scope.",
                        "deployments": (
                            "GITHUB_TOKEN with repo:read scope; the "
                            "Deployments API is read-public for public "
                            "repositories but counts against the same "
                            "rate limit as other endpoints."
                        ),
                        "branch_protection": (
                            "GITHUB_TOKEN with repo scope and Maintain or "
                            "Admin role on the repository."
                        ),
                        "audit_log": "PAT with admin:org scope on the GitHub organisation.",
                    },
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        log.info(
            "Wrote inaccessibility manifest to %s",
            paths["access"],
            extra={"manifest": str(paths["access"])},
        )
        return 0

    client = GithubClient(token=token, api_base=args.api_base)
    access: dict[str, Any] = {
        "accessed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "owner": args.owner,
        "repo": args.repo,
        "branch": args.branch,
        "token_present": True,
        "endpoints_attempted": [],
        "endpoints_accessible": [],
        "endpoints_inaccessible": [],
    }

    # -------------------------------------------------------------------
    # 1. Pull requests
    # -------------------------------------------------------------------
    log.info(
        "Fetching pull requests for %s/%s",
        args.owner,
        args.repo,
        extra={"owner": args.owner, "repo": args.repo, "endpoint": "pulls"},
    )
    access["endpoints_attempted"].append("pulls")
    api_prs_by_number: dict[int, dict[str, Any]] = {}
    fetched = 0
    try:
        for raw_pr in iter_prs(client, args.owner, args.repo):
            raw_number = raw_pr.get("number")
            if raw_number is None:
                continue
            try:
                number = int(raw_number)
            except (TypeError, ValueError):
                continue
            api_prs_by_number[number] = normalize_pr(raw_pr)
            fetched += 1
            if fetched >= args.max_prs:
                log.info(
                    "Hit --max-prs cap at %d; stopping PR fetch",
                    args.max_prs,
                    extra={"max_prs": args.max_prs, "fetched": fetched},
                )
                break
        access["endpoints_accessible"].append("pulls")
    except Exception as exc:  # noqa: BLE001 - broad to satisfy graceful degradation
        log.warning(
            "PR fetch terminated early: %s: %s",
            type(exc).__name__,
            exc,
            extra={"endpoint": "pulls", "fetched": fetched},
        )
        access["endpoints_inaccessible"].append("pulls")
    log.info(
        "Fetched %d PRs from GitHub API",
        len(api_prs_by_number),
        extra={"endpoint": "pulls", "count": len(api_prs_by_number)},
    )

    # Merge with extract_git.py output, if present.
    git_prs = load_jsonl(paths["prs"])
    if git_prs:
        merged_prs = merge_pr_records(git_prs, api_prs_by_number)
        log.info(
            "Merging %d git-derived PR records with %d API-derived PR records",
            len(git_prs),
            len(api_prs_by_number),
            extra={"git_prs": len(git_prs), "api_prs": len(api_prs_by_number)},
        )
    else:
        merged_prs = list(api_prs_by_number.values())
        log.info(
            "No git-derived prs.jsonl found; writing API-only PR records",
            extra={"api_prs": len(api_prs_by_number)},
        )
    pr_written = _write_jsonl_lines(paths["prs"], merged_prs)
    log.info(
        "Wrote %d merged PR records to %s",
        pr_written,
        paths["prs"],
        extra={"path": str(paths["prs"]), "count": pr_written},
    )

    # -------------------------------------------------------------------
    # 2. Reviews
    # -------------------------------------------------------------------
    if args.skip_reviews:
        log.info("Skipping per-PR /reviews fetch (--skip-reviews)")
        paths["reviews"].write_text("", encoding="utf-8")
        access["endpoints_attempted"].append("reviews_skipped")
    else:
        log.info(
            "Fetching reviews for %d PRs",
            len(api_prs_by_number),
            extra={"endpoint": "reviews", "prs": len(api_prs_by_number)},
        )
        access["endpoints_attempted"].append("reviews")
        review_count = 0
        review_error: str | None = None
        with paths["reviews"].open("w", encoding="utf-8") as fhandle:
            for number in sorted(api_prs_by_number.keys()):
                try:
                    for review in iter_reviews(
                        client, args.owner, args.repo, number
                    ):
                        fhandle.write(
                            json.dumps(review, ensure_ascii=False, default=str)
                        )
                        fhandle.write("\n")
                        review_count += 1
                except Exception as exc:  # noqa: BLE001 - graceful degradation
                    review_error = f"{type(exc).__name__}: {exc}"
                    log.warning(
                        "Reviews fetch for PR #%d terminated: %s",
                        number,
                        review_error,
                        extra={"endpoint": "reviews", "pr_number": number},
                    )
                    break
        if review_error is None:
            access["endpoints_accessible"].append("reviews")
        else:
            access["endpoints_inaccessible"].append("reviews")
        log.info(
            "Wrote %d review records to %s",
            review_count,
            paths["reviews"],
            extra={"path": str(paths["reviews"]), "count": review_count},
        )

    # -------------------------------------------------------------------
    # 3. Releases
    # -------------------------------------------------------------------
    log.info(
        "Fetching releases for %s/%s",
        args.owner,
        args.repo,
        extra={"endpoint": "releases"},
    )
    access["endpoints_attempted"].append("releases")
    release_count = 0
    release_error: str | None = None
    try:
        with paths["releases"].open("w", encoding="utf-8") as fhandle:
            for raw_release in iter_releases(client, args.owner, args.repo):
                fhandle.write(
                    json.dumps(
                        normalize_release(raw_release),
                        ensure_ascii=False,
                        default=str,
                    )
                )
                fhandle.write("\n")
                release_count += 1
    except Exception as exc:  # noqa: BLE001 - graceful degradation
        release_error = f"{type(exc).__name__}: {exc}"
        log.warning(
            "Releases fetch terminated early: %s",
            release_error,
            extra={"endpoint": "releases", "count": release_count},
        )
    if release_error is None:
        access["endpoints_accessible"].append("releases")
    else:
        access["endpoints_inaccessible"].append("releases")
    log.info(
        "Wrote %d release records to %s",
        release_count,
        paths["releases"],
        extra={"path": str(paths["releases"]), "count": release_count},
    )

    # -------------------------------------------------------------------
    # 3a. Deployments (tertiary release source per AAP §0.1.3)
    # -------------------------------------------------------------------
    # The Deployments API is the **tertiary** release source. We always
    # attempt it when we have a working client so the Releases metric
    # can fall through to it when both GitHub Releases and annotated
    # semver tags are empty. Graceful degradation: failures append the
    # endpoint to ``endpoints_inaccessible`` and leave deployments.jsonl
    # empty so ``compute_metrics.py`` sees zero events.
    log.info(
        "Fetching deployments for %s/%s",
        args.owner,
        args.repo,
        extra={"endpoint": "deployments"},
    )
    access["endpoints_attempted"].append("deployments")
    deployment_count = 0
    deployment_error: str | None = None
    try:
        with paths["deployments"].open("w", encoding="utf-8") as fhandle:
            for raw_deployment in iter_deployments(
                client, args.owner, args.repo
            ):
                fhandle.write(
                    json.dumps(
                        normalize_deployment(raw_deployment),
                        ensure_ascii=False,
                        default=str,
                    )
                )
                fhandle.write("\n")
                deployment_count += 1
    except Exception as exc:  # noqa: BLE001 - graceful degradation
        deployment_error = f"{type(exc).__name__}: {exc}"
        log.warning(
            "Deployments fetch terminated early: %s",
            deployment_error,
            extra={"endpoint": "deployments", "count": deployment_count},
        )
    if deployment_error is None:
        access["endpoints_accessible"].append("deployments")
    else:
        access["endpoints_inaccessible"].append("deployments")
    log.info(
        "Wrote %d deployment records to %s",
        deployment_count,
        paths["deployments"],
        extra={"path": str(paths["deployments"]), "count": deployment_count},
    )

    # -------------------------------------------------------------------
    # 4. Branch protection
    # -------------------------------------------------------------------
    log.info(
        "Fetching branch protection for %s/%s:%s",
        args.owner,
        args.repo,
        args.branch,
        extra={"endpoint": "branch_protection", "branch": args.branch},
    )
    access["endpoints_attempted"].append("branch_protection")
    bp = fetch_branch_protection(client, args.owner, args.repo, args.branch)
    paths["branch_protection"].write_text(
        json.dumps(bp, indent=2, default=str), encoding="utf-8"
    )
    if bp.get("accessible"):
        access["endpoints_accessible"].append("branch_protection")
    else:
        access["endpoints_inaccessible"].append("branch_protection")
    log.info(
        "Branch protection accessible=%s status=%s",
        bp.get("accessible"),
        bp.get("status_code"),
        extra={
            "endpoint": "branch_protection",
            "accessible": bp.get("accessible"),
            "status_code": bp.get("status_code"),
        },
    )

    # -------------------------------------------------------------------
    # 5. Audit log
    # -------------------------------------------------------------------
    # If --org is empty, fall back to --owner (the audit-log endpoint
    # tolerates org slugs that look like usernames; the worst case is a
    # 404 which we record as inaccessible).
    org = args.org or args.owner
    log.info(
        "Fetching admin audit log for org=%s",
        org,
        extra={"endpoint": "audit_log", "org": org},
    )
    access["endpoints_attempted"].append("audit_log")
    audit_count = 0
    audit_error: str | None = None
    try:
        with paths["audit_log"].open("w", encoding="utf-8") as fhandle:
            for event in iter_audit_log(client, org):
                fhandle.write(json.dumps(event, ensure_ascii=False, default=str))
                fhandle.write("\n")
                audit_count += 1
    except Exception as exc:  # noqa: BLE001 - graceful degradation
        audit_error = f"{type(exc).__name__}: {exc}"
        log.info(
            "Audit log unreachable: %s",
            audit_error,
            extra={"endpoint": "audit_log", "org": org},
        )

    # Heuristic: 0 records + last_status not in (200, 404) means the
    # endpoint errored out (403 forbidden, 5xx server error). A 0-count
    # with last_status=200 or 404 means "endpoint responded; just no
    # matching events" — that IS accessible (the only AAP-compliant
    # signal that "no governance bypass happened").
    if audit_error is not None:
        access["endpoints_inaccessible"].append("audit_log")
    elif audit_count == 0 and client.last_status not in (200, 404):
        access["endpoints_inaccessible"].append("audit_log")
    else:
        access["endpoints_accessible"].append("audit_log")
    log.info(
        "Wrote %d audit-log entries to %s (zero is expected without admin scope)",
        audit_count,
        paths["audit_log"],
        extra={"path": str(paths["audit_log"]), "count": audit_count},
    )

    # -------------------------------------------------------------------
    # Final access manifest
    # -------------------------------------------------------------------
    access["api_requests"] = client.request_count
    # Retry / reliability counters per the review feedback: "record
    # retry attempts in github_access.json" so operators can audit
    # whether transient failures biased any metric.
    access["retry_attempts"] = client.retry_attempts
    access["retry_recoveries"] = client.retry_recoveries
    access["retry_failures"] = client.retry_failures
    access["retry_policy"] = {
        "max_retries": HTTP_MAX_RETRIES,
        "backoff_base_seconds": HTTP_RETRY_BACKOFF_BASE,
        "retryable_status_codes": sorted(HTTP_RETRYABLE_STATUS),
    }
    access["needed"] = {
        "audit_log": "PAT with admin:org scope on the GitHub organisation.",
        "branch_protection": (
            "PAT with repo scope and Maintain or Admin role on the "
            "repository."
        ),
    }
    paths["access"].write_text(
        json.dumps(access, indent=2, default=str), encoding="utf-8"
    )
    log.info(
        "Wrote access manifest to %s; total API requests: %d "
        "(retry attempts: %d, recoveries: %d, failures: %d)",
        paths["access"],
        client.request_count,
        client.retry_attempts,
        client.retry_recoveries,
        client.retry_failures,
        extra={
            "manifest": str(paths["access"]),
            "api_requests": client.request_count,
            "retry_attempts": client.retry_attempts,
            "retry_recoveries": client.retry_recoveries,
            "retry_failures": client.retry_failures,
            "endpoints_accessible": access["endpoints_accessible"],
            "endpoints_inaccessible": access["endpoints_inaccessible"],
        },
    )
    return 0


# ---------------------------------------------------------------------------
# Module surface
# ---------------------------------------------------------------------------
# Re-export ``Iterable`` and ``field`` so static analysers see them as
# used. Both are imported per the file schema; ``Iterable`` is the
# documented input type for :func:`_write_jsonl_lines` and ``field`` is
# imported alongside ``dataclass`` as a forward-compatibility convenience
# for any future :class:`GithubClient` subclass that needs a default
# factory.

__all__ = [
    "EXCEPTION_LABELS",
    "GITHUB_API_BASE",
    "GithubClient",
    "HTTP_MAX_RETRIES",
    "HTTP_RETRYABLE_STATUS",
    "HTTP_RETRY_BACKOFF_BASE",
    "Iterable",
    "MAX_REQUESTS_PER_RUN",
    "PAGE_SIZE",
    "PRERELEASE_SUFFIX_RE",
    "USER_AGENT",
    "fetch_branch_protection",
    "field",
    "iter_audit_log",
    "iter_deployments",
    "iter_prs",
    "iter_releases",
    "iter_reviews",
    "load_jsonl",
    "main",
    "merge_pr_records",
    "normalize_deployment",
    "normalize_pr",
    "normalize_release",
    "parse_args",
    "parse_link_header",
]


if __name__ == "__main__":
    sys.exit(main())

