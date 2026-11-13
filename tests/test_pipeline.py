import json
import re
import tempfile
import unittest
from pathlib import Path

from specstats import derive, extract, github, summarize
from specstats.orgs import Attributor, company_to_org, load_aliases
from tests.fakegithub import REPO, FakeGitHub

QUIET = dict(log=lambda *a: None)


def client(fake):
    return github.Client(token="t", transport=fake, sleep=lambda s: None, **QUIET)


def populated(**kw):
    gh = FakeGitHub(**kw)
    gh.add_issue(1, "2025-01-01T00:00:00Z", author="ann")
    gh.add_comment(1, "2025-01-03T00:00:00Z", "ed")
    gh.add_issue(2, "2025-02-01T00:00:00Z", author="alice", is_pr=True,
                 merged_at="2025-02-10T00:00:00Z", merged_by="ed",
                 reviews=[("ed", "2025-02-05T00:00:00Z", "APPROVED", "User", 2)])
    gh.add_issue(3, "2025-03-01T00:00:00Z", author="ed", is_pr=True,
                 merged_at="2025-03-02T00:00:00Z", merged_by="ed")
    gh.add_event(1, "2025-01-02T00:00:00Z", "labeled", "ed")
    gh.add_event(2, "2025-02-10T00:00:00Z", "merged", "ed")
    return gh


class ExtractTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = extract.connect(Path(self.tmp.name) / "raw.sqlite")

    def tearDown(self):
        self.tmp.cleanup()

    def count(self, table):
        return self.db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

    def test_full_sync_then_unchanged_is_all_304s(self):
        gh = populated()
        extract.sync_repo(client(gh), self.db, REPO, **QUIET)
        self.assertEqual(self.count("items"), 3)
        self.assertEqual(self.count("issue_comments"), 1)
        self.assertEqual(self.count("review_comments"), 2)
        self.assertEqual(self.count("events"), 2)
        self.assertEqual(self.count("pulls"), 2)
        self.assertEqual(self.count("pr_reviews"), 1)
        self.assertEqual(extract.comment_mismatches(self.db, REPO), ([], []))
        # Nothing changed. The second run re-reads the overlap once (its URL now
        # has `since`, so the first run's ETags don't apply); after that, one
        # conditional request per stream, all 304s.
        extract.sync_repo(client(gh), self.db, REPO, **QUIET)
        c = client(gh)
        extract.sync_repo(c, self.db, REPO, **QUIET)
        self.assertEqual((c.requests, c.not_modified), (4, 4))

    def test_incremental_fetches_only_what_changed(self):
        gh = populated()
        extract.sync_repo(client(gh), self.db, REPO, **QUIET)
        gh.add_comment(2, "2025-06-01T00:00:00Z", "bob")
        c = client(gh)
        extract.sync_repo(c, self.db, REPO, **QUIET)
        self.assertEqual(self.count("issue_comments"), 2)
        self.assertEqual(extract.stale_prs(self.db, REPO, "reviews"), [])
        per_pr = [u for _, u in gh.calls[-c.requests:] if "/pulls/" in u and "/pulls/comments" not in u]
        self.assertEqual(len(per_pr), 2)  # PR 2's pull and reviews, nothing for PR 3

    def test_overlap_catches_a_late_arrival(self):
        gh = populated()
        extract.sync_repo(client(gh), self.db, REPO, **QUIET)
        # A comment that became visible late, timestamped just before the cursor.
        cursor = self.db.execute("SELECT cursor FROM cursors WHERE stream='issue_comments'").fetchone()[0]
        gh.add_comment(1, "2025-01-02T12:00:00Z", "bob", touch=False)
        gh.add_comment(3, cursor, "carol")
        extract.sync_repo(client(gh), self.db, REPO, **QUIET)
        self.assertEqual(self.count("issue_comments"), 3)

    def test_counts_heal_a_missed_comment(self):
        gh = populated()
        extract.sync_repo(client(gh), self.db, REPO, **QUIET)
        # A comment far older than the overlap shows up (e.g. it was missed),
        # and the item's updated_at moves, so its count is checked.
        gh.add_comment(1, "2024-06-01T00:00:00Z", "bob", touch=False)
        gh.touch(1, "2025-07-01T00:00:00Z")
        extract.sync_repo(client(gh), self.db, REPO, **QUIET)
        self.assertEqual(self.count("issue_comments"), 2)
        self.assertEqual(extract.comment_mismatches(self.db, REPO), ([], []))

    def test_pagination_limit_restarts_from_since(self):
        gh = FakeGitHub(page=2, page_limit=2)
        for i in range(1, 10):
            gh.add_issue(i, f"2025-01-{i:02d}T00:00:00Z")
        extract.sync_ascending(client(gh), self.db, REPO, "items", **QUIET)
        self.assertEqual(self.count("items"), 9)

    def test_events_floor_falls_back_to_per_item(self):
        gh = FakeGitHub(page=2, page_limit=1)
        for i in range(1, 5):
            gh.add_issue(i, f"2025-01-{i:02d}T00:00:00Z")
            gh.add_event(i, f"2025-01-{i:02d}T01:00:00Z", "labeled", "ed")
        c = client(gh)
        extract.sync_events(c, self.db, REPO, **QUIET)
        self.assertEqual(self.count("events"), 2)  # one page only
        extract.sync_ascending(c, self.db, REPO, "items", **QUIET)
        extract.fetch_item_events(c, self.db, REPO, **QUIET)
        self.assertEqual(self.count("events"), 4)

    def test_reconcile_accounts_for_every_number(self):
        gh = populated()
        extract.sync_repo(client(gh), self.db, REPO, **QUIET)
        del gh.issues[1]           # deleted on GitHub
        gh.add_issue(6, "2020-01-01T00:00:00Z")  # one we somehow never saw
        gh.transferred.add(5)      # 4 and 5 never existed here: 4 deleted, 5 moved away
        r = extract.reconcile(client(gh), self.db, REPO, **QUIET)
        self.assertEqual(r["highest"], 6)
        self.assertEqual(r["newly_gone"], [1, 4, 5])
        gone = dict(self.db.execute("SELECT number, reason FROM gone").fetchall())
        self.assertEqual(gone, {1: "deleted", 4: "deleted", 5: "transferred"})
        self.assertEqual(r["stored"] + r["gone"], r["highest"])
        # The deleted item's last version is kept in history.
        self.assertEqual(self.db.execute("SELECT removed FROM history WHERE tbl='items'").fetchone(), (1,))
        # The next reconcile doesn't recheck known gone numbers.
        c = client(gh)
        extract.reconcile(c, self.db, REPO, **QUIET)
        self.assertFalse([u for _, u in gh.calls[-c.requests:] if re.search(r"/issues/\d+$", u)])

    def test_history_keeps_previous_versions(self):
        gh = populated()
        extract.sync_repo(client(gh), self.db, REPO, **QUIET)
        comment = gh.issue_comments[0]
        comment["body"], comment["updated_at"] = "edited", "2025-08-01T00:00:00Z"
        extract.sync_repo(client(gh), self.db, REPO, **QUIET)
        old = self.db.execute("SELECT json FROM history WHERE tbl='issue_comments'").fetchall()
        self.assertEqual([json.loads(j)["body"] for (j,) in old], ["hi"])
        # Re-reading the overlap doesn't add history for unchanged objects.
        extract.sync_repo(client(gh), self.db, REPO, **QUIET)
        self.assertEqual(self.count("history"), 1)

    def test_turning_on_a_pr_resource_later(self):
        gh = populated()
        extract.sync_repo(client(gh), self.db, REPO, **QUIET)
        c = client(gh)
        n = extract.sync_pr_resources(c, self.db, REPO, resources=["pull", "reviews", "commits"], **QUIET)
        self.assertEqual(n, 2)  # commits for both PRs, nothing else refetched
        self.assertTrue(all("/commits" in u for _, u in gh.calls[-c.requests:]))

    def test_users(self):
        gh = populated()
        gh.add_comment(1, "2025-04-01T00:00:00Z", "dependabot[bot]", typ="Bot")
        gh.profiles = {"ed": "Apple"}
        extract.sync_repo(client(gh), self.db, REPO, **QUIET)
        logins = extract.users_to_fetch(self.db)
        self.assertEqual(logins, ["alice", "ann", "ed"])
        extract.extract_users(client(gh), self.db, logins, **QUIET)
        self.assertEqual(extract.users_to_fetch(self.db), [])


