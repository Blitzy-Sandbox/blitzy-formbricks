#!/usr/bin/env python3
"""
acceleration.scripts.extract_ci_tests
=====================================

CI test-artifact extractor for the Development Acceleration Analysis pipeline.

The script discovers GitHub Actions workflow runs for the three test-bearing
workflows (``test.yml``, ``e2e.yml``, ``chromatic.yml``) on ``main``,
downloads every available artifact, unpacks the ZIP in memory, locates
JUnit-shaped XML reports, and emits one JSON record per
``(workflow run, test case)`` tuple to
``acceleration/data/test_results.jsonl``. A sibling manifest at
``acceleration/data/test_results_access.json`` documents what was retrieved
and — crucially — whether the data is sufficient to compute Metric 11
(Escaped Defects) or whether the metric must report
``Insufficient signal — CI test history unavailable``.

Outputs (under ``acceleration/data/`` by default)
-------------------------------------------------

``test_results.jsonl``
    One JSON object per line. Each record describes a single test case
    observed in a single workflow run, carrying:

    - ``workflow`` — the source workflow filename (``test.yml``,
      ``e2e.yml``, ``chromatic.yml``).
    - ``workflow_id`` — the numeric GitHub Actions workflow ID.
    - ``run_id`` — the numeric workflow-run ID.
    - ``head_sha`` — the commit SHA the run targeted on ``main``. This
      is the join key consumed by ``compute_metrics.py`` to bin a test
      transition into a temporal window.
    - ``created_at`` — the workflow run's creation timestamp (ISO-8601
      UTC string as returned by the GitHub API).
    - ``artifact_id`` / ``artifact_name`` — provenance of the JUnit XML
      file the record was parsed from.
    - ``test_id`` — the stable identifier ``"{classname}::{name}"`` used
      to detect per-test transitions across runs (``passing → failing``,
      ``passing → skipped``, etc.).
    - ``classname`` / ``name`` — the JUnit ``<testcase>`` ``classname``
      and ``name`` attributes (or the parent ``<testsuite>`` ``name``
      when ``classname`` is absent).
    - ``status`` — one of ``passed`` / ``failed`` / ``errored`` /
      ``skipped`` (mapped from ``<failure>`` / ``<error>`` /
      ``<skipped>`` children of the ``<testcase>``).
    - ``time_seconds`` — execution time in seconds when reported, else
      ``None``.
    - ``message`` — the failure / error message truncated to 500
      characters, else ``None``.

    Empty file when the API was not called (``--skip-network`` or absent
    ``GITHUB_TOKEN``) or when no JUnit-shaped artifacts were located.

``test_results_access.json``
    Access manifest documenting:

    - ``available`` — ``True`` when at least one test record was
      written; ``False`` otherwise.
    - ``reason`` — populated when ``available`` is ``False`` with a
      short human-readable explanation copied into the Insufficient-Signal
      caveat in the report.
    - ``tried`` — list of workflow filenames the extractor attempted to
      resolve.
    - ``needed`` — the data source ``compute_metrics.py`` would require
      to lift the metric out of Insufficient-Signal status.
    - When ``available`` is ``True``: ``workflows``, ``workflow_ids``,
      ``runs_seen``, ``runs_with_test_artifacts``, ``records_written``,
      ``api_requests``.

Authority
---------

- AAP §0.4.1 — enumerates ``acceleration/scripts/extract_ci_tests.py``
  as a CREATE target.
- AAP §0.3.2.2 — CI Test Extractor description ("downloads and parses
  JUnit XML artifacts from GitHub Actions runs; rationale: Metric 11
  requires per-test transition history").
- AAP §0.3.4 — Escaped Defects implementation details ("Pull JUnit XML
  or equivalent artifacts from ``test.yml``, ``e2e.yml``, ``chromatic.yml``
  runs. Track per-test transitions on ``main``: ``passing → failing``
  (regression) and newly-marked ``skipped|disabled|xfail`` (suppressed
  signal). Flaky tests (alternating pass/fail) counted only if failing
  in ≥3 consecutive runs. Also report skipped-rate
  (``skipped / total``) to normalize for test-suite growth").
- Source: ``.github/workflows/test.yml`` — unit tests entry point.
- Source: ``.github/workflows/e2e.yml`` — Playwright E2E with
  ``playwright-report`` artifact upload (line 234-239).
- Source: ``.github/workflows/chromatic.yml`` — Storybook visual
  regression runner.

Read-only discipline (AAP §0.7.2.1, §0.8.7, §0.8.8)
---------------------------------------------------

- HTTP method: ``GET`` only. No ``POST``, ``PUT``, ``PATCH``, ``DELETE``.
- Filesystem writes are confined to ``test_results.jsonl`` and
  ``test_results_access.json`` under the supplied ``--output-dir``.
- ZIP archives are unpacked in memory via :class:`io.BytesIO`; no
  temporary files leak outside the process (Phase 9 of the agent
  prompt).
- Stdlib-only by design (AAP §0.6.1, §0.8.8). HTTP calls are issued via
  :mod:`urllib.request` so the pipeline runs on a clean Python 3.10+
  installation without ``pip install``.

Graceful degradation (AAP §0.3.4)
---------------------------------

- ``--skip-network`` or absent ``GITHUB_TOKEN`` → touch
  ``test_results.jsonl`` (empty) and write a manifest with
  ``available: false`` and a ``reason`` documenting the cause. Exit
  code ``0`` so the orchestrator continues with whatever local-only
  metrics remain.
- Network errors (``URLError`` / ``HTTPError`` / rate-limit exhaustion)
  are caught per-workflow; partial results from preceding workflows are
  preserved.
- Corrupt ZIPs (``BadZipFile``) and malformed XML (``ET.ParseError``)
  are recorded as zero records for that artifact and the loop
  continues.

Invocation
----------

.. code-block:: bash

    # End-to-end run against the live GitHub API:
    python3 acceleration/scripts/extract_ci_tests.py \\
        --owner formbricks --repo formbricks \\
        --output-dir acceleration/data

    # Offline smoke test (no network) that still touches the outputs:
    python3 acceleration/scripts/extract_ci_tests.py --skip-network \\
        --output-dir /tmp/ci_out

    # Reduced-fetch run for local development:
    python3 acceleration/scripts/extract_ci_tests.py --max-runs 25

Integration with the pipeline
-----------------------------

- Runs after ``extract_github.py``. Workflow IDs are independently
  resolved here, so the ordering is purely for log readability; the
  extractor does not consume any output produced by
  ``extract_github.py``.
- Output consumed by ``compute_metrics.py`` for Metric 11
  (Escaped Defects).
- ``test_results_access.json`` is read by ``compute_metrics.py`` to
  decide between computing the metric and reporting
  ``Insufficient signal — CI test history unavailable``.

See also
--------

- :mod:`acceleration.observability.logger` — structured JSON logger
  (Rule 1 Observability).
- :mod:`acceleration.scripts.extract_github` — sibling extractor that
  shares the ``GithubClient`` shape.
- :mod:`acceleration.scripts.compute_metrics` — downstream consumer.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator

# ---------------------------------------------------------------------------
# Public constants
# ---------------------------------------------------------------------------
# Module-level constants are part of the public surface (see ``__all__``)
# so test harnesses and downstream consumers can reference them without
# duplication. Type annotations are deliberately spelled out so the
# constants serve as a contract document in addition to runtime values.

# Base URL for the GitHub REST API. Overridable via ``--api-base`` /
# ``GITHUB_API`` for GitHub Enterprise Server installs (e.g.
# ``https://github.example.com/api/v3``).
GITHUB_API_BASE: str = "https://api.github.com"

# User-Agent string sent on every request. GitHub's API documentation
# requires every request to identify itself. Sharing the same User-Agent
# across the extractors keeps the rate-limit envelope consolidated and
# makes the pipeline easy to identify in server-side audit logs.
USER_AGENT: str = "acceleration-analysis-pipeline/1.0"

# Workflow filenames of interest. Resolved to numeric workflow IDs at
# runtime via :func:`list_target_workflow_ids` because the
# ``/actions/workflows/{id}/runs`` endpoint requires the numeric ID rather
# than the filename. The tuple is the authoritative source-of-truth for
# Metric 11 — adding a workflow here transparently widens the extractor's
# scope.
TARGET_WORKFLOW_FILENAMES: tuple[str, ...] = ("test.yml", "e2e.yml", "chromatic.yml")

# Page size for paginated GitHub list endpoints. ``100`` is the
# GitHub-imposed maximum; using anything smaller wastes API quota.
PAGE_SIZE: int = 100

# Safety cap on the number of workflow runs visited per workflow.
# Sized to comfortably exceed the Formbricks history while remaining
# tight enough to keep an unauthenticated mis-configured run cheap.
# Overridable per-invocation via ``--max-runs``.
MAX_RUNS_PER_WORKFLOW: int = 600

# Hard cap on the size (bytes) of any single artifact we will accept.
# Larger artifacts are skipped to keep the in-memory ZIP unpacking
# bounded and to avoid disrupting the run on a maintainer who uploaded
# a stray multi-GB blob alongside the JUnit XML. 50 MiB is well above
# the largest test-report artifact observed in OSS Next.js monorepos.
MAX_ARTIFACT_BYTES: int = 50 * 1024 * 1024  # 50 MiB

# Upper bound on HTTP requests issued by a single invocation. Sized for
# ``MAX_RUNS_PER_WORKFLOW`` × len(``TARGET_WORKFLOW_FILENAMES``) × small
# constant for artifact listing/download, plus headroom for workflow
# listing pagination.
MAX_REQUESTS_PER_RUN: int = 1500

# Retry policy for transient HTTP failures (review feedback: "Add bounded
# retries with backoff around workflow run/artifact ZIP requests and
# record failures in test_results_access.json."). Same shape as the
# sibling :mod:`acceleration.scripts.extract_github` policy.
HTTP_MAX_RETRIES: int = 3
HTTP_RETRY_BACKOFF_BASE: float = 2.0
HTTP_RETRYABLE_STATUS: frozenset[int] = frozenset({500, 502, 503, 504})

# Regular-expression patterns identifying JUnit-shaped XML files inside a
# downloaded artifact ZIP. All three conventional names are covered:
#
# - ``junit.xml`` / ``junit-results.xml`` / ``junit-vitest.xml``
#   (Vitest, Jest, Karma defaults).
# - ``test-results.xml`` / ``unit-test-results.xml`` (Playwright,
#   pytest, Maven Surefire).
# - ``results.xml`` (legacy Surefire / xUnit conventions).
#
# Patterns are case-insensitive because some CI configurations
# capitalise the filename (e.g. ``JUnit.xml``) and because the
# JUnit/Surefire conventions are case-insensitive on Windows where the
# producer may run.
JUNIT_FILENAME_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"junit.*\.xml$", re.IGNORECASE),
    re.compile(r".*test-results?\.xml$", re.IGNORECASE),
    re.compile(r"^results?\.xml$", re.IGNORECASE),
)



# ---------------------------------------------------------------------------
# HTTP client (stdlib-only GET, with rate-limit and pagination awareness)
# ---------------------------------------------------------------------------


@dataclass
class GithubClient:
    """Minimal GitHub REST client built from :mod:`urllib.request`.

    Shares its shape with the sibling :class:`acceleration.scripts.
    extract_github.GithubClient` so engineers familiar with one
    extractor can reason about the other. The difference is twofold:
    this client supports a ``raw=True`` mode on :meth:`get` for binary
    payloads (artifact ZIP downloads) and uses a 60-second timeout to
    accommodate the larger transfer sizes typical of test-report
    archives.

    The client is **GET-only**. There is no method that issues
    ``POST`` / ``PUT`` / ``PATCH`` / ``DELETE``, satisfying AAP §0.7.2.1
    read-only operations and AAP §0.8.7 process-specific constraints.

    Attributes
    ----------
    token : str or None
        Personal Access Token, fine-grained PAT, GitHub App installation
        token, or ``None`` for unauthenticated calls. Unauthenticated
        calls to the Actions API are subject to GitHub's 60/hour limit
        and return ``403`` almost immediately on a real repository, so
        :func:`main` short-circuits to the graceful-degradation path
        when ``GITHUB_TOKEN`` is absent.
    request_count : int
        Number of HTTP requests issued so far in this run. Incremented
        by :meth:`get`. Capped by :data:`MAX_REQUESTS_PER_RUN` to avoid
        pathological pagination loops.
    api_base : str
        REST API base URL (no trailing slash). Default
        :data:`GITHUB_API_BASE`. Overridable for GitHub Enterprise
        Server installs.
    last_status : int
        HTTP status code returned by the most recent :meth:`get` call.
        Initialised to ``0``. Used by callers to disambiguate "endpoint
        returned 0 results" (success, status 200/404) from "endpoint
        was unreachable" (timeout, DNS, 5xx).
    """

    token: str | None
    request_count: int = 0
    api_base: str = GITHUB_API_BASE
    last_status: int = 0
    # Retry / reliability counters per the review feedback. Recorded
    # in ``test_results_access.json`` so operators can audit whether
    # transient failures degraded Metric 11 (Escaped Defects).
    retry_attempts: int = 0
    retry_recoveries: int = 0
    retry_failures: int = 0

    def headers(self) -> dict[str, str]:
        """Compose the request headers for a GitHub REST API call.

        Always includes the conventional ``Accept`` and ``User-Agent``
        headers plus the API version pin
        (``X-GitHub-Api-Version: 2022-11-28``). When :attr:`token` is
        non-empty, a ``Bearer`` ``Authorization`` header is added;
        otherwise the call is unauthenticated.

        Returns
        -------
        dict[str, str]
            Header name → header value mapping ready for
            :class:`urllib.request.Request`. A fresh dict per call so
            callers can safely mutate the result.
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
        raw: bool = False,
        max_retries: int | None = None,
        retry_backoff_base: float | None = None,
    ) -> tuple[int, Any, dict[str, str]]:
        """Issue a single HTTP ``GET`` to the supplied URL with bounded retries.

        Retry policy mirrors
        :meth:`acceleration.scripts.extract_github.GithubClient.get`:
        retry on 5xx (500, 502, 503, 504), :class:`urllib.error.URLError`,
        :class:`TimeoutError`, and other transient :class:`OSError`
        instances (e.g. :class:`ConnectionResetError`,
        :class:`BrokenPipeError`). 4xx are NOT retried (deterministic);
        429 is NOT retried at this layer (the upstream rate-limit handler
        is the correct response).

        Parameters
        ----------
        url : str
            Absolute URL to fetch.
        params : dict[str, Any] or None
            Optional query parameters to URL-encode and append to
            ``url``. When supplied, ``url`` is rewritten to
            ``f"{url}?{urlencode(params)}"``. Pass ``None`` when the
            URL already carries its query string.
        raw : bool, keyword-only
            When ``True``, the response body is returned as raw
            ``bytes`` (for artifact ZIP downloads). When ``False`` (the
            default), the body is decoded as UTF-8 and parsed as JSON
            when possible.
        max_retries : int or None
            Maximum number of retry attempts (in addition to the
            initial attempt). Defaults to :data:`HTTP_MAX_RETRIES`.
            Pass ``0`` to disable retries.
        retry_backoff_base : float or None
            Backoff base in seconds. Defaults to
            :data:`HTTP_RETRY_BACKOFF_BASE`. The nth retry sleeps for
            ``retry_backoff_base * 2**(n-1)`` seconds.

        Returns
        -------
        tuple[int, Any, dict[str, str]]
            ``(status_code, body, headers)``. ``body`` is ``bytes`` when
            ``raw=True``, otherwise parsed JSON if the response decoded
            cleanly or a raw UTF-8 string if not. ``headers`` has
            lower-cased keys for case-insensitive lookup. On a
            network-level failure ``(0, error_string, {})`` is returned;
            the caller treats status ``0`` as "endpoint not reachable".

        Raises
        ------
        RuntimeError
            When :attr:`request_count` has already reached
            :data:`MAX_REQUESTS_PER_RUN`. This fail-fast guard prevents
            pathological pagination loops from exhausting an API quota.
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
                # 60-second timeout for artifact ZIP downloads; small
                # JSON responses return long before the cap.
                with urllib.request.urlopen(req, timeout=60) as resp:
                    self.last_status = resp.status
                    hdrs = {k.lower(): v for k, v in resp.headers.items()}
                    if retried_at_least_once:
                        self.retry_recoveries += 1
                    if raw:
                        return resp.status, resp.read(), hdrs
                    body = resp.read().decode("utf-8", errors="replace")
                    try:
                        return resp.status, json.loads(body), hdrs
                    except json.JSONDecodeError:
                        return resp.status, body, hdrs
            except urllib.error.HTTPError as exc:
                self.last_status = exc.code
                data = exc.read() if exc.fp else b""
                hdrs = {
                    k.lower(): v for k, v in (exc.headers or {}).items()
                }
                if exc.code in HTTP_RETRYABLE_STATUS and attempt < retries:
                    self.retry_attempts += 1
                    retried_at_least_once = True
                    time.sleep(backoff_base * (2 ** attempt))
                    continue
                if retried_at_least_once:
                    if exc.code in HTTP_RETRYABLE_STATUS:
                        self.retry_failures += 1
                    else:
                        self.retry_recoveries += 1
                if raw:
                    return exc.code, data, hdrs
                text = data.decode("utf-8", errors="replace")
                try:
                    return exc.code, json.loads(text), hdrs
                except (json.JSONDecodeError, ValueError):
                    return exc.code, text, hdrs
            except urllib.error.URLError as exc:
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
                self.last_status = 0
                if attempt < retries:
                    self.retry_attempts += 1
                    retried_at_least_once = True
                    time.sleep(backoff_base * (2 ** attempt))
                    continue
                if retried_at_least_once:
                    self.retry_failures += 1
                return 0, str(exc), {}
        # Defensive fallback: only reachable if ``retries`` were
        # negative, which the clamp prevents.
        return 0, "retry loop fell through", {}

    def respect_rate_limit(self, hdrs: dict[str, str]) -> None:
        """Sleep, if necessary, to respect the primary GitHub rate limit.

        When the most recent response indicates ``≤ 2`` remaining
        requests before the reset (``x-ratelimit-remaining`` header),
        the caller is paused until ``x-ratelimit-reset`` + 2 seconds.
        The sleep is clamped to a minimum of 5 seconds (avoiding tight
        retry loops on unsynchronised clocks) and a maximum of 120
        seconds (avoiding accidentally pausing forever on a
        misformatted reset timestamp).

        Parameters
        ----------
        hdrs : dict[str, str]
            Response headers from the most recent :meth:`get`. Keys
            are expected to be lower-cased (which :meth:`get` does
            automatically).
        """

        remaining = hdrs.get("x-ratelimit-remaining")
        reset = hdrs.get("x-ratelimit-reset")
        if remaining and reset:
            try:
                if int(remaining) <= 2:
                    # Sleep until 2 seconds past the reset epoch, but
                    # never less than 5 seconds (clock-skew safety) and
                    # never more than 120 seconds (pathological-header
                    # safety).
                    sleep_for = min(
                        max(5, int(reset) - int(time.time()) + 2),
                        120,
                    )
                    time.sleep(sleep_for)
            except ValueError:
                # If either header is unparseable, do not block the run.
                return


# ---------------------------------------------------------------------------
# Workflow / run / artifact discovery
# ---------------------------------------------------------------------------


def list_target_workflow_ids(
    client: GithubClient,
    owner: str,
    repo: str,
) -> dict[str, int]:
    """Return ``{workflow_file_name: workflow_id}`` for each target match.

    Paginates ``GET /repos/{owner}/{repo}/actions/workflows`` until
    exhausted and harvests the numeric workflow IDs for every entry
    whose ``path`` ends with one of :data:`TARGET_WORKFLOW_FILENAMES`.
    Stops on the first non-200 status so partial discovery still drives
    later phases.

    Parameters
    ----------
    client : GithubClient
        Configured HTTP client.
    owner : str
        Repository owner (user or organisation slug).
    repo : str
        Repository name.

    Returns
    -------
    dict[str, int]
        Mapping of workflow filename to numeric workflow ID. Workflows
        absent from the repository are omitted from the result; callers
        skip them gracefully (see :func:`main`).

    Notes
    -----
    The endpoint returns workflows in stable creation order, but no
    documented sort guarantee is relied upon. A workflow's ``path``
    looks like ``".github/workflows/test.yml"`` — the suffix match
    against ``f"/{fname}"`` avoids false positives for nested
    workflows in custom locations (e.g. ``services/foo/test.yml``).
    """

    out: dict[str, int] = {}
    url = f"{client.api_base}/repos/{owner}/{repo}/actions/workflows"
    page = 1
    while True:
        status, data, hdrs = client.get(
            url,
            params={"per_page": PAGE_SIZE, "page": page},
        )
        client.respect_rate_limit(hdrs)
        if status != 200 or not isinstance(data, dict):
            # Either an authorisation failure (401/403), a transient
            # error, or an unexpected payload shape. Stop the
            # pagination loop and let the caller treat the result as
            # whatever has been collected so far (typically empty).
            break
        workflows = data.get("workflows") or []
        for workflow in workflows:
            path = workflow.get("path", "") or ""
            workflow_id = workflow.get("id")
            if workflow_id is None:
                continue
            for fname in TARGET_WORKFLOW_FILENAMES:
                # Suffix match against ``/{fname}`` so we accept
                # ``.github/workflows/test.yml`` but not
                # ``services/foo/legacy-test.yml``.
                if path.endswith(f"/{fname}"):
                    out[fname] = int(workflow_id)
        # GitHub pages 1-indexed; a partial page indicates the last
        # page so we exit before issuing a wasted extra request.
        if len(workflows) < PAGE_SIZE:
            break
        page += 1
    return out


def list_workflow_runs(
    client: GithubClient,
    owner: str,
    repo: str,
    workflow_id: int,
    *,
    max_runs: int | None = None,
) -> Iterator[dict[str, Any]]:
    """Yield workflow runs on ``branch=main`` filtered to completed status.

    Iterates ``GET /repos/{owner}/{repo}/actions/workflows/{workflow_id}/runs``
    pages until either the API exhausts the result set, the
    ``max_runs`` cap is reached, or a non-200 status is observed.

    The ``branch=main`` filter excludes pull-request and feature-branch
    runs (per AAP §0.3.4 Escaped Defects: transitions are tracked on
    ``main`` only). The ``status=completed`` filter excludes still-running
    or queued executions so the per-test outcome is final.

    Parameters
    ----------
    client : GithubClient
        Configured HTTP client.
    owner : str
        Repository owner.
    repo : str
        Repository name.
    workflow_id : int
        Numeric workflow ID returned by :func:`list_target_workflow_ids`.
    max_runs : int or None, keyword-only
        Override the module-level :data:`MAX_RUNS_PER_WORKFLOW` cap for
        a single call. ``None`` (default) uses the module-level value.
        Pass a lower number for fast local development; pass ``None``
        for production runs.

    Yields
    ------
    dict[str, Any]
        Raw workflow-run record from the GitHub API. Includes ``id``,
        ``head_sha``, ``created_at``, ``status``, ``conclusion``,
        ``head_branch``, ``run_number``, etc.

    Notes
    -----
    Default ordering is descending by ``created_at`` (newest first),
    which is the GitHub API default for this endpoint. Callers that
    need chronological ordering for transition detection should sort
    the yielded records by ``created_at`` after collection.
    """

    cap = MAX_RUNS_PER_WORKFLOW if max_runs is None else max(1, max_runs)
    url = (
        f"{client.api_base}/repos/{owner}/{repo}/actions/workflows/"
        f"{workflow_id}/runs"
    )
    page = 1
    yielded = 0
    while yielded < cap:
        status, data, hdrs = client.get(
            url,
            params={
                "per_page": PAGE_SIZE,
                "page": page,
                "branch": "main",
                "status": "completed",
            },
        )
        client.respect_rate_limit(hdrs)
        if status != 200 or not isinstance(data, dict):
            break
        runs = data.get("workflow_runs") or []
        if not runs:
            break
        for run in runs:
            yield run
            yielded += 1
            if yielded >= cap:
                break
        # Partial page implies the API has returned everything it has.
        if len(runs) < PAGE_SIZE:
            break
        page += 1


def list_run_artifacts(
    client: GithubClient,
    owner: str,
    repo: str,
    run_id: int,
) -> list[dict[str, Any]]:
    """List every artifact attached to a workflow run.

    Paginates ``GET /repos/{owner}/{repo}/actions/runs/{run_id}/artifacts``.
    Each artifact carries ``id``, ``name``, ``size_in_bytes``,
    ``archive_download_url``, ``expired``, ``created_at``,
    ``updated_at``. The ``expired`` field is checked by the caller
    before attempting the download.

    Parameters
    ----------
    client : GithubClient
        Configured HTTP client.
    owner : str
        Repository owner.
    repo : str
        Repository name.
    run_id : int
        Numeric workflow-run ID.

    Returns
    -------
    list[dict[str, Any]]
        All artifact records for the run; empty when the run has no
        artifacts or when the endpoint returned a non-200 response.

    Notes
    -----
    GitHub artifact retention defaults to 90 days. Runs older than the
    retention window list artifacts with ``expired: true``; downloads
    of expired artifacts return ``410 Gone`` which the caller treats
    as a soft skip (see :func:`extract_for_workflow`).
    """

    url = (
        f"{client.api_base}/repos/{owner}/{repo}/actions/runs/"
        f"{run_id}/artifacts"
    )
    artifacts: list[dict[str, Any]] = []
    page = 1
    while True:
        status, data, hdrs = client.get(
            url,
            params={"per_page": PAGE_SIZE, "page": page},
        )
        client.respect_rate_limit(hdrs)
        if status != 200 or not isinstance(data, dict):
            break
        page_artifacts = data.get("artifacts") or []
        artifacts.extend(page_artifacts)
        if len(page_artifacts) < PAGE_SIZE:
            break
        page += 1
    return artifacts


def download_artifact_zip(
    client: GithubClient,
    owner: str,
    repo: str,
    artifact_id: int,
) -> bytes | None:
    """Download an artifact archive as raw ZIP bytes.

    Calls ``GET /repos/{owner}/{repo}/actions/artifacts/{artifact_id}/zip``
    with ``raw=True`` so the response body is returned as ``bytes`` for
    in-memory ZIP unpacking. Respects :data:`MAX_ARTIFACT_BYTES` —
    artifacts larger than the cap are discarded to keep the unpacking
    bounded.

    Parameters
    ----------
    client : GithubClient
        Configured HTTP client.
    owner : str
        Repository owner.
    repo : str
        Repository name.
    artifact_id : int
        Numeric artifact ID returned by :func:`list_run_artifacts`.

    Returns
    -------
    bytes or None
        ZIP archive bytes, or ``None`` when the artifact is unavailable
        (non-200 response, non-bytes body, expired artifact, or oversize).

    Notes
    -----
    The endpoint emits a ``302`` redirect to a signed S3-backed URL.
    :mod:`urllib.request` follows redirects transparently and the
    bearer ``Authorization`` header is stripped by ``urllib`` on the
    cross-origin redirect (the signed URL carries its own authn),
    matching the documented GitHub behaviour.
    """

    url = (
        f"{client.api_base}/repos/{owner}/{repo}/actions/artifacts/"
        f"{artifact_id}/zip"
    )
    status, body, _hdrs = client.get(url, raw=True)
    if status != 200:
        return None
    if not isinstance(body, (bytes, bytearray)):
        return None
    if len(body) > MAX_ARTIFACT_BYTES:
        return None
    return bytes(body)



# ---------------------------------------------------------------------------
# JUnit XML parsing
# ---------------------------------------------------------------------------


def is_junit_filename(name: str) -> bool:
    """Return ``True`` when ``name`` matches a JUnit-shaped XML convention.

    Used by :func:`extract_junit_from_zip` to filter artifact contents
    down to candidate test-report files. Matching is delegated to
    :data:`JUNIT_FILENAME_PATTERNS`; the function searches each pattern
    (``re.search``) so a basename match wins regardless of any
    directory prefix introduced by the artifact producer
    (e.g. ``reports/junit.xml``).

    Parameters
    ----------
    name : str
        ZIP member filename as exposed by :class:`zipfile.ZipInfo.filename`.

    Returns
    -------
    bool
        ``True`` when at least one pattern in
        :data:`JUNIT_FILENAME_PATTERNS` matches.
    """

    if not name:
        return False
    return any(pattern.search(name) for pattern in JUNIT_FILENAME_PATTERNS)


def parse_junit_xml(content: bytes) -> list[dict[str, Any]]:
    """Parse a JUnit XML document into per-test records.

    Handles both top-level shapes observed in OSS Next.js monorepos:

    1. ``<testsuites>`` root containing one or more ``<testsuite>`` elements
       (Vitest, Jest, pytest default).
    2. ``<testsuite>`` root (legacy Surefire / xUnit; sometimes emitted
       by Karma).

    For each ``<testcase>`` element the function emits one record with
    a stable ``test_id`` (``"{classname}::{name}"``) used by
    ``compute_metrics.py`` to detect per-test transitions across runs.

    The function is total: malformed XML returns an empty list rather
    than raising, so the caller can keep moving across artifacts.

    Parameters
    ----------
    content : bytes
        XML bytes as read from a ZIP member. Encoding is honoured by
        :func:`xml.etree.ElementTree.fromstring` via the XML declaration.

    Returns
    -------
    list[dict[str, Any]]
        Per-test records. Each record carries:

        - ``classname`` — JUnit ``classname`` attribute (falls back to
          the parent ``<testsuite>`` ``name``).
        - ``name`` — JUnit ``name`` attribute on the ``<testcase>``.
        - ``test_id`` — ``"{classname}::{name}"`` stable identifier.
        - ``status`` — one of ``passed`` / ``failed`` / ``errored`` /
          ``skipped``.
        - ``time_seconds`` — execution time in seconds when present
          and parseable, else ``None``.
        - ``message`` — failure / error message truncated to 500
          characters, else ``None``.

    Notes
    -----
    Status precedence: ``failed`` (``<failure>``) beats ``errored``
    (``<error>``) which beats ``skipped`` (``<skipped>``) which beats
    the default ``passed``. The last-write-wins behaviour of the loop
    realises this precedence since the JUnit schema does not mandate
    a fixed child ordering.

    Namespace handling: XML namespaces are stripped by splitting the
    tag on ``"}"`` and taking the local-name suffix, which tolerates
    namespace-decorated producers (e.g. ``{junit}testcase``).
    """

    out: list[dict[str, Any]] = []
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        # Malformed XML — the artifact may have been truncated during
        # upload or written by an incompatible producer. The caller
        # continues with the next artifact.
        return out
    except (ValueError, TypeError):
        # Defensive: ET.fromstring usually only raises ParseError, but
        # some implementations raise ValueError on empty inputs.
        return out

    # Resolve the suite list. Handle both the documented
    # ``<testsuites>`` and ``<testsuite>`` roots, and one defensive
    # fallback: a non-conforming root whose grandchildren contain
    # ``<testsuite>`` (some Karma reporters wrap with custom roots).
    root_tag = root.tag.split("}")[-1]
    suites: list[ET.Element]
    if root_tag == "testsuites":
        suites = list(root.findall(".//testsuite"))
    elif root_tag == "testsuite":
        suites = [root]
    else:
        suites = list(root.findall(".//testsuite"))

    for suite in suites:
        suite_name = suite.attrib.get("name") or ""
        for case in suite.findall("testcase"):
            # ``classname`` is preferred but JUnit allows it to be
            # absent for parameterised tests; fall back to the parent
            # suite name so the ``test_id`` remains stable across runs.
            classname = case.attrib.get("classname") or suite_name
            name = case.attrib.get("name") or ""
            time_raw = case.attrib.get("time")
            try:
                time_seconds = float(time_raw) if time_raw else None
            except (ValueError, TypeError):
                time_seconds = None

            # Default outcome is ``passed``; a ``<failure>``,
            # ``<error>``, or ``<skipped>`` child upgrades it. Status
            # precedence is realised by the iteration order — the
            # last-encountered child wins, matching the JUnit schema's
            # implicit precedence (a test cannot be both failed and
            # skipped).
            status = "passed"
            message: str | None = None
            for child in case:
                # Strip XML namespace prefixes if present, e.g.
                # ``{junit}failure`` → ``failure``.
                tag = child.tag.split("}")[-1]
                if tag == "failure":
                    status = "failed"
                    raw_message = child.attrib.get("message") or ""
                    message = raw_message[:500] if raw_message else None
                elif tag == "error":
                    status = "errored"
                    raw_message = child.attrib.get("message") or ""
                    message = raw_message[:500] if raw_message else None
                elif tag == "skipped":
                    status = "skipped"

            out.append(
                {
                    "classname": classname,
                    "name": name,
                    "test_id": f"{classname}::{name}",
                    "status": status,
                    "time_seconds": time_seconds,
                    "message": message,
                }
            )
    return out


def extract_junit_from_zip(zip_bytes: bytes) -> list[dict[str, Any]]:
    """Open an artifact ZIP in memory and extract every JUnit-shaped record.

    The ZIP is opened from an :class:`io.BytesIO` wrapper so no
    temporary files are written to disk (Phase 9 Read-Only Discipline
    of the agent prompt). Every member is filtered through
    :func:`is_junit_filename`; the contents of matching members are
    decoded and dispatched to :func:`parse_junit_xml`.

    Parameters
    ----------
    zip_bytes : bytes
        Raw ZIP archive returned by :func:`download_artifact_zip`.

    Returns
    -------
    list[dict[str, Any]]
        Concatenation of every JUnit ``<testcase>`` record found in
        every JUnit-shaped XML member of the archive. Empty when the
        ZIP is corrupt, empty, or contains no JUnit-shaped files.

    Notes
    -----
    The function is total: ZIP-level errors
    (:class:`zipfile.BadZipFile`) and member-level read errors are
    swallowed and the loop continues. This satisfies AAP §0.3.4
    graceful degradation: a single bad artifact does not abort the
    run.

    Memory bound: :data:`MAX_ARTIFACT_BYTES` caps the input size, so
    the maximum in-flight memory is bounded by that constant.
    """

    records: list[dict[str, Any]] = []
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
            for info in archive.infolist():
                # ``is_dir`` returns True for directory entries; we
                # only care about file members.
                if info.is_dir():
                    continue
                if not is_junit_filename(info.filename):
                    continue
                try:
                    with archive.open(info) as fhandle:
                        data = fhandle.read()
                except (zipfile.BadZipFile, OSError, RuntimeError):
                    # Individual member-level errors should not abort
                    # the loop. ``RuntimeError`` covers encrypted ZIPs
                    # which the stdlib can iterate but not read without
                    # a password.
                    continue
                records.extend(parse_junit_xml(data))
    except zipfile.BadZipFile:
        # The archive itself is corrupt or truncated. Return whatever
        # records we collected before the failure (typically empty).
        return records
    except OSError:
        # Defensive: BytesIO doesn't raise OSError under normal use,
        # but a sufficiently broken payload could.
        return records
    return records



# ---------------------------------------------------------------------------
# Per-workflow extraction loop
# ---------------------------------------------------------------------------


def extract_for_workflow(
    client: GithubClient,
    owner: str,
    repo: str,
    workflow_name: str,
    workflow_id: int,
    log: Any,
    *,
    max_runs: int | None = None,
) -> tuple[list[dict[str, Any]], int, int]:
    """Visit every recent run of a workflow and collect JUnit test records.

    For each run yielded by :func:`list_workflow_runs`:

    1. Enumerate its artifacts via :func:`list_run_artifacts`.
    2. Skip expired artifacts (the API exposes an ``expired: True``
       field after retention expires).
    3. Download each non-expired artifact via
       :func:`download_artifact_zip` (subject to
       :data:`MAX_ARTIFACT_BYTES`).
    4. Extract every JUnit-shaped XML inside via
       :func:`extract_junit_from_zip`.
    5. Tag each parsed case with the run-level provenance (``run_id``,
       ``head_sha``, ``created_at``, ``artifact_id``, ``artifact_name``)
       and append to ``records``.

    Parameters
    ----------
    client : GithubClient
        Configured HTTP client.
    owner : str
        Repository owner.
    repo : str
        Repository name.
    workflow_name : str
        Workflow filename — one of :data:`TARGET_WORKFLOW_FILENAMES`.
        Embedded into each record so downstream consumers can filter
        by workflow.
    workflow_id : int
        Numeric workflow ID resolved by
        :func:`list_target_workflow_ids`.
    log : Any
        Structured logger (or stdlib logging logger as a fallback).
        ``Any`` because the script is invocable with either the
        :mod:`acceleration.observability.logger` JSON logger or the
        stdlib logger.
    max_runs : int or None, keyword-only
        Override the :data:`MAX_RUNS_PER_WORKFLOW` cap for testing.
        ``None`` (default) uses the module-level value.

    Returns
    -------
    tuple[list[dict[str, Any]], int, int]
        Three-tuple of:

        - ``records`` — per-(run, test) entries ready to be written to
          ``test_results.jsonl``.
        - ``runs_seen`` — number of completed runs visited (helps
          populate the access manifest's ``runs_seen`` count).
        - ``runs_with_artifacts`` — number of runs from which at
          least one JUnit-shaped record was parsed. The ratio
          ``runs_with_artifacts / runs_seen`` is the boundary
          condition for Metric 11 confidence.

    Notes
    -----
    The function never raises out — every per-run error is captured
    and logged, the loop continues with the next run, and partial
    results survive. This satisfies AAP §0.3.4 graceful degradation.
    """

    records: list[dict[str, Any]] = []
    runs_seen = 0
    runs_with_artifacts = 0

    runs_iter = list_workflow_runs(
        client, owner, repo, workflow_id, max_runs=max_runs
    )
    for run in runs_iter:
        runs_seen += 1
        run_id = run.get("id")
        head_sha = run.get("head_sha")
        created_at = run.get("created_at")
        if run_id is None:
            # Defensive: a run record with no ID is unusable.
            continue
        try:
            run_id_int = int(run_id)
        except (TypeError, ValueError):
            continue

        # Step 1: list artifacts.
        try:
            artifacts = list_run_artifacts(client, owner, repo, run_id_int)
        except RuntimeError:
            # Hit the MAX_REQUESTS_PER_RUN ceiling — surface to the
            # caller so the access manifest reflects the truncation.
            raise
        except Exception as exc:  # noqa: BLE001 - graceful degradation
            log.warning(
                "Artifact listing failed for run %s: %s: %s",
                run_id_int,
                type(exc).__name__,
                exc,
            )
            continue

        had_artifact = False
        for art in artifacts:
            # Skip expired artifacts (retention window passed).
            if art.get("expired"):
                continue
            artifact_id_raw = art.get("id")
            if artifact_id_raw is None:
                continue
            try:
                artifact_id = int(artifact_id_raw)
            except (TypeError, ValueError):
                continue

            # Step 2: download and unpack.
            try:
                zip_bytes = download_artifact_zip(
                    client, owner, repo, artifact_id
                )
            except RuntimeError:
                # Request-cap exceeded; propagate.
                raise
            except Exception as exc:  # noqa: BLE001 - graceful degradation
                log.warning(
                    "Artifact download failed for run %s artifact %s: %s: %s",
                    run_id_int,
                    artifact_id,
                    type(exc).__name__,
                    exc,
                )
                continue
            if zip_bytes is None:
                continue

            # Step 3: parse JUnit XML members.
            cases = extract_junit_from_zip(zip_bytes)
            if not cases:
                continue

            had_artifact = True
            artifact_name = art.get("name")
            for case in cases:
                # Each record gets run-level provenance plus the
                # per-test fields from :func:`parse_junit_xml`. The
                # field order is stable so ``compute_metrics.py`` can
                # rely on the schema without per-record introspection.
                records.append(
                    {
                        "workflow": workflow_name,
                        "workflow_id": workflow_id,
                        "run_id": run_id_int,
                        "head_sha": head_sha,
                        "created_at": created_at,
                        "artifact_id": artifact_id,
                        "artifact_name": artifact_name,
                        "test_id": case["test_id"],
                        "classname": case["classname"],
                        "name": case["name"],
                        "status": case["status"],
                        "time_seconds": case["time_seconds"],
                        "message": case["message"],
                    }
                )
        if had_artifact:
            runs_with_artifacts += 1
        # Per-run debug logging helps diagnose unexpected gaps in
        # the test-results stream during local development.
        log.debug(
            "workflow=%s run=%s artifacts=%d records_total=%d",
            workflow_name,
            run_id_int,
            len(artifacts),
            len(records),
        )
    return records, runs_seen, runs_with_artifacts


def _write_jsonl_lines(
    path: Path,
    records: Iterable[dict[str, Any]],
) -> int:
    """Write an iterable of records as one JSON line each.

    Helper used by :func:`main` to keep the orchestration
    straightforward. Records are serialised with
    ``ensure_ascii=False`` (so non-ASCII test names round-trip cleanly)
    and ``default=str`` (so any stray non-JSON-native value falls back
    to its string representation rather than raising).

    Parameters
    ----------
    path : Path
        Output path. The parent directory is assumed to exist; the
        caller (typically :func:`main`) takes care of
        ``mkdir(parents=True, exist_ok=True)``.
    records : Iterable[dict[str, Any]]
        Records to write. Any iterable shape is accepted so the
        caller can stream from a generator without materialising the
        list in memory.

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



# ---------------------------------------------------------------------------
# CLI argument parsing
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments.

    All flags carry environment-variable defaults so the script slots
    cleanly into the orchestrator without explicit per-call wiring. The
    ``--owner`` / ``--repo`` / ``--api-base`` defaults match
    ``acceleration.scripts.extract_github.parse_args`` so a single
    ``REPO_OWNER`` / ``REPO_NAME`` / ``GITHUB_API`` configuration drives
    every extractor identically.

    Parameters
    ----------
    argv : list[str] or None
        Argument vector excluding the program name. ``None`` (the
        default) instructs :mod:`argparse` to consume :data:`sys.argv`.

    Returns
    -------
    argparse.Namespace
        Parsed namespace with attributes ``owner``, ``repo``,
        ``output_dir``, ``api_base``, ``skip_network``, ``max_runs``.
    """

    parser = argparse.ArgumentParser(
        prog="extract_ci_tests",
        description=(
            "Download GitHub Actions JUnit artifacts for test.yml, "
            "e2e.yml, and chromatic.yml on `main` and emit per-(run, test) "
            "records to acceleration/data/test_results.jsonl. HTTP GET only; "
            "read-only per AAP §0.7.2.1."
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
        help=(
            "Directory under which test_results.jsonl and "
            "test_results_access.json are written. Created if missing."
        ),
    )
    parser.add_argument(
        "--api-base",
        default=os.environ.get("GITHUB_API", GITHUB_API_BASE),
        help=(
            "Override the GitHub API base URL (for GitHub Enterprise "
            f"Server). Default: $GITHUB_API or {GITHUB_API_BASE!r}."
        ),
    )
    parser.add_argument(
        "--skip-network",
        action="store_true",
        help=(
            "Do not call the GitHub Actions API. Touches "
            "test_results.jsonl (empty) and writes a "
            "test_results_access.json with available=false. Useful for "
            "offline smoke tests."
        ),
    )
    parser.add_argument(
        "--max-runs",
        type=int,
        default=MAX_RUNS_PER_WORKFLOW,
        help=(
            "Override the MAX_RUNS_PER_WORKFLOW cap for this invocation "
            "(default: %(default)d). Lower values speed up local "
            "development; production runs should leave the default."
        ),
    )
    return parser.parse_args(argv)


# ---------------------------------------------------------------------------
# Main entrypoint
# ---------------------------------------------------------------------------


def _build_unavailable_manifest(reason: str) -> dict[str, Any]:
    """Construct the ``test_results_access.json`` payload for failure paths.

    Centralises the structure so the ``--skip-network`` path and the
    "no JUnit artifacts found" path produce manifests with the same
    shape, easing the downstream contract in
    ``compute_metrics.py``.

    Parameters
    ----------
    reason : str
        Short human-readable explanation. Copied into the
        Insufficient-Signal caveat in the report.

    Returns
    -------
    dict[str, Any]
        Manifest payload ready for :func:`json.dumps`.
    """

    return {
        "available": False,
        "reason": reason,
        "tried": list(TARGET_WORKFLOW_FILENAMES),
        "needed": (
            "GITHUB_TOKEN with actions:read scope on the repository AND "
            "JUnit-shaped XML artifacts (junit*.xml, *test-results.xml, "
            "or results.xml) uploaded by the target workflows."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    """Run the CI test-artifact extractor end-to-end.

    Steps:

    1. Parse CLI arguments.
    2. Initialise the structured JSON logger (with a stdlib-logging
       fallback per AAP Rule 1).
    3. If ``--skip-network`` or no token, touch outputs with an
       unavailable manifest and exit 0.
    4. Resolve numeric workflow IDs for each target filename via
       :func:`list_target_workflow_ids`.
    5. For each resolved workflow, visit recent runs and extract
       JUnit-shaped records via :func:`extract_for_workflow`. Each
       per-workflow error is captured into the manifest rather than
       aborting the run.
    6. Write the consolidated ``test_results.jsonl`` and a populated
       ``test_results_access.json`` documenting what was retrieved.

    Parameters
    ----------
    argv : list[str] or None
        Argument vector excluding the program name. ``None`` defers
        to :data:`sys.argv`.

    Returns
    -------
    int
        Exit code. Always ``0`` — every error path is captured into
        the manifest as an inaccessibility record. Downstream
        consumers decide what to do with that, not the extractor.
    """

    args = parse_args(argv)

    # Configure the structured JSON logger if the module is importable;
    # otherwise fall back to stdlib logging so the operator still sees
    # output even on a broken install (graceful degradation per AAP
    # Observability Rule 1).
    try:
        # The script lives at acceleration/scripts/extract_ci_tests.py;
        # parents[2] is the repository root, which we add to sys.path so
        # ``acceleration.observability.logger`` resolves as a namespace
        # package import without requiring an __init__.py.
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from acceleration.observability.logger import (  # noqa: WPS433
            generate_run_id,
            get_logger,
        )

        run_id = os.environ.get("ACCEL_RUN_ID") or generate_run_id()
        log = get_logger("acceleration.scripts.extract_ci_tests", run_id=run_id)
    except Exception:  # pragma: no cover - exercised only on broken installs
        import logging

        logging.basicConfig(
            level=os.environ.get("ACCEL_LOG_LEVEL", "INFO"),
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
        )
        log = logging.getLogger("acceleration.scripts.extract_ci_tests")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.output_dir / "test_results.jsonl"
    access_path = args.output_dir / "test_results_access.json"

    token = os.environ.get("GITHUB_TOKEN")
    # Graceful degradation path: ``--skip-network`` or missing token →
    # touch outputs and emit an unavailable manifest. Exit cleanly so
    # the orchestrator continues with whatever local-only metrics
    # remain.
    if args.skip_network or not token:
        reason_short = (
            "skip-network supplied"
            if args.skip_network
            else "GITHUB_TOKEN absent"
        )
        reason_long = (
            f"GitHub Actions Artifacts API not accessed: {reason_short}. "
            "Metric 11 (Escaped Defects) will report Insufficient signal — "
            "CI test history unavailable per AAP §0.3.4."
        )
        log.info(
            "Not calling Actions API: %s",
            reason_short,
            extra={
                "owner": args.owner,
                "repo": args.repo,
                "skip_network": args.skip_network,
            },
        )
        out_path.write_text("", encoding="utf-8")
        access_path.write_text(
            json.dumps(
                _build_unavailable_manifest(reason_long),
                indent=2,
            ),
            encoding="utf-8",
        )
        log.info(
            "Wrote unavailable manifest to %s",
            access_path,
            extra={"manifest": str(access_path)},
        )
        return 0

    # Construct the HTTP client. ``request_count`` is automatically
    # capped by :data:`MAX_REQUESTS_PER_RUN`.
    client = GithubClient(token=token, api_base=args.api_base)

    log.info(
        "Listing workflows for %s/%s",
        args.owner,
        args.repo,
        extra={
            "owner": args.owner,
            "repo": args.repo,
            "targets": list(TARGET_WORKFLOW_FILENAMES),
        },
    )
    workflow_ids: dict[str, int] = {}
    try:
        workflow_ids = list_target_workflow_ids(client, args.owner, args.repo)
    except RuntimeError as exc:
        # Hit the request cap before discovery completed; treat as
        # unavailable but preserve the request-count visible in the
        # manifest so an operator can raise the cap if needed.
        log.warning(
            "Workflow listing terminated by request-cap: %s",
            exc,
            extra={"api_requests": client.request_count},
        )
    log.info(
        "Located workflows: %s",
        workflow_ids,
        extra={"workflow_ids": workflow_ids},
    )

    total_runs_seen = 0
    total_runs_with_artifacts = 0
    total_records = 0
    workflows_seen: list[str] = []
    workflows_with_records: list[str] = []
    per_workflow_runs_seen: dict[str, int] = {}
    per_workflow_runs_with_artifacts: dict[str, int] = {}
    per_workflow_record_count: dict[str, int] = {}
    truncated_by_request_cap = False

    # Open the JSONL output once and stream into it so the in-memory
    # footprint is bounded by the largest per-workflow record list,
    # not the cumulative result.
    with out_path.open("w", encoding="utf-8") as fhandle:
        for fname in TARGET_WORKFLOW_FILENAMES:
            wf_id = workflow_ids.get(fname)
            if wf_id is None:
                log.info(
                    "Workflow %s not found in repository; skipping",
                    fname,
                    extra={"workflow": fname},
                )
                continue
            workflows_seen.append(fname)
            try:
                records, runs_seen, runs_with_art = extract_for_workflow(
                    client,
                    args.owner,
                    args.repo,
                    fname,
                    wf_id,
                    log,
                    max_runs=args.max_runs,
                )
            except RuntimeError as exc:
                # Request-cap exceeded mid-stream. Preserve whatever
                # was written and record the truncation in the
                # manifest.
                log.warning(
                    "Workflow %s extraction halted by request-cap: %s",
                    fname,
                    exc,
                    extra={
                        "workflow": fname,
                        "api_requests": client.request_count,
                    },
                )
                truncated_by_request_cap = True
                break
            except Exception as exc:  # noqa: BLE001 - graceful degradation
                log.warning(
                    "Workflow %s extraction terminated early: %s: %s",
                    fname,
                    type(exc).__name__,
                    exc,
                    extra={"workflow": fname},
                )
                continue

            per_workflow_runs_seen[fname] = runs_seen
            per_workflow_runs_with_artifacts[fname] = runs_with_art
            per_workflow_record_count[fname] = len(records)
            total_runs_seen += runs_seen
            total_runs_with_artifacts += runs_with_art
            total_records += len(records)
            if records:
                workflows_with_records.append(fname)
            for rec in records:
                fhandle.write(json.dumps(rec, ensure_ascii=False, default=str))
                fhandle.write("\n")
            log.info(
                "Workflow %s: %d records from %d/%d runs with artifacts",
                fname,
                len(records),
                runs_with_art,
                runs_seen,
                extra={
                    "workflow": fname,
                    "records": len(records),
                    "runs_with_artifacts": runs_with_art,
                    "runs_seen": runs_seen,
                },
            )

    # Build the final access manifest.
    available = total_records > 0
    manifest: dict[str, Any] = {
        "accessed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "owner": args.owner,
        "repo": args.repo,
        "available": available,
        "tried": list(TARGET_WORKFLOW_FILENAMES),
        "workflows": list(workflow_ids.keys()),
        "workflow_ids": workflow_ids,
        "workflows_seen": workflows_seen,
        "workflows_with_records": workflows_with_records,
        "runs_seen": total_runs_seen,
        "runs_with_test_artifacts": total_runs_with_artifacts,
        "records_written": total_records,
        "api_requests": client.request_count,
        # Retry / reliability counters per the review feedback: record
        # retry attempts in test_results_access.json so operators can
        # audit whether transient failures (5xx, URLError, timeouts)
        # biased Metric 11's input data. ``retry_attempts`` counts every
        # retry across the run; ``retry_recoveries`` counts retried
        # calls that ultimately succeeded; ``retry_failures`` counts
        # retried calls that exhausted the budget. The static
        # ``retry_policy`` snapshot allows downstream consumers to
        # reproduce the exact retry schedule without reading source.
        "retry_attempts": client.retry_attempts,
        "retry_recoveries": client.retry_recoveries,
        "retry_failures": client.retry_failures,
        "retry_policy": {
            "max_retries": HTTP_MAX_RETRIES,
            "backoff_base_seconds": HTTP_RETRY_BACKOFF_BASE,
            "retryable_status_codes": sorted(HTTP_RETRYABLE_STATUS),
        },
        "per_workflow_runs_seen": per_workflow_runs_seen,
        "per_workflow_runs_with_artifacts": per_workflow_runs_with_artifacts,
        "per_workflow_record_count": per_workflow_record_count,
        "truncated_by_request_cap": truncated_by_request_cap,
    }
    if available:
        manifest["reason"] = None
        manifest["needed"] = None
    else:
        manifest["reason"] = (
            "No JUnit-shaped artifacts found in target workflow runs."
        )
        manifest["needed"] = (
            "Workflows must publish JUnit XML artifacts "
            "(junit*.xml, test-results.xml, or results.xml) and the "
            "GITHUB_TOKEN must have actions:read scope to download them."
        )

    access_path.write_text(
        json.dumps(manifest, indent=2, default=str),
        encoding="utf-8",
    )

    log.info(
        "Wrote %d test records from %d/%d runs with artifacts; "
        "api_requests=%d (retry attempts: %d, recoveries: %d, failures: %d)",
        total_records,
        total_runs_with_artifacts,
        total_runs_seen,
        client.request_count,
        client.retry_attempts,
        client.retry_recoveries,
        client.retry_failures,
        extra={
            "records": total_records,
            "runs_with_artifacts": total_runs_with_artifacts,
            "runs_seen": total_runs_seen,
            "api_requests": client.request_count,
            "retry_attempts": client.retry_attempts,
            "retry_recoveries": client.retry_recoveries,
            "retry_failures": client.retry_failures,
            "out_path": str(out_path),
            "manifest": str(access_path),
        },
    )
    return 0


# ---------------------------------------------------------------------------
# Module surface
# ---------------------------------------------------------------------------
# Public exports for downstream consumers and test harnesses. The set
# matches the schema's ``exports`` list one-for-one; any drift between
# this list and the schema is a defect.

__all__ = [
    # Constants
    "GITHUB_API_BASE",
    "USER_AGENT",
    "TARGET_WORKFLOW_FILENAMES",
    "PAGE_SIZE",
    "MAX_RUNS_PER_WORKFLOW",
    "MAX_ARTIFACT_BYTES",
    "MAX_REQUESTS_PER_RUN",
    "JUNIT_FILENAME_PATTERNS",
    # Retry policy constants (re-exported so the orchestrator and test
    # harnesses can pin against the same exponential-backoff schedule
    # the live extractor uses; mirrors :mod:`extract_github` so both
    # network extractors expose an identical reliability surface.)
    "HTTP_MAX_RETRIES",
    "HTTP_RETRY_BACKOFF_BASE",
    "HTTP_RETRYABLE_STATUS",
    # Class
    "GithubClient",
    # Functions
    "main",
    "parse_args",
    "list_target_workflow_ids",
    "list_workflow_runs",
    "list_run_artifacts",
    "download_artifact_zip",
    "is_junit_filename",
    "parse_junit_xml",
    "extract_junit_from_zip",
    "extract_for_workflow",
]


if __name__ == "__main__":
    sys.exit(main())

