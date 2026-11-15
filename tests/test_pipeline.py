import json
import os
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
    requests: each takes a second on a fake clock."""
    if requests is None:
        return github.Client(token="t", transport=fake, sleep=lambda s: None, **QUIET)
    t = [0.0]

    def sleep(s):
        t[0] += s

    def transport(*a):
        t[0] += 1
        return fake(*a)
    return github.Client(token="t", transport=transport, sleep=sleep, clock=lambda: t[0],
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
    return gh


FULL = {"issues": 1, "prs": 2, "pulls": 2, "comments": 1, "events": 5, "reviews": 1, "review_comments": 2,
        "gone": 0}


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
        # The fake's data is from early 2025; "now" is just after it.
        clock = mock.patch.object(extract, "now", return_value="2025-04-01T00:00:00Z")
        clock.start()
        self.addCleanup(clock.stop)


class ExtractTest(TempDirs):
    def store(self):
        """A fresh RepoStore each time, so every run starts from the files alone."""
        return extract.RepoStore(REPO)

    def sync(self, gh, c=None, **kw):
        extract.sync_repo(c or client(gh), self.store(), **kw, **QUIET)

    def count(self, what):
        return self.store().counts()[what]

    def issue_dir(self):
        return self.files / REPO / "issues"

    def calls(self, gh, c):
        return [u.split("?")[0].replace(f"https://api.github.com/repos/{REPO}", "")
                for _, u in gh.calls[-c.requests:]]

    def test_backfill_then_unchanged_is_two_304s(self):
        gh = populated()
        self.sync(gh)
        self.assertEqual(self.store().counts(), FULL)
        # The first update re-reads what changed during the backfill; after
        # that, one conditional request for items and one for events.
        self.sync(gh)
        c = client(gh)
        self.sync(gh, c)
        self.assertEqual((c.requests, c.not_modified), (2, 2))

    def test_backfill_fetches_by_number(self):
        gh = populated()
        c = client(gh)
        self.sync(gh, c)
        self.assertEqual(self.calls(gh, c), [
            "/issues/events", "/issues/events", "/issues/events",
            "/issues", "/issues",  # the highest number
            "/issues/1", "/issues/1/comments",
            "/issues/2", "/pulls/2", "/pulls/2/reviews", "/pulls/2/comments",
            "/issues/3", "/pulls/3", "/pulls/3/reviews"])  # no review comments: none to fetch

    def test_backfill_logs_progress(self):
        gh = populated()
        lines = []
        with mock.patch.object(extract, "PROGRESS_EVERY", 2), mock.patch.object(extract, "PROGRESS_PAGES", 2):
            extract.sync_repo(client(gh), self.store(), log=lines.append)
        self.assertEqual([l.split(" (")[0] for l in lines], [
            f"{REPO} events: read 2 pages, back to 2025-02-10T00:00:00Z",
            f"{REPO} events: read back to 2025-02-10T00:00:00Z",
            f"{REPO} items: backfilled up to 2 of 3",
            f"{REPO} items: backfilled numbers 1..3"])

    def test_file_layout_and_format(self):
        gh = populated()
        self.sync(gh)
        d = self.files / REPO
        files = sorted(str(p.relative_to(d)) for p in d.rglob("*") if p.is_file())
        self.assertEqual(files, ["issues/1/comments.json", "issues/1/events.json", "issues/1/index.json",
                                 "issues/2/events.json", "issues/2/index.json",
                                 "issues/3/events.json", "issues/3/index.json",
                                 "pulls/2/comments.json", "pulls/2/index.json", "pulls/2/reviews.json",
                                 "pulls/3/index.json", "state.json"])
        text = (d / "issues/2/index.json").read_text(encoding="utf-8")
        self.assertTrue(text.startswith('{\n  "number": 2,\n'))
        self.assertTrue(text.endswith("}\n") and not text.endswith("\n\n"))
        self.assertEqual(json.loads(text), gh.issues[2])
        # Events are stored without the embedded issue, as /issues/{n}/events returns them.
        self.assertNotIn("issue", json.loads((d / "issues/1/events.json").read_text())[0])

    def test_deleted_and_transferred_numbers_are_gone(self):
        gh = populated()
        gh.add_issue(6, "2025-04-01T00:00:00Z")
        gh.add_event(5, "2025-03-03T00:00:00Z", "labeled", "ed")  # stored, then removed with #5
        gh.add_event(5, "2025-03-04T00:00:00Z", "unlabeled", "ed")  # (an odd count: a full last page fails)
        gh.transferred.add(4)  # moved to another repo: a redirect, not followed
        self.sync(gh)          # 5 was deleted (410)
        self.assertEqual(self.store().gone(), {4, 5})
        self.assertEqual(sorted(int(p.name) for p in self.issue_dir().iterdir()), [1, 2, 3, 6])

    def test_highest_includes_an_issue_transferred_in(self):
        gh = populated()
        # Transferred in after #3 was created: it keeps its older creation
        # date, but gets the next number, and the transfer moves updated_at.
        gh.add_issue(4, "2024-06-01T00:00:00Z")
        gh.touch(4, "2025-03-05T00:00:00Z")
        self.sync(gh)
        self.assertEqual(self.store().section("items")["highest"], 4)
        self.assertIn(4, self.store().index())

    def test_update_syncs_only_what_changed(self):
        gh = populated()
        self.sync(gh)
        self.sync(gh)
        gh.add_comment(1, "2025-06-01T00:00:00Z", "bob")
        c = client(gh)
        self.sync(gh, c)
        self.assertEqual(self.calls(gh, c), ["/issues/events", "/issues", "/issues/1", "/issues/1/comments"])
        self.assertEqual(self.count("comments"), 2)

    def test_new_numbers_fill_the_gap(self):
        gh = populated()
        self.sync(gh)
        gh.add_issue(5, "2025-06-01T00:00:00Z")  # 4 was created and deleted in between
        self.sync(gh)
        self.assertEqual(self.store().gone(), {4})
        self.assertEqual(self.store().section("items")["highest"], 5)
        self.assertIn(5, self.store().index())

    def test_items_created_during_the_backfill(self):
        gh = populated()

        def create(n):
            if n == 4:  # after the highest number was found
                gh.add_issue(4, "2025-05-01T00:00:00Z")
                gh.add_comment(1, "2025-05-02T00:00:00Z", "bob")
        gh.before_request = create
        self.sync(gh)
        gh.before_request = None
        self.sync(gh)
        self.assertIn(4, self.store().index())
        self.assertEqual(self.count("comments"), 2)

    def test_deleted_comment_is_dropped(self):
        gh = populated()
        self.sync(gh)
        gh.issue_comments.clear()
        gh.issues[1]["comments"] = 0
        gh.touch(1, "2025-07-01T00:00:00Z")
        self.sync(gh)
        self.assertEqual(self.count("comments"), 0)
        self.assertFalse((self.issue_dir() / "1/comments.json").exists())

    def test_edits_replace_the_stored_version(self):
        gh = populated()
        self.sync(gh)
        comment = gh.issue_comments[0]
        comment["body"], comment["updated_at"] = "edited", "2025-08-01T00:00:00Z"
        gh.touch(1, "2025-08-01T00:00:00Z")
        self.sync(gh)
        self.assertEqual([c["body"] for c in self.store().get("issues", 1, "comments")], ["edited"])

    def test_update_during_listing_skips_nothing(self):
        gh = populated()
        self.sync(gh)
        for i in range(4, 10):
            gh.add_issue(i, f"2025-06-{i:02d}T00:00:00Z")

        def update_read_item(n):
            # Once #4 has been synced from the first page of the listing,
            # it's updated, so it moves to the end of the listing.
            if gh.calls[-1][1].endswith("/issues/4/comments") or gh.calls[-1][1].endswith("/issues/4"):
                gh.before_request = None
                gh.touch(4, "2025-07-01T00:00:00Z")
        gh.before_request = update_read_item
        self.sync(gh)
        self.assertEqual(sorted(self.store().index()), list(range(1, 10)))
        self.assertEqual(self.store().get("issues", 4)["updated_at"], "2025-07-01T00:00:00Z")

    def test_events_without_an_item_update_are_picked_up(self):
        gh = populated()
        self.sync(gh)
        gh.add_event(1, "2025-09-01T00:00:00Z", "referenced", "bob")  # updated_at doesn't move
        self.sync(gh)
        self.assertEqual(self.count("events"), 6)
        c = client(gh)
        self.sync(gh, c)
        self.assertEqual((c.requests, c.not_modified), (2, 2))

    def test_events_of_deleted_issues_are_dropped(self):
        gh = populated()
        gh.add_event(4, "2025-03-03T00:00:00Z", "labeled", "ed")  # 4 is deleted; its events stay listed
        gh.add_event(4, "2025-03-04T00:00:00Z", "unlabeled", "ed")  # (an odd count: a full last page fails)
        self.sync(gh)
        # 4 is above the highest number, so it isn't known to be gone yet.
        self.assertEqual(self.store().gone(), set())
        self.assertTrue((self.issue_dir() / "4/events.json").exists())
        gh.add_issue(5, "2025-06-01T00:00:00Z")
        gh.touch(5, "2025-06-01T00:00:00Z")
        self.sync(gh)
        self.assertEqual(self.store().gone(), {4})
        self.assertFalse((self.issue_dir() / "4").exists())

    def test_events_listing_that_stops_early_fails(self):
        gh = populated(page_limit=2)
        with self.assertRaisesRegex(extract.CheckFailed, "won't page /issues/events past page 2"):
            self.sync(gh)
        self.assertEqual(self.count("events"), 4)  # the events read are stored

    def test_events_listing_cut_off_silently_fails(self):
        # GitHub ended whatwg/html's listing at page 300: full, with no next link.
        gh = populated(page_cap=2)
        with self.assertRaisesRegex(extract.CheckFailed, "stops at page 2, a full page"):
            self.sync(gh)
        self.assertFalse(self.store().section("events").get("done"))

    def test_closed_item_without_a_closed_event_fails(self):
        gh = populated()
        gh.close(1, "2025-04-01T00:00:00Z", event=False)
        with self.assertRaisesRegex(extract.CheckFailed, r"closed with no `closed` event: 1$"):
            self.sync(gh)

    def test_reconcile_catches_deletions_and_missed_updates(self):
        gh = populated()
        self.sync(gh)
        del gh.issues[1]                        # deleted, which no update listing shows
        gh.issues[3]["title"] = "missed"        # changed, and somehow not seen
        gh.issues[3]["updated_at"] = "2020-01-01T00:00:00Z"
        self.sync(gh)
        self.assertIn(1, self.store().index())
        self.sync(gh, reconcile_=True)
        self.assertEqual(self.store().gone(), {1})
        self.assertFalse((self.issue_dir() / "1").exists())
        self.assertEqual(self.store().get("issues", 3)["title"], "missed")

    def test_changing_pr_resources_fails(self):
        gh = populated()
        self.sync(gh)
        with mock.patch.object(extract, "load_pr_resources", return_value=["pull", "reviews", "commits"]):
            with self.assertRaisesRegex(extract.CheckFailed, "pr_resources"):
                self.sync(gh)

    def test_deadline_stops_cleanly_and_the_next_run_continues(self):
        gh = populated()
        for i in range(2):  # enough events for several pages, and an odd count
            gh.add_event(2, f"2025-02-1{i}T00:00:00Z", "labeled", "ann")
        runs = 0
        while True:
            runs += 1
            self.assertLess(runs, 100)
            try:
                self.sync(gh, client(gh, requests=5))  # events, then a PR: issue, pull, reviews, comments
                break
            except github.DeadlineReached:
                pass
        self.assertGreater(runs, 3)
        self.assertEqual(self.store().counts(), dict(FULL, events=7))
        self.assertFalse(list(self.files.rglob("*.tmp")))

    def test_stored_repos(self):
        self.assertEqual(extract.stored_repos(), [])
        self.sync(populated())
        self.assertEqual(extract.stored_repos(), [REPO])


class ClientTest(unittest.TestCase):
    def test_no_gap_and_server_errors_are_retried(self):
        sleeps = []
        responses = [(502, {}, b""), (200, {}, b'{"ok": 1}'), (200, {}, b'{"ok": 2}')]
        c = github.Client(token="t", transport=lambda *a: responses.pop(0), sleep=sleeps.append,
                          clock=lambda: 0.0, **QUIET)
        self.assertEqual(c.rest("/x").data, {"ok": 1})
        self.assertEqual(c.rest("/y").data, {"ok": 2})
        self.assertEqual(sleeps, [30])  # the retry, and no other waiting

    def test_low_budget_stops_without_waiting(self):
        sleeps = []

        def transport(*a):
            return 200, {"x-ratelimit-remaining": "499", "x-ratelimit-reset": str(time.time() + 600),
                         "x-ratelimit-limit": "5000"}, b"[]"
        c = github.Client(token="t", transport=transport, sleep=sleeps.append, clock=lambda: 0.0, **QUIET)
        # The budget is low, but the response that said so is still returned...
        self.assertEqual(c.rest("/x").data, [])
        # ...and the run stops before the next request instead of waiting.
        with self.assertRaisesRegex(github.RateLimited, "499 left"):
            c.rest("/y")
        self.assertEqual((c.requests, sleeps), (1, []))

    def test_smaller_budget_keeps_a_tenth(self):
        def transport(*a):
            return 200, {"x-ratelimit-remaining": "150", "x-ratelimit-limit": "1000"}, b"[]"
        c = github.Client(token="t", transport=transport, sleep=lambda s: None, **QUIET)
        c.rest("/x")
        c.rest("/y")  # 150 is above a tenth of 1,000
        self.assertEqual(c.requests, 2)

    def test_rate_limit_responses_stop_without_waiting(self):
        for status, headers, body in [
                (429, {"Retry-After": "7"}, b""),
                (403, {}, b'{"message": "You have exceeded a secondary rate limit"}'),
                (403, {"x-ratelimit-remaining": "0", "x-ratelimit-reset": str(time.time() + 600)}, b"{}")]:
            sleeps = []
            c = github.Client(token="t", transport=lambda *a: (status, headers, body), sleep=sleeps.append,
                              clock=lambda: 0.0, **QUIET)
            with self.assertRaises(github.RateLimited):
                c.rest("/x")
            self.assertEqual((c.requests, sleeps), (1, []))

    def test_deadline(self):
        t = [0.0]
        c = github.Client(token="t", transport=lambda *a: (200, {}, b"[]"), sleep=lambda s: None,
                          clock=lambda: t[0], seconds_left=60, **QUIET)
        c.rest("/x")
        t[0] = 61
        with self.assertRaises(github.DeadlineReached):
            c.rest("/y")
        self.assertEqual(c.requests, 1)

    def test_redirect_is_gone(self):
        c = github.Client(token="t", transport=lambda *a: (301, {"Location": "https://api.github.com/x"}, b""),
                          sleep=lambda s: None, **QUIET)
        with self.assertRaises(github.Gone):
            c.rest("/repos/whatwg/html/issues/1")


if __name__ == "__main__":
    unittest.main()
