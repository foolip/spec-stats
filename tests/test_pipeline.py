import json
import tempfile
import unittest
from pathlib import Path

from specstats import derive, extract, github, summarize
from specstats.orgs import Attributor, company_to_org, load_aliases


def actor(login, typename="User"):
    return {"__typename": typename, "login": login}


def pr(number, updated, author="alice", merged_by="editor", reviews=(), comments=(), merged=True,
       more_reviews=False):
    return {
        "number": number, "title": f"PR {number}", "url": "", "state": "MERGED" if merged else "OPEN",
        "isDraft": False, "createdAt": "2025-01-02T00:00:00Z", "updatedAt": updated,
        "closedAt": updated if merged else None, "mergedAt": updated if merged else None,
        "author": actor(author), "mergedBy": actor(merged_by) if merged else None,
        "additions": 1, "deletions": 1, "changedFiles": 1, "body": "", "labels": {"nodes": []},
        "reviews": {"pageInfo": {"hasNextPage": more_reviews, "endCursor": "r1" if more_reviews else None},
                    "nodes": list(reviews)},
        "comments": {"pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": list(comments)},
    }


def review(login, at, state="APPROVED", inline=0, typename="User"):
    return {"author": actor(login, typename), "state": state, "submittedAt": at, "body": "",
            "comments": {"totalCount": inline}}


def comment(login, at, typename="User"):
    return {"author": actor(login, typename), "createdAt": at, "body": ""}


class FakeGitHub:
    """Serves list queries from `nodes` (sorted newest-updated first), PAGE at a time."""

    def __init__(self, nodes, page=2, extra_reviews=None, profiles=None):
        self.nodes = sorted(nodes, key=lambda n: n["updatedAt"], reverse=True)
        self.page = page
        self.extra_reviews = extra_reviews or {}
        self.profiles = profiles or {}
        self.calls = []

    def __call__(self, url, body, headers):
        req = json.loads(body)
        q, v = req["query"], req["variables"]
        self.calls.append(q)
        rate = {"cost": 1, "remaining": 4999, "resetAt": "2099-01-01T00:00:00Z"}
        if "pullRequests(" in q:
            start = int(v["after"] or 0)
            chunk = self.nodes[start:start + self.page]
            end = start + len(chunk)
            data = {"repository": {"pullRequests": {
                "pageInfo": {"hasNextPage": end < len(self.nodes), "endCursor": str(end)},
                "nodes": json.loads(json.dumps(chunk))}}, "rateLimit": rate}
        elif "pullRequest(number" in q:
            data = {"repository": {"pullRequest": {"reviews": {
                "pageInfo": {"hasNextPage": False, "endCursor": None},
                "nodes": self.extra_reviews.get(v["number"], [])}}}, "rateLimit": rate}
        elif "user(login" in q:
            data = {"rateLimit": rate}
            i = 0
            while f"u{i}:" in q:
                login = q.split(f"u{i}: user(login: ")[1].split(")")[0].strip('"')
                data[f"u{i}"] = {"login": login, "company": self.profiles.get(login)}
                i += 1
        else:
            raise AssertionError(q)
        return 200, {}, json.dumps({"data": data}).encode()


def client(fake):
    return github.Client(token="t", transport=fake, sleep=lambda s: None, log=lambda *a: None)


class ExtractTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = extract.connect(Path(self.tmp.name) / "raw.sqlite")

    def tearDown(self):
        self.tmp.cleanup()

    def stored(self):
        return {n: u for n, u in self.db.execute("SELECT number, updated_at FROM nodes")}

    def test_full_then_incremental(self):
        nodes = [pr(i, f"2025-01-{i:02d}T00:00:00Z") for i in range(1, 6)]
        fake = FakeGitHub(nodes)
        self.assertEqual(extract.extract_repo(client(fake), self.db, "whatwg/dom", "pr", log=lambda *a: None), 5)
        self.assertEqual(len(self.stored()), 5)
        # PR 2 is updated; an incremental run fetches only it and stops early.
        nodes[1] = pr(2, "2025-02-01T00:00:00Z")
        fake = FakeGitHub(nodes)
        self.assertEqual(extract.extract_repo(client(fake), self.db, "whatwg/dom", "pr", log=lambda *a: None), 1)
        self.assertEqual(len(fake.calls), 1)
        self.assertEqual(self.stored()[2], "2025-02-01T00:00:00Z")

    def test_since_then_backfill(self):
        nodes = [pr(i, f"2025-01-{i:02d}T00:00:00Z") for i in range(1, 7)]
        extract.extract_repo(client(FakeGitHub(nodes)), self.db, "whatwg/dom", "pr",
                             since="2025-01-04", log=lambda *a: None)
        self.assertEqual(sorted(self.stored()), [4, 5, 6])
        # Going further back stores only the older ones.
        n = extract.extract_repo(client(FakeGitHub(nodes)), self.db, "whatwg/dom", "pr",
                                 since="2025-01-02", log=lambda *a: None)
        self.assertEqual(n, 2)
        self.assertEqual(sorted(self.stored()), [2, 3, 4, 5, 6])

    def test_nested_pages_completed(self):
        nodes = [pr(1, "2025-01-01T00:00:00Z", reviews=[review("bob", "2025-01-01T00:00:00Z")],
                    more_reviews=True)]
        fake = FakeGitHub(nodes, extra_reviews={1: [review("carol", "2025-01-01T01:00:00Z")]})
        extract.extract_repo(client(fake), self.db, "whatwg/dom", "pr", log=lambda *a: None)
        node = json.loads(self.db.execute("SELECT json FROM nodes").fetchone()[0])
        self.assertEqual([r["author"]["login"] for r in node["reviews"]["nodes"]], ["bob", "carol"])

    def test_users(self):
        nodes = [pr(1, "2025-01-01T00:00:00Z", reviews=[review("bob", "2025-01-01T00:00:00Z"),
                                                        review("dependabot", "2025-01-01T00:00:00Z", typename="Bot")])]
        fake = FakeGitHub(nodes, profiles={"bob": "@mozilla"})
        extract.extract_repo(client(fake), self.db, "whatwg/dom", "pr", log=lambda *a: None)
        logins = extract.users_to_fetch(self.db)
        self.assertEqual(logins, ["alice", "bob", "editor"])
        extract.extract_users(client(fake), self.db, logins, log=lambda *a: None)
        self.assertEqual(extract.users_to_fetch(self.db), [])


