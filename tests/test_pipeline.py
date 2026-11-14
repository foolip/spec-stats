import json
import os
import re
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from specstats import extract, github
from tests.fakegithub import REPO, FakeGitHub

QUIET = dict(log=lambda *a: None)
extract.PER_PAGE = 2  # small pages, so a few rows exercise paging


def client(fake, requests=None):
    """A client for `fake`. With `requests`, its deadline allows that many
    requests: each starts a second after the last on a fake clock."""
    if requests is None:
        return github.Client(token="t", transport=fake, sleep=lambda s: None, **QUIET)
    t = [0.0]

    def sleep(s):
        t[0] += s
    return github.Client(token="t", transport=fake, sleep=sleep, clock=lambda: t[0],
                         seconds_left=requests - 1, **QUIET)


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


class TempDirs(unittest.TestCase):
    """A temporary directory per test, with data/github/ inside it, so tests
    never write into the checkout."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.files = Path(self.tmp.name) / "github"
        env = mock.patch.dict(os.environ, {"SPECSTATS_GITHUB": str(self.files)})
        env.start()
        self.addCleanup(env.stop)
        self.addCleanup(self.tmp.cleanup)


class ExtractTest(TempDirs):
    def store(self):
        """A fresh RepoStore each time, so every run starts from the files alone."""
        return extract.RepoStore(REPO)

    def sync(self, gh, c=None):
        extract.sync_repo(c or client(gh), self.store(), **QUIET)

    def count(self, what):
        return self.store().counts()[what]

    def issue_dir(self):
        return self.files / REPO / "issues"

    def test_full_sync_then_unchanged_is_all_304s(self):
        gh = populated()
        self.sync(gh)
        self.assertEqual(self.store().counts(), {"issues": 1, "prs": 2, "pulls": 2, "comments": 1, "events": 2,
                                                 "reviews": 1, "review_comments": 2, "gone": 0})
        self.assertEqual(extract.comment_mismatches(self.store()), ([], []))
        # Nothing changed. The second run re-reads the overlap once (its URL now
        # has `since`, so the first run's ETags don't apply); after that, one
        # conditional request per stream, all 304s.
        self.sync(gh)
        c = client(gh)
        self.sync(gh, c)
        self.assertEqual((c.requests, c.not_modified), (4, 4))

    def test_file_layout_and_format(self):
        gh = populated()
        self.sync(gh)
        d = self.files / REPO
        files = sorted(str(p.relative_to(d)) for p in d.rglob("*") if p.is_file())
        self.assertEqual(files, ["issues/1.json", "issues/1/comments.json", "issues/1/events.json",
                                 "issues/2.json", "issues/2/events.json", "issues/3.json",
                                 "pulls/2.json", "pulls/2/comments.json", "pulls/2/reviews.json",
                                 "pulls/3.json", "state.json"])
        text = (d / "issues/2.json").read_text(encoding="utf-8")
        self.assertTrue(text.startswith('{\n  "number": 2,\n'))
        self.assertTrue(text.endswith("}\n") and not text.endswith("\n\n"))
        self.assertEqual(json.loads(text), gh.issues[2])
        # Events are stored without the embedded issue, as /issues/{n}/events returns them.
        self.assertNotIn("issue", json.loads((d / "issues/1/events.json").read_text())[0])
        # An update rewrites the file.
        gh.touch(2, "2025-09-01T00:00:00Z")
        self.sync(gh)
        self.assertEqual(json.loads((d / "issues/2.json").read_text())["updated_at"], "2025-09-01T00:00:00Z")

    def test_incremental_fetches_only_what_changed(self):
        gh = populated()
        self.sync(gh)
        gh.add_comment(2, "2025-06-01T00:00:00Z", "bob")
        c = client(gh)
        self.sync(gh, c)
        self.assertEqual(self.count("comments"), 2)
        self.assertEqual(extract.stale_prs(self.store(), "reviews"), [])
        per_pr = [u for _, u in gh.calls[-c.requests:] if "/pulls/" in u and "/pulls/comments" not in u]
        self.assertEqual(len(per_pr), 2)  # PR 2's pull and reviews, nothing for PR 3

    def test_overlap_catches_a_late_arrival(self):
        gh = populated()
        self.sync(gh)
        # A comment that became visible late, timestamped just before the cursor.
        cursor = self.store().cursor("issue_comments")["cursor"]
        gh.add_comment(1, "2025-01-02T12:00:00Z", "bob", touch=False)
        gh.add_comment(3, cursor, "carol")
        self.sync(gh)
        self.assertEqual(self.count("comments"), 3)

    def test_counts_heal_a_missed_comment(self):
        gh = populated()
        self.sync(gh)
        # A comment far older than the overlap shows up (e.g. it was missed),
        # and the item's updated_at moves, so its count is checked.
        gh.add_comment(1, "2024-06-01T00:00:00Z", "bob", touch=False)
        gh.touch(1, "2025-07-01T00:00:00Z")
        self.sync(gh)
        self.assertEqual(self.count("comments"), 2)
        self.assertEqual(extract.comment_mismatches(self.store()), ([], []))

    def test_deleted_comment_is_dropped(self):
        gh = populated()
        self.sync(gh)
        gh.issue_comments.clear()
        gh.issues[1]["comments"] = 0
        gh.touch(1, "2025-07-01T00:00:00Z")
        self.sync(gh)
        self.assertEqual(self.count("comments"), 0)
        self.assertFalse((self.issue_dir() / "1/comments.json").exists())

    def test_keyset_paging_never_pages_deep(self):
        gh = FakeGitHub(page_limit=1)  # GitHub refuses page 2 and beyond
        for i in range(1, 10):
            gh.add_issue(i, f"2025-01-{i:02d}T00:00:00Z")
        extract.sync_ascending(client(gh), self.store(), "items", **QUIET)
        self.assertEqual(self.count("issues"), 9)

    def test_update_during_listing_skips_nothing(self):
        gh = FakeGitHub()
        for i in range(1, 10):
            gh.add_issue(i, f"2025-01-{i:02d}T00:00:00Z")

        def update_read_item(n):
            if n == 2:  # after the first page: an item we've read is updated
                gh.touch(1, "2025-06-01T00:00:00Z")
        gh.before_request = update_read_item
        extract.sync_ascending(client(gh), self.store(), "items", **QUIET)
        self.assertEqual(self.count("issues"), 9)
        self.assertEqual(self.store().get("issues", 1)["updated_at"], "2025-06-01T00:00:00Z")

    def test_events_floor_falls_back_to_per_item(self):
        gh = FakeGitHub(page=2, page_limit=1)
        for i in range(1, 5):
            gh.add_issue(i, f"2025-01-{i:02d}T00:00:00Z")
            gh.add_event(i, f"2025-01-{i:02d}T01:00:00Z", "labeled", "ed")
        c = client(gh)
        extract.sync_events(c, self.store(), **QUIET)
        self.assertEqual(self.count("events"), 2)  # one page only
        extract.sync_ascending(c, self.store(), "items", **QUIET)
        extract.fetch_item_events(c, self.store(), **QUIET)
        self.assertEqual(self.count("events"), 4)

    def test_reconcile_accounts_for_every_number(self):
        gh = populated()
        self.sync(gh)
        del gh.issues[1]           # deleted on GitHub
        gh.add_issue(6, "2020-01-01T00:00:00Z")  # one we somehow never saw
        gh.transferred.add(5)      # 4 and 5 never existed here: 4 deleted, 5 moved away
        r = extract.reconcile(client(gh), self.store(), **QUIET)
        self.assertEqual(r["highest"], 6)
        self.assertEqual(r["newly_gone"], [1, 4, 5])
        gone = {n: g["reason"] for n, g in self.store().gone().items()}
        self.assertEqual(gone, {1: "deleted", 4: "deleted", 5: "transferred"})
        self.assertEqual(r["stored"] + r["gone"], r["highest"])
        # Everything stored for the deleted item is removed (git keeps it).
        self.assertEqual(sorted(p.name for p in self.issue_dir().iterdir()),
                         ["2", "2.json", "3.json", "6.json"])
        # The next reconcile doesn't recheck known gone numbers.
        c = client(gh)
        extract.reconcile(c, self.store(), **QUIET)
        self.assertFalse([u for _, u in gh.calls[-c.requests:] if re.search(r"/issues/\d+$", u)])

    def test_edits_replace_the_stored_version(self):
        gh = populated()
        self.sync(gh)
        comment = gh.issue_comments[0]
        comment["body"], comment["updated_at"] = "edited", "2025-08-01T00:00:00Z"
        self.sync(gh)
        stored = self.store().get("issues", 1, "comments")
        self.assertEqual([c["body"] for c in stored], ["edited"])

    def test_turning_on_a_pr_resource_later(self):
        gh = populated()
        self.sync(gh)
        c = client(gh)
        n = extract.sync_pr_resources(c, self.store(), resources=["pull", "reviews", "commits"], **QUIET)
        self.assertEqual(n, 2)  # commits for both PRs, nothing else refetched
        self.assertTrue(all("/commits" in u for _, u in gh.calls[-c.requests:]))

    def test_deadline_stops_cleanly_and_the_next_run_continues(self):
        gh = populated()
        for i in range(3):  # enough events for several pages
            gh.add_event(2, f"2025-02-1{i}T00:00:00Z", "labeled", "ann")
        runs = 0
        while True:
            runs += 1
            self.assertLess(runs, 100)
            try:
                self.sync(gh, client(gh, requests=6))
                break
            except github.DeadlineReached:
                pass
        self.assertGreater(runs, 3)
        self.assertEqual(self.store().counts(), {"issues": 1, "prs": 2, "pulls": 2, "comments": 1, "events": 5,
                                                 "reviews": 1, "review_comments": 2, "gone": 0})
        self.assertEqual(extract.comment_mismatches(self.store()), ([], []))
        self.assertEqual(extract.stale_prs(self.store(), "reviews"), [])
        self.assertFalse(list(self.files.rglob("*.tmp")))

    def test_users(self):
        gh = populated()
        gh.add_comment(1, "2025-04-01T00:00:00Z", "dependabot[bot]", typ="Bot")
        gh.profiles = {"ed": "Apple"}
        self.sync(gh)
        logins = extract.users_to_fetch()
        self.assertEqual(logins, ["alice", "ann", "ed"])
        extract.extract_users(client(gh), logins, **QUIET)
        self.assertEqual(extract.users_to_fetch(), [])
        self.assertEqual(extract.load_profiles()["ed"]["company"], "Apple")
        self.assertEqual(extract.stored_repos(), [REPO])


class ClientTest(unittest.TestCase):
    def test_throttle_and_backoff(self):
        sleeps = []
        responses = [(429, {"Retry-After": "7"}, b""), (200, {}, b'{"ok": 1}')]
        c = github.Client(token="t", transport=lambda *a: responses.pop(0), sleep=sleeps.append,
                          clock=lambda: 0.0, **QUIET)
        self.assertEqual(c.rest("/x").data, {"ok": 1})
        self.assertIn(7.0, sleeps)
        self.assertIn(1.0, sleeps)  # the second request waited MIN_INTERVAL

    def test_deadline(self):
        t = [0.0]

        def transport(*a):
            return 200, {"x-ratelimit-remaining": "10", "x-ratelimit-reset": str(time.time() + 600),
                         "x-ratelimit-limit": "5000"}, b"[]"
        c = github.Client(token="t", transport=transport, sleep=lambda s: t.__setitem__(0, t[0] + s),
                          clock=lambda: t[0], seconds_left=60, **QUIET)
        # The budget is low, but the response that said so is still returned...
        self.assertEqual(c.rest("/x").data, [])
        # ...and the 10-minute pause, which would end past the deadline, isn't taken.
        with self.assertRaises(github.DeadlineReached):
            c.rest("/y")
        self.assertEqual((c.requests, t[0]), (1, 0.0))

    def test_secondary_rate_limit(self):
        sleeps = []
        responses = [(403, {}, b'{"message": "You have exceeded a secondary rate limit"}'),
                     (200, {}, b"[]")]
        c = github.Client(token="t", transport=lambda *a: responses.pop(0), sleep=sleeps.append,
                          clock=lambda: 0.0, **QUIET)
        self.assertEqual(c.rest("/x").data, [])
        self.assertIn(30, sleeps)


if __name__ == "__main__":
    unittest.main()
