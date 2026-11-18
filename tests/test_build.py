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

    def events(self, data):
        """number -> [(day, event type)]"""
        out = {}
        items, ev = data["items"], data["events"]
        for d, i, e in zip(ev["day"], ev["item"], ev["event"]):
            out.setdefault(items["number"][i], []).append((d, data["event_types"][e]))
        return out

    def test_open_prs(self):
        gh = populated()  # #1 an issue, #2 and #3 PRs merged in the window
        # Open when the window starts, closed in it.
        gh.add_issue(10, "2024-01-01T00:00:00Z", is_pr=True)
        gh.close(10, "2025-01-15T00:00:00Z")
        # Closed before the window starts, touched in it: no events in the window.
        gh.add_issue(11, "2024-01-01T00:00:00Z", is_pr=True, closed_at="2024-02-01T00:00:00Z")
        gh.add_comment(11, "2025-01-05T00:00:00Z", "ed")
        # Open since before the window, never touched since (fetched as an old open item).
        gh.add_issue(12, "2023-01-01T00:00:00Z", is_pr=True)
        # Closed and reopened in the window.
        gh.add_issue(13, "2025-01-01T00:00:00Z", is_pr=True)
        gh.close(13, "2025-01-02T00:00:00Z")
        gh.add_event(13, "2025-01-03T00:00:00Z", "reopened", "ed")
        gh.issues[13]["state"] = "open"
        gh.touch(13, "2025-01-03T00:00:00Z")
        # Reopened and closed again on one day: both kept, in time order.
        gh.add_issue(16, "2025-02-01T00:00:00Z", is_pr=True)
        gh.close(16, "2025-02-05T00:00:00Z")
        gh.add_event(16, "2025-02-20T09:00:00Z", "reopened", "ed")
        gh.close(16, "2025-02-20T17:00:00Z")
        # Closed after the window ends: still open on its last day.
        gh.add_issue(14, "2025-03-15T00:00:00Z", is_pr=True)
        gh.close(14, "2025-04-01T12:00:00Z")
        # Created after the window ends: not there at all.
        gh.add_issue(15, "2025-04-01T06:00:00Z", is_pr=True)
        self.sync(gh)

        data, logs = self.build()
        self.assertEqual(data["meta"], {"from": "2024-06-01", "to": "2025-03-31"})
        self.assertEqual(data["event_types"], ["_carried_in", "_carried_in_as_draft", "_created",
                                               "_created_as_draft", "closed", "reopened",
                                               "convert_to_draft", "ready_for_review"])
        self.assertEqual(data["repos"], {"name": ["dom"], "standard": ["DOM"]})
        self.assertEqual(data["items"], {"repo": [0] * 7, "number": [2, 3, 10, 12, 13, 14, 16]})
        self.assertEqual(self.events(data), {
            2: [(day("2025-02-01"), "_created"), (day("2025-02-10"), "closed")],
            3: [(day("2025-03-01"), "_created"), (day("2025-03-02"), "closed")],
            10: [(0, "_carried_in"), (day("2025-01-15"), "closed")],
            12: [(0, "_carried_in")],
            13: [(day("2025-01-01"), "_created"), (day("2025-01-02"), "closed"),
                 (day("2025-01-03"), "reopened")],
            14: [(day("2025-03-15"), "_created")],
            16: [(day("2025-02-01"), "_created"), (day("2025-02-05"), "closed"),
                 (day("2025-02-20"), "reopened"), (day("2025-02-20"), "closed")],
        })
        # Sorted by day, then item.
        ev = data["events"]
        self.assertEqual(list(zip(ev["day"], ev["item"])), sorted(zip(ev["day"], ev["item"])))
        self.assertEqual(logs, [])

    def test_drafts(self):
        gh = populated()
        # Created as a draft, ready later (GitHub has no event for the first).
        gh.add_issue(10, "2025-01-01T00:00:00Z", is_pr=True, draft_ready_at="2025-01-10T00:00:00Z")
        # Created as a draft, still one.
        gh.add_issue(11, "2025-01-01T00:00:00Z", is_pr=True)
        gh.pulls[11]["draft"] = True
        # Ready when created, made a draft, then closed as one.
        gh.add_issue(12, "2025-01-01T00:00:00Z", is_pr=True)
        gh.add_event(12, "2025-01-05T00:00:00Z", "convert_to_draft", "alice")
        gh.pulls[12]["draft"] = True
        gh.close(12, "2025-01-20T00:00:00Z")
        # Open as a draft when the window starts, ready in it.
        gh.add_issue(13, "2024-01-01T00:00:00Z", is_pr=True, draft_ready_at="2025-02-01T00:00:00Z")
        # A draft when the window starts, but closed then; reopened in it.
        gh.add_issue(14, "2024-01-01T00:00:00Z", is_pr=True, closed_at="2024-02-01T00:00:00Z")
        gh.pulls[14]["draft"] = True
        gh.add_event(14, "2025-02-01T00:00:00Z", "reopened", "ed")
        gh.issues[14]["state"] = "open"
        gh.touch(14, "2025-02-01T00:00:00Z")
        self.sync(gh)
        data, logs = self.build()
        ev = self.events(data)
        self.assertEqual(ev[10], [(day("2025-01-01"), "_created"), (day("2025-01-01"), "_created_as_draft"),
                                  (day("2025-01-10"), "ready_for_review")])
        self.assertEqual(ev[11], [(day("2025-01-01"), "_created"), (day("2025-01-01"), "_created_as_draft")])
        self.assertEqual(ev[12], [(day("2025-01-01"), "_created"), (day("2025-01-05"), "convert_to_draft"),
                                  (day("2025-01-20"), "closed")])
        self.assertEqual(ev[13], [(0, "_carried_in"), (0, "_carried_in_as_draft"),
                                  (day("2025-02-01"), "ready_for_review")])
        self.assertEqual(ev[14], [(0, "_carried_in_as_draft"), (day("2025-02-01"), "reopened")])
        self.assertEqual(logs, [])

    def test_the_items_own_state_wins(self):
        gh = populated()
        gh.add_issue(10, "2025-01-01T00:00:00Z", is_pr=True)
        gh.close(10, "2025-02-01T00:00:00Z", event=False)  # whatwg/fullscreen #220
        gh.add_issue(11, "2025-01-01T00:00:00Z", is_pr=True)
        gh.close(11, "2025-01-10T00:00:00Z")
        gh.add_event(11, "2025-01-20T00:00:00Z", "closed", "ed")  # closed twice
        gh.add_issue(12, "2025-01-01T00:00:00Z", is_pr=True, draft_ready_at="2025-01-05T00:00:00Z")
        gh.pulls[12].update(draft=True, updated_at="2025-01-07T00:00:00Z")  # a draft again, with no event
        self.sync(gh)
        data, logs = self.build()
        self.assertEqual(self.events(data)[12], [
            (day("2025-01-01"), "_created"), (day("2025-01-01"), "_created_as_draft"),
            (day("2025-01-05"), "ready_for_review"), (day("2025-01-07"), "convert_to_draft")])
        self.assertEqual(self.events(data)[10], [(day("2025-01-01"), "_created"), (day("2025-02-01"), "closed")])
        self.assertEqual(self.events(data)[11], [(day("2025-01-01"), "_created"), (day("2025-01-10"), "closed")])
        self.assertEqual(logs, ["fixed up from the item's own state (closed with no `closed` event): 1",
                                "fixed up from the item's own state (draft state differs from the last draft event): 1"])

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

    def test_write(self):
        gh = populated()
        self.sync(gh)
        data, _ = self.build()
        path, size = build.write(data, self.files.parent / "out" / "data.json")
        self.assertEqual(json.loads(path.read_text()), data)
        self.assertEqual(size, path.stat().st_size)
