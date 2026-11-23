import json

from specstats import build, extract
from tests.fakegithub import REPO
from tests.test_pipeline import QUIET, START, TempDirs, client, populated

# START is 2024-06-01. The window ends the day before the newest
# updated_at seen (the repo's cursor).
STANDARDS = {REPO: "DOM"}


def day(date):
    return (build._day(date) - build._day(START)).days


class BuildTest(TempDirs):
    def sync(self, gh, **kw):
        extract.sync_repo(client(gh), extract.RepoStore(REPO), **kw, **QUIET)

    def build(self, standards=STANDARDS):
        logs = []
        data = build.build(standards=standards, updated_since=START, log=logs.append)
        return data, logs

    def rows(self, data):
        """number -> (kind, created, closed, later_in_day)"""
        items = build.expand(data)
        return {n: (k, c, cl, li) for n, k, c, cl, li in
                zip(items["number"], items["kind"], items["created"], items["closed"], items["later_in_day"])}

    def test_prs(self):
        gh = populated()  # #1 an open issue, #2 and #3 PRs merged in the window
        # Open when the window starts, closed in it.
        gh.add_issue(10, "2024-01-01T00:00:00Z", is_pr=True)
        gh.close(10, "2025-01-15T00:00:00Z")
        # Closed before the window starts, touched in it: not an item.
        gh.add_issue(11, "2024-01-01T00:00:00Z", is_pr=True, closed_at="2024-02-01T00:00:00Z")
        gh.add_comment(11, "2025-01-05T00:00:00Z", "ed")
        # Open since before the window, never touched since (fetched as an old open item).
        gh.add_issue(12, "2023-01-01T00:00:00Z", is_pr=True)
        # Closed and reopened in the window: open.
        gh.add_issue(13, "2025-01-01T00:00:00Z", is_pr=True)
        gh.close(13, "2025-01-02T00:00:00Z")
        gh.add_event(13, "2025-01-03T00:00:00Z", "reopened", "ed")
        gh.issues[13]["state"] = "open"
        gh.touch(13, "2025-01-03T00:00:00Z")
        # Closed, then reopened and closed again on one day: closed then.
        gh.add_issue(16, "2025-02-01T00:00:00Z", is_pr=True)
        gh.close(16, "2025-02-05T00:00:00Z")
        gh.add_event(16, "2025-02-20T09:00:00Z", "reopened", "ed")
        gh.close(16, "2025-02-20T17:00:00Z")
        # Closed after the window ends: open at its end.
        gh.add_issue(14, "2025-03-15T00:00:00Z", is_pr=True)
        gh.close(14, "2025-04-01T12:00:00Z")
        # Created after the window ends: not there at all.
        gh.add_issue(15, "2025-04-01T06:00:00Z", is_pr=True)
        # A draft is an open PR like any other.
        gh.add_issue(17, "2025-03-20T00:00:00Z", is_pr=True)
        gh.pulls[17]["draft"] = True
        self.sync(gh)

        data, logs = self.build()
        self.assertEqual(data["meta"], {"from": "2024-06-01", "to": "2025-03-31"})
        self.assertEqual(set(data), {"meta", "repos", "items"})
        self.assertEqual(data["repos"], {"name": ["dom"], "standard": ["DOM"]})
        self.assertEqual(self.rows(data), {
            1: (0, day("2025-01-01"), None, 0),
            # Merged 9 days after it was created, and 1 day after.
            2: (2, day("2025-02-01"), 9, 0),
            3: (2, day("2025-03-01"), 1, 0),
            10: (1, day("2024-01-01"), day("2025-01-15") - day("2024-01-01"), 0),
            12: (1, day("2023-01-01"), None, 0),
            13: (1, day("2025-01-01"), None, 0),
            14: (1, day("2025-03-15"), None, 0),
            # From creation to the last close: 19 days and 17 hours.
            16: (1, day("2025-02-01"), 19, 1),
            17: (1, day("2025-03-20"), None, 0),
        })
        self.assertLess(day("2023-01-01"), 0)  # opened before the window
        # As stored: numbers and creation days as differences from the
        # previous item of the same repo.
        self.assertEqual(data["items"]["number"], [1, 1, 1, 7, 2, 1, 1, 2, 1])
        self.assertEqual(data["items"]["created"][:2], [day("2025-01-01"), day("2025-02-01") - day("2025-01-01")])
        self.assertEqual(logs, [])

    def test_issues(self):
        gh = populated()  # #1 an issue, open
        # Closed in the window 2 days and an hour after it was created.
        gh.add_issue(10, "2025-01-01T00:00:00Z")
        gh.close(10, "2025-01-03T01:00:00Z")
        # Open when the window starts, closed, reopened and closed again in
        # it: counted from creation to the last close.
        gh.add_issue(11, "2024-05-01T00:00:00Z")
        gh.close(11, "2025-01-10T00:00:00Z")
        gh.add_event(11, "2025-01-12T00:00:00Z", "reopened", "ed")
        gh.close(11, "2025-01-20T00:00:00Z")
        # Closed in the window, then reopened: open at the end.
        gh.add_issue(12, "2025-01-01T00:00:00Z")
        gh.close(12, "2025-01-05T00:00:00Z")
        gh.add_event(12, "2025-01-06T00:00:00Z", "reopened", "ed")
        gh.issues[12]["state"] = "open"
        gh.touch(12, "2025-01-06T00:00:00Z")
        # Closed before the window started, touched in it: not an item.
        gh.add_issue(13, "2024-01-01T00:00:00Z", closed_at="2024-02-01T00:00:00Z")
        gh.add_comment(13, "2025-01-05T00:00:00Z", "ed")
        # Closed after the window ends: open at its end.
        gh.add_issue(14, "2025-03-15T00:00:00Z")
        gh.close(14, "2025-04-01T12:00:00Z")
        # Closed with no `closed` event: the issue's own state wins.
        gh.add_issue(15, "2025-01-01T00:00:00Z")
        gh.close(15, "2025-01-02T00:00:00Z", event=False)
        # Closed before the window started, reopened and closed again in
        # it: open from its creation, as GitHub search counts it.
        gh.add_issue(16, "2024-01-01T00:00:00Z", closed_at="2024-02-01T00:00:00Z")
        gh.add_event(16, "2025-02-01T00:00:00Z", "reopened", "ed")
        gh.close(16, "2025-02-02T00:00:00Z")
        self.sync(gh)
        data, logs = self.build()
        rows = self.rows(data)
        self.assertNotIn(13, rows)
        self.assertEqual({n: r for n, r in rows.items() if r[0] == 0}, {
            1: (0, day("2025-01-01"), None, 0),
            10: (0, day("2025-01-01"), 2, 1),
            11: (0, day("2024-05-01"), day("2025-01-20") - day("2024-05-01"), 0),
            12: (0, day("2025-01-01"), None, 0),
            14: (0, day("2025-03-15"), None, 0),
            15: (0, day("2025-01-01"), 1, 0),
            16: (0, day("2024-01-01"), day("2025-02-02") - day("2024-01-01"), 0),
        })
        self.assertEqual(logs, ["fixed up from the item's own state (closed with no `closed` event): 1"])

    def test_time_open_rounds_up_to_whole_days(self):
        gh = populated()
        # Merged 24 hours and 1 second after it was created: 2 days.
        gh.add_issue(10, "2025-01-05T00:00:00Z", is_pr=True, merged_at="2025-01-06T00:00:01Z", merged_by="ed")
        # Exactly 24 hours: 1 day.
        gh.add_issue(11, "2025-01-05T12:00:00Z", is_pr=True, merged_at="2025-01-06T12:00:00Z", merged_by="ed")
        # 12 hours across midnight: 1 day.
        gh.add_issue(12, "2025-01-05T20:00:00Z", is_pr=True, merged_at="2025-01-06T08:00:00Z", merged_by="ed")
        # Within the same day: 1 day.
        gh.add_issue(13, "2025-01-05T08:00:00Z", is_pr=True, merged_at="2025-01-05T09:00:00Z", merged_by="ed")
        # Created as a draft: still from its creation.
        gh.add_issue(14, "2025-01-01T00:00:00Z", is_pr=True, draft_ready_at="2025-01-03T00:00:00Z",
                     merged_at="2025-01-03T06:00:00Z", merged_by="ed")
        # Merged in the window, but created before it started.
        gh.add_issue(15, "2024-05-01T12:00:00Z", is_pr=True, merged_at="2025-01-01T12:00:00Z", merged_by="ed")
        self.sync(gh)
        data, logs = self.build()
        rows = self.rows(data)
        days_open = {n: rows[n][2] + rows[n][3] for n in range(10, 16)}
        self.assertEqual(days_open, {10: 2, 11: 1, 12: 1, 13: 1, 14: 3, 15: day("2025-01-01") - day("2024-05-01")})
        self.assertEqual({rows[n][0] for n in range(10, 16)}, {2})
        self.assertEqual(logs, [])

    def test_the_items_own_state_wins(self):
        gh = populated()
        gh.add_issue(10, "2025-01-01T00:00:00Z", is_pr=True)
        gh.close(10, "2025-02-01T00:00:00Z", event=False)  # whatwg/fullscreen #220
        gh.add_issue(11, "2025-01-01T00:00:00Z", is_pr=True)
        gh.close(11, "2025-01-10T00:00:00Z")
        gh.add_event(11, "2025-01-20T00:00:00Z", "closed", "ed")  # closed twice: the first counts
        # Merged, with a later `closed` and `reopened` (never seen on GitHub):
        # closed at the merge.
        gh.add_issue(12, "2025-01-01T00:00:00Z", is_pr=True, merged_at="2025-01-05T00:00:00Z", merged_by="ed")
        gh.add_event(12, "2025-01-07T00:00:00Z", "reopened", "ed")
        gh.add_event(12, "2025-01-09T00:00:00Z", "closed", "ed")
        self.sync(gh)
        data, logs = self.build()
        rows = self.rows(data)
        self.assertEqual(rows[10], (1, day("2025-01-01"), 31, 0))
        self.assertEqual(rows[11], (1, day("2025-01-01"), 9, 0))
        self.assertEqual(rows[12], (2, day("2025-01-01"), 4, 0))
        self.assertEqual(logs, [
            "fixed up from the item's own state (closed with no `closed` event): 1",
            "fixed up from the item's own state (merged, but its last close isn't the merge: closed at the merge): 1"])

    def test_incomplete_repos_are_left_out(self):
        gh = populated()
        self.sync(gh)
        store = extract.RepoStore(REPO)
        store.state["items"]["started"] = "2025-04-01T00:00:00Z"  # first listing not done
        store.save_state()
        with self.assertRaisesRegex(ValueError, "no repo has complete data"):
            self.build()
        del store.state["items"]["started"]
        store.save_state()
        data, logs = self.build(dict(STANDARDS, **{"whatwg/url": "URL"}))
        self.assertEqual(data["repos"]["name"], ["dom"])
        self.assertEqual(logs, ["whatwg/url: nothing stored; left out"])

    def test_the_window_ends_before_the_newest_time_seen_in_any_repo(self):
        gh = populated()
        self.sync(gh)
        store = extract.RepoStore(REPO)
        self.assertEqual(store.state["items"]["cursor"], "2025-03-02T00:00:00Z")
        self.assertEqual(self.build()[0]["meta"]["to"], "2025-03-01")
        store.state["items"]["rows"] = "2025-03-25T10:00:00Z"
        store.save_state()
        self.assertEqual(self.build()[0]["meta"]["to"], "2025-03-24")
        other = extract.RepoStore("whatwg/url")
        other.state = dict(store.state, items=dict(store.state["items"], cursor="2025-03-28T08:00:00Z"))
        other.save_state()
        data, _ = self.build(dict(STANDARDS, **{"whatwg/url": "URL"}))
        self.assertEqual((data["meta"]["to"], data["repos"]["name"]), ("2025-03-27", ["dom", "url"]))

    def test_repos_are_in_spec_order(self):
        gh = populated()
        self.sync(gh)
        store = extract.RepoStore(REPO)
        other = extract.RepoStore("whatwg/bluetooth")
        other.state = store.state
        other.save_state()
        data, _ = self.build(dict(STANDARDS, **{"whatwg/bluetooth": "Web Bluetooth"}))
        self.assertEqual(data["repos"], {"name": ["dom", "bluetooth"], "standard": ["DOM", "Web Bluetooth"]})

    def test_spec_order(self):
        names = ["XMLHttpRequest", "WebUSB", "Web IDL", "WebHID", "WebNFC", "URL Pattern", "URL", "HTML", "Fetch"]
        self.assertEqual(sorted(names, key=build.spec_order),
                         ["Fetch", "HTML", "URL", "URL Pattern", "WebHID", "Web IDL", "WebNFC", "WebUSB",
                          "XMLHttpRequest"])

    def test_write(self):
        gh = populated()
        self.sync(gh)
        data, _ = self.build()
        path, size = build.write(data, self.files.parent / "out" / "data.json")
        self.assertEqual(json.loads(path.read_text()), data)
        self.assertEqual(size, path.stat().st_size)
