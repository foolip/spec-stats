"""A throttled, serial GitHub REST client (standard library only).

Ground rule 2 (docs/plan.md): one request at a time, at least
MIN_INTERVAL seconds apart, back off on rate limits, send ETags so
unchanged listings come back as free 304s, and identify ourselves in the
User-Agent.
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
MIN_INTERVAL = 1.0  # seconds between requests
MAX_RETRIES = 6
# Pause before the hourly budget is spent, so the operator's token stays
# usable for other things.
RATE_LIMIT_FLOOR = 500


class GitHubError(Exception):
    pass


class NotFound(GitHubError):
    """404 or 410: the item was deleted (or never existed)."""

    def __init__(self, status, url):
        super().__init__(f"HTTP {status} for {url}")
        self.status = status


class PaginationLimit(GitHubError):
    """GitHub refused to page this deep (HTTP 422)."""


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


def _http(method, url, body, headers):
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
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
                 min_interval=MIN_INTERVAL, log=print):
        self.token = token if token is not None else load_token()
        self.transport = transport or _http
        self.sleep = sleep
        self.clock = clock
        self.min_interval = min_interval
        self.log = log
        self._last = None
        self.requests = 0
        self.not_modified = 0

    def _throttle(self):
        if self._last is not None:
            wait = self.min_interval - (self.clock() - self._last)
            if wait > 0:
                self.sleep(wait)
        self._last = self.clock()

    def _send(self, method, url, body=None, extra_headers=None):
        headers = {
            "Authorization": f"bearer {self.token}",
            "User-Agent": user_agent(),
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if body is not None:
            headers["Content-Type"] = "application/json"
        headers.update(extra_headers or {})
        delay = 30
        for _ in range(MAX_RETRIES):
            self._throttle()
            self.requests += 1
            try:
                status, resp_headers, raw = self.transport(method, url, body, headers)
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                self.log(f"network error ({e}); retrying in {delay}s")
                self.sleep(delay)
                delay *= 2
                continue
            lower = _lower(resp_headers)
            secondary = status == 403 and (b"secondary rate limit" in raw.lower()
                                           or lower.get("x-ratelimit-remaining") == "0")
            if status == 429 or secondary or status in (502, 503, 504):
                wait = self._backoff(lower, delay)
                self.log(f"HTTP {status}; backing off {wait:.0f}s")
                self.sleep(wait)
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
        if status in (404, 410):
            raise NotFound(status, url)
        if status == 422:
            raise PaginationLimit(f"HTTP 422 for {url}: {raw[:300]!r}")
        if status != 200:
            raise GitHubError(f"HTTP {status} for {url}: {raw[:500]!r}")
        return Response(status, headers, json.loads(raw))

    @staticmethod
    def _backoff(headers, default):
        if "retry-after" in headers:
            return max(float(headers["retry-after"]), 1)
        if headers.get("x-ratelimit-remaining") == "0" and "x-ratelimit-reset" in headers:
            return max(float(headers["x-ratelimit-reset"]) - time.time(), 1) + 5
        return default

    def _respect_budget(self, headers):
        remaining = headers.get("x-ratelimit-remaining")
        reset = headers.get("x-ratelimit-reset")
        # Keep a reserve: 500, or a tenth of a smaller budget (Actions'
        # built-in token gets 1,000 an hour).
        floor = min(RATE_LIMIT_FLOOR, int(headers.get("x-ratelimit-limit", 5000)) // 10)
        if remaining is not None and reset is not None and int(remaining) < floor:
            wait = max(float(reset) - time.time(), 1) + 5
            self.log(f"rate limit low ({remaining} left); pausing {wait:.0f}s until reset")
            self.sleep(wait)
