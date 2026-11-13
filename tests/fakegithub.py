"""An in-memory GitHub, enough of REST and GraphQL for the extractor's tests."""

import hashlib
import json
import re
import urllib.parse

REPO = "whatwg/dom"
API = "https://api.github.com"


def user(login, typ="User"):
    return {"login": login, "type": typ}


class FakeGitHub:
    def __init__(self, page=2, page_limit=None):
        self.page = page              # items per page, whatever per_page asks for
        self.page_limit = page_limit  # deepest page served before HTTP 422
        self.issues = {}
        self.issue_comments = []
        self.review_comments = []
        self.events = []
        self.prs = {}                 # number -> GraphQL PullRequest node
        self.profiles = {}
        self.calls = []
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
        if is_pr:
            obj["pull_request"] = {"merged_at": merged_at}
            self.prs[number] = {
                "number": number, "updatedAt": obj["updated_at"], "state": "MERGED" if merged_at else "OPEN",
                "isDraft": False, "createdAt": at, "closedAt": merged_at, "mergedAt": merged_at,
                "mergedBy": {"__typename": "User", "login": merged_by} if merged_by else None,
                "author": {"__typename": "User", "login": author},
                "reviews": self._conn([]), "commits": self._conn([]), "files": self._conn([])}
            for r in reviews:
                self.add_review(number, *r)
            if draft_ready_at:
                self.add_event(number, draft_ready_at, "ready_for_review", author)
        return obj

    @staticmethod
    def _conn(nodes):
        return {"totalCount": len(nodes), "pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": nodes}

    def touch(self, number, at):
        self.issues[number]["updated_at"] = at
        if number in self.prs:
            self.prs[number]["updatedAt"] = at

    def add_comment(self, number, at, login, body="hi", typ="User", touch=True):
        self.issue_comments.append({"id": self.next_id(), "issue_url": f"{API}/repos/{REPO}/issues/{number}",
                                    "created_at": at, "updated_at": at, "user": user(login, typ), "body": body})
        self.issues[number]["comments"] += 1
        if touch:
            self.touch(number, at)

    def add_review(self, number, login, at, state="APPROVED", typename="User", inline=0):
        review = {"databaseId": self.next_id(), "author": {"__typename": typename, "login": login},
                  "state": state, "createdAt": at, "submittedAt": at, "body": "",
                  "comments": {"totalCount": inline}}
        conn = self.prs[number]["reviews"]
        conn["nodes"].append(review)
        conn["totalCount"] += 1
        for _ in range(inline):
            self.review_comments.append({
                "id": self.next_id(), "pull_request_url": f"{API}/repos/{REPO}/pulls/{number}",
                "pull_request_review_id": review["databaseId"], "created_at": at, "updated_at": at,
                "user": user(login, "Bot" if typename == "Bot" else "User"), "body": "nit"})
        self.touch(number, max(at, self.issues[number]["updated_at"]))

    def add_event(self, number, at, event, actor):
        self.events.append({"id": self.next_id(), "created_at": at, "event": event,
                            "actor": user(actor), "issue": {"number": number}})

    # --- serving ---

    def __call__(self, method, url, body, headers):
        self.calls.append((method, url))
        if method == "POST":
            return self._graphql(json.loads(body))
        parsed = urllib.parse.urlparse(url)
        q = dict(urllib.parse.parse_qsl(parsed.query))
        path = parsed.path[len(f"/repos/{REPO}"):]
        if path == "/issues":
            rows = sorted(self.issues.values(), key=lambda o: o["updated_at"])
            return self._list(url, q, headers, self._since(rows, q))
        if path == "/issues/comments":
            return self._list(url, q, headers, self._since(sorted(self.issue_comments, key=lambda o: o["updated_at"]), q))
        if path == "/pulls/comments":
            return self._list(url, q, headers, self._since(sorted(self.review_comments, key=lambda o: o["updated_at"]), q))
        if path == "/issues/events":
            return self._list(url, q, headers, sorted(self.events, key=lambda o: -o["id"]))
        m = re.fullmatch(r"/issues/(\d+)", path)
        if m:
            n = int(m.group(1))
            if n not in self.issues:
                return 404, {}, b'{"message": "Not Found"}'
            return 200, {}, json.dumps(self.issues[n]).encode()
        m = re.fullmatch(r"/(issues|pulls)/(\d+)/(comments|events)", path)
        if m:
            kind, n, what = m.group(1), int(m.group(2)), m.group(3)
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
        etag = '"%s"' % hashlib.sha1(json.dumps(rows, sort_keys=True).encode()).hexdigest()
        if page == 1 and headers.get("If-None-Match") == etag:
            return 304, {"ETag": etag}, b""
        chunk = rows[(page - 1) * self.page: page * self.page]
        out = {"ETag": etag}
        if page * self.page < len(rows):
            base = url.split("&page=")[0].split("?page=")[0]
            out["Link"] = f'<{base}{"&" if "?" in base else "?"}page={page + 1}>; rel="next"'
        return 200, out, json.dumps(chunk).encode()

    def _graphql(self, req):
        query, v = req["query"], req["variables"]
        rate = {"cost": 1, "remaining": 4999, "resetAt": "2099-01-01T00:00:00Z"}
        if "pullRequest(number: $number)" in query:
            conn = re.search(r"pullRequest\(number: \$number\) \{\s*(\w+)\(", query).group(1)
            data = {"repository": {"pullRequest": {conn: self._conn([])}}, "rateLimit": rate}
        elif re.search(r"p\d+: pullRequest", query):
            repo = {}
            for n in map(int, re.findall(r"p(\d+): pullRequest", query)):
                repo[f"p{n}"] = json.loads(json.dumps(self.prs[n])) if n in self.prs else None
            data = {"repository": repo, "rateLimit": rate}
        elif "issues(first: 100" in query or "pullRequests(first: 100" in query:
            want_pr = "pullRequests(" in query
            nodes = [{"number": o["number"], "updatedAt": o["updated_at"]} for o in self.issues.values()
                     if ("pull_request" in o) == want_pr]
            conn = {"totalCount": len(nodes), "pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": nodes}
            data = {"repository": {"pullRequests" if want_pr else "issues": conn}, "rateLimit": rate}
        elif "user(login" in query:
            data = {"rateLimit": rate}
            for alias, login in re.findall(r'(u\d+): user\(login: "([^"]+)"\)', query):
                data[alias] = {"login": login, "company": self.profiles.get(login)}
        else:
            raise AssertionError(query)
        return 200, {}, json.dumps({"data": data}).encode()