class ClientTest(unittest.TestCase):
    def test_throttle_and_backoff(self):
        sleeps = []
        responses = [(429, {"Retry-After": "7"}, b""), (200, {}, b'{"ok": 1}')]
        c = github.Client(token="t", transport=lambda *a: responses.pop(0), sleep=sleeps.append,
                          clock=lambda: 0.0, **QUIET)
        self.assertEqual(c.rest("/x").data, {"ok": 1})
        self.assertIn(7.0, sleeps)
        self.assertIn(1.0, sleeps)  # the second request waited MIN_INTERVAL

    def test_secondary_rate_limit(self):
        sleeps = []
        responses = [(403, {}, b'{"message": "You have exceeded a secondary rate limit"}'),
                     (200, {}, b"[]")]
        c = github.Client(token="t", transport=lambda *a: responses.pop(0), sleep=sleeps.append,
                          clock=lambda: 0.0, **QUIET)
        self.assertEqual(c.rest("/x").data, [])
        self.assertIn(30, sleeps)


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
            gh = populated()
            gh.add_review(2, "alice", "2025-02-06T00:00:00Z", "COMMENTED")         # self-review
            gh.add_review(2, "copilot", "2025-02-06T00:00:00Z", typ="Bot")         # bot
            gh.add_comment(2, "2025-02-07T00:00:00Z", "ann", body="<!-- This comment is programmatically generated -->")
            gh.add_issue(4, "2025-03-01T00:00:00Z", author="ann", is_pr=True, draft_ready_at="2025-03-20T00:00:00Z")
            gh.add_comment(4, "2025-03-05T00:00:00Z", "ed")   # during the draft: not a response
            gh.add_comment(4, "2025-03-22T00:00:00Z", "ed")
            gh.profiles = {"ed": "Apple", "alice": "@google"}
            db = extract.connect(tmp / "raw.sqlite")
            extract.sync_repo(client(gh), db, REPO, **QUIET)
            extract.extract_users(client(gh), db, extract.users_to_fetch(db), **QUIET)
            derive.derive(tmp / "raw.sqlite", tmp / "derived.sqlite")

            d = __import__("sqlite3").connect(tmp / "derived.sqlite")
            merges = d.execute("SELECT number, detail FROM actions WHERE action='merge' ORDER BY number").fetchall()
            self.assertEqual(merges, [(2, "other"), (3, "self")])
            self.assertEqual(d.execute("SELECT COUNT(*) FROM actions WHERE action='review'").fetchone()[0], 1)
            self.assertEqual(d.execute("SELECT COUNT(*) FROM actions WHERE action='review_comment'").fetchone()[0], 2)
            # The boilerplate comment and ann's own comments don't count.
            self.assertEqual(d.execute("SELECT COUNT(*) FROM actions WHERE action='comment'").fetchone()[0], 3)
            ready, first = d.execute("SELECT ready_at, first_response_at FROM items WHERE number=4").fetchone()
            self.assertEqual((ready, first), ("2025-03-20T00:00:00Z", "2025-03-22T00:00:00Z"))

            s = summarize.summarize(tmp / "derived.sqlite", tmp / "out", today="2026-01-15")
            rows = {(m, o, a): n for m, _, o, a, n in s["org_monthly"]}
            self.assertEqual(rows[("2025-02", "Apple", "review")], 1)
            self.assertEqual(rows[("2025-02", "Apple", "merge")], 1)
            self.assertEqual(rows[("2025-02", "Google", "pr")], 1)
            resp = {(r, k, q): row for r, k, q, *row in s["response"]}
            self.assertEqual(resp[("whatwg/dom", "pr", "2025-Q1")], [3, 1, 3.0])  # PR 3 never answered
            self.assertTrue((tmp / "out" / "org_monthly.csv").exists())

    def test_people_needed(self):
        self.assertEqual(summarize.people_needed([10, 5, 3, 2], 0.5), 1)
        self.assertEqual(summarize.people_needed([5, 5, 5, 5], 0.8), 4)
        self.assertEqual(summarize.people_needed([], 0.5), 0)


if __name__ == "__main__":
    unittest.main()
