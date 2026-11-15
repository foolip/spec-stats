"""A serial GitHub REST client (standard library only).

Ground rule 2 (docs/plan.md): one request at a time, with no gap between
them (GitHub asks for serial requests, not slow ones; Octokit doesn't space
out GETs either), keep a reserve of the hourly budget, stop the run rather
than wait whenever GitHub says to wait for quota (the next run continues),
send ETags so unchanged listings come back as free 304s (only with the
token that got the ETag: Actions' built-in token is new every run), and
identify ourselves in the User-Agent.
"""

import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request

from . import paths

API = "https://api.github.com"
MAX_RETRIES = 6
# Pause before the hourly budget is spent, so the operator's token stays
# usable for other things.
RATE_LIMIT_FLOOR = 500


class GitHubError(Exception):
    pass


class Gone(GitHubError):
    """404, 410 or a redirect: the item was deleted, never existed, or was
    transferred to another repo. Redirects aren't followed, so nothing is
    fetched from the other repo; a transfer is treated as a deletion."""

    def __init__(self, status, url):
        super().__init__(f"HTTP {status} for {url}")
        self.status = status


class PaginationLimit(GitHubError):
    """GitHub refused to page this deep (HTTP 422)."""


class Stopped(Exception):
    """The run stops cleanly before the next request; the next run continues.
    Raised only between requests, so nothing fetched is lost."""


class DeadlineReached(Stopped):
    """The run's deadline came before the next request (or before the end of
    a retry delay)."""


class RateLimited(Stopped):
    """GitHub says to wait for quota: the hourly reserve is reached, or a
    429 or secondary rate limit. The run stops instead of idling until the
    reset."""


def load_token():
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        return token.strip()
    try:
        out = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, check=True)
        return out.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        raise GitHubError("No GitHub token: set GITHUB_TOKEN or sign in with `gh auth login`.")


def user_agent():
    contact = paths.settings().get("contact")
    if contact:
        return f"spec-stats (+https://github.com/foolip/spec-stats; {contact})"
    return "spec-stats (+https://github.com/foolip/spec-stats)"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None  # urllib then raises HTTPError with the 3xx status


_OPENER = urllib.request.build_opener(_NoRedirect)


def _http(method, url, body, headers):
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with _OPENER.open(req, timeout=120) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers or {}), e.read()


LINK_NEXT = re.compile(r'<([^>]+)>;\s*rel="next"')


def next_link(headers):
    m = LINK_NEXT.search(_lower(headers).get("link", ""))
    return m.group(1) if m else None


def _lower(headers):
    return {k.lower(): v for k, v in headers.items()}


class Response:
    def __init__(self, status, headers, data):
        self.status = status
        self.headers = _lower(headers)
        self.data = data

    @property
    def etag(self):
        return self.headers.get("etag")

    @property
    def next(self):
        return next_link(self.headers)


class Client:
    """Runs requests one at a time. `transport(method, url, body, headers)`
    returning (status, headers, raw bytes) is replaceable in tests."""

    def __init__(self, token=None, transport=None, sleep=time.sleep, clock=time.monotonic,
                 log=print, seconds_left=None):
        self.token = token if token is not None else load_token()
        self.transport = transport or _http
        self.sleep = sleep
        self.clock = clock
        self.log = log
        self.requests = 0
        self.not_modified = 0
        # In clock() time: no request starts, and no retry delay runs, past this.
        self.deadline = clock() + seconds_left if seconds_left is not None else None
        self._out_of_quota = None  # why the run stops before its next request
        self.rate_limit = None  # the hourly limit GitHub reports for this token, once known

    def _wait(self, seconds):
        if self.deadline is not None and self.clock() + seconds > self.deadline:
            raise DeadlineReached(f"deadline reached ({self.requests} requests made)")
        if seconds > 0:
            self.sleep(seconds)

    def _before_request(self):
        if self._out_of_quota:
            raise RateLimited(self._out_of_quota)
        self._wait(0)  # checks the deadline

    def _send(self, method, url, body=None, extra_headers=None):
        headers = {
            "Authorization": f"bearer {self.token}",
            "User-Agent": user_agent(),
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2026-03-10",
        }
        if body is not None:
            headers["Content-Type"] = "application/json"
        headers.update(extra_headers or {})
        delay = 30
        for _ in range(MAX_RETRIES):
            self._before_request()
            self.requests += 1
            try:
                status, resp_headers, raw = self.transport(method, url, body, headers)
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                self.log(f"network error ({e}); retrying in {delay}s")
                self._wait(delay)
                delay *= 2
                continue
            lower = _lower(resp_headers)
            secondary = status == 403 and (b"secondary rate limit" in raw.lower()
                                           or lower.get("x-ratelimit-remaining") == "0")
            if status == 429 or secondary:
                raise RateLimited(f"HTTP {status} rate limit ({self._reset_note(lower)}; "
                                  f"{self.requests} requests made)")
            if status in (502, 503, 504):
                wait = float(lower.get("retry-after", delay))
                self.log(f"HTTP {status}; retrying in {wait:.0f}s")
                self._wait(wait)
                delay *= 2
                continue
            self._respect_budget(lower)
            return status, resp_headers, raw
        raise GitHubError(f"giving up on {url} after {MAX_RETRIES} attempts")

    def rest(self, path_or_url, params=None, etag=None):
        """GET a REST resource. Returns a Response; status 304 has data None."""
        url = path_or_url if path_or_url.startswith("http") else API + path_or_url
        if params:
            url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
        status, headers, raw = self._send("GET", url, extra_headers={"If-None-Match": etag} if etag else None)
        if status == 304:
            self.not_modified += 1
            return Response(304, headers, None)
        if status in (301, 302, 307, 308, 404, 410):
            raise Gone(status, url)
        if status == 422:
            raise PaginationLimit(f"HTTP 422 for {url}: {raw[:300]!r}")
        if status != 200:
            raise GitHubError(f"HTTP {status} for {url}: {raw[:500]!r}")
        return Response(status, headers, json.loads(raw))

    @staticmethod
    def _reset_note(headers):
        if "retry-after" in headers:
            return f"retry after {headers['retry-after']}s"
        if "x-ratelimit-reset" in headers:
            return f"resets in {max(float(headers['x-ratelimit-reset']) - time.time(), 0):.0f}s"
        return "no reset time given"

    def _respect_budget(self, headers):
        remaining = headers.get("x-ratelimit-remaining")
        if self.rate_limit is None and "x-ratelimit-limit" in headers:
            self.rate_limit = int(headers["x-ratelimit-limit"])
            self.log(f"rate limit: {self.rate_limit} an hour, {remaining} left ({self._reset_note(headers)})")
        # Keep a reserve: 500, or a tenth of a smaller budget. The run stops
        # with exactly that many left, not one fewer.
        floor = min(RATE_LIMIT_FLOOR, int(headers.get("x-ratelimit-limit", 5000)) // 10)
        if remaining is not None and int(remaining) <= floor:
            # Stops before the next request rather than now, so this
            # response is returned and stored.
            self._out_of_quota = (f"hourly rate limit reserve reached ({remaining} left, "
                                  f"{self._reset_note(headers)}; {self.requests} requests made)")
