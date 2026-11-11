"""Tests for the epic changes to the projector. Standard library only.

    /opt/homebrew/bin/python3 factory/tests/test_epic.py

Every test builds its own world in a temporary directory: a vault, a meta-repo
with three nested repositories, worktrees made with `git worktree add`, and a
hand-written `gh-cache.json`. The projector then runs for real, offline, against
that world. Nothing here reads the user's config, vault, worktrees or network.

What is covered, by section of `specs/epic-stack-plan.md`, "Changes to the
factory":

    the PR-head join             JoinTests, BoardTests
    the other machine is unchanged JoinTests.test_other_machine_*, BoardTests
    no stray gate, state, timeline BoardTests
    the false-join guards        SliceOfTests, JoinTests.test_guard_*
    the blueprint fallback       BlueprintTests
    mark-ready, lowest slice     DeriveTests
    stack sync, not a rebase     DeriveTests, BoardTests
    the rescue                   RescueTests, BoardTests, TeardownPlanTests
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional

FACTORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FACTORY))
sys.dont_write_bytecode = True

from tool import cli, config, derive, ext_epic, ext_teardown, probe, render  # noqa: E402
from tool.model import GATES, MERGED, PR_READY, SCAFFOLDED, SHIPPED, Ctx, FeatureCard  # noqa: E402

GIT_ENV = {
    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid",
    "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull,
}


def git(cwd: Path, *args: str) -> str:
    env = dict(os.environ)
    env.update(GIT_ENV)
    p = subprocess.run(["git", "-C", str(cwd)] + list(args), capture_output=True, text=True, env=env)
    if p.returncode != 0:
        raise AssertionError("git %s failed in %s: %s" % (" ".join(args), cwd, p.stderr))
    return p.stdout


def pr(number: int, head: str, state: str = "OPEN", draft: bool = True, **more: Any) -> Dict[str, Any]:
    row = {
        "number": number,
        "headRefName": head,
        "state": state,
        "isDraft": draft,
        "title": "PR %d" % number,
        "url": "https://github.com/idaholab/moose/pull/%d" % number,
        "updatedAt": "2026-11-0%dT10:00:00Z" % (1 + number % 8),
        "mergedAt": "2026-11-05T10:00:00Z" if state == "MERGED" else None,
        "ci": "green",
        "failing": [],
        "mergeable": "MERGEABLE",
        "reviewDecision": None,
        "headRefOid": "0" * 40,
    }
    row.update(more)
    return row


class World:
    """A scratch vault, meta-repo and worktree root, wired through one config file."""

    def __init__(self) -> None:
        self.tmp = Path(os.path.realpath(tempfile.mkdtemp(prefix="factory-epic-test-")))
        self.vault = self.tmp / "vault"
        self.meta = self.tmp / "meta"
        self.wts = self.tmp / "worktrees"
        self.state = self.meta / "factory" / "state"
        for d in (self.vault, self.wts, self.tmp / "claude" / "sessions", self.tmp / "scan"):
            d.mkdir(parents=True)
        (self.vault / "Ideas.md").write_text("# Ideas\n")
        self._repo(self.meta, "main")
        for sub in config.SUBMODULES:
            self._repo(self.meta / sub, "devel")
        self.cfg_file = self.tmp / "config.toml"
        self.cfg_file.write_text(
            "\n".join(
                [
                    'vault = "%s"' % self.vault,
                    'worktrees_root = "%s"' % self.wts,
                    'meta_repo = "%s"' % self.meta,
                    'claude_home = "%s"' % (self.tmp / "claude"),
                    'notifier = ""',
                    "campaign_roots = []",
                    "gh_cache_ttl = 999999999",
                    "",
                ]
            )
        )
        self._saved = dict(os.environ)
        for name in list(os.environ):
            if name.startswith(("MOOSE_FACTORY_", "FACTORY_")):
                del os.environ[name]
        os.environ["MOOSE_FACTORY_CONFIG"] = str(self.cfg_file)
        os.environ["FACTORY_TMP_DIR"] = str(self.tmp / "scan")
        os.environ["GIT_OPTIONAL_LOCKS"] = "0"
        self.prs: List[Dict[str, Any]] = []
        self.prs_blackbear: List[Dict[str, Any]] = []
        self.write_cache()

    def close(self) -> None:
        os.environ.clear()
        os.environ.update(self._saved)
        shutil.rmtree(str(self.tmp), ignore_errors=True)

    def _repo(self, path: Path, branch: str) -> None:
        path.mkdir(parents=True, exist_ok=True)
        git(path, "init", "-q", "-b", branch)
        (path / "README").write_text("x\n")
        git(path, "add", "README")
        git(path, "commit", "-q", "-m", "init")
        if branch == "devel":
            # What a fetch of upstream leaves behind, with no remote to fetch.
            for name in ("devel", "next"):
                git(path, "update-ref", "refs/remotes/upstream/" + name, "HEAD")

    def worktree(self, name: str, epic: Optional[str] = None, slices: int = 0) -> Path:
        """A feature worktree with a moose checkout on branch `name`.

        `epic` is the text of specs/epic.md, or None for an ordinary feature.
        `slices` makes that many commits and one local ref `epic/<name>/s<k>` each.
        """
        wt = self.wts / name
        git(self.meta, "worktree", "add", "-q", "-b", name, str(wt))
        moose = wt / "moose"
        git(self.meta / "moose", "worktree", "add", "-q", "-b", name, str(moose))
        (wt / "specs").mkdir()
        if epic is not None:
            (wt / "specs" / "epic.md").write_text(epic)
        for k in range(1, slices + 1):
            (moose / ("slice%d.txt" % k)).write_text("slice %d\n" % k)
            git(moose, "add", "-A")
            git(moose, "commit", "-q", "-m", "feat: slice %d" % k)
            git(moose, "branch", "epic/%s/s%d" % (name, k))
        return wt

    def write_cache(self) -> None:
        self.state.mkdir(parents=True, exist_ok=True)
        payload = {
            "at": time.time(),
            "as_of": probe.iso(),
            "ok": True,
            "repos": {"moose": self.prs, "blackbear": self.prs_blackbear, "isopod": []},
        }
        (self.state / "gh-cache.json").write_text(json.dumps(payload))

    def cfg(self) -> config.Config:
        return config.load(offline=True)

    def round(self) -> Dict[str, Dict[str, Any]]:
        self.write_cache()
        obs, _meta = probe.round_all(self.cfg())
        return obs

    def board(self) -> str:
        self.write_cache()
        out, errs = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(errs):
            code = cli.main(["--offline", "board"])
        if code not in (0, 1):
            raise AssertionError("board exit %s\n%s\n%s" % (code, out.getvalue(), errs.getvalue()))
        return out.getvalue() + errs.getvalue()

    def names(self, directory: Path) -> List[str]:
        return sorted(p.name for p in directory.iterdir()) if directory.is_dir() else []


EPIC_MD = """---
epic: {name}
issue: 12345
---
# Epic

## Slices

| id | title | needs | a user can | tests |
|---|---|---|---|---|
| s1 | first | - | x | t1 |
| s2 | second | s1 | y | t2 |
| s3 | third | s2 | z | t3 |

## Seams

