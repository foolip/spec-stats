"""An in-memory GitHub, enough of the REST API for the extractor's tests."""

import json
import re
import urllib.parse

REPO = "whatwg/dom"
API = "https://api.github.com"


def user(login, typ="User"):
    return {"login": login, "type": typ}


class FakeGitHub:
    def __init__(self, page=2, page_limit=None, page_cap=None):
        self.page = page              # items per page, whatever per_page asks for
        self.page_limit = page_limit  # deepest page served before HTTP 422
        self.page_cap = page_cap      # deepest page served, silently, with no next link
        self.issues = {}
        self.issue_comments = []
        self.review_comments = []
        self.events = []
        self.pulls = {}               # number -> REST pull request object
        self.reviews = {}             # number -> [REST review objects]
        self.timeline_drop = set()    # ids left out of timelines
        self.unprocessable = {}       # path (after the repo) -> message, answered with HTTP 422
        self.transferred = set()      # issue numbers moved to another repo (served as a redirect)
        self.sort_keys = {}           # number -> the updated_at /issues sorts and filters it by, if not
                                      # its own (GitHub's is sometimes older: whatwg/html #127)
        self.calls = []
        self.missing = False          # the repo itself answers 404 (not public)
        self.before_request = None    # called with the request count, to change state mid-run
        self._id = 1000

    # --- building state ---

    def next_id(self):
        self._id += 1
        return self._id

    def add_issue(self, number, at, author="alice", is_pr=False, merged_at=None, merged_by=None,
                  draft_ready_at=None, reviews=(), labels=()):
        obj = {"number": number, "created_at": at, "updated_at": max(at, merged_at or at), "closed_at": merged_at,
               "state": "closed" if merged_at else "open", "user": user(author), "comments": 0,
               "labels": [{"name": l} for l in labels],
               "repository_url": f"{API}/repos/{REPO}"}
        self.issues[number] = obj
        if merged_at:
            self.add_event(number, merged_at, "merged", merged_by)
            self.add_event(number, merged_at, "closed", merged_by)
        if is_pr:
            obj["pull_request"] = {"merged_at": merged_at}
            self.pulls[number] = {
                "number": number, "node_id": f"PR_{number}", "updated_at": obj["updated_at"],
                "state": "closed" if merged_at else "open", "draft": False, "created_at": at,
                "merged_at": merged_at, "merged_by": user(merged_by) if merged_by else None,
                "user": user(author), "review_comments": 0, "additions": 1, "deletions": 1, "changed_files": 1}
            self.reviews[number] = []
            for r in reviews:
                self.add_review(number, *r)
            if draft_ready_at:
                self.add_event(number, draft_ready_at, "ready_for_review", author)
        return obj

    def close(self, number, at, actor="ed", event=True):
        self.issues[number].update(state="closed", closed_at=at)
        if event:
            self.add_event(number, at, "closed", actor)
        self.touch(number, at)

    def touch(self, number, at):
        self.issues[number]["updated_at"] = at
        if number in self.pulls:
            self.pulls[number]["updated_at"] = at

    def add_comment(self, number, at, login, body="hi", typ="User", touch=True):
        self.issue_comments.append({"id": self.next_id(), "issue_url": f"{API}/repos/{REPO}/issues/{number}",
                                    "created_at": at, "updated_at": at, "user": user(login, typ), "body": body})
        self.issues[number]["comments"] += 1
        if touch:
            self.touch(number, at)

    def add_review(self, number, login, at, state="APPROVED", typ="User", inline=0):
        review = {"id": self.next_id(), "node_id": "PRR", "user": user(login, typ), "state": state,
                  "submitted_at": at, "body": ""}
        self.reviews[number].append(review)
        for _ in range(inline):
            self.review_comments.append({
                "id": self.next_id(), "pull_request_url": f"{API}/repos/{REPO}/pulls/{number}",
                "pull_request_review_id": review["id"], "created_at": at, "updated_at": at,
                "user": user(login, typ), "body": "nit"})
            self.pulls[number]["review_comments"] += 1
        self.touch(number, max(at, self.issues[number]["updated_at"]))

    def add_event(self, number, at, event, actor):
        self.events.append({"id": self.next_id(), "created_at": at, "event": event,
                            "actor": user(actor), "issue": {"number": number}})

    # --- serving ---

    def __call__(self, method, url, body, headers):
        self.calls.append((method, url))
        if self.before_request:
            self.before_request(len(self.calls))
        parsed = urllib.parse.urlparse(url)
        q = dict(urllib.parse.parse_qsl(parsed.query))
        path = parsed.path[len(f"/repos/{REPO}"):]
        if self.missing:
            return 404, {}, b'{"message": "Not Found"}'
        if path in self.unprocessable:
            return 422, {}, json.dumps({"message": self.unprocessable[path], "status": "422"}).encode()
        if path == "/issues":
            def key(o):
                if q.get("sort") == "created":
                    return o["created_at"]
                return self.sort_keys.get(o["number"], o["updated_at"])
            rows = sorted(self.issues.values(), key=lambda o: (key(o), o["number"]),
                          reverse=q.get("direction") == "desc")
            return self._list(url, q, headers, [o for o in rows if "since" not in q or key(o) >= q["since"]])
        if path == "/issues/comments":
            return self._list(url, q, headers, self._since(sorted(self.issue_comments, key=lambda o: o["updated_at"]), q))
        if path == "/pulls/comments":
            return self._list(url, q, headers, self._since(sorted(self.review_comments, key=lambda o: o["updated_at"]), q))
        if path == "/issues/events":
            return self._list(url, q, headers, sorted(self.events, key=lambda o: -o["id"]))
        m = re.fullmatch(r"/issues/(\d+)", path)
        if m:
            n = int(m.group(1))
            if n in self.transferred:
                return 301, {"Location": f"{API}/repositories/1/issues/1"}, b'{"message": "Moved Permanently"}'

            if n not in self.issues:
                return 410, {}, b'{"message": "This issue was deleted"}'
            return 200, {}, json.dumps(self.issues[n]).encode()
        m = re.fullmatch(r"/pulls/(\d+)", path)
        if m:
            return 200, {}, json.dumps(self.pulls[int(m.group(1))]).encode()
        m = re.fullmatch(r"/pulls/(\d+)/reviews", path)
        if m:
            return self._list(url, q, headers, self.reviews[int(m.group(1))])
        m = re.fullmatch(r"/issues/(\d+)/timeline", path)
        if m:  # roughly GitHub's shape; `timeline_drop` leaves out ids, to test the check
            n = int(m.group(1))
            rows = [dict(c, event="commented") for c in self.issue_comments
                    if c["issue_url"].endswith(f"/issues/{n}")]
            rows += [dict(r, event="reviewed") for r in self.reviews.get(n, [])]
            inline = [c for c in self.review_comments if c["pull_request_url"].endswith(f"/pulls/{n}")]
            if inline:
                rows.append({"event": "line-commented", "comments": inline})
            rows += [dict((k, v) for k, v in e.items() if k != "issue") for e in self.events
                     if e["issue"]["number"] == n]
            rows = [r for r in rows if r.get("id") not in self.timeline_drop]
            return self._list(url, q, headers, rows)
        m = re.fullmatch(r"/(issues|pulls)/(\d+)/(comments|events)", path)
        if m:
            kind, n, what = m.group(1), int(m.group(2)), m.group(3)
            if n in self.transferred or n not in self.issues:  # as GET /issues/{n} answers
                return 410, {}, b'{"message": "This issue was deleted"}'
            if what == "events":
                rows = [dict((k, v) for k, v in e.items() if k != "issue") for e in self.events
                        if e["issue"]["number"] == n]
            elif kind == "issues":
                rows = [c for c in self.issue_comments if c["issue_url"].endswith(f"/issues/{n}")]
            else:
                rows = [c for c in self.review_comments if c["pull_request_url"].endswith(f"/pulls/{n}")]
            return self._list(url, q, headers, rows)
        raise AssertionError(url)

    @staticmethod
    def _since(rows, q):
        return [r for r in rows if "since" not in q or r["updated_at"] >= q["since"]]

    def _list(self, url, q, headers, rows):
        page = int(q.get("page", 1))
        if self.page_limit and page > self.page_limit:
            return 422, {}, b'{"message": "pagination is limited"}'
        size = int(q.get("per_page", self.page))
        chunk = rows[(page - 1) * size: page * size]
        out = {}
        if page * size < len(rows) and not (self.page_cap and page >= self.page_cap):
            base = url.split("&page=")[0].split("?page=")[0]
            out["Link"] = f'<{base}{"&" if "?" in base else "?"}page={page + 1}>; rel="next"'
        return 200, out, json.dumps(chunk).encode()
