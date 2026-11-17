import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from specstats import check, extract, github, listing_check, timeline_check
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


START = "2024-06-01T00:00:00Z"

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
        # Items updated since then are fetched: all of populated()'s.
        self.since = mock.patch.object(extract, "load_updated_since", return_value=START)
        self.since.start()
        self.addCleanup(self.since.stop)


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

    def test_backfill_then_unchanged_is_two_requests(self):
        gh = populated()
        self.sync(gh)
        self.assertEqual(self.store().counts(), FULL)
        # One request for items and one for events, and nothing to store.
        c = client(gh)
        self.sync(gh, c)
        self.assertEqual(self.calls(gh, c), ["/issues", "/issues/events"])
        self.assertEqual(self.store().counts(), FULL)

    def test_first_listing_fetches_each_item_by_number(self):
        gh = populated()
        c = client(gh)
        self.sync(gh, c)
        # The listing's rows are stored as the items: no GET /issues/{n}.
        self.assertEqual(self.calls(gh, c), [
            "/issues",  # updated since the start: #1 and #2
            "/issues/1/comments", "/issues/1/events",
            "/issues/2/events", "/pulls/2", "/pulls/2/reviews", "/pulls/2/comments",
            "/issues",  # keyset: since a second before the page's mark (#1's updated_at): the same page,
            "/issues",  # so the offset link, page 2: #3
            "/issues/3/events", "/pulls/3", "/pulls/3/reviews",  # no review comments to fetch
            "/issues/events"])  # after the first listing: events since it started
        self.assertEqual(gh.calls[0][1].split("?")[1],
                         "state=all&sort=updated&direction=asc&per_page=2&since=2024-06-01T00%3A00%3A00Z")

    def test_items_updated_before_the_start_are_not_fetched(self):
        gh = populated()
        gh.add_issue(4, "2024-01-01T00:00:00Z")  # last updated before the start
        gh.add_event(4, "2025-03-10T00:00:00Z", "referenced", "ed")  # doesn't move updated_at
        self.sync(gh)
        self.sync(gh)
        self.assertEqual(sorted(self.store().index()), [1, 2, 3])
        # Its event in the repo-wide listing is dropped, not stored on its own.
        self.assertFalse((self.issue_dir() / "4").exists())
        # Once it's updated, it's fetched whole, events included.
        gh.add_comment(4, "2025-05-01T00:00:00Z", "bob")
        self.sync(gh)
        self.assertEqual(sorted(self.store().index()), [1, 2, 3, 4])
        self.assertEqual(len(self.store().get("issues", 4, "events")), 1)
    def test_first_listing_logs_progress(self):
        gh = populated()
        lines = []
        extract.sync_repo(client(gh), self.store(), log=lines.append)
        self.assertEqual([l.split(" (")[0] for l in lines], [
            f"{REPO} items: synced 2 of 2 listed, up to 2025-01-03T00:00:00Z",  # the page's mark
            f"{REPO} items: synced 1 of 1 listed, up to 2025-03-02T00:00:00Z",
            f"{REPO} items: synced 3 changed",
            f"{REPO} events: stored 0"])
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

    def test_deleted_and_transferred_numbers_are_not_fetched(self):
        gh = populated()
        gh.add_issue(6, "2025-04-01T00:00:00Z")
        gh.add_event(5, "2025-03-03T00:00:00Z", "labeled", "ed")
        gh.transferred.add(4)  # moved to another repo, and 5 deleted: neither is listed
        c = client(gh)
        self.sync(gh, c)
        self.assertFalse([u for u in self.calls(gh, c) if u.startswith(("/issues/4", "/issues/5"))])
        self.assertEqual(self.store().gone(), set())
        self.assertEqual(sorted(int(p.name) for p in self.issue_dir().iterdir()), [1, 2, 3, 6])
    def test_listed_item_deleted_before_it_is_synced_is_gone(self):
        gh = populated()

        def delete(n):
            if gh.calls[-1][1].split("?")[0].endswith("/issues/1/comments"):
                del gh.issues[1]  # after the listing returned it
        gh.before_request = delete
        self.sync(gh)
        self.assertEqual(self.store().gone(), {1})
        self.assertFalse((self.issue_dir() / "1").exists())
        self.assertIn(2, self.store().index())

    def test_an_issue_transferred_in_is_listed(self):
        gh = populated()
        # Transferred in after #3 was created: it keeps its older creation
        # date, but gets the next number, and the transfer moves updated_at.
        gh.add_issue(4, "2024-01-01T00:00:00Z")
        gh.touch(4, "2025-03-05T00:00:00Z")
        self.sync(gh)
        self.assertIn(4, self.store().index())
    def test_update_syncs_only_what_changed(self):
        gh = populated()
        self.sync(gh)
        self.sync(gh)
        gh.add_comment(1, "2025-06-01T00:00:00Z", "bob")
        c = client(gh)
        self.sync(gh, c)
        self.assertEqual(self.calls(gh, c), ["/issues", "/issues/1/comments", "/issues/1/events",
                                             "/issues/events"])
        self.assertEqual(self.count("comments"), 2)

    def test_new_items_are_fetched(self):
        gh = populated()
        self.sync(gh)
        gh.add_issue(5, "2025-06-01T00:00:00Z")  # 4 was created and deleted in between
        self.sync(gh)
        self.assertEqual(sorted(self.store().index()), [1, 2, 3, 5])
        self.assertEqual(self.store().gone(), set())
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
            # While #4, from the first page of the listing, is being
            # synced, it's updated, so it moves to the end of the listing,
            # and the stored row is out of date until it's listed again.
            if gh.calls[-1][1].split("?")[0].endswith("/issues/4/events"):
                gh.before_request = None
                gh.touch(4, "2025-07-01T00:00:00Z")
        gh.before_request = update_read_item
        self.sync(gh)
        self.assertEqual(sorted(self.store().index()), list(range(1, 10)))
        self.assertEqual(self.store().get("issues", 4)["updated_at"], "2025-07-01T00:00:00Z")

    def test_rows_out_of_place_in_the_listing_skip_nothing(self):
        # whatwg/html #127, #2973, #1518 and #7617 came among rows updated by
        # 2026-10-02 with updated_at from 2026-10-08 to 2026-10-19; going on
        # from the newest skipped the 98 items in between.
        gh = FakeGitHub()
        for n in range(1, 13):
            gh.add_issue(n, f"2025-01-{n:02d}T00:00:00Z")
        for n in (3, 4):  # sorted where they were, returned as updated later
            gh.sort_keys[n] = gh.issues[n]["updated_at"]
            gh.touch(n, f"2025-01-2{n}T00:00:00Z")
        with mock.patch.object(extract, "PER_PAGE", 4):
            self.sync(gh)
        self.assertEqual(sorted(self.store().index()), list(range(1, 13)))

    def test_events_without_an_item_update_are_picked_up(self):
        gh = populated()
        self.sync(gh)
        gh.add_event(1, "2025-09-01T00:00:00Z", "referenced", "bob")  # updated_at doesn't move
        self.sync(gh)
        self.assertEqual(self.count("events"), 6)
        c = client(gh)
        self.sync(gh, c)
        self.assertEqual(c.requests, 2)

    def test_events_of_items_not_stored_are_dropped(self):
        gh = populated()
        # 4 is deleted, but its events stay in the repo-wide listing; they're
        # newer than the first listing, so the first read of the events listing has them.
        gh.add_event(4, "2025-05-01T00:00:00Z", "labeled", "ed")
        gh.add_event(4, "2025-05-02T00:00:00Z", "unlabeled", "ed")
        self.sync(gh)
        self.assertFalse((self.issue_dir() / "4").exists())
        self.assertEqual(check.check_repo(self.store()), [])
    def test_backfill_reads_no_events_listing(self):
        # Events come with each item, so a backfill doesn't depend on how far
        # back GitHub pages the repo-wide listing (300 pages for whatwg/html).
        gh = populated(page_limit=1)
        with self.assertRaises(github.DeadlineReached):
            self.sync(gh, client(gh, requests=8))  # stops mid-backfill
        self.assertFalse([u for _, u in gh.calls if "/issues/events" in u])
        self.assertGreater(self.count("events"), 0)

    def new_events(self, gh, count):
        for i in range(count):
            gh.add_event(1, f"2025-05-0{i + 1}T00:00:00Z", "labeled", "ed")

    def test_events_listing_that_stops_early_fails(self):
        gh = populated()
        self.sync(gh)
        self.new_events(gh, 5)
        gh.page_limit = 2
        with self.assertRaisesRegex(extract.CheckFailed, "won't page /issues/events back to"):
            self.sync(gh)
        self.assertEqual(self.count("events"), 9)  # the events read are stored

    def test_events_listing_cut_off_silently_fails(self):
        # GitHub ended whatwg/html's listing at page 300: full, with no next link.
        gh = populated()
        self.sync(gh)
        self.new_events(gh, 5)
        gh.page_cap = 2
        with self.assertRaisesRegex(extract.CheckFailed, "a full page with no next link"):
            self.sync(gh)

    def test_inconsistent_data_is_stored_and_found_by_check(self):
        # GitHub's data isn't always consistent (whatwg/fullscreen #220: a
        # closed PR with no events at all). The fetch stores it and passes;
        # check reports it.
        gh = populated()
        gh.close(1, "2025-04-01T00:00:00Z", event=False)
        self.sync(gh)
        self.assertEqual(self.store().get("issues", 1)["state"], "closed")
        self.assertEqual(check.check_repo(self.store()), [("closed with no `closed` event", [1])])
        text, found = check.report()
        self.assertTrue(found)
        self.assertIn("closed with no `closed` event: 1", text)

    def test_check_finds_process_bugs(self):
        gh = populated()
        self.sync(gh)
        self.assertEqual(check.check_repo(self.store()), [])
        self.assertEqual(check.report(), (f"# Consistency checks\n\n- {REPO}: OK\n", False))
        # As if files went missing between fetching and committing.
        (self.files / REPO / "pulls/3/index.json").unlink()
        (self.issue_dir() / "1/index.json").unlink()
        self.assertEqual(check.check_repo(extract.RepoStore(REPO)), [
            ("a PR with no pulls/{n}/index.json (and no 422 recorded for it)", [3]),
            ("events stored for a number with no issues/{n}/index.json", [1])])

    def test_pull_refused_with_422_is_recorded_and_the_rest_stored(self):
        # whatwg/dom #548: GET /pulls/548 answers 422 "too many files changed".
        gh = populated()
        too_many = "The request could not be processed because too many files changed"
        gh.unprocessable["/pulls/2"] = too_many
        c = client(gh)
        self.sync(gh, c)
        store = self.store()
        self.assertIsNone(store.get("pulls", 2))
        self.assertIsNotNone(store.get("pulls", 2, "reviews"))
        self.assertEqual(len(store.get("pulls", 2, "comments")), 2)  # fetched: no count to say there are none
        self.assertEqual(store.get("issues", 2)["number"], 2)
        self.assertEqual({n: {k: v for k, v in r.items() if k != "checked_at"} for n, r in store.refused().items()},
                         {2: {"pull": too_many}})
        self.assertEqual(check.check_repo(store), [])
        text, found = check.report()
        self.assertFalse(found)
        self.assertIn(f"(refused by GitHub, not a finding) #2 pull: {too_many}", text)
        # The next run fetches the item again, changed or not; while GitHub
        # still refuses, the record stays.
        c = client(gh)
        self.sync(gh, c)
        self.assertEqual(self.calls(gh, c)[0], "/issues/2")
        self.assertEqual(set(self.store().refused()), {2})
        # Once GitHub answers (whatwg/dom #548's did, a run later), it's
        # stored and the record dropped.
        del gh.unprocessable["/pulls/2"]
        self.sync(gh)
        self.assertIsNotNone(self.store().get("pulls", 2))
        self.assertEqual(self.store().refused(), {})

    def test_other_422s_still_fail(self):
        gh = populated()
        gh.unprocessable["/pulls/2/reviews"] = "something else"
        with self.assertRaisesRegex(github.Unprocessable, "something else"):
            self.sync(gh)

    def test_stopped_first_listing_continues_and_then_reads_events(self):
        gh = populated()
        with self.assertRaises(github.DeadlineReached):
            self.sync(gh, client(gh, requests=6))  # the listing and #1, then stops in #2
        self.assertEqual(sorted(self.store().index()), [1])
        self.assertNotIn("events", self.store().state)
        self.assertEqual(check.check_repo(self.store()), [])
        self.sync(gh)
        self.assertEqual(self.store().counts(), FULL)
        self.assertEqual(self.store().section("events")["cursor"], "2025-04-01T00:00:00Z")
        self.assertNotIn("started", self.store().section("items"))
    def test_reconcile_catches_deletions_and_missed_updates(self):
        gh = populated()
        gh.add_issue(4, "2024-01-01T00:00:00Z")  # updated before the start: not fetched
        self.sync(gh)
        gh.transferred.add(2)                   # transferred, and
        del gh.issues[1], gh.issues[2]          # deleted, which no update listing shows
        gh.issues[3]["title"] = "missed"        # changed, and somehow not seen
        gh.issues[3]["updated_at"] = "2025-03-01T12:00:00Z"
        self.sync(gh)
        self.assertIn(1, self.store().index())
        c = client(gh)
        self.sync(gh, c, reconcile_=True)
        self.assertNotIn("/issues/4", self.calls(gh, c))
        self.assertEqual(self.store().gone(), {1, 2})
        self.assertFalse((self.issue_dir() / "1").exists())
        self.assertEqual(self.store().get("issues", 3)["title"], "missed")

    def test_moving_the_start_back_fetches_only_the_items_in_between(self):
        gh = populated()
        gh.add_issue(4, "2023-06-01T00:00:00Z")
        gh.add_issue(5, "2023-01-01T00:00:00Z")
        self.sync(gh)
        self.assertEqual(sorted(self.store().index()), [1, 2, 3])
        self.since.stop()
        with mock.patch.object(extract, "load_updated_since", return_value="2023-03-01T00:00:00Z"):
            c = client(gh)
            self.sync(gh, c)
        self.assertEqual(self.calls(gh, c), [
            "/issues",  # updates: nothing changed
            "/issues", "/issues/4/events",  # since the new start: #4, and #1 (after the old start)
            "/issues", "/issues",  # the keyset (the same page) and the offset link, until the mark
            # passes the old start
            "/issues/events"])
        self.assertEqual(sorted(self.store().index()), [1, 2, 3, 4])
        items = self.store().section("items")
        self.assertEqual(items["from"], "2023-03-01T00:00:00Z")
        self.assertNotIn("extend", items)
        # Moving it forward again removes what's last updated before it,
        # and fetches nothing.
        self.since.start()
        c = client(gh)
        self.sync(gh, c)
        self.assertEqual((c.requests, self.store().section("items")["from"]), (2, START))
        self.assertEqual(sorted(self.store().index()), [1, 2, 3])
        self.assertFalse((self.issue_dir() / "4").exists())

    def test_moving_the_start_back_resumes_where_it_stopped(self):
        gh = populated()
        for i in range(4, 10):
            gh.add_issue(i, f"2023-0{i}-01T00:00:00Z")
        self.sync(gh)
        self.since.stop()
        with mock.patch.object(extract, "load_updated_since", return_value="2023-01-01T00:00:00Z"):
            runs = 0
            while True:
                runs += 1
                self.assertLess(runs, 20)
                try:
                    self.sync(gh, client(gh, requests=6))
                    break
                except github.DeadlineReached:
                    self.assertIn("extend", self.store().section("items"))
        self.assertGreater(runs, 2)
        self.assertEqual(sorted(self.store().index()), list(range(1, 10)))
        self.assertEqual(self.store().section("items")["from"], "2023-01-01T00:00:00Z")

    def test_by_number_state_is_converted(self):
        gh = populated()
        gh.add_issue(4, "2024-01-01T00:00:00Z")  # last updated before the start
        gh.unprocessable["/pulls/2"] = "too many files changed"
        self.since.stop()
        with mock.patch.object(extract, "load_updated_since", return_value="2023-01-01T00:00:00Z"):
            self.sync(gh)
        self.since.start()
        del gh.unprocessable["/pulls/2"]
        store = self.store()
        del store.state["items"]["from"]
        # A finished by-number backfill: it keeps its cursor, starts at
        # `since`, and what's last updated before that is removed.
        store.state["items"]["highest"] = 4
        store.state["refused"]["4"] = {"pull": "as if", "checked_at": "2025-04-01T00:00:00Z"}
        store.save_state()
        c = client(gh)
        self.sync(gh, c)
        self.assertEqual(self.calls(gh, c)[0], "/issues/2")  # the 422 retried; #4's record went with it
        self.assertEqual(self.store().refused(), {})
        self.assertEqual(sorted(self.store().index()), [1, 2, 3])
        self.assertFalse((self.issue_dir() / "4").exists())
        self.assertEqual(self.store().section("items"),  # the last page's mark: #2
                         {"cursor": "2025-02-10T00:00:00Z", "from": START})
        # An unfinished one: the listing starts from the start date, and
        # skips what's stored unchanged.
        store = self.store()
        store.state["items"] = {"started": "2025-03-01T00:00:00Z", "highest": 3, "next": 2}
        del store.state["events"]
        store.save_state()
        gh.add_comment(3, "2025-05-01T00:00:00Z", "bob")
        c = client(gh)
        self.sync(gh, c)
        self.assertEqual([u for u in self.calls(gh, c) if u != "/issues"],
                         ["/issues/3/comments", "/issues/3/events", "/pulls/3", "/pulls/3/reviews",
                          "/issues/events"])
        self.assertEqual(self.store().section("items"), {"from": START, "cursor": "2025-05-01T00:00:00Z"})

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
                self.sync(gh, client(gh, requests=7))  # a page of the listing, and the biggest item:
                # #2's issue, events (2 pages), pull, reviews and review comments
                break
            except github.DeadlineReached:
                pass
        self.assertGreater(runs, 2)
        self.assertEqual(self.store().counts(), dict(FULL, events=7))
        self.assertFalse(list(self.files.rglob("*.tmp")))

    def test_stored_repos(self):
        self.assertEqual(extract.stored_repos(), [])
        self.sync(populated())
        self.assertEqual(extract.stored_repos(), [REPO])


