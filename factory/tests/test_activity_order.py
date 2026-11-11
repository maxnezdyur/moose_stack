"""The card order inside every board group: the newest activity first.

    /opt/homebrew/bin/python3 factory/tests/test_activity_order.py

The key is ``model.activity_key``. Home.md, Board.html and ``factory board``
all sort by it. The stamp is the newest probe value, never the clock.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

FACTORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FACTORY))
sys.path.insert(0, str(FACTORY / "tests"))
sys.dont_write_bytecode = True

from tool import derive, ext_board_html  # noqa: E402
from tool.model import NEEDS_YOU, BoardCard, FeatureCard, activity_key  # noqa: E402
from test_epic import GIT_ENV, WorldCase, git, pr  # noqa: E402


class KeyTests(unittest.TestCase):
    def test_newest_first_id_on_tie_unstamped_last(self) -> None:
        cards = [
            FeatureCard(id="d"),
            FeatureCard(id="b", activity_at=100.0),
            FeatureCard(id="a", activity_at=100.0),
            FeatureCard(id="c", activity_at=300.0),
            FeatureCard(id="a0"),
            BoardCard(id="camp", activity_at=200.0),
        ]
        self.assertEqual(
            [c.id for c in sorted(cards, key=activity_key)], ["c", "camp", "a", "b", "a0", "d"]
        )

    def test_flags_do_not_set_the_order(self) -> None:
        red = FeatureCard(id="red", flags=["conflicting", "ci-red"], activity_at=1.0)
        quiet = FeatureCard(id="quiet", flags=["marker-missing"], activity_at=2.0)
        self.assertEqual([c.id for c in sorted([red, quiet], key=activity_key)], ["quiet", "red"])

    def test_activity_at_reads_every_probe_but_fetch_head(self) -> None:
        obs = {
            "pulse": 10.0,
            "blueprint": {"mtime": 20.0},
            "build": {"mtime": 30.0},
            "sessions": [{"updatedAt": 40_000, "statusUpdatedAt": 50_000}],
            "prs": [{"updatedAt": "1970-01-01T00:01:00Z"}],
            "repos": {"moose": {"head_at": 70, "fetched_at": 9_999_999.0}},
        }
        self.assertEqual(derive.activity_at(obs), 70.0)
        obs["repos"]["moose"]["head_at"] = None
        self.assertEqual(derive.activity_at(obs), 60.0)       # the PR, not FETCH_HEAD
        obs["prs"] = []
        self.assertEqual(derive.activity_at(obs), 50.0)       # epoch ms read as seconds
        self.assertIsNone(derive.activity_at({"repos": {"m": {"fetched_at": 5.0}}}))


class BoardOrderTests(WorldCase):
    def commit_at(self, name: str, when: str) -> None:
        moose = self.w.wts / name / "moose"
        (moose / "work.txt").write_text(when + "\n")
        env = dict(os.environ)
        env.update(GIT_ENV)
        env.update({"GIT_AUTHOR_DATE": when, "GIT_COMMITTER_DATE": when})
        import subprocess

        subprocess.run(["git", "-C", str(moose), "add", "-A"], check=True, env=env)
        subprocess.run(["git", "-C", str(moose), "commit", "-q", "-m", "w"], check=True, env=env)

    def test_home_and_board_html_share_the_order(self) -> None:
        # Ids in reverse of the activity order, so an id sort would fail.
        for name, when in (("alpha", "2031-01-01T00:00:00Z"),
                           ("bravo", "2032-01-01T00:00:00Z"),
                           ("charlie", "2033-01-01T00:00:00Z")):
            self.w.worktree(name)
            self.commit_at(name, when)
        self.w.board()
        home = (self.w.vault / "Home.md").read_text()
        idx = [home.index("[[%s]]" % n) for n in ("charlie", "bravo", "alpha")]
        self.assertEqual(idx, sorted(idx), home)
        page = (self.w.vault / "Board.html").read_text()
        idx = [page.index(">%s<" % n) for n in ("charlie", "bravo", "alpha")]
        self.assertEqual(idx, sorted(idx))


if __name__ == "__main__":
    unittest.main(verbosity=1)