class ClientTest(unittest.TestCase):
    def test_throttle_and_backoff(self):
        sleeps = []
        responses = [(429, {"Retry-After": "7"}, b""), (200, {}, b'{"data": {"ok": 1}}')]
        c = github.Client(token="t", transport=lambda *a: responses.pop(0), sleep=sleeps.append,
                          clock=lambda: 0.0, log=lambda *a: None)
        self.assertEqual(c.query("{ ok }"), {"ok": 1})
        self.assertIn(7.0, sleeps)
        self.assertIn(1.0, sleeps)  # the second request waited MIN_INTERVAL


class OrgsTest(unittest.TestCase):
    def test_company_field(self):
        aliases = load_aliases()
        self.assertEqual(company_to_org("@google", aliases), "Google")
        self.assertEqual(company_to_org("Mozilla Corporation", aliases), "Mozilla")
        self.assertEqual(company_to_org("Apple Inc.", aliases), "Apple")
        self.assertEqual(company_to_org("@igalia @webkit", aliases), "Igalia")
        self.assertIsNone(company_to_org("", aliases))
        self.assertIsNone(company_to_org("Freelance", aliases))

    def test_dated_override(self):
        attr = Attributor({"x": {"company": "Google"}},
                          affiliations={"x": [{"org": "Mozilla", "until": "2024-01-01"}]}, bots=set())
        self.assertEqual(attr.org("x", "2023-06-01T00:00:00Z"), "Mozilla")
        self.assertEqual(attr.org("x", "2024-06-01T00:00:00Z"), "Google")


class DeriveSummarizeTest(unittest.TestCase):
    def test_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            db = extract.connect(tmp / "raw.sqlite")
            nodes = [
                pr(1, "2025-03-10T00:00:00Z", author="alice", merged_by="ed",
                   reviews=[review("ed", "2025-03-05T00:00:00Z", inline=3),
                            review("alice", "2025-03-06T00:00:00Z", state="COMMENTED"),  # self
                            review("bot", "2025-03-06T00:00:00Z", typename="Bot")],
                   comments=[comment("ann", "2025-01-03T00:00:00Z")]),
                pr(2, "2025-04-10T00:00:00Z", author="ann", merged_by="ed",
                   reviews=[review("ed", "2025-04-09T00:00:00Z")]),
            ]
            extract.extract_repo(client(FakeGitHub(nodes)), db, "whatwg/dom", "pr", log=lambda *a: None)
            for login, company in [("ed", "Apple"), ("alice", "@google"), ("ann", None)]:
                db.execute("INSERT INTO users VALUES (?, '', ?)", (login, json.dumps({"login": login, "company": company})))
            db.commit()
            derive.derive(tmp / "raw.sqlite", tmp / "derived.sqlite")
            s = summarize.summarize(tmp / "derived.sqlite", tmp / "out", today="2026-01-15")
            rows = {(m, o, a): n for m, _, o, a, n in s["org_monthly"]}
            self.assertEqual(rows[("2025-03", "Apple", "review")], 1)
            self.assertEqual(rows[("2025-03", "Apple", "merge")], 1)
            self.assertEqual(rows[("2025-03", "Google", "pr")], 1)
            self.assertEqual(rows[("2025-01", "Unknown", "comment")], 1)
            self.assertNotIn(("2025-03", "Google", "review"), rows)  # self-review left out
            conc = {(r, a): row for r, a, *row in s["concentration"]}
            self.assertEqual(conc[("*", "review")], [2, 1, 1, 1, 1.0])
            resp = {(r, k, q): row for r, k, q, *row in s["response"]}
            self.assertEqual(resp[("whatwg/dom", "pr", "2025-Q1")], [2, 0, 49.0])  # 1 and 97 days
            self.assertTrue((tmp / "out" / "org_monthly.csv").exists())

    def test_people_needed(self):
        self.assertEqual(summarize.people_needed([10, 5, 3, 2], 0.5), 1)
        self.assertEqual(summarize.people_needed([5, 5, 5, 5], 0.8), 4)
        self.assertEqual(summarize.people_needed([], 0.5), 0)


if __name__ == "__main__":
    unittest.main()