class TimelineCheckTest(TempDirs):
    def test_report(self):
        env = mock.patch.dict(os.environ, {"SPECSTATS_DATA": str(Path(self.tmp.name) / "private")})
        env.start()
        self.addCleanup(env.stop)
        gh = populated()
        extract.sync_repo(client(gh), extract.RepoStore(REPO), **QUIET)
        store = extract.RepoStore(REPO)
        dropped_comment = gh.issue_comments[0]["id"]
        dropped_event = gh.events[0]["id"]
        gh.timeline_drop = {dropped_comment, dropped_event}
        gh.add_comment(1, "2025-05-01T00:00:00Z", "ann")  # after the stored fetch: new
        numbers = timeline_check.sample(store, 10)
        self.assertEqual(numbers, [1, 2, 3])
        out = timeline_check.check(client(gh), store, numbers, **QUIET)
        self.assertIn("| comments | 1 | 1 | 0 | 1 | 0 | 1 |", out)
        self.assertIn("| reviews | 1 | 1 | 1 | 0 | 0 | 0 |", out)
        self.assertIn("| review_comments | 2 | 2 | 2 | 0 | 0 | 0 |", out)
        self.assertIn(f"Stored but not in the timeline: #1 {dropped_comment}", out)
        self.assertIn("Fields only in the timeline's copy: `event` (1)", out)
        self.assertIn("Timeline entries without an id: `line-commented` (1)", out)
        self.assertTrue((Path(self.tmp.name) / "private/timeline" / REPO / "2.json").exists())
        self.assertFalse((self.files / REPO / "issues/1/timeline.json").exists())