One sentence.
"""


class WorldCase(unittest.TestCase):
    def setUp(self) -> None:
        self.w = World()
        self.addCleanup(self.w.close)


# --------------------------------------------------------------------------
# slice_of: the rule that decides whether a head is a slice
# --------------------------------------------------------------------------


class SliceOfTests(unittest.TestCase):
    def test_slice_head(self) -> None:
        self.assertEqual(probe.slice_of("epic/modal/s2"), ("modal", 2))
        self.assertEqual(probe.slice_of("epic/modal/s10"), ("modal", 10))
        self.assertEqual(probe.slice_of("epic/a-s1/s12"), ("a-s1", 12))

    def test_nothing_else_is_a_slice(self) -> None:
        for head in ("modal", "modal-s2", "x-s3", "upload-to-s3", "epic", "epic/modal", "epic/modal/",
                     "epic/modal/2", "epic/modal/sx", "epic/modal/s2b", "epic/modal/s2/", "/epic/modal/s2",
                     "Epic/modal/s2", "epics/modal/s2", "user/epic/modal/s2", ""):
            self.assertIsNone(probe.slice_of(head), head)

    def test_bad_numbers_and_bad_names_are_rejected(self) -> None:
        for head in ("epic/x/s0", "epic/x/s01", "epic/x/s00", "epic/x/y/s1", "epic//s1",
                     "epic/../s1", "epic/.x/s1", "epic/x y/s1", "epic/" + "x" * 65 + "/s1"):
            self.assertIsNone(probe.slice_of(head), head)

    def test_which_card_is_an_epic(self) -> None:
        self.assertTrue(probe.is_epic({"worktree": "/w", "epic": {"path": "x", "order": []}}))
        self.assertTrue(probe.is_epic({"worktree": "/w", "stale": ["epic"]}))
        self.assertTrue(probe.is_epic({"worktree": None, "epic": {"path": None, "order": []}}))
        self.assertFalse(probe.is_epic({"worktree": "/w", "stale": ["blueprint"]}))
        self.assertFalse(probe.is_epic({"worktree": None, "stale": ["epic"]}))
        self.assertFalse(probe.is_epic({"worktree": None}))


# --------------------------------------------------------------------------
# The join, through a real probe round
# --------------------------------------------------------------------------


class JoinTests(WorldCase):
    def collisions(self) -> List[Dict[str, Any]]:
        self.w.write_cache()
        _obs, meta = probe.round_all(self.w.cfg())
        return list(meta.get("epic_collisions") or [])

    # ---- the worktree path --------------------------------------------------

    def test_slice_prs_join_the_epic_card(self) -> None:
        self.w.worktree("modal", EPIC_MD.format(name="modal"), slices=2)
        self.w.prs = [pr(101, "epic/modal/s1", draft=False), pr(102, "epic/modal/s2"),
                      pr(90, "epic/modal/s9", state="MERGED"), pr(77, "other-thing")]
        obs = self.w.round()
        self.assertEqual(sorted(obs), ["modal", "other-thing"])
        rows = {p["number"]: p for p in obs["modal"]["prs"]}
        self.assertEqual(sorted(rows), [90, 101, 102])
        self.assertEqual([rows[n]["slice"] for n in (101, 102, 90)], [1, 2, 9])
        self.assertTrue(all(p["repo"] == "moose" for p in rows.values()))
        self.assertNotIn("slice", obs["other-thing"]["prs"][0])
        self.assertEqual(obs["modal"]["epic"]["order"], [1, 2, 3])
        self.assertNotIn("epic", obs["other-thing"])

    def test_an_ordinary_worktree_is_unchanged(self) -> None:
        self.w.worktree("plain")
        self.w.prs = [pr(5, "plain")]
        obs = self.w.round()
        self.assertEqual(sorted(obs), ["plain"])
        self.assertEqual([p["number"] for p in obs["plain"]["prs"]], [5])
        self.assertNotIn("slice", obs["plain"]["prs"][0])
        self.assertNotIn("epic", obs["plain"])

    def test_a_slice_in_another_repository_joins(self) -> None:
        self.w.worktree("modal", EPIC_MD.format(name="modal"))
        self.w.prs = [pr(101, "epic/modal/s1")]
        self.w.prs_blackbear = [pr(7, "epic/modal/s2", url="https://github.com/idaholab/blackbear/pull/7")]
        obs = self.w.round()
        self.assertEqual(sorted(obs), ["modal"])
        got = sorted((p["repo"], p["number"], p["slice"]) for p in obs["modal"]["prs"])
        self.assertEqual(got, [("blackbear", 7, 2), ("moose", 101, 1)])

    def test_a_checked_out_slice_branch_is_still_a_slice(self) -> None:
        # No worktree should check out a slice ref. If one does, the head is
        # still a slice of its epic, never the pull request of that worktree.
        self.w.worktree("modal", EPIC_MD.format(name="modal"), slices=1)
        odd = self.w.worktree("odd")
        git(odd / "moose", "checkout", "-q", "epic/modal/s1")
        self.w.prs = [pr(101, "epic/modal/s1")]
        obs = self.w.round()
        self.assertEqual([(p["number"], p["slice"]) for p in obs["modal"]["prs"]], [(101, 1)])
        self.assertEqual(obs["odd"]["prs"], [])

    def test_a_failed_read_of_the_plan_does_not_unjoin(self) -> None:
        self.w.worktree("modal", EPIC_MD.format(name="modal"))
        self.w.prs = [pr(101, "epic/modal/s1"), pr(102, "epic/modal/s2")]
        real = probe.epic
        probe.epic = lambda worktree: (None, False)
        try:
            obs = self.w.round()
        finally:
            probe.epic = real
        self.assertEqual(sorted(obs), ["modal"])
        self.assertIn("epic", obs["modal"]["stale"])
        self.assertEqual(sorted(p["slice"] for p in obs["modal"]["prs"]), [1, 2])

    def test_a_failed_worktree_list_holds_the_slices(self) -> None:
        # One good run, so the state remembers the cards. Then `git worktree
        # list` fails. The epic card is recovered and its slices come back with
        # it. The slice of the ordinary feature stays a collision. Neither one
        # turns a worktree card into a PR-only card.
        self.w.worktree("modal", EPIC_MD.format(name="modal"))
        self.w.worktree("plain")
        self.w.prs = [pr(101, "epic/modal/s1"), pr(102, "epic/modal/s2", state="MERGED"),
                      pr(31, "epic/plain/s1")]
        self.w.board()
        real = probe.all_worktrees
        probe.all_worktrees = lambda cfg: ({}, False)
        try:
            self.w.write_cache()
            obs, meta = probe.round_all(self.w.cfg())
        finally:
            probe.all_worktrees = real
        self.assertEqual(sorted(obs), ["modal", "plain"])
        self.assertEqual(sorted(p["slice"] for p in obs["modal"]["prs"]), [1, 2])
        self.assertTrue(obs["modal"]["worktree"])
        self.assertEqual(obs["plain"]["prs"], [])
        self.assertEqual([c["number"] for c in meta["epic_collisions"]], [31])

    # ---- the PR-only path ---------------------------------------------------

    def test_pr_only_slices_make_one_card(self) -> None:
        # No worktree here: the other Mac, or this one after a teardown.
        self.w.prs = [pr(102, "epic/modal/s2"), pr(101, "epic/modal/s1", draft=False),
                      pr(90, "epic/modal/s3", state="MERGED"), pr(80, "epic/modal/s4", state="CLOSED")]
        self.w.prs_blackbear = [pr(7, "epic/modal/s5")]
        obs = self.w.round()
        self.assertEqual(sorted(obs), ["modal"])
        card = obs["modal"]
        self.assertEqual(card["provenance"], "discovered-pr")
        self.assertIsNone(card["worktree"])
        self.assertEqual(card["epic"], {"path": None, "order": []})
        self.assertEqual(
            [(p["repo"], p["number"], p["slice"]) for p in card["prs"]],
            [("blackbear", 7, 5), ("moose", 102, 2), ("moose", 101, 1), ("moose", 90, 3), ("moose", 80, 4)],
        )

    def test_pr_only_slices_with_none_open_make_no_card(self) -> None:
        self.w.prs = [pr(90, "epic/modal/s1", state="MERGED"), pr(80, "epic/modal/s2", state="CLOSED")]
        self.assertEqual(self.w.round(), {})
        self.assertEqual(self.collisions(), [])

    def test_a_recovered_pr_only_card_keeps_its_marker(self) -> None:
        self.w.prs = [pr(101, "epic/modal/s1"), pr(102, "epic/modal/s2")]
        self.w.board()
        real = probe.github
        probe.github = lambda cfg: ({"at": 0, "repos": {}, "as_of": None}, False)
        try:
            obs, _meta = probe.round_all(self.w.cfg())
        finally:
            probe.github = real
        self.assertEqual(sorted(obs), ["modal"])
        self.assertEqual(obs["modal"]["epic"], {"path": None, "order": []})
        self.assertIn("github", obs["modal"]["stale"])

    # ---- x-s3 is an ordinary head again -------------------------------------

    def test_a_dash_s_suffix_means_nothing(self) -> None:
        self.w.worktree("plain")
        self.w.worktree("modal", EPIC_MD.format(name="modal"))
        self.w.prs = [pr(31, "plain-s3"), pr(32, "plain-s4", state="MERGED"),
                      pr(33, "plain-s5", state="CLOSED"), pr(30, "plain"),
                      pr(41, "modal-s1"), pr(42, "modal-s2", state="MERGED"), pr(60, "upload-to-s3")]
        obs = self.w.round()
        self.assertEqual(sorted(obs), ["modal", "modal-s1", "plain", "plain-s3", "upload-to-s3"])
        self.assertEqual([p["number"] for p in obs["plain"]["prs"]], [30])
        self.assertEqual(obs["modal"]["prs"], [])
        for card in obs.values():
            for row in card["prs"]:
                self.assertNotIn("slice", row)
        self.assertEqual(self.collisions(), [])

    def test_a_malformed_epic_head_is_an_ordinary_unsafe_head(self) -> None:
        self.w.worktree("x", EPIC_MD.format(name="x"))
        self.w.prs = [pr(1, "epic/x/s0"), pr(2, "epic/x/s01"), pr(3, "epic/x/y/s1"), pr(4, "epic//s1"),
                      pr(5, "epic/x/s1")]
        self.w.write_cache()
        obs, meta = probe.round_all(self.w.cfg())
        self.assertEqual(sorted(obs), ["x"])
        self.assertEqual([p["number"] for p in obs["x"]["prs"]], [5])
        # today's rule for any head with a slash: named on Home, never a card
        self.assertEqual(sorted(r["number"] for r in meta["skipped_prs"]), [1, 2, 3, 4])
        self.assertNotIn("epic_collisions", meta)

    # ---- the collision ------------------------------------------------------

    def test_collision_with_an_ordinary_worktree(self) -> None:
        self.w.worktree("plain")
        self.w.prs = [pr(31, "epic/plain/s1"), pr(32, "epic/plain/s2", state="MERGED"), pr(30, "plain")]
        obs = self.w.round()
        self.assertEqual(sorted(obs), ["plain"])
        self.assertEqual([p["number"] for p in obs["plain"]["prs"]], [30])
        got = self.collisions()
        self.assertEqual(sorted(c["number"] for c in got), [31, 32])
        self.assertTrue(all(c["epic"] == "plain" and "no specs/epic.md" in c["why"] for c in got))

    def test_collision_with_an_ordinary_pr_only_card(self) -> None:
        # The head is literally `tool`, and somebody named an epic `tool` too.
        self.w.prs = [pr(31, "epic/tool/s1"), pr(30, "tool")]
        obs = self.w.round()
        self.assertEqual(sorted(obs), ["tool"])
        self.assertEqual([p["number"] for p in obs["tool"]["prs"]], [30])
        self.assertNotIn("epic", obs["tool"])
        got = self.collisions()
        self.assertEqual([c["number"] for c in got], [31])
        self.assertIn("ordinary pull request", got[0]["why"])

    def test_collision_does_not_depend_on_the_order_of_the_list(self) -> None:
        self.w.prs = [pr(30, "tool"), pr(31, "epic/tool/s1")]
        obs = self.w.round()
        self.assertEqual([p["number"] for p in obs["tool"]["prs"]], [30])
        self.assertEqual([c["number"] for c in self.collisions()], [31])

    def test_an_ideas_slug_equal_to_the_epic_name(self) -> None:
        (self.w.vault / "Ideas.md").write_text("# Ideas\n- modal\n- far\n- later\n")
        self.w.worktree("modal", EPIC_MD.format(name="modal"))
        self.w.prs = [pr(101, "epic/modal/s1"), pr(201, "epic/far/s1")]
        self.w.write_cache()
        obs, meta = probe.round_all(self.w.cfg())
        # one card each: the worktree epic, the PR-only epic, and the idea nobody started
        self.assertEqual(sorted(obs), ["far", "later", "modal"])
        self.assertEqual(obs["modal"]["provenance"], "discovered-worktree")
        self.assertEqual(obs["far"]["provenance"], "discovered-pr")
        self.assertEqual(obs["later"]["provenance"], "idea")
        self.assertEqual([p["slice"] for p in obs["modal"]["prs"]], [1])
        self.assertEqual([p["slice"] for p in obs["far"]["prs"]], [1])
        self.assertEqual(sorted(r["slug"] for r in meta["ideas"]["matched"]), ["far", "modal"])
        self.assertEqual([r["slug"] for r in meta["ideas"]["unmatched"]], ["later"])
        self.assertNotIn("epic_collisions", meta)

    def test_unsafe_head_is_still_skipped(self) -> None:
        self.w.prs = [pr(9, "user/branch-s2")]
        self.assertEqual(self.w.round(), {})


# --------------------------------------------------------------------------
# The blueprint fallback and the epic marker
# --------------------------------------------------------------------------


class BlueprintTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="factory-epic-bp-"))
        self.addCleanup(shutil.rmtree, str(self.tmp), True)
        (self.tmp / "specs").mkdir()

    def write(self, name: str, text: str) -> None:
        (self.tmp / "specs" / name).write_text(text)

    def test_epic_and_handoff_are_never_the_blueprint(self) -> None:
        self.write("epic.md", "---\nfeature: modal\nstatus: approved\n---\n")
        self.write("handoff.md", "---\nfeature: modal\n---\n")
        self.assertEqual(probe.blueprint(self.tmp), (None, True))

    def test_another_markdown_file_is_still_adopted(self) -> None:
        self.write("epic.md", "---\nfeature: modal\n---\n")
        self.write("plan-old.md", "---\nfeature: modal\nstatus: draft\n---\n")
        got, ok = probe.blueprint(self.tmp)
        self.assertTrue(ok)
        self.assertEqual(Path(got["path"]).name, "plan-old.md")

    def test_blueprint_md_still_wins(self) -> None:
        self.write("epic.md", "---\nepic: modal\n---\n")
        self.write("blueprint.md", "---\nfeature: modal\nstatus: draft\n---\n")
        got, _ok = probe.blueprint(self.tmp)
        self.assertEqual(Path(got["path"]).name, "blueprint.md")
        self.assertEqual(got["status"], "draft")

    def test_epic_marker(self) -> None:
        self.assertEqual(probe.epic(self.tmp), (None, True))
        self.write("epic.md", EPIC_MD.format(name="modal").replace("| s2 |", "| `s7` |"))
        got, ok = probe.epic(self.tmp)
        self.assertTrue(ok)
        self.assertEqual(got["order"], [1, 7, 3])
        self.write("epic.md", "---\nepic: modal\n---\nno table here\n")
        self.assertEqual(probe.epic(self.tmp)[0]["order"], [])


# --------------------------------------------------------------------------
# derive: mark-ready and the rebase command
# --------------------------------------------------------------------------


def _gates(**granted: bool) -> Dict[str, Dict[str, Any]]:
    return {g: {"state": "granted" if granted.get(g) else "pending"} for g in GATES}


class DeriveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="factory-epic-derive-"))
        self.addCleanup(shutil.rmtree, str(self.tmp), True)
        self.cfg = config.Config(
            repo_root=self.tmp / "meta", vault=self.tmp / "vault", state_dir=self.tmp / "state",
            worktree_root=self.tmp / "wts", claude_home=self.tmp / "claude",
        )
        self.wt = str(self.tmp / "wts" / "modal")
        self.now = "2026-11-10T12:00:00-05:00"

    def card(self, prs: List[Dict[str, Any]], epic: bool = True, worktree: bool = True,
             gates: Optional[Dict[str, Any]] = None) -> FeatureCard:
        for p in prs:
            p.setdefault("repo", "moose")
        obs: Dict[str, Any] = {
            "id": "modal",
            "worktree": self.wt if worktree else None,
            "provenance": "discovered-worktree" if worktree else "discovered-pr",
            "repos": {"moose": {"branch": "modal", "head": "f" * 40, "dirty": 0, "ahead": 2,
                                "fetched": "2026-11-10", "fetched_at": 1.0}} if worktree else {},
            "prs": prs,
            "sessions": [],
            "skills": {"names": ["moose-ship"], "has_ship": True},
        }
        if epic and worktree:
            obs["epic"] = {"path": self.wt + "/specs/epic.md", "order": [1, 2, 3]}
        card, _events = derive.derive_card(obs, {}, self.cfg, self.now, gates or _gates(ship=True))
        self.assertEqual(card.errors, [])
        return card

    # ---- mark-ready ---------------------------------------------------------

    def test_mark_ready_names_the_lowest_open_slice(self) -> None:
        # s2 is the newest pull request, so it is the card's primary PR today.
        s1 = pr(101, "epic/modal/s1", slice=1, updatedAt="2026-11-01T10:00:00Z")
        s2 = pr(102, "epic/modal/s2", slice=2, updatedAt="2026-11-09T10:00:00Z")
        card = self.card([s2, s1])
        self.assertEqual(card.primary_pr()["number"], 102)
        self.assertEqual(card.next_action.verb, "mark-ready")
        self.assertEqual(card.next_action.command, "open " + s1["url"])
        self.assertIn("moose #101", card.next_action.why)
        self.assertIn("s1", card.next_action.why)

    def test_mark_ready_skips_a_merged_lower_slice(self) -> None:
        s1 = pr(101, "epic/modal/s1", state="MERGED", slice=1)
        s2 = pr(102, "epic/modal/s2", slice=2)
        s3 = pr(103, "epic/modal/s3", slice=3, updatedAt="2026-11-09T10:00:00Z")
        card = self.card([s3, s2, s1])
        self.assertEqual(card.next_action.verb, "mark-ready")
        self.assertEqual(card.next_action.command, "open " + s2["url"])

    def test_no_mark_ready_for_an_upper_slice(self) -> None:
        # The lowest open slice is in review. The gate record lags by a run.
        s1 = pr(101, "epic/modal/s1", draft=False, slice=1)
        s2 = pr(102, "epic/modal/s2", slice=2, updatedAt="2026-11-09T10:00:00Z")
        card = self.card([s2, s1])
        self.assertEqual(card.gates.get("_due"), "pr_ready")
        self.assertNotEqual(card.next_action.verb, "mark-ready")

    def test_mark_ready_is_unchanged_for_an_ordinary_card(self) -> None:
        only = pr(55, "modal")
        card = self.card([only], epic=False)
        self.assertEqual(card.next_action.verb, "mark-ready")
        self.assertEqual(card.next_action.command, "open " + only["url"])
        self.assertEqual(card.next_action.why, "moose #55 is a green draft. Only you can mark it ready.")

    def test_a_pr_only_card_marks_ready_as_before(self) -> None:
        # On the machine without the worktree a slice is an ordinary PR-only card.
        only = pr(102, "epic/modal/s2")
        card = self.card([only], worktree=False)
        self.assertEqual(card.next_action.verb, "mark-ready")
        self.assertEqual(card.next_action.why, "moose #102 is a green draft. Only you can mark it ready.")

    # ---- the rebase command -------------------------------------------------

    def test_conflicting_epic_prints_stack_sync(self) -> None:
        s1 = pr(101, "epic/modal/s1", slice=1, mergeable="CONFLICTING")
        card = self.card([s1])
        self.assertIn("conflicting", card.flags)
        self.assertEqual(card.next_action.verb, "rebase")
        self.assertEqual(
            card.next_action.command,
            "cd %s && %s sync" % (self.wt, self.cfg.repo_root / "scripts" / "stack"),
        )
        self.assertNotIn("git rebase", card.next_action.command)

    def test_a_flag_names_the_slice_it_is_about(self) -> None:
        # s2 is the newest pull request; the trouble is on s1.
        s1 = pr(101, "epic/modal/s1", slice=1, mergeable="CONFLICTING")
        s2 = pr(102, "epic/modal/s2", slice=2, updatedAt="2026-11-09T10:00:00Z")
        self.assertIn("moose #101 is CONFLICTING", self.card([s2, s1]).next_action.why)

        s1 = pr(101, "epic/modal/s1", slice=1, ci="red", failing=[{"name": "Precheck", "url": ""}])
        s2 = pr(102, "epic/modal/s2", slice=2, updatedAt="2026-11-09T10:00:00Z")
        na = self.card([s2, s1]).next_action
        self.assertEqual(na.verb, "fix-ci")
        self.assertIn("--pr 101 ", na.command)
        self.assertIn("moose #101 is red (Precheck)", na.why)

        s1 = pr(101, "epic/modal/s1", draft=False, slice=1, reviewDecision="CHANGES_REQUESTED")
        s2 = pr(102, "epic/modal/s2", slice=2, updatedAt="2026-11-09T10:00:00Z")
        na = self.card([s2, s1]).next_action
        self.assertEqual(na.command, "gh pr view 101 --repo idaholab/moose --comments")

    def test_a_flag_on_an_ordinary_card_names_its_primary_pr(self) -> None:
        only = pr(55, "modal", ci="red", headRefOid="f" * 40, failing=[{"name": "Precheck", "url": ""}])
        na = self.card([only], epic=False).next_action
        self.assertIn("--pr 55 ", na.command)

    def test_conflicting_ordinary_card_prints_the_plain_rebase(self) -> None:
        # The head is this checkout's branch, so the verdict counts only for its sha.
        card = self.card([pr(55, "modal", mergeable="CONFLICTING", headRefOid="f" * 40)], epic=False)
        self.assertEqual(
            card.next_action.command,
            "cd %s/moose && git fetch upstream && git rebase upstream/devel" % (self.wt,),
        )

    def test_conflicting_pr_only_card_reads_the_checks(self) -> None:
        card = self.card([pr(101, "epic/modal/s1", mergeable="CONFLICTING")], worktree=False)
        self.assertEqual(card.next_action.command, "gh pr checks 101 --repo idaholab/moose")


# --------------------------------------------------------------------------
# The lane of an epic: merged only when the chain is finished
# --------------------------------------------------------------------------


class LaneTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="factory-epic-lane-"))
        self.addCleanup(shutil.rmtree, str(self.tmp), True)
        self.cfg = config.Config(
            repo_root=self.tmp / "meta", vault=self.tmp / "vault", state_dir=self.tmp / "state",
            worktree_root=self.tmp / "wts", claude_home=self.tmp / "claude",
        )
        self.wt = str(self.tmp / "wts" / "modal")
        self.prev: Dict[str, Any] = {}
        self.events: List[Dict[str, Any]] = []

    def step(self, prs: List[Dict[str, Any]], order: Any = (1, 2), epic: bool = True,
             worktree: bool = True, stale: Any = ()) -> FeatureCard:
        """One board run for one card, with the state carried to the next step."""
        for p in prs:
            p.setdefault("repo", "moose")
        obs: Dict[str, Any] = {
            "id": "modal",
            "worktree": self.wt if worktree else None,
            "provenance": "discovered-worktree" if worktree else "discovered-pr",
            "repos": {"moose": {"branch": "modal", "head": "f" * 40, "dirty": 0, "ahead": 2,
                                "fetched": "2026-11-10", "fetched_at": 1.0}} if worktree else {},
            "prs": prs,
            "sessions": [],
            "stale": list(stale),
            "skills": {"names": ["moose-ship"], "has_ship": True},
        }
        if epic:
            obs["epic"] = {"path": (self.wt + "/specs/epic.md") if worktree else None,
                           "order": list(order) if worktree else []}
        card, events = derive.derive_card(obs, self.prev, self.cfg, "2026-11-10T12:00:00-05:00",
                                          _gates(ship=True, pr_ready=True))
        self.assertEqual(card.errors, [])
        self.events.extend(events)
        self.prev["lane"] = card.lane          # what derive_all stores
        return card

    def test_the_sequence_one_merged_one_sealed_then_draft_then_all_merged(self) -> None:
        card = self.step([pr(101, "epic/modal/s1", draft=False, slice=1)])
        self.assertEqual(card.lane, PR_READY)

        # s1 merged. s2 is sealed: a commit and a ref, no pull request.
        card = self.step([pr(101, "epic/modal/s1", state="MERGED", slice=1)])
        self.assertEqual(card.lane, SCAFFOLDED)
        self.assertNotIn("signal-regression", card.flags)
        self.assertNotEqual(card.next_action.verb, "teardown")
        self.assertNotEqual(card.gates.get("_due"), "teardown")
        self.assertEqual([(e["from"], e["to"], e["cause"]) for e in self.events],
                         [(PR_READY, SCAFFOLDED, "epic-next-slice")])
        self.assertEqual(self.prev["epic_merged"], [1])

        # s2 opens as a draft.
        card = self.step([pr(101, "epic/modal/s1", state="MERGED", slice=1), pr(102, "epic/modal/s2", slice=2)])
        self.assertEqual(card.lane, SHIPPED)
        self.assertNotIn("signal-regression", card.flags)
        self.assertNotEqual(card.next_action.verb, "teardown")
        self.assertNotIn("teardown", card.next_action.command)

        # every slice in the plan has merged.
        card = self.step([pr(101, "epic/modal/s1", state="MERGED", slice=1),
                          pr(102, "epic/modal/s2", state="MERGED", slice=2)])
        self.assertEqual(card.lane, MERGED)
        self.assertEqual(card.gates.get("_due"), "teardown")
        self.assertEqual(card.next_action.verb, "teardown")
        self.assertEqual(len(self.events), 1)

    def test_a_stored_merged_is_not_held_for_an_unfinished_chain(self) -> None:
        # State from before this rule, or a plan that gained a slice.
        self.prev = {"lane": MERGED}
        card = self.step([pr(101, "epic/modal/s1", state="MERGED", slice=1), pr(102, "epic/modal/s2", slice=2)])
        self.assertEqual(card.lane, SHIPPED)
        self.assertNotIn("signal-regression", card.flags)
        self.assertEqual(self.events[0]["cause"], "epic-next-slice")

    def test_a_plan_with_no_readable_order_never_proves_merged(self) -> None:
        card = self.step([pr(101, "epic/modal/s1", state="MERGED", slice=1),
                          pr(102, "epic/modal/s2", state="MERGED", slice=2)], order=())
        self.assertNotEqual(card.lane, MERGED)
        self.assertNotEqual(card.next_action.verb, "teardown")

    def test_a_plan_that_could_not_be_read_never_proves_merged(self) -> None:
        card = self.step([pr(101, "epic/modal/s1", state="MERGED", slice=1)], epic=False, stale=("epic",))
        self.assertNotEqual(card.lane, MERGED)

    def test_a_slice_the_plan_lists_and_nobody_built_keeps_it_open(self) -> None:
        card = self.step([pr(101, "epic/modal/s1", state="MERGED", slice=1),
                          pr(102, "epic/modal/s2", state="MERGED", slice=2)], order=(1, 2, 3))
        self.assertNotEqual(card.lane, MERGED)

    def test_a_merged_slice_that_left_the_gh_window_still_counts(self) -> None:
        self.step([pr(101, "epic/modal/s1", state="MERGED", slice=1), pr(102, "epic/modal/s2", slice=2)])
        # months later `gh pr list` no longer returns #101
        card = self.step([pr(102, "epic/modal/s2", state="MERGED", slice=2)])
        self.assertEqual(self.prev["epic_merged"], [1, 2])
        self.assertEqual(card.lane, MERGED)

    def test_an_ordinary_card_is_merged_as_before(self) -> None:
        card = self.step([pr(55, "modal", state="MERGED")], epic=False)
        self.assertEqual(card.lane, MERGED)
        self.assertEqual(card.next_action.verb, "teardown")
        self.assertNotIn("epic_merged", self.prev)

    def test_an_ordinary_card_still_holds_its_lane(self) -> None:
        self.prev = {"lane": PR_READY}
        card = self.step([], epic=False)
        self.assertEqual(card.lane, PR_READY)
        self.assertIn("signal-regression", card.flags)
        self.assertEqual(self.events, [])

    def test_a_pr_only_epic_card_is_shipped_while_a_slice_is_open(self) -> None:
        card = self.step([pr(101, "epic/modal/s1", state="MERGED", slice=1), pr(102, "epic/modal/s2", slice=2)],
                         worktree=False)
        self.assertEqual(card.lane, SHIPPED)
        self.assertNotIn("epic_merged", self.prev)


# --------------------------------------------------------------------------
# The rescue
# --------------------------------------------------------------------------


class FakeCtx:
    def __init__(self, cfg: config.Config, dry_run: bool = False) -> None:
        self.config, self.dry_run, self.obs, self.meta, self.logs = cfg, dry_run, {}, {}, []

    def log(self, msg: str) -> None:
        self.logs.append(msg)


class RescueTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(os.path.realpath(tempfile.mkdtemp(prefix="factory-epic-rescue-")))
        self.addCleanup(shutil.rmtree, str(self.tmp), True)
        self.cfg = config.Config(
            repo_root=self.tmp / "meta", vault=self.tmp / "vault", state_dir=self.tmp / "state",
            worktree_root=self.tmp / "wts", claude_home=self.tmp / "claude",
        )
        self.wt = self.tmp / "wts" / "modal"
        specs = self.wt / "specs"
        (specs / "slices" / "s1" / "proof").mkdir(parents=True)
        (specs / "slices" / "s2").mkdir()
        (specs / "epic.md").write_text("# epic\n")
        (specs / "blueprint.md").write_text("the live slice, never rescued here\n")
        (specs / "slices" / "s1" / "blueprint.md").write_text("slice 1\n")
        (specs / "slices" / "s1" / "review-modal.md").write_text("review\n")
        (specs / "slices" / "s1" / "proof" / "claim.txt").write_text("proof\n")
        (specs / "slices" / "s2" / "blueprint.md").write_text("slice 2\n")
        self.ctx = FakeCtx(self.cfg)
        self.dest = self.cfg.artifacts_dir / "modal"

    def tree(self) -> List[str]:
        return sorted(p.relative_to(self.dest).as_posix() for p in self.dest.rglob("*") if p.is_file())

    def test_copies_the_plan_and_every_archived_slice_file(self) -> None:
        rec = ext_epic.rescue_all(self.ctx, "modal", self.wt)
        self.assertEqual(rec, {"files": 5, "not_rescued": []})
        self.assertEqual(
            self.tree(),
            ["epic.md", "slices/s1/blueprint.md", "slices/s1/proof/claim.txt",
             "slices/s1/review-modal.md", "slices/s2/blueprint.md"],
        )
        self.assertEqual((self.dest / "slices/s1/proof/claim.txt").read_text(), "proof\n")
        self.assertEqual(ext_epic.unrescued(self.ctx, "modal", self.wt), [])

    def test_second_run_copies_nothing(self) -> None:
        ext_epic.rescue_all(self.ctx, "modal", self.wt)
        before = {n: (self.dest / n).stat().st_mtime_ns for n in self.tree()}
        for rel, src in ext_epic.sources(self.wt)[0]:
            self.assertEqual(ext_epic.rescue(self.ctx, src, self.dest / rel), "same")
        self.assertEqual(before, {n: (self.dest / n).stat().st_mtime_ns for n in self.tree()})
        # copy2 kept the source mtime, which is what makes the second run a no-op
        self.assertEqual(
            (self.dest / "epic.md").stat().st_mtime_ns, (self.wt / "specs/epic.md").stat().st_mtime_ns
        )

    def test_a_newer_plan_replaces_the_copy(self) -> None:
        ext_epic.rescue_all(self.ctx, "modal", self.wt)
        (self.wt / "specs/epic.md").write_text("# epic\n\n## Amendments\n- one\n")
        ext_epic.rescue_all(self.ctx, "modal", self.wt)
        self.assertIn("Amendments", (self.dest / "epic.md").read_text())

    def test_an_emptied_file_never_replaces_the_copy(self) -> None:
        ext_epic.rescue_all(self.ctx, "modal", self.wt)
        (self.wt / "specs/slices/s1/blueprint.md").write_text("")
        rec = ext_epic.rescue_all(self.ctx, "modal", self.wt)
        self.assertEqual((self.dest / "slices/s1/blueprint.md").read_text(), "slice 1\n")
        self.assertEqual(len(rec["not_rescued"]), 1)
        self.assertIn("slices/s1/blueprint.md", rec["not_rescued"][0])

    def test_a_symlink_is_never_followed(self) -> None:
        secret = self.tmp / "outside.txt"
        secret.write_text("not ours\n")
        os.symlink(str(secret), str(self.wt / "specs/slices/s1/link.txt"))
        os.symlink(str(self.tmp), str(self.wt / "specs/slices/s1/linkdir"))
        rec = ext_epic.rescue_all(self.ctx, "modal", self.wt)
        self.assertEqual(rec["files"], 5)
        self.assertEqual(
            rec["not_rescued"],
            ["slices/s1/link.txt (a symlink)", "slices/s1/linkdir/ (a symlink)"],
        )
        self.assertNotIn("slices/s1/link.txt", self.tree())
        self.assertFalse((self.dest / "slices/s1/linkdir").exists())
        self.assertEqual(len(ext_epic.unrescued(self.ctx, "modal", self.wt)), 2)

    def test_a_file_over_the_cap_is_named_not_copied(self) -> None:
        big = self.wt / "specs/slices/s1/proof/big.bin"
        big.write_bytes(b"x" * 2048)
        old = ext_epic.MAX_FILE_BYTES
        ext_epic.MAX_FILE_BYTES = 1024
        try:
            rec = ext_epic.rescue_all(self.ctx, "modal", self.wt)
        finally:
            ext_epic.MAX_FILE_BYTES = old
        self.assertEqual(rec["not_rescued"], ["slices/s1/proof/big.bin (over 1024 bytes)"])
        self.assertFalse((self.dest / "slices/s1/proof/big.bin").exists())

    def test_a_shorter_source_with_bytes_replaces_the_copy(self) -> None:
        # The rule: a source that has bytes always wins, because the worktree
        # file is the truth while it exists. Only an empty one is held back.
        ext_epic.rescue_all(self.ctx, "modal", self.wt)
        (self.wt / "specs/slices/s1/blueprint.md").write_text("sl\n")
        rec = ext_epic.rescue_all(self.ctx, "modal", self.wt)
        self.assertEqual(rec["not_rescued"], [])
        self.assertEqual((self.dest / "slices/s1/blueprint.md").read_text(), "sl\n")

    def budget_world(self) -> FakeCtx:
        specs = self.wt / "specs"
        (specs / "slices" / "s1" / "blueprint.md").write_bytes(b"b" * 300_000)
        (specs / "slices" / "s1" / "review-modal.md").write_bytes(b"r" * 300_000)
        (specs / "slices" / "s2" / "blueprint.md").write_bytes(b"b" * 300_000)
        (specs / "slices" / "s1" / "proof" / "big.bin").write_bytes(b"x" * 500_000)
        (specs / "slices" / "s10").mkdir()
        (specs / "slices" / "s10" / "blueprint.md").write_text("slice 10\n")
        self.cfg.epic_rescue_max_mb = 1
        return FakeCtx(self.cfg)

    def test_the_byte_budget_keeps_the_plans_and_names_the_rest(self) -> None:
        ctx = self.budget_world()
        chosen, left = ext_epic.select(ctx, self.wt)
        self.assertEqual(
            [rel for rel, _p in chosen],
            ["epic.md", "slices/s1/blueprint.md", "slices/s1/review-modal.md",
             "slices/s2/blueprint.md", "slices/s10/blueprint.md", "slices/s1/proof/claim.txt"],
        )
        self.assertEqual(left, ["slices/s1/proof/big.bin (over the 1 MB budget of one epic)"])
        rec = ext_epic.rescue_all(ctx, "modal", self.wt)
        self.assertEqual(rec["files"], 6)
        self.assertEqual(rec["not_rescued"], left)
        self.assertFalse((self.dest / "slices/s1/proof/big.bin").exists())
        self.assertLessEqual(sum(p.stat().st_size for p in self.dest.rglob("*") if p.is_file()), 1_000_000)
        self.assertEqual(ext_epic.unrescued(ctx, "modal", self.wt), left)
        # the same worktree gives the same selection
        self.assertEqual(ext_epic.select(ctx, self.wt), (chosen, left))

    def test_the_default_budget_is_the_setting(self) -> None:
        self.assertEqual(config.EPIC_RESCUE_MAX_MB, 20)
        self.assertEqual(ext_epic.budget_bytes(self.ctx), 20_000_000)
        self.assertIn("epic_rescue_max_mb", config.KEY_NAMES)

    def test_a_directory_that_cannot_be_listed_is_named(self) -> None:
        locked = self.wt / "specs/slices/s1/proof"
        os.chmod(str(locked), 0)
        self.addCleanup(os.chmod, str(locked), 0o755)
        if os.access(str(locked), os.R_OK):
            self.skipTest("this user can read a mode-0 directory")
        rows, skipped = ext_epic.sources(self.wt)
        self.assertNotIn("slices/s1/proof/claim.txt", [rel for rel, _p in rows])
        self.assertEqual(len(skipped), 1)
        self.assertTrue(skipped[0].startswith("slices/s1/proof/ (cannot be listed:"), skipped[0])
        self.assertIn(skipped[0], ext_epic.unrescued(self.ctx, "modal", self.wt))

    def test_dry_run_writes_nothing(self) -> None:
        ext_epic.rescue_all(FakeCtx(self.cfg, dry_run=True), "modal", self.wt)
        self.assertFalse(self.dest.exists())

    def test_refuses_a_destination_outside_artifacts(self) -> None:
        with self.assertRaises(config.RefusedWrite):
            ext_epic.rescue(self.ctx, self.wt / "specs/epic.md", self.cfg.vault / "Features" / "x.md")
        with self.assertRaises(config.RefusedWrite):
            ext_epic.rescue(self.ctx, self.wt / "specs/epic.md",
                            self.cfg.artifacts_dir / ".." / "Home.md")

    def test_the_renderer_still_refuses_artifacts(self) -> None:
        with self.assertRaises(config.RefusedWrite):
            render.guard_path(self.cfg, self.dest / "epic.md")

    def test_an_ordinary_worktree_has_nothing_to_rescue(self) -> None:
        plain = self.tmp / "wts" / "plain"
        (plain / "specs").mkdir(parents=True)
        (plain / "specs" / "blueprint.md").write_text("x\n")
        self.assertEqual(ext_epic.rescue_all(self.ctx, "plain", plain), {"files": 0, "not_rescued": []})
        self.assertFalse((self.cfg.artifacts_dir / "plain").exists())


# --------------------------------------------------------------------------
# End to end: the board on a scratch epic
# --------------------------------------------------------------------------


class BoardTests(WorldCase):
    def epic_world(self) -> Path:
        wt = self.w.worktree("modal", EPIC_MD.format(name="modal"), slices=2)
        (wt / "specs" / "slices" / "s1").mkdir(parents=True)
        (wt / "specs" / "slices" / "s1" / "blueprint.md").write_text("---\nfeature: modal\n---\nslice 1\n")
        self.w.worktree("plain")
        self.w.prs = [pr(102, "epic/modal/s2", updatedAt="2026-11-09T10:00:00Z"),
                      pr(101, "epic/modal/s1", draft=False, reviewDecision="REVIEW_REQUIRED"),
                      pr(55, "plain")]
        return wt

    def test_one_card_and_no_stray_files(self) -> None:
        self.epic_world()
        self.w.board()
        v = self.w.vault
        self.assertEqual(self.w.names(v / "Features"), ["modal.md", "plain.md"])
        self.assertEqual(self.w.names(v / ".factory" / "gates"), ["modal.json", "plain.json"])
        self.assertEqual(self.w.names(v / ".factory" / "timeline"), ["modal.ndjson", "plain.ndjson"])
        state = [n for n in self.w.names(self.w.state) if n.startswith(("modal", "plain"))]
        self.assertEqual(state, ["modal.json", "plain.json"])
        home = (v / "Home.md").read_text()
        self.assertIn("[[modal]]", home)
        self.assertNotIn("epic/modal", home)
        # A slice head holds two slashes. It never becomes a path anywhere the
        # board writes: no directory `epic`, nothing nested under one.
        for root in (v / ".factory", self.w.state, v / "Features"):
            nested = [q.relative_to(root).as_posix() for q in root.rglob("*")
                      if q.relative_to(root).parts[0] == "epic" or len(q.relative_to(root).parts) > 2]
            self.assertEqual(nested, [], root)

    def test_the_note_lists_the_slices_in_order(self) -> None:
        self.epic_world()
        self.w.board()
        note = (self.w.vault / "Features" / "modal.md").read_text()
        self.assertIn("## Epic", note)
        self.assertIn("- Plan: [[Specs/modal/epic|epic.md]]", note)
        self.assertIn("in the order of the plan", note)
        i1 = note.index("  - s1: [moose #101](https://github.com/idaholab/moose/pull/101), ready")
        i2 = note.index("  - s2: [moose #102](https://github.com/idaholab/moose/pull/102), draft")
        self.assertLess(i1, i2)
        self.assertIn("- Archived slice plans: [[Specs/modal/slices/s1/blueprint|s1]]", note)
        self.assertNotIn("## Epic", (self.w.vault / "Features" / "plain.md").read_text())

    def test_the_plan_and_the_slices_are_rescued(self) -> None:
        wt = self.epic_world()
        self.w.board()
        dest = self.w.vault / "Artifacts" / "modal"
        self.assertEqual((dest / "epic.md").read_bytes(), (wt / "specs" / "epic.md").read_bytes())
        self.assertTrue((dest / "slices" / "s1" / "blueprint.md").is_file())
        self.assertFalse((self.w.vault / "Artifacts" / "plain" / "epic.md").exists())
        # the archived slice blueprint under specs/slices/ is not the live blueprint
        obs = json.loads((self.w.state / "modal.json").read_text())["obs"]
        self.assertIsNone(obs["blueprint"])

    def test_second_run_and_rebuild_are_byte_identical(self) -> None:
        self.epic_world()
        self.w.board()
        v = self.w.vault
        first = {p.name: p.read_bytes() for p in (v / "Features").glob("*.md")}
        first["Home.md"] = (v / "Home.md").read_bytes()
        self.w.board()
        again = {p.name: p.read_bytes() for p in (v / "Features").glob("*.md")}
        again["Home.md"] = (v / "Home.md").read_bytes()
        self.assertEqual(first, again)
        for p in list((v / "Features").glob("*.md")) + [v / "Home.md", v / "Board.html"]:
            p.unlink()
        self.w.board()
        rebuilt = {p.name: p.read_bytes() for p in (v / "Features").glob("*.md")}
        rebuilt["Home.md"] = (v / "Home.md").read_bytes()
        self.assertEqual(first, rebuilt)

    def test_a_conflicting_slice_prints_stack_sync_on_the_card(self) -> None:
        wt = self.epic_world()
        self.w.prs[0]["mergeable"] = "CONFLICTING"
        self.w.board()
        note = (self.w.vault / "Features" / "modal.md").read_text()
        want = "cd %s && %s sync" % (wt, self.w.meta / "scripts" / "stack")
        self.assertIn(want, note)
        self.assertNotIn("git rebase upstream/devel", note)

    def test_other_machine_one_card_and_no_stray_files(self) -> None:
        # No worktree: the other Mac, or this one after a teardown.
        self.w.prs = [pr(102, "epic/modal/s2"), pr(101, "epic/modal/s1", draft=False),
                      pr(90, "epic/modal/s3", state="MERGED")]
        self.w.board()
        v = self.w.vault
        self.assertEqual(self.w.names(v / "Features"), ["modal.md"])
        self.assertEqual(self.w.names(v / ".factory" / "gates"), ["modal.json"])
        self.assertEqual(self.w.names(v / ".factory" / "timeline"), ["modal.ndjson"])
        self.assertEqual(
            [n for n in self.w.names(self.w.state) if n not in ("gh-cache.json", "manifest.json", "stamps.json")],
            ["modal.json"],
        )
        note = (v / "Features" / "modal.md").read_text()
        self.assertIn("- Plan: _no `specs/epic.md` on this machine.", note)
        self.assertIn("- Slices with a pull request, in numeric order:", note)
        i1 = note.index("  - s1: [moose #101](https://github.com/idaholab/moose/pull/101), ready")
        i2 = note.index("  - s2: [moose #102](https://github.com/idaholab/moose/pull/102), draft")
        i3 = note.index("  - s3: [moose #90](https://github.com/idaholab/moose/pull/90), merged")
        self.assertLess(i1, i2)
        self.assertLess(i2, i3)

    def test_a_collision_writes_no_gate_and_says_so(self) -> None:
        self.w.worktree("plain")
        self.w.prs = [pr(31, "epic/plain/s1"), pr(32, "epic/plain/s2", state="MERGED")]
        log = self.w.board()
        v = self.w.vault
        self.assertEqual(self.w.names(v / "Features"), ["plain.md"])
        # No pull request reached the card, so nothing was ever granted on it.
        self.assertEqual(self.w.names(v / ".factory" / "gates"), [])
        events = [json.loads(line)["event"]
                  for line in (v / ".factory" / "timeline" / "plain.ndjson").read_text().splitlines()]
        self.assertEqual(events, ["adopted"])
        self.assertEqual(json.loads((self.w.state / "plain.json").read_text())["obs"]["prs"], [])
        self.assertNotIn("## Epic", (v / "Features" / "plain.md").read_text())
        self.assertEqual(log.count("epic: 2 slice pull request(s) are on no card"), 1)
        self.assertIn("moose #31 epic/plain/s1", log)
        # doctor reads what the board left, with no probe round of its own
        ctx = Ctx(config=self.w.cfg(), state_dir=self.w.state, vault_dir=v, now="x")
        rows = {name: (ok, hint) for name, ok, hint in ext_epic.doctor_checks(ctx)}
        ok, hint = rows["every slice pull request is on the card of its epic"]
        self.assertFalse(ok)
        self.assertIn("moose #32 epic/plain/s2", hint)
        # and the row clears when the collision does
        self.w.prs = []
        self.w.board()
        self.assertFalse((self.w.state / ext_epic.COLLISIONS_NAME).exists())
        rows = {name: ok for name, ok, _hint in ext_epic.doctor_checks(ctx)}
        self.assertTrue(rows["every slice pull request is on the card of its epic"])

    def test_a_slice_shaped_head_never_touches_an_ordinary_card(self) -> None:
        # The gate files are append-only, so this is the test that matters most.
        self.w.worktree("plain")
        self.w.prs = [pr(31, "plain-s3"), pr(32, "plain-s4", state="MERGED"),
                      pr(33, "plain-s5", state="CLOSED")]
        self.w.board()
        v = self.w.vault
        self.assertEqual(self.w.names(v / "Features"), ["plain-s3.md", "plain.md"])
        # No grant was ever made on `plain`, so it has no gate file at all.
        self.assertEqual(self.w.names(v / ".factory" / "gates"), ["plain-s3.json"])
        own = json.loads((v / ".factory" / "gates" / "plain-s3.json").read_text())
        self.assertEqual(sorted(own), ["ship"])
        self.assertEqual((own["ship"]["state"], own["ship"]["via"]), ("granted", "gh"))
        events = [json.loads(line)["event"]
                  for line in (v / ".factory" / "timeline" / "plain.ndjson").read_text().splitlines()]
        self.assertNotIn("gate-granted", events)
        obs = json.loads((self.w.state / "plain.json").read_text())["obs"]
        self.assertEqual(obs["prs"], [])
        self.assertNotIn("## Epic", (v / "Features" / "plain.md").read_text())

    def test_the_rescued_copy_outlives_the_worktree(self) -> None:
        wt = self.epic_world()
        self.w.prs = [pr(101, "epic/modal/s1", state="MERGED"), pr(102, "epic/modal/s2", state="MERGED")]
        self.w.board()
        git(self.w.meta / "moose", "worktree", "remove", "--force", str(wt / "moose"))
        git(self.w.meta, "worktree", "remove", "--force", str(wt))
        self.w.board()
        dest = self.w.vault / "Artifacts" / "modal"
        self.assertEqual((dest / "epic.md").read_text(), EPIC_MD.format(name="modal"))
        self.assertTrue((dest / "slices" / "s1" / "blueprint.md").is_file())

    def lane(self, feature: str = "modal") -> str:
        return json.loads((self.w.state / (feature + ".json")).read_text())["lane"]

    def test_the_lane_sequence_on_the_board(self) -> None:
        two = EPIC_MD.format(name="modal").replace("| s3 | third | s2 | z | t3 |\n", "")
        self.w.worktree("modal", two, slices=2)
        v = self.w.vault

        def home_offers_teardown() -> bool:
            return "teardown modal" in (v / "Home.md").read_text()

        self.w.prs = [pr(101, "epic/modal/s1", draft=False)]
        self.w.board()
        self.assertEqual(self.lane(), PR_READY)

        self.w.prs = [pr(101, "epic/modal/s1", state="MERGED")]      # s2 sealed, no pull request
        self.w.board()
        self.assertEqual(self.lane(), SCAFFOLDED)
        self.assertFalse(home_offers_teardown())
        note = (v / "Features" / "modal.md").read_text()
        self.assertNotIn("signal-regression", note.split("## Epic")[0])

        self.w.prs = [pr(101, "epic/modal/s1", state="MERGED"), pr(102, "epic/modal/s2")]
        self.w.board()
        self.assertEqual(self.lane(), SHIPPED)
        self.assertFalse(home_offers_teardown())

        self.w.prs = [pr(101, "epic/modal/s1", state="MERGED"), pr(102, "epic/modal/s2", state="MERGED")]
        self.w.board()
        self.assertEqual(self.lane(), MERGED)
        self.assertTrue(home_offers_teardown())
        state = json.loads((self.w.state / "modal.json").read_text())
        self.assertEqual(state["epic_merged"], [1, 2])
        causes = [json.loads(line).get("cause")
                  for line in (v / ".factory" / "timeline" / "modal.ndjson").read_text().splitlines()]
        self.assertEqual([c for c in causes if c], ["epic-next-slice"])

    def test_rebuild_is_byte_identical_with_a_collision_present(self) -> None:
        self.epic_world()
        self.w.prs += [pr(31, "epic/plain/s1"), pr(32, "epic/plain/s2", state="MERGED")]
        self.w.board()
        v = self.w.vault
        kept = self.w.state / ext_epic.COLLISIONS_NAME

        def picture() -> Dict[str, bytes]:
            out = {p.name: p.read_bytes() for p in (v / "Features").glob("*.md")}
            out["Home.md"] = (v / "Home.md").read_bytes()
            out["Board.html"] = (v / "Board.html").read_bytes()
            out["collisions"] = kept.read_bytes()
            out["gates"] = json.dumps({p.name: p.read_text() for p in (v / ".factory" / "gates").glob("*")},
                                      sort_keys=True).encode()
            return out

        first, stamp = picture(), kept.stat().st_mtime_ns
        self.assertEqual(sorted(json.loads(first["gates"])), ["modal.json", "plain.json"])
        self.w.board()
        self.assertEqual(picture(), first)
        self.assertEqual(kept.stat().st_mtime_ns, stamp)          # not rewritten when nothing changed
        for path in list((v / "Features").glob("*.md")) + [v / "Home.md", v / "Board.html"]:
            path.unlink()
        self.w.board()
        self.assertEqual(picture(), first)

    def test_after_a_teardown_the_same_card_goes_on(self) -> None:
        # Slice 2 is still open when the worktree goes. The card keeps its id,
        # its gate file and its timeline, and now links the rescued plan.
        wt = self.epic_world()
        self.w.board()
        git(self.w.meta / "moose", "worktree", "remove", "--force", str(wt / "moose"))
        git(self.w.meta, "worktree", "remove", "--force", str(wt))
        self.w.board()
        v = self.w.vault
        self.assertIn("modal.md", self.w.names(v / "Features"))
        self.assertEqual([n for n in self.w.names(v / ".factory" / "gates") if n.startswith("modal")],
                         ["modal.json"])
        note = (v / "Features" / "modal.md").read_text()
        self.assertIn("- Plan: [[Artifacts/modal/epic|epic.md]]", note)
        self.assertIn("  - s1: [moose #101]", note)
        self.assertIn("  - s2: [moose #102]", note)

    def test_a_card_whose_plan_is_gone_links_the_rescued_copy(self) -> None:
        wt = self.epic_world()
        self.w.prs = []
        self.w.board()
        (wt / "specs" / "epic.md").unlink()
        self.w.board()
        note = (self.w.vault / "Features" / "modal.md").read_text()
        self.assertIn("- Plan: [[Artifacts/modal/epic|epic.md]]", note)
        self.assertIn("[[Artifacts/modal/slices/s1/blueprint|s1]]", note)


class TeardownPlanTests(WorldCase):
    def plan(self, force: bool = False) -> Dict[str, Any]:
        self.w.write_cache()
        ctx = cli.build_ctx(self.w.cfg(), dry_run=False, quiet=True)
        card = ctx.card("modal")
        self.assertIsNotNone(card)
        return ext_teardown.plan(card, ctx, force=force, measure=False)

    def test_rescued_files_do_not_block(self) -> None:
        self.w.worktree("modal", EPIC_MD.format(name="modal"))
        planned = self.plan()
        self.assertEqual(planned["epic_lost"], [])
        self.assertFalse([b for b in planned["blockers"] if "Artifacts/" in b])

    def test_an_unrescued_file_blocks_until_force(self) -> None:
        wt = self.w.worktree("modal", EPIC_MD.format(name="modal"))
        (wt / "specs" / "slices" / "s1").mkdir(parents=True)
        os.symlink(str(self.w.tmp), str(wt / "specs" / "slices" / "s1" / "elsewhere"))
        planned = self.plan()
        self.assertEqual(planned["epic_lost"], ["slices/s1/elsewhere/ (a symlink)"])
        hit = [b for b in planned["blockers"] if "have no copy in Artifacts/modal/" in b]
        self.assertEqual(len(hit), 1)
        self.assertTrue(hit[0].endswith("(--force overrides)"))
        forced = self.plan(force=True)
        self.assertFalse([b for b in forced["blockers"] if "Artifacts/" in b])
        self.assertTrue([x for x in forced["warnings"] if "have no copy in Artifacts/modal/" in x])

    def test_an_ordinary_card_is_unchanged(self) -> None:
        self.w.worktree("modal")
        planned = self.plan()
        self.assertEqual(planned["epic_lost"], [])

    def test_a_check_that_raises_blocks(self) -> None:
        self.w.worktree("modal", EPIC_MD.format(name="modal"))
        real = ext_epic.unrescued

        def boom(*_a: Any, **_k: Any) -> List[str]:
            raise PermissionError("no")

        ext_epic.unrescued = boom
        try:
            planned = self.plan()
            forced = self.plan(force=True)
        finally:
            ext_epic.unrescued = real
        self.assertEqual(planned["epic_lost"], ["the check itself failed (PermissionError: no)"])
        hit = [b for b in planned["blockers"] if "have no copy in Artifacts/modal/" in b]
        self.assertEqual(len(hit), 1)
        self.assertIn("the check itself failed", hit[0])
        self.assertFalse([b for b in forced["blockers"] if "Artifacts/" in b])

    def test_a_file_over_the_budget_blocks(self) -> None:
        wt = self.w.worktree("modal", EPIC_MD.format(name="modal"))
        (wt / "specs" / "slices" / "s1").mkdir(parents=True)
        (wt / "specs" / "slices" / "s1" / "figure.png").write_bytes(b"x" * 1_500_000)
        self.w.cfg_file.write_text(self.w.cfg_file.read_text() + "epic_rescue_max_mb = 1\n")
        planned = self.plan()
        self.assertEqual(
            planned["epic_lost"], ["slices/s1/figure.png (over the 1 MB budget of one epic)"]
        )
        self.assertTrue([b for b in planned["blockers"] if "over the 1 MB budget" in b])
        self.assertFalse((self.w.vault / "Artifacts" / "modal" / "slices" / "s1" / "figure.png").exists())



class TeardownChainTests(WorldCase):
    """An epic's branch is never pushed. Teardown judges the chain instead."""

    def setUp(self) -> None:
        super().setUp()
        self.wt = self.w.worktree("modal", EPIC_MD.format(name="modal"), slices=2)
        self.main = self.w.meta / "moose"
        self.checkout = self.wt / "moose"

    def sha(self, ref: str) -> str:
        return git(self.main, "rev-parse", ref).strip()

    def publish(self, k: int, ref: Optional[str] = None) -> None:
        git(self.main, "update-ref", "refs/remotes/origin/epic/modal/s%d" % k,
            self.sha(ref or "epic/modal/s%d" % k))

    def plan(self, force: bool = False, feature: str = "modal") -> Dict[str, Any]:
        self.w.write_cache()
        ctx = cli.build_ctx(self.w.cfg(), dry_run=False, quiet=True)
        card = ctx.card(feature)
        self.assertIsNotNone(card)
        self.card = card
        return ext_teardown.plan(card, ctx, force=force, measure=False)

    def moose(self, planned: Dict[str, Any], key: str = "blockers") -> List[str]:
        return [line for line in planned[key] if line.startswith("moose: ")]

    def test_a_published_chain_does_not_block(self) -> None:
        self.publish(1)
        self.publish(2)
        planned = self.plan()
        # The old test would fire: two commits ahead on a branch that was never pushed.
        self.assertEqual(self.card.repos["moose"]["ahead"], 2)
        self.assertIs(self.card.repos["moose"]["pushed"], False)
        self.assertEqual(self.moose(planned), [])
        self.assertFalse([b for b in planned["blockers"] if "never pushed" in b and b.startswith("moose ")])

    def test_a_pass_says_what_it_leaned_on(self) -> None:
        self.publish(1)
        self.publish(2)
        planned = self.plan()
        note = [w for w in planned["warnings"] if w.startswith("moose: 2 slice(s) equal the fork as of the last fetch")]
        self.assertEqual(len(note), 1)
        self.assertIn("epic/modal/s1, epic/modal/s2", note[0])
        self.assertIn("nothing was fetched", note[0])

    def test_a_detached_checkout_gets_the_ordinary_test(self) -> None:
        # Both slices are published, so the chain alone would pass. The commit
        # below is on no branch at all.
        self.publish(1)
        self.publish(2)
        git(self.checkout, "checkout", "-q", "--detach")
        (self.checkout / "stray.txt").write_text("x\n")
        git(self.checkout, "add", "-A")
        git(self.checkout, "commit", "-q", "-m", "stray work")
        planned = self.plan()
        self.assertIn("moose is 3 commits ahead and was never pushed (--force overrides)", planned["blockers"])
        self.assertEqual(self.moose(planned), [])          # the branch `modal` itself is still fine

    def test_a_renamed_checkout_gets_the_ordinary_test(self) -> None:
        self.publish(1)
        self.publish(2)
        git(self.checkout, "checkout", "-q", "-b", "modal-redo")
        (self.checkout / "redo.txt").write_text("x\n")
        git(self.checkout, "add", "-A")
        git(self.checkout, "commit", "-q", "-m", "redo")
        planned = self.plan()
        self.assertIn("moose is 3 commits ahead and was never pushed (--force overrides)", planned["blockers"])

    def test_off_the_branch_the_chain_is_still_judged(self) -> None:
        # Detached, and the branch `modal` holds a slice the fork never got.
        self.publish(1)
        git(self.checkout, "checkout", "-q", "--detach")
        planned = self.plan()
        self.assertTrue([b for b in planned["blockers"] if "never pushed (--force overrides)" in b and b.startswith("moose is")])
        hit = self.moose(planned)
        self.assertEqual(len(hit), 1)
        self.assertIn("epic/modal/s2", hit[0])

    def test_an_absent_branch_is_a_problem_not_a_pass(self) -> None:
        run = lambda argv: probe.run(argv)
        report = ext_epic.chain(str(self.main), "no-such-epic", run)
        self.assertIs(report["branch"], False)
        self.assertEqual(len(report["problems"]), 1)
        self.assertIn("there is no local branch no-such-epic here", report["problems"][0])
        ok = ext_epic.chain(str(self.main), "modal", run)
        self.assertIs(ok["branch"], True)

    def test_a_merged_chain_does_not_block(self) -> None:
        # Both slices are in next. The fork branches are gone, as after a merge.
        git(self.main, "update-ref", "refs/remotes/upstream/next", self.sha("modal"))
        self.assertEqual(self.moose(self.plan()), [])

    def test_a_wip_commit_blocks_and_is_named(self) -> None:
        self.publish(1)
        self.publish(2)
        (self.checkout / "wip.txt").write_text("half done\n")
        git(self.checkout, "add", "-A")
        git(self.checkout, "commit", "-q", "-m", "WIP slice 3")
        hit = self.moose(self.plan())
        self.assertEqual(len(hit), 1)
        self.assertIn("1 commit(s) on modal are in no slice: %s WIP slice 3" % self.sha("modal")[:9], hit[0])
        self.assertTrue(hit[0].endswith("(--force overrides)"))

    def test_a_sealed_slice_that_was_never_published_blocks(self) -> None:
        self.publish(1)
        hit = self.moose(self.plan())
        self.assertEqual(len(hit), 1)
        self.assertIn("epic/modal/s2 (%s) was sealed and never published" % self.sha("epic/modal/s2")[:9], hit[0])

    def test_a_slice_that_differs_from_the_fork_blocks(self) -> None:
        self.publish(1)
        self.publish(2, ref="epic/modal/s1")        # the fork holds an older slice 2
        hit = self.moose(self.plan())
        self.assertEqual(len(hit), 1)
        self.assertIn("epic/modal/s2 differs from the fork as of the last fetch: local %s, origin %s"
                      % (self.sha("epic/modal/s2")[:9], self.sha("epic/modal/s1")[:9]), hit[0])

    def test_nothing_published_names_every_slice(self) -> None:
        hit = self.moose(self.plan())
        self.assertEqual(len(hit), 2)
        self.assertIn("epic/modal/s1", hit[0])
        self.assertIn("epic/modal/s2", hit[1])

    def test_force_turns_the_chain_problems_into_notes(self) -> None:
        forced = self.plan(force=True)
        self.assertEqual(self.moose(forced), [])
        self.assertEqual(len([w for w in self.moose(forced, "warnings") if "never published" in w]), 2)

    def test_no_upstream_ref_blocks(self) -> None:
        for name in ("devel", "next"):
            git(self.main, "update-ref", "-d", "refs/remotes/upstream/" + name)
        self.publish(1)
        self.publish(2)
        hit = self.moose(self.plan())
        self.assertEqual(len(hit), 1)
        self.assertIn("no upstream/next and no upstream/devel ref", hit[0])

    def test_refs_that_cannot_be_read_block(self) -> None:
        self.publish(1)
        self.publish(2)
        real = ext_teardown.RUN

        def run(argv: List[str], timeout: Optional[int] = None) -> Any:
            if "for-each-ref" in argv and "refs/heads/modal" in argv:
                return ("", False)
            return real(argv, timeout=timeout)

        ext_teardown.RUN = run
        try:
            planned = self.plan()
        finally:
            ext_teardown.RUN = real
        self.assertEqual(len(self.moose(planned)), 1)
        self.assertIn("the refs could not be read", self.moose(planned)[0])

    def test_a_chain_check_that_raises_blocks(self) -> None:
        real = ext_epic.chain

        def boom(*_a: Any, **_k: Any) -> Dict[str, Any]:
            raise RuntimeError("no")

        ext_epic.chain = boom
        try:
            planned = self.plan()
        finally:
            ext_epic.chain = real
        self.assertTrue([b for b in planned["blockers"] if "the chain check itself failed (RuntimeError: no)" in b])

    def test_the_plan_lists_the_refs_it_leaves_behind(self) -> None:
        self.publish(1)
        self.publish(2)
        git(self.main, "update-ref", "refs/stack/modal/pushed/s1", self.sha("epic/modal/s1"))
        planned = self.plan()
        self.assertEqual(
            planned["epic_left"],
            {"moose": ["epic/modal/s1", "epic/modal/s2", "refs/stack/modal/pushed/s1"]},
        )
        note = [w for w in planned["warnings"] if w.startswith("moose keeps 3 local ref(s) of this epic")]
        self.assertEqual(len(note), 1)
        self.assertIn("epic/modal/s1, epic/modal/s2, refs/stack/modal/pushed/s1", note[0])
        self.assertIn("/feature-remove", note[0])
        # and it deletes none of them: no command names a slice ref
        flat = [" ".join(argv) for _label, argv in planned["commands"]]
        self.assertFalse([c for c in flat if "epic/modal" in c or "refs/stack" in c])
        self.assertIn("git -C %s branch -D modal" % self.main, flat)

    def test_an_ordinary_card_keeps_the_never_pushed_test(self) -> None:
        plain = self.w.worktree("plain")
        (plain / "moose" / "work.txt").write_text("x\n")
        git(plain / "moose", "add", "-A")
        git(plain / "moose", "commit", "-q", "-m", "feat: work")
        planned = self.plan(feature="plain")
        self.assertIn("moose is 1 commits ahead and was never pushed (--force overrides)", planned["blockers"])
        self.assertEqual(planned["epic_left"], {})
        self.assertFalse([w for w in planned["warnings"] if "local ref(s) of this epic" in w])


if __name__ == "__main__":
    unittest.main(verbosity=1)
