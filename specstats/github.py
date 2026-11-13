"""A throttled, serial GitHub GraphQL client (standard library only).

Ground rule 2 (docs/plan.md): one request at a time, at least
MIN_INTERVAL seconds apart, back off on rate limits, and identify
ourselves in the User-Agent.
"""

import json
import os
import subprocess
import time
import urllib.error
import urllib.request

from . import paths

ENDPOINT = "https://api.github.com/graphql"
MIN_INTERVAL = 1.0  # seconds between requests
MAX_RETRIES = 6
# Stop well before the hourly GraphQL budget is spent, so the operator's
# token stays usable for other things.
RATE_LIMIT_FLOOR = 500


class GitHubError(Exception):
    pass


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


def _http_post(url, body, headers):
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.status, dict(resp.headers), resp.read()


class Client:
    """Runs GraphQL queries one at a time. `transport` is replaceable in tests."""

    def __init__(self, token=None, transport=None, sleep=time.sleep, clock=time.monotonic,
                 min_interval=MIN_INTERVAL, log=print):
        self.token = token if token is not None else load_token()
        self.transport = transport or _http_post
        self.sleep = sleep
        self.clock = clock
        self.min_interval = min_interval
        self.log = log
        self._last = None
        self.requests = 0
        self.rate_limit = None

    def _throttle(self):
        if self._last is not None:
            wait = self.min_interval - (self.clock() - self._last)
            if wait > 0:
                self.sleep(wait)
        self._last = self.clock()

    def query(self, query, variables=None):
        body = json.dumps({"query": query, "variables": variables or {}}).encode()
        headers = {
            "Authorization": f"bearer {self.token}",
            "Content-Type": "application/json",
            "User-Agent": user_agent(),
        }
        delay = 30
        for attempt in range(MAX_RETRIES):
            self._throttle()
            self.requests += 1
            try:
                status, resp_headers, raw = self.transport(ENDPOINT, body, headers)
            except urllib.error.HTTPError as e:
                status, resp_headers, raw = e.code, dict(e.headers or {}), e.read()
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                self.log(f"network error ({e}); retrying in {delay}s")
                self.sleep(delay)
                delay *= 2
                continue
            if status in (403, 429, 502, 503, 504):
                wait = self._backoff(resp_headers, delay)
                self.log(f"HTTP {status}; backing off {wait:.0f}s")
                self.sleep(wait)
                delay *= 2
                continue
            if status != 200:
                raise GitHubError(f"HTTP {status}: {raw[:500]!r}")
            data = json.loads(raw)
            errors = data.get("errors")
            if errors:
                if any(e.get("type") == "RATE_LIMITED" for e in errors):
                    wait = self._backoff(resp_headers, delay)
                    self.log(f"rate limited; backing off {wait:.0f}s")
                    self.sleep(wait)
                    delay *= 2
                    continue
                raise GitHubError(json.dumps(errors)[:1000])
            self._note_rate_limit(data.get("data") or {})
            return data["data"]
        raise GitHubError(f"giving up after {MAX_RETRIES} attempts")

    @staticmethod
    def _backoff(headers, default):
        headers = {k.lower(): v for k, v in headers.items()}
        if "retry-after" in headers:
            return max(float(headers["retry-after"]), 1)
        if headers.get("x-ratelimit-remaining") == "0" and "x-ratelimit-reset" in headers:
            return max(float(headers["x-ratelimit-reset"]) - time.time(), 1) + 5
        return default

    def _note_rate_limit(self, data):
        rl = data.get("rateLimit")
        if not rl:
            return
        self.rate_limit = rl
        if rl["remaining"] < RATE_LIMIT_FLOOR:
            reset = rl.get("resetAt", "")
            self.log(f"rate limit low ({rl['remaining']} left, resets {reset}); pausing until reset")
            wait = _seconds_until(reset)
            self.sleep(wait + 5)


def _seconds_until(iso):
    from datetime import datetime, timezone
    try:
        t = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return 600
    return max((t - datetime.now(timezone.utc)).total_seconds(), 1)