class ListingCheckTest(unittest.TestCase):
    def test_report(self):
        gh = populated()
        self.assertIn("of the 3 compared (1 issues, 2 PRs), 3 are identical",
                      listing_check.check(client(gh), REPO, size=2, **QUIET))
        self.assertIn("No differences", listing_check.check(client(gh), REPO, size=2, **QUIET))

        def transport(method, url, body, headers):
            status, h, data = gh(method, url, body, headers)
            if "/issues/" in url:  # GET /issues/{n}: one field more, one less, one different
                obj = json.loads(data)
                obj["extra"], obj["user"]["login"] = 1, "someone"
                del obj["labels"]
                data = json.dumps(obj).encode()
            elif url.endswith("direction=desc&per_page=2"):  # changed in between
                rows = json.loads(data)
                rows[0]["updated_at"] = "2020-01-01T00:00:00Z"
                data = json.dumps(rows).encode()
            return status, h, data
        c = github.Client(token="t", transport=transport, sleep=lambda s: None, **QUIET)
        out = listing_check.check(c, REPO, size=2, **QUIET)
        self.assertIn("1 skipped (changed in between); of the 2 compared (1 issues, 1 PRs), 0 are identical", out)
        self.assertIn("| only in GET /issues/{n} | `extra` | 2 | #2: 1 |", out)
        self.assertIn("| only in the listing | `labels` | 2 | #2: [] |", out)
        self.assertIn("| different values | `user.login` | 2 | #2: listing 'alice', GET 'someone' |", out)


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
            return 200, {"x-ratelimit-remaining": "500", "x-ratelimit-reset": str(time.time() + 600),
                         "x-ratelimit-limit": "5000"}, b"[]"
        c = github.Client(token="t", transport=transport, sleep=sleeps.append, clock=lambda: 0.0, **QUIET)
        # The budget is low, but the response that said so is still returned...
        self.assertEqual(c.rest("/x").data, [])
        # ...and the run stops before the next request instead of waiting.
        with self.assertRaisesRegex(github.RateLimited, "500 left"):
            c.rest("/y")
        self.assertEqual((c.requests, sleeps), (1, []))

    def test_rate_limit_is_logged_once(self):
        lines = []

        def transport(*a):
            return 200, {"x-ratelimit-remaining": "4990", "x-ratelimit-limit": "5000"}, b"[]"
        c = github.Client(token="t", transport=transport, sleep=lambda s: None, log=lines.append)
        c.rest("/x")
        c.rest("/y")
        self.assertEqual(c.rate_limit, 5000)
        self.assertEqual(lines, ["rate limit: 5000 an hour, 4990 left (no reset time given)"])

    def test_one_above_the_reserve_continues(self):
        def transport(*a):
            return 200, {"x-ratelimit-remaining": "501", "x-ratelimit-limit": "5000"}, b"[]"
        c = github.Client(token="t", transport=transport, sleep=lambda s: None, **QUIET)
        c.rest("/x")
        c.rest("/y")
        self.assertEqual(c.requests, 2)

    def test_smaller_budget_keeps_a_tenth(self):
        remaining = ["150", "101", "100"]

        def transport(*a):
            return 200, {"x-ratelimit-remaining": remaining.pop(0), "x-ratelimit-limit": "1000"}, b"[]"
        c = github.Client(token="t", transport=transport, sleep=lambda s: None, **QUIET)
        for path in ("/x", "/y", "/z"):  # 150 and 101 are above a tenth of 1,000; 100 isn't
            c.rest(path)
        with self.assertRaisesRegex(github.RateLimited, "100 left"):
            c.rest("/w")
        self.assertEqual(c.requests, 3)

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
