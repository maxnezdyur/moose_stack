"""The test lab for scripts/stack.

Each test builds scratch repositories in a temporary directory: a bare
`upstream` (branches devel and next), a bare `origin` (the fork), a work
checkout at <tmp>/wt/moose on branch E, and a `maint` clone that plays the
maintainer. No test touches a real repository, the network or GitHub; `gh` is
a fake that reads a JSON file.

Run from the repository root:

    python3 -m unittest discover -s scripts/tests -v
"""

import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

STACK = Path(__file__).resolve().parents[1] / "stack"


def load_stack(env):
    """Import scripts/stack as a module, under the given environment."""
    with mock.patch.dict(os.environ, env, clear=True), \
            mock.patch.object(sys, "dont_write_bytecode", True):
        loader = importlib.machinery.SourceFileLoader("stack_under_test", str(STACK))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
    return module


# Slice branch names come from scripts/stack, the one place that spells them.
# No test writes a slice branch name as a literal.
NAMING = load_stack(dict(os.environ))


def sref(n, epic="E"):
    return NAMING.slice_branch(epic, n)


S1, S2, S3, S4 = (sref(n) for n in (1, 2, 3, 4))


def push_pending(sid):
    """The exact `problem:` text for a lowest open slice whose push was deferred."""
    return NAMING.PUSH_PENDING % sid

FAKE_GH = r'''
import json, os, sys
if os.environ.get("FAKE_GH_FAIL"):
    sys.exit(1)
args = sys.argv[1:]
if os.environ.get("FAKE_GH_LOG"):
    open(os.environ["FAKE_GH_LOG"], "a").write(json.dumps(args) + "\n")
head = args[args.index("--head") + 1]
data = json.load(open(os.environ["FAKE_GH_DATA"]))
print(json.dumps(data.get(head, [])))
'''

FAKE_FORMATTER = """#!/bin/sh
# Stand-in for git-clang-format: fails on request and on a file that does not exist.
[ -n "$FAKE_FMT_FAIL" ] && { echo "formatter exploded" >&2; exit 2; }
for a in "$@"; do
  [ "$a" = "--" ] && continue
  [ -e "$a" ] || { echo "error: $a does not exist" >&2; exit 2; }
  echo "$a" >> "$FAKE_FMT_LOG"
done
exit 0
"""

BASE_LINES = ["line%02d" % i for i in range(1, 21)]


def shared(**changes):
    """The 20-line shared file with some lines replaced: shared(l02='x')."""
    lines = list(BASE_LINES)
    for key, value in changes.items():
        lines[int(key[1:]) - 1] = value
    return "\n".join(lines) + "\n"


class Lab:
    def __init__(self, tmp):
        self.tmp = Path(tmp)
        self.up = self.tmp / "upstream.git"
        self.fork = self.tmp / "origin.git"
        self.wt = self.tmp / "wt"
        self.moose = self.wt / "moose"
        self.maint = self.tmp / "maint"
        self.gh_data = self.tmp / "gh.json"
        self.gh_data.write_text("{}")
        fake = self.tmp / "fake_gh.py"
        fake.write_text(FAKE_GH)
        home = self.tmp / "home"
        home.mkdir()
        bindir = self.tmp / "bin"
        bindir.mkdir()
        (bindir / "git-clang-format").write_text(FAKE_FORMATTER)
        os.chmod(bindir / "git-clang-format", 0o755)
        self.fmt_log = self.tmp / "formatted.log"
        self.env = dict(os.environ)
        for key in list(self.env):
            if key.startswith("GIT_") or key.startswith("STACK_"):
                del self.env[key]
        self.env.update({
            "HOME": str(home), "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_AUTHOR_NAME": "Lab", "GIT_AUTHOR_EMAIL": "lab@example.invalid",
            "GIT_COMMITTER_NAME": "Lab", "GIT_COMMITTER_EMAIL": "lab@example.invalid",
            "STACK_GH": "%s %s" % (sys.executable, fake), "FAKE_GH_DATA": str(self.gh_data),
            "STACK_CLAUDE_HOME": str(home / ".claude"), "GIT_TERMINAL_PROMPT": "0",
            "PATH": "%s%s%s" % (bindir, os.pathsep, os.environ.get("PATH", "")),
            "FAKE_FMT_LOG": str(self.fmt_log),
        })
        self.env.pop("FAKE_FMT_FAIL", None)
        self.env.pop("FAKE_GH_FAIL", None)
        self._build()

    # ---- plumbing

    def git(self, *args, cwd=None, check=True):
        proc = subprocess.run(["git"] + [str(a) for a in args], cwd=str(cwd or self.moose),
                              env=self.env, capture_output=True, text=True)
        if check and proc.returncode != 0:
            raise AssertionError("git %s failed:\n%s%s" % (" ".join(map(str, args)), proc.stdout,
                                                          proc.stderr))
        return proc.stdout.strip()

    def stack(self, *args, cwd=None, env=None):
        full = dict(self.env)
        if env:
            full.update(env)
        argv = [sys.executable, str(STACK)]
        if cwd is None:
            argv += ["-C", str(self.moose)]
        proc = subprocess.run(argv + [str(a) for a in args], cwd=str(cwd or self.moose), env=full,
                              capture_output=True, text=True)
        return proc.returncode, proc.stdout, proc.stderr

    def ok(self, *args, **kw):
        rc, out, err = self.stack(*args, **kw)
        if rc != 0:
            raise AssertionError("stack %s -> %d\n%s%s" % (" ".join(map(str, args)), rc, out, err))
        return out

    def sha(self, rev, cwd=None):
        return self.git("rev-parse", rev, cwd=cwd)

    def write(self, name, text, cwd=None):
        path = Path(cwd or self.moose) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def commit(self, message, cwd=None, **files):
        for name, text in files.items():
            self.write(name.replace("__", "."), text, cwd=cwd)
        self.git("add", "-A", cwd=cwd)
        self.git("commit", "-q", "-m", message, cwd=cwd)
        return self.sha("HEAD", cwd=cwd)

    def status(self):
        return json.loads(self.ok("status", "--json"))

    def row(self, sid):
        return [r for r in self.status()["slices"] if r["id"] == sid][0]

    def subjects(self, rng):
        out = self.git("log", "--format=%s", "--reverse", rng)
        return out.splitlines() if out else []

    def patch_id(self, commit):
        show = subprocess.run(["git", "show", "-U0", "--format=", commit], cwd=str(self.moose),
                              env=self.env, capture_output=True, text=True).stdout
        return subprocess.run(["git", "patch-id", "--stable"], input=show, cwd=str(self.moose),
                              env=self.env, capture_output=True, text=True).stdout.split()[0]

    def set_pr(self, head, number, state="OPEN", draft=True, oid=None):
        data = json.loads(self.gh_data.read_text())
        data[head] = [{"number": number, "state": state, "isDraft": draft,
                       "headRefOid": oid or "0" * 40}]
        self.gh_data.write_text(json.dumps(data))

    # ---- the world

    def _build(self):
        seed = self.tmp / "seed"
        self.git("init", "-q", "-b", "devel", seed, cwd=self.tmp)
        self.commit("devel 1", cwd=seed, shared__txt=shared(), readme__txt="base\n")
        self.git("init", "-q", "--bare", "-b", "next", self.up, cwd=self.tmp)
        self.git("push", "-q", self.up, "devel", cwd=seed)
        self.git("switch", "-q", "-c", "next", cwd=seed)
        self.commit("next 1", cwd=seed, upstream_a__txt="a\n")
        self.git("push", "-q", self.up, "next", cwd=seed)
        self.git("clone", "-q", "--bare", self.up, self.fork, cwd=self.tmp)
        self.wt.mkdir()
        (self.wt / "specs").mkdir()
        (self.wt / "specs" / "epic.md").write_text("---\nepic: E\n---\n")
        self.git("clone", "-q", "-o", "upstream", self.up, self.moose, cwd=self.tmp)
        self.git("remote", "add", "origin", self.fork)
        self.git("switch", "-q", "--no-track", "-c", "E", "upstream/devel")
        self.git("clone", "-q", self.up, self.maint, cwd=self.tmp)
        self.git("remote", "add", "fork", self.fork, cwd=self.maint)

    def slice(self, n, subject=None, seal=True):
        """One slice commit: its own file and one line of the shared file."""
        text = (self.moose / "shared.txt").read_text().splitlines()
        text[{1: 1, 2: 7, 3: 13, 4: 15}[n]] += " s%d" % n
        self.write("shared.txt", "\n".join(text) + "\n")
        self.write("s%d.txt" % n, "slice %d\n" % n)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", subject or "feat: slice %d" % n)
        if seal:
            self.assert_out = self.ok("seal")
        return self.sha("HEAD")

    def chain(self, n=2):
        return [self.slice(k) for k in range(1, n + 1)]

    def edit_line(self, number, value):
        text = (self.moose / "shared.txt").read_text().splitlines()
        text[number - 1] = value
        self.write("shared.txt", "\n".join(text) + "\n")

    def upstream_commit(self, message, **files):
        self.git("fetch", "-q", "origin", cwd=self.maint)
        self.git("switch", "-q", "next", cwd=self.maint)
        self.git("reset", "-q", "--hard", "origin/next", cwd=self.maint)
        sha = self.commit(message, cwd=self.maint, **files)
        self.git("push", "-q", "origin", "next", cwd=self.maint)
        return sha

    def upstream_merge(self, sha, number=1):
        """Merge a slice into upstream/next with a real merge commit, as GitHub does."""
        self.git("fetch", "-q", "origin", cwd=self.maint)
        self.git("fetch", "-q", "fork", cwd=self.maint)
        self.git("switch", "-q", "next", cwd=self.maint)
        self.git("reset", "-q", "--hard", "origin/next", cwd=self.maint)
        self.git("merge", "-q", "--no-ff", "-m", "Merge pull request #%d" % number, sha,
                 cwd=self.maint)
        self.git("push", "-q", "origin", "next", cwd=self.maint)
        return self.sha("HEAD", cwd=self.maint)

    def maintainer_push(self, branch, amend=False, merge_next=False):
        """A maintainer changes a PR head on the fork."""
        self.git("fetch", "-q", "fork", cwd=self.maint)
        self.git("fetch", "-q", "origin", cwd=self.maint)
        self.git("switch", "-q", "--detach", "fork/" + branch, cwd=self.maint)
        if merge_next:
            self.git("merge", "-q", "--no-ff", "-m", "Merge branch 'next'", "origin/next",
                     cwd=self.maint)
        elif amend:
            self.write("maint.txt", "amended by a maintainer\n", cwd=self.maint)
            self.git("add", "-A", cwd=self.maint)
            self.git("commit", "-q", "--amend", "--no-edit", cwd=self.maint)
        else:
            self.commit("maintainer: tweak", cwd=self.maint, maint__txt="from a maintainer\n")
        self.git("push", "-q", "--force", "fork", "HEAD:refs/heads/" + branch, cwd=self.maint)
        return self.sha("HEAD", cwd=self.maint)

    def fork_sha(self, branch):
        out = self.git("ls-remote", self.fork, "refs/heads/" + branch, cwd=self.tmp)
        return out.split()[0] if out else None


class StackTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.lab = Lab(os.path.realpath(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def crash(self, argv, where):
        """Run a verb in this process and kill it when it reaches the function `where`."""
        lab = self.lab
        module = load_stack(lab.env)

        def boom(*a, **k):
            raise KeyboardInterrupt("killed")

        with mock.patch.dict(os.environ, lab.env, clear=True), \
                mock.patch.object(module, where, boom), \
                contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(KeyboardInterrupt):
                module.main(["-C", str(lab.moose)] + argv)

    def refuse(self, *args, contains=(), **kw):
        rc, out, err = self.lab.stack(*args, **kw)
        self.assertEqual(rc, 1, "expected a refusal from `stack %s`\n%s%s"
                         % (" ".join(map(str, args)), out, err))
        self.assertTrue(err.startswith("stack: refused:"), err)
        for text in ([contains] if isinstance(contains, str) else contains):
            self.assertIn(text, err)
        return err

    def refs(self, branch=True):
        """Every local branch and every stack record. `branch=False` leaves out the
        epic branch, which moves when the fix itself is committed."""
        lab = self.lab
        out = lab.git("for-each-ref", "--format=%(refname) %(objectname)", "refs/heads", "refs/stack")
        found = dict(line.split(" ") for line in out.splitlines())
        if not branch:
            found.pop("refs/heads/" + lab.git("rev-parse", "--abbrev-ref", "E"), None)
        return found


# --------------------------------------------------------------------------- seal, status, base


class SealAndStatus(StackTest):
    def test_seal_allocates_ids_monotonically_and_refuses_a_wip_commit(self):
        lab = self.lab
        s1 = lab.slice(1)
        self.assertEqual(lab.assert_out.strip(), "s1")
        lab.slice(2)
        self.assertEqual(lab.assert_out.strip(), "s2")
        self.assertEqual(lab.sha("refs/stack/E/base"), lab.sha("upstream/devel"))
        # Slice 2 is dropped by hand. Its id is never used again.
        lab.git("update-ref", "-d", ("refs/heads/" + S2))
        lab.git("reset", "-q", "--keep", s1)
        lab.commit("feat: another slice", other__txt="x\n")
        self.assertEqual(lab.ok("seal").strip(), "s3")
        self.assertEqual(lab.sha(S3), lab.sha("HEAD"))
        # Nothing above the top slice.
        self.refuse("seal", contains="exactly one commit")
        # A WIP commit is not a slice.
        lab.commit("WIP half done", wip__txt="x\n")
        self.refuse("seal", contains="unfinished")
        # Two commits above the top slice.
        lab.commit("feat: second", second__txt="x\n")
        self.refuse("seal", contains="exactly one commit")
        self.assertIsNone(lab.git("for-each-ref", ("refs/heads/" + S4)) or None)

    def test_seal_first_slice_must_be_one_commit_above_upstream(self):
        lab = self.lab
        self.refuse("seal", contains="first slice")
        lab.commit("feat: a", a__txt="a\n")
        lab.commit("feat: b", b__txt="b\n")
        self.refuse("seal", contains="first slice")

    def test_status_json_shape(self):
        lab = self.lab
        lab.chain(2)
        lab.write("loose.txt", "x\n")
        data = lab.status()
        self.assertEqual(sorted(data), sorted([
            "epic", "checkout", "tip", "base", "next", "slices", "wip", "chain_ok",
            "rebase_in_progress", "problems", "notes"]))
        self.assertEqual(data["notes"], [])
        self.assertEqual(data["epic"], "E")
        self.assertEqual(data["base"], lab.sha("upstream/devel"))
        self.assertTrue(data["chain_ok"])
        self.assertFalse(data["rebase_in_progress"])
        self.assertEqual([r["id"] for r in data["slices"]], ["s1", "s2"])
        self.assertEqual(sorted(data["slices"][0]), sorted([
            "id", "ref", "sha", "commits", "state", "pr", "pushed_sha", "fork_sha", "drift",
            "behind"]))
        row = data["slices"][1]
        self.assertEqual((row["ref"], row["sha"], row["commits"], row["state"], row["pr"]),
                         (S2, lab.sha(S2), 1, "sealed", None))
        self.assertEqual(data["wip"], {"parked": 0, "unsealed": 0, "fixups": 0, "dirty": 1})
        self.assertEqual(data["problems"], [])
        text = lab.ok("status", "--no-gh")
        self.assertIn("chain: ok", text)

    def test_status_table_for_people(self):
        lab = self.lab
        s1, s2 = lab.chain(2)
        lab.ok("push", "s1", "s2")
        lab.set_pr(S1, 11, draft=False)
        lab.set_pr(S2, 12)
        lab.write("loose.txt", "x\n")
        lab.ok("park")
        lines = lab.ok("status").splitlines()
        row1 = [l for l in lines if l.split()[:1] == ["s1"]][0].split()
        self.assertEqual(row1[:3], ["s1", s1[:9], "1"])
        self.assertIn("in review", " ".join(row1))
        self.assertIn("#11", row1)
        row2 = [l for l in lines if l.split()[:1] == ["s2"]][0]
        self.assertRegex(row2, r"s2 +%s +1 +draft +#12" % s2[:9])
        self.assertIn("work above the top slice: 2 parked commit(s), 0 unsealed commit(s), "
                      "0 dirty path(s)", lines)
        self.assertEqual(lines[-1], "chain: ok")
        lab.maintainer_push(S2)
        self.assertRegex(lab.ok("status"), r"s2 .* DRIFT")
        lab.ok("unpark")
        lab.git("update-ref", ("refs/heads/" + S1), lab.sha("upstream/next"))   # break the chain
        text = lab.ok("status", "--no-gh")
        self.assertRegex(text, "chain: BROKEN %s \\(\\w+\\) is not built on %s"
                         % (re.escape(S2), re.escape(S1)))

    def test_status_states_follow_github(self):
        lab = self.lab
        lab.chain(3)
        lab.ok("push", "s1", "s2")
        lab.set_pr(S1, 11, draft=False)
        lab.set_pr(S2, 12, draft=True)
        rows = {r["id"]: r for r in lab.status()["slices"]}
        self.assertEqual([rows[k]["state"] for k in ("s1", "s2", "s3")],
                         ["in-review", "draft", "sealed"])
        self.assertEqual(rows["s1"]["pr"], 11)
        self.assertEqual(rows["s1"]["drift"], False)
        # With no answer from gh, a published slice is unknown and an unpublished one is sealed.
        rc, out, err = lab.stack("status", "--json", env={"FAKE_GH_FAIL": "1"})
        rows = {r["id"]: r for r in json.loads(out)["slices"]}
        self.assertEqual([rows[k]["state"] for k in ("s1", "s2", "s3")],
                         ["unknown", "unknown", "sealed"])

    def test_slots_counts_open_prs(self):
        lab = self.lab
        lab.chain(3)
        self.assertEqual(lab.ok("slots").strip(), "2")
        lab.ok("push", "s1", "s2")
        lab.set_pr(S1, 11, draft=False)
        self.assertEqual(lab.ok("slots").strip(), "1")
        lab.set_pr(S2, 12)
        self.assertEqual(lab.ok("slots").strip(), "0")
        self.refuse("slots", env={"FAKE_GH_FAIL": "1"}, contains="gh did not answer")

    def test_base_names_the_previous_slice_and_refuses_a_stale_one(self):
        lab = self.lab
        lab.chain(2)
        fork_point = lab.sha("upstream/devel")
        self.assertEqual(lab.ok("base").strip(), S2)
        self.assertEqual(lab.ok("base", "s2").strip(), S1)
        self.assertEqual(lab.ok("base", "s2", "--sha").strip(), lab.sha(S1))
        self.assertEqual(lab.ok("base", "s1").strip(), fork_point, "the lowest slice: the fork point")
        for sid in ("s1", "s2", None):
            printed = lab.ok(*(["base", sid] if sid else ["base"])).strip()
            lab.git("merge-base", "--is-ancestor", printed, "HEAD")
        # A plain rebase leaves the slice refs behind: the base is then wrong, and says so.
        lab.upstream_commit("next 2", upstream_b__txt="b\n")
        lab.git("fetch", "-q", "upstream")
        lab.git("rebase", "-q", "upstream/next")
        self.refuse("base", contains="not an ancestor of HEAD")

    def test_discovery_from_the_worktree_root_and_from_a_subdirectory(self):
        lab = self.lab
        lab.chain(1)
        lab.git("init", "-q", lab.wt, cwd=lab.tmp)
        rc, out, err = lab.stack("status", "--json", "--no-gh", cwd=lab.wt)
        self.assertEqual(rc, 0, err)
        self.assertEqual(json.loads(out)["epic"], "E")
        sub = lab.moose / "deep" / "er"
        sub.mkdir(parents=True)
        rc, out, err = lab.stack("status", "--json", "--no-gh", cwd=sub)
        self.assertEqual(json.loads(out)["checkout"], str(lab.moose))


# --------------------------------------------------------------------------- park


class Park(StackTest):
    def test_park_unpark_round_trip_keeps_staged_unstaged_and_untracked(self):
        lab = self.lab
        lab.chain(2)
        lab.write("staged_new.txt", "staged\n")
        lab.write("twice.txt", "staged version\n")
        lab.git("add", "staged_new.txt", "twice.txt")
        lab.write("twice.txt", "working version\n")
        lab.edit_line(18, "unstaged edit")
        lab.write("untracked_new.txt", "untracked\n")
        before = lab.git("status", "--porcelain")
        tip = lab.sha("HEAD")
        lab.ok("park")
        self.assertEqual(lab.git("status", "--porcelain"), "")
        self.assertEqual(lab.subjects((S2 + "..HEAD")), ["WIP index", "WIP tree"])
        self.assertEqual(lab.status()["wip"]["parked"], 2)
        self.assertIn("nothing to park", lab.ok("park"))
        self.assertEqual(lab.subjects((S2 + "..HEAD")), ["WIP index", "WIP tree"])
        lab.ok("unpark")
        self.assertEqual(lab.sha("HEAD"), tip)
        self.assertEqual(lab.git("status", "--porcelain"), before)
        self.assertEqual(lab.git("show", ":twice.txt"), "staged version")
        self.assertEqual((lab.moose / "twice.txt").read_text(), "working version\n")
        self.assertEqual(lab.git("diff", "--cached", "--name-only").split(),
                         ["staged_new.txt", "twice.txt"])
        self.assertEqual(lab.git("ls-files", "--others", "--exclude-standard"), "untracked_new.txt")

    def test_park_with_only_new_files_parks_them(self):
        lab = self.lab
        lab.chain(1)
        lab.write("only_new.txt", "new\n")
        lab.ok("park")
        self.assertEqual(lab.git("status", "--porcelain"), "")
        self.assertIn("only_new.txt", lab.git("show", "--name-only", "--format=", "HEAD"))
        lab.ok("unpark")
        self.assertEqual(lab.git("status", "--porcelain"), "?? only_new.txt")

    def test_unpark_with_a_slice_on_top_is_a_no_op(self):
        lab = self.lab
        lab.chain(2)
        tip, before = lab.sha("HEAD"), self.refs()
        out = lab.ok("park")
        self.assertEqual(out.strip(), "nothing to park")
        out = lab.ok("unpark")
        self.assertEqual(out.strip(), "nothing parked")
        self.assertEqual(lab.sha("HEAD"), tip)
        self.assertEqual(self.refs(), before, "no ref and no commit moves")
        self.assertEqual(lab.git("status", "--porcelain"), "")
        # A lone WIP commit that park did not make is not popped either.
        lab.commit("WIP by hand", hand__txt="x\n")
        self.assertEqual(lab.ok("unpark").strip(), "nothing parked")
        self.assertEqual(lab.subjects((S2 + "..HEAD")), ["WIP by hand"])

    def test_park_twice_with_new_dirty_work_refuses(self):
        lab = self.lab
        lab.chain(1)
        lab.write("a.txt", "a\n")
        lab.ok("park")
        lab.write("b.txt", "b\n")
        self.refuse("park", contains="already parked")
        self.assertEqual(lab.git("status", "--porcelain"), "?? b.txt")


# --------------------------------------------------------------------------- fix


class Fix(StackTest):
    def test_clean_squash_fix_with_parked_wip_and_a_new_untracked_file(self):
        lab = self.lab
        s1, s2 = lab.chain(2)
        base = lab.sha("upstream/devel")
        s2_patch = lab.patch_id(s2)
        # Slice 3 in progress: a staged new file, an unstaged edit, an untracked file.
        lab.write("s3.txt", "slice 3\n")
        lab.git("add", "s3.txt")
        lab.edit_line(18, "line18 wip")
        lab.write("notes_new.txt", "untracked\n")
        lab.ok("park")
        lab.edit_line(4, "line04 fixed")
        lab.git("add", "shared.txt")
        out = lab.ok("fix", "s1")
        self.assertIn("next: stack unpark", out)
        self.assertRegex(out, r"s2 +moved .*content unchanged")
        n1, n2 = lab.sha(S1), lab.sha(S2)
        self.assertNotEqual(n1, s1)
        self.assertNotEqual(n2, s2)
        self.assertEqual(lab.sha((S1 + "^")), base)
        self.assertEqual(lab.sha((S2 + "^")), n1)
        self.assertIn("line04 fixed", lab.git("show", (S1 + ":shared.txt")))
        self.assertEqual(lab.subjects("%s..E" % base),
                         ["feat: slice 1", "feat: slice 2", "WIP index", "WIP tree"])
        self.assertEqual(lab.patch_id(n2), s2_patch)
        self.assertTrue(lab.status()["chain_ok"])
        lab.ok("unpark")
        self.assertEqual(lab.sha("HEAD"), n2)
        self.assertEqual(lab.git("diff", "--cached", "--name-only"), "s3.txt")
        self.assertEqual(lab.git("diff", "--name-only"), "shared.txt")
        self.assertEqual(lab.git("ls-files", "--others", "--exclude-standard"), "notes_new.txt")
        self.assertIn("line18 wip", (lab.moose / "shared.txt").read_text())
        self.assertIn("line04 fixed", (lab.moose / "shared.txt").read_text())

    def test_append_fix_keeps_lower_shas_and_fast_forwards(self):
        lab = self.lab
        s1, s2 = lab.chain(2)
        lab.ok("push", "s1", "s2")
        lab.set_pr(S1, 11, draft=False)
        lab.set_pr(S2, 12, draft=True)
        lab.edit_line(4, "line04 review fix")
        lab.git("add", "shared.txt")
        self.refuse("fix", "s1", contains=["in review", "--append -m"])
        self.assertEqual(lab.git("diff", "--cached", "--name-only"), "shared.txt")
        lab.ok("fix", "s1", "-m", "Address review: line 4")
        n1, n2 = lab.sha(S1), lab.sha(S2)
        self.assertEqual(lab.sha((S1 + "^")), s1, "the reviewed commit keeps its SHA")
        self.assertEqual(lab.subjects(("%s.." + S1) % s1), ["Address review: line 4"])
        self.assertEqual(lab.sha((S2 + "^")), n1)
        self.assertEqual(lab.row("s1")["commits"], 2)
        out = lab.ok("push")
        self.assertIn("fast-forward", out)
        self.assertIn("deferred: s2", out)
        self.assertEqual(lab.fork_sha(S1), n1)
        self.assertEqual(lab.fork_sha(S2), s2, "a draft that only moved is not pushed")
        self.assertEqual(lab.git("merge-base", "--is-ancestor", s1, n1, check=False), "")

    def test_append_message_from_a_file_and_on_several_lines(self):
        lab = self.lab
        lab.chain(2)
        msg = lab.tmp / "msg.txt"
        msg.write_text("Address review\n\nSecond paragraph.\n")
        lab.edit_line(4, "line04 a")
        lab.git("add", "-A")
        lab.ok("fix", "s1", "--append", "-F", msg)
        self.assertEqual(lab.git("log", "-1", "--format=%B", S1),
                         "Address review\n\nSecond paragraph.")
        lab.edit_line(5, "line05 b")
        lab.git("add", "-A")
        lab.ok("fix", "s2", "--append", "-m", "Subject line\n\nBody line.")
        self.assertEqual(lab.git("log", "-1", "--format=%B", S2), "Subject line\n\nBody line.")
        lab.edit_line(6, "line06 c")
        lab.git("add", "-A")
        self.refuse("fix", "s1", "--append", contains="needs a message")
        self.assertEqual(lab.git("diff", "--cached", "--name-only"), "shared.txt")

    def test_a_rebase_aborted_by_hand_is_closed_cleanly(self):
        lab = self.lab
        lab.chain(2)
        before, tip = self.refs(), lab.sha("HEAD")
        lab.edit_line(8, "line08 FIX")
        lab.git("add", "shared.txt")
        rc, out, err = lab.stack("fix", "s1", "--squash")
        self.assertEqual(rc, 3)
        lab.git("rebase", "--abort")                      # not through stack
        self.refuse("push", contains="interrupted")
        self.assertIn("restack-in-progress", " ".join(lab.status()["problems"]))
        lab.ok("fix", "--continue")
        self.assertEqual(self.refs(), before)
        self.assertEqual(lab.sha("HEAD"), tip)
        self.assertEqual(lab.git("diff", "--cached", "--name-only"), "shared.txt")
        self.assertEqual(lab.status()["problems"], [])

    def test_squash_into_a_multi_commit_slice_folds_into_its_last_commit(self):
        lab = self.lab
        s1, s2 = lab.chain(2)
        lab.edit_line(4, "line04 first")
        lab.git("add", "-A")
        lab.ok("fix", "s1", "--append", "-m", "second commit of slice 1")
        lab.edit_line(5, "line05 folded")
        lab.git("add", "-A")
        lab.ok("fix", "s1", "--squash")
        self.assertEqual(lab.sha((S1 + "^")), s1)
        self.assertEqual(lab.subjects(("%s.." + S1) % s1), ["second commit of slice 1"])
        self.assertIn("line05 folded", lab.git("show", (S1 + ":shared.txt")))
        self.assertEqual(lab.row("s1")["commits"], 2)

    def test_fix_conflicting_with_slice_2_and_with_wip_leaves_refs_until_done(self):
        lab = self.lab
        s1, s2 = lab.chain(2)
        lab.edit_line(18, "line18 wip")
        lab.ok("park")
        before = self.refs(branch=False)
        lab.edit_line(8, "line08 FIX")      # slice 2 also changed this line
        lab.edit_line(18, "line18 FIX")     # the parked work also changed this line
        lab.git("add", "shared.txt")
        rc, out, err = lab.stack("fix", "s1", "--squash")
        self.assertEqual(rc, 3, err)
        self.assertIn("stack fix --continue", err)
        stops = 0
        resolutions = [
            shared(l02="line02 s1", l08="line08 FIX", l18="line18 FIX"),
            shared(l02="line02 s1", l08="line08 FIX s2", l18="line18 FIX"),
            shared(l02="line02 s1", l08="line08 FIX s2", l18="line18 FIX wip"),
        ]
        while rc == 3:
            self.assertEqual(self.refs(branch=False), before,
                             "no slice ref moves while the restack is stopped")
            self.assertTrue(lab.status()["rebase_in_progress"])
            self.refuse("push", contains="a restack is stopped")
            self.refuse("fix", "--continue", contains="unresolved conflict")
            lab.write("shared.txt", resolutions[stops])
            lab.git("add", "shared.txt")
            stops += 1
            rc, out, err = lab.stack("fix", "--continue")
        self.assertEqual(rc, 0, err)
        self.assertEqual(stops, 3, "one stop at the fixup, one at slice 2, one at the WIP")
        self.assertNotEqual(lab.sha(S1), s1)
        self.assertEqual(lab.sha((S2 + "^")), lab.sha(S1))
        self.assertIn("line08 FIX", lab.git("show", (S1 + ":shared.txt")))
        self.assertIn("line08 FIX s2", lab.git("show", (S2 + ":shared.txt")))
        self.assertIn("CONTENT CHANGED", out)
        data = lab.status()
        self.assertTrue(data["chain_ok"])
        self.assertFalse(data["rebase_in_progress"])
        self.assertEqual(data["wip"]["parked"], 2)
        lab.ok("unpark")
        self.assertIn("line18 FIX wip", (lab.moose / "shared.txt").read_text())

    def test_fix_abort_restores_everything(self):
        lab = self.lab
        lab.chain(2)
        lab.edit_line(18, "line18 wip")
        lab.ok("park")
        before, tip = self.refs(), lab.sha("HEAD")
        lab.edit_line(8, "line08 FIX")
        lab.git("add", "shared.txt")
        rc, out, err = lab.stack("fix", "s1", "--squash")
        self.assertEqual(rc, 3)
        lab.ok("fix", "--abort")
        self.assertEqual(self.refs(), before)
        self.assertEqual(lab.sha("HEAD"), tip)
        self.assertEqual(lab.git("symbolic-ref", "--short", "HEAD"), "E")
        self.assertEqual(lab.git("diff", "--cached", "--name-only"), "shared.txt",
                         "the fix is staged again")
        self.assertIn("line08 FIX", lab.git("show", ":shared.txt"))
        self.assertFalse(lab.status()["rebase_in_progress"])
        self.refuse("fix", "--abort", contains="no stack restack")

    def test_unrelated_branches_that_point_into_the_range_do_not_move(self):
        lab = self.lab
        s1, s2 = lab.chain(2)
        lab.slice(3)
        lab.git("config", "rebase.updateRefs", "true")   # the repository-wide trap
        lab.git("branch", "backup-before-fix", S2)
        lab.git("branch", "other-feature", S1)
        lab.git("worktree", "add", "-q", "-b", "forked-off-s2", lab.tmp / "y", S2)
        forked = lab.commit("feat: on the fork", cwd=lab.tmp / "y", y__txt="y\n")
        lab.edit_line(4, "line04 fixed")
        lab.git("add", "shared.txt")
        lab.ok("fix", "s1", "--squash")
        self.assertEqual(lab.sha("backup-before-fix"), s2)
        self.assertEqual(lab.sha("other-feature"), s1)
        self.assertEqual(lab.sha("forked-off-s2"), forked)
        self.assertNotEqual(lab.sha(S1), s1)
        self.assertNotEqual(lab.sha(S2), s2)
        self.assertEqual(lab.sha(S3), lab.sha("HEAD"))
        self.assertTrue(lab.status()["chain_ok"])

    def test_slice_ref_checked_out_in_another_worktree_refuses(self):
        lab = self.lab
        lab.chain(2)
        lab.git("worktree", "add", "-q", lab.tmp / "x", S1)
        before, tip = self.refs(), lab.sha("HEAD")
        lab.edit_line(4, "line04 fixed")
        lab.git("add", "shared.txt")
        self.refuse("fix", "s2", "--squash", contains=["checked out in a worktree", S1])
        self.assertEqual(self.refs(), before)
        self.assertEqual(lab.sha("HEAD"), tip)
        self.assertEqual(lab.git("diff", "--cached", "--name-only"), "shared.txt")
        # A detached checkout of the same commit is harmless.
        lab.git("switch", "-q", "--detach", cwd=lab.tmp / "x")
        lab.ok("fix", "s2", "--squash")

    def test_chain_broken_by_a_plain_rebase_refuses_with_the_recovery(self):
        lab = self.lab
        lab.chain(2)
        good = lab.sha("HEAD")
        lab.ok("push", "s1", "s2")
        lab.upstream_commit("next 2", upstream_b__txt="b\n")
        lab.git("fetch", "-q", "upstream")
        lab.git("rebase", "-q", "upstream/next")        # what the board printed before this plan
        lab.edit_line(4, "line04 fixed")
        lab.git("add", "shared.txt")
        for verb in (["fix", "s1", "--squash"], ["push", "--all"], ["sync", "--no-fetch"]):
            err = self.refuse(*verb, contains=["the chain is broken", "git reset --keep"])
        self.assertIn(good[:9], err)
        data = lab.status()
        self.assertFalse(data["chain_ok"])
        # The printed recovery restores the chain.
        lab.git("restore", "--staged", "--worktree", "shared.txt")
        lab.git("reset", "-q", "--keep", good)
        self.assertTrue(lab.status()["chain_ok"])
        lab.ok("sync", "--no-fetch")

    def test_two_slices_with_identical_subjects_fixup_lands_in_the_right_one(self):
        lab = self.lab
        s1 = lab.slice(1, subject="feat: same subject")
        s2 = lab.slice(2, subject="feat: same subject")
        lab.write("s2.txt", "slice 2 fixed\n")
        lab.git("add", "s2.txt")
        lab.ok("fix", "s2", "--squash")
        self.assertEqual(lab.sha(S1), s1, "slice 1 is not touched")
        self.assertEqual(lab.git("show", (S2 + ":s2.txt")), "slice 2 fixed")
        self.assertEqual(lab.sha((S2 + "^")), s1)

    def test_base_is_the_parent_of_the_lowest_unmerged_slice_when_next_is_behind(self):
        lab = self.lab
        # devel moves ahead of what upstream/next holds: a fork point outside next.
        lab.git("switch", "-q", "-C", "devel", "origin/devel", cwd=lab.maint)
        d2 = lab.commit("devel 2", cwd=lab.maint, devel_only__txt="d\n")
        lab.git("push", "-q", "origin", "devel", cwd=lab.maint)
        lab.git("fetch", "-q", "upstream")
        lab.git("switch", "-q", "--no-track", "-c", "F", "upstream/devel")
        self.assertNotEqual(lab.git("merge-base", "F", "upstream/next"), d2)
        s1, s2 = lab.chain(2)
        self.assertEqual(lab.status()["base"], d2)
        lab.edit_line(4, "line04 fixed")
        lab.git("add", "shared.txt")
        lab.ok("fix", "s1", "--squash")
        self.assertEqual(lab.sha((sref(1, "F") + "^")), d2, "the upstream commit below the stack is not rewritten")
        self.assertEqual(lab.subjects("%s..F" % d2), ["feat: slice 1", "feat: slice 2"])
        self.assertEqual(lab.status()["base"], d2)

    def test_merge_commit_in_the_range_refuses(self):
        lab = self.lab
        lab.chain(2)
        lab.git("merge", "-q", "--no-ff", "-m", "Merge branch 'next'", "upstream/next")
        before, tip = self.refs(), lab.sha("HEAD")
        lab.edit_line(4, "line04 fixed")
        lab.git("add", "shared.txt")
        self.refuse("fix", "s1", "--squash", contains="merge commit")
        self.assertEqual(self.refs(), before)
        self.assertEqual(lab.sha("HEAD"), tip)
        self.assertEqual(lab.git("diff", "--cached", "--name-only"), "shared.txt")

    def test_fix_needs_a_staged_fix_and_parked_work(self):
        lab = self.lab
        lab.chain(2)
        self.refuse("fix", "s1", "--squash", contains="nothing is staged")
        lab.edit_line(4, "line04 fixed")
        lab.git("add", "shared.txt")
        lab.write("loose.txt", "x\n")
        tip = lab.sha("HEAD")
        self.refuse("fix", "s1", "--squash", contains="neither staged nor parked")
        self.assertEqual(lab.sha("HEAD"), tip)
        rc, out, err = lab.stack("fix")
        self.assertEqual(rc, 2)

    def test_fix_does_not_guess_when_github_does_not_answer(self):
        lab = self.lab
        lab.chain(2)
        lab.ok("push", "s1")
        lab.edit_line(4, "line04 fixed")
        lab.git("add", "shared.txt")
        self.refuse("fix", "s1", env={"FAKE_GH_FAIL": "1"}, contains=["does not guess", "--append"])
        self.assertEqual(lab.git("diff", "--cached", "--name-only"), "shared.txt")
        # A slice this machine never pushed has no PR to hurt: it is sealed.
        lab.git("restore", "--staged", "--worktree", "shared.txt")
        lab.write("s2.txt", "slice 2 fixed\n")
        lab.git("add", "s2.txt")
        lab.ok("fix", "s2", env={"FAKE_GH_FAIL": "1"})


# --------------------------------------------------------------------------- push


class Push(StackTest):
    def test_first_push_of_a_new_slice(self):
        lab = self.lab
        s1, s2 = lab.chain(2)
        self.assertIn("nothing to push", lab.ok("push"))
        self.assertIsNone(lab.fork_sha(S1))
        self.assertIn(("would push " + S1), lab.ok("push", "s1", "--dry-run"))
        self.assertIsNone(lab.fork_sha(S1))
        lab.ok("push", "s1")
        self.assertEqual(lab.fork_sha(S1), s1)
        self.assertIsNone(lab.fork_sha(S2))
        self.assertEqual(lab.sha("refs/stack/E/pushed/s1"), s1)
        self.assertEqual(lab.row("s1")["drift"], False)
        self.assertIn("nothing to push", lab.ok("push"))

    def test_first_push_refuses_when_the_fork_already_has_the_branch(self):
        lab = self.lab
        s1, s2 = lab.chain(2)
        lab.git("push", "-q", lab.fork, ("%s:refs/heads/" + S1) % lab.sha("upstream/devel"))
        self.refuse("push", "s1", contains=["stack-drift", "stack adopt s1"])
        self.assertEqual(lab.fork_sha(S1), lab.sha("upstream/devel"))

    def test_push_skips_a_draft_slice_that_was_only_moved(self):
        lab = self.lab
        s1, s2 = lab.chain(2)
        lab.ok("push", "s1", "s2")
        lab.set_pr(S1, 11)
        lab.set_pr(S2, 12)
        lab.edit_line(4, "line04 fixed")
        lab.git("add", "shared.txt")
        lab.ok("fix", "s1")
        n1, n2 = lab.sha(S1), lab.sha(S2)
        out = lab.ok("push")
        self.assertIn("REWRITE", out)
        self.assertIn("deferred: s2", out)
        self.assertEqual(lab.fork_sha(S1), n1)
        self.assertEqual(lab.fork_sha(S2), s2)
        self.assertEqual(lab.sha("refs/stack/E/pushed/s2"), s2)
        row = lab.row("s2")
        self.assertEqual((row["drift"], row["behind"]), (False, True), "deferred is not drift")
        self.assertRegex(lab.ok("status"), r"s2 .* behind \(push deferred\)")
        self.assertEqual(lab.status()["problems"], [], "slice 1 is the lowest and is current")
        lab.ok("push", "s2")
        self.assertEqual(lab.fork_sha(S2), n2)

    def test_push_refuses_a_wip_or_fixup_commit_below_a_ref(self):
        lab = self.lab
        lab.chain(1)
        lab.commit("WIP not done", wip__txt="x\n")
        lab.commit("feat: slice 2", s2__txt="slice 2\n")
        lab.git("update-ref", ("refs/heads/" + S2), "HEAD")     # a ref set by hand above a WIP
        self.refuse("push", "s2", contains=["unfinished commit", "WIP not done"])
        self.assertIsNone(lab.fork_sha(S2))
        lab.git("update-ref", "-d", ("refs/heads/" + S2))
        lab.git("reset", "-q", "--keep", S1)
        lab.commit("fixup! feat: slice 1", fx__txt="x\n")
        lab.git("update-ref", ("refs/heads/" + S2), "HEAD")
        self.refuse("push", "s2", contains="unfinished commit")
        self.assertIn("unfinished commit", " ".join(lab.status()["problems"]))

    def _race(self, fetch_first):
        """A foreign commit lands on the fork between the fork check and the push."""
        lab = self.lab
        s1, s2 = lab.chain(2)
        lab.ok("push", "s1", "s2")
        lab.edit_line(4, "line04 fixed")
        lab.git("add", "shared.txt")
        lab.ok("fix", "s1", "--squash")
        recorded = (lab.sha("refs/stack/E/pushed/s1"), lab.sha("refs/stack/E/pushed/s2"))
        foreign = {}
        module = load_stack(lab.env)
        real = module.Ctx.require_no_drift

        def check_then_race(ctx, slices):
            fork = real(ctx, slices)
            foreign["sha"] = lab.maintainer_push(S2)
            if fetch_first:
                lab.git("fetch", "-q", "origin")
            return fork

        err = io.StringIO()
        with mock.patch.dict(os.environ, lab.env, clear=True), \
                mock.patch.object(module.Ctx, "require_no_drift", check_then_race), \
                contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            rc = module.main(["-C", str(lab.moose), "push", "--all"])
        self.assertEqual(rc, 1, err.getvalue())
        self.assertIn("nothing on the fork changed", err.getvalue())
        self.assertEqual(lab.fork_sha(S1), s1, "slice 1 was not pushed alone")
        self.assertEqual(lab.fork_sha(S2), foreign["sha"], "the foreign commit survives")
        self.assertEqual((lab.sha("refs/stack/E/pushed/s1"), lab.sha("refs/stack/E/pushed/s2")),
                         recorded)

    def test_push_is_atomic_one_stale_lease_rejects_all(self):
        self._race(fetch_first=False)

    def test_push_after_a_fetch_of_origin_still_refuses_to_overwrite_a_foreign_commit(self):
        self._race(fetch_first=True)

    def test_drift_blocks_fix_sync_and_push_and_names_adopt(self):
        lab = self.lab
        s1, s2 = lab.chain(2)
        lab.ok("push", "s1", "s2")
        foreign = lab.maintainer_push(S2)
        lab.git("fetch", "-q", "origin")           # a routine fetch must not hide the drift
        lab.edit_line(4, "line04 fixed")
        lab.git("add", "shared.txt")
        before = self.refs()
        for verb in (["fix", "s1", "--squash"], ["sync", "--no-fetch"], ["push", "--all"]):
            self.refuse(*verb, contains=["stack-drift", "stack adopt s2"])
        self.assertEqual({k: v for k, v in self.refs().items() if "remotes" not in k}, before)
        self.assertEqual(lab.fork_sha(S2), foreign)
        self.assertEqual(lab.row("s2")["drift"], True)
        self.assertEqual(lab.git("diff", "--cached", "--name-only"), "shared.txt")


# --------------------------------------------------------------------------- merge and sync


class MergeAndSync(StackTest):
    def _merged_first_slice(self):
        lab = self.lab
        s1, s2 = lab.chain(2)
        lab.slice(3)
        lab.ok("push", "s1", "s2")
        lab.set_pr(S1, 11, draft=False)
        lab.set_pr(S2, 12)
        lab.upstream_merge(s1, 11)
        lab.set_pr(S1, 11, state="MERGED", draft=False, oid=s1)
        return s1, s2

    def test_slice_1_merged_upstream_by_a_real_merge_commit(self):
        lab = self.lab
        s1, s2 = self._merged_first_slice()
        out = lab.ok("sync")
        self.assertIn("s1 is merged", out)
        self.assertIn("no rebase is needed", out)
        self.assertEqual(lab.sha(S1), s1, "the merged slice keeps its SHA and its local ref")
        self.assertEqual(lab.sha(S2), s2, "nothing was rebased")
        rows = {r["id"]: r for r in lab.status()["slices"]}
        self.assertEqual(rows["s1"]["state"], "merged")
        self.assertEqual(rows["s2"]["state"], "draft")
        self.assertEqual(rows["s2"]["commits"], 1)
        self.assertEqual(lab.status()["base"], s1)
        self.assertEqual(lab.ok("base", "s2").strip(), S1, "a merged slice keeps its ref")
        self.assertEqual(lab.ok("base", "s2", "--sha").strip(), s1)
        self.assertEqual(lab.ok("base", "s3").strip(), S2)
        self.assertEqual(sorted(lab.git("diff", "--name-only", ("upstream/next..." + S2)).split()),
                         ["s2.txt", "shared.txt"], "PR 2 is slice 2 only, with no rebase")
        self.assertEqual(lab.subjects(("upstream/next.." + S2)), ["feat: slice 2"])
        lab.edit_line(4, "line04 fixed")
        lab.git("add", "shared.txt")
        self.refuse("fix", "s1", "--squash", contains=["merged", "slice being built"])
        # A fix to slice 2 now rewrites slice 2 and up only.
        lab.ok("fix", "s2")
        self.assertEqual(lab.sha(S1), s1)
        self.assertEqual(lab.sha((S2 + "^")), s1)
        self.refuse("push", "s1", contains="merged")

    def test_sync_rebase_after_a_merge_drops_nothing_and_keeps_patch_ids(self):
        lab = self.lab
        s1, s2 = self._merged_first_slice()
        s3 = lab.sha(S3)
        p2, p3 = lab.patch_id(s2), lab.patch_id(s3)
        lab.upstream_commit("next 3", upstream_c__txt="c\n")
        self.assertIn("no conflict", lab.ok("sync"))
        self.assertEqual(lab.sha(S2), s2, "sync alone never rebases")
        out = lab.ok("sync", "--rebase")
        nxt = lab.sha("upstream/next")
        self.assertEqual(lab.sha(S1), s1, "the merged slice is not copied")
        self.assertEqual(lab.sha((S2 + "^")), nxt)
        self.assertEqual(lab.sha((S3 + "^")), lab.sha(S2))
        self.assertEqual(lab.subjects("upstream/next..E"), ["feat: slice 2", "feat: slice 3"])
        self.assertEqual((lab.patch_id(S2), lab.patch_id(S3)), (p2, p3))
        self.assertRegex(out, r"s2 +moved .*content unchanged")
        data = lab.status()
        self.assertTrue(data["chain_ok"])
        self.assertEqual(data["base"], nxt)
        self.assertEqual({r["id"]: r["commits"] for r in data["slices"]}["s2"], 1)
        self.assertIn("nothing to rebase", lab.ok("sync", "--rebase"))
        # After the rebase a diff from slice 1 would hold upstream commits: the base is the fork point.
        self.assertEqual(lab.ok("base", "s2").strip(), nxt)
        lab.git("merge-base", "--is-ancestor", nxt, "HEAD")
        self.assertEqual(sorted(lab.git("diff", "--name-only", ("%s.." + S2) % nxt).split()),
                         ["s2.txt", "shared.txt"])

    def test_sync_never_rebases_onto_devel(self):
        lab = self.lab
        s1, s2 = self._merged_first_slice()
        # devel is behind next: it does not hold slice 1 yet. It also moved.
        lab.git("switch", "-q", "-C", "devel", "origin/devel", cwd=lab.maint)
        lab.commit("devel 2", cwd=lab.maint, devel_only__txt="d\n")
        lab.git("push", "-q", "origin", "devel", cwd=lab.maint)
        lab.git("fetch", "-q", "upstream")
        lab.upstream_commit("next 3", upstream_c__txt="c\n")
        lab.ok("sync", "--rebase")
        self.assertEqual(lab.git("log", "--format=%s", "upstream/next..E", "--grep", "slice 1"), "",
                         "no second copy of the merged slice")
        self.assertEqual(lab.sha((S2 + "^")), lab.sha("upstream/next"))
        self.assertNotEqual(lab.git("merge-base", "--is-ancestor", "upstream/devel", "E",
                                    check=False), "never", "devel plays no part")
        rc, out, err = lab.stack("sync", "--onto", "upstream/devel")
        self.assertEqual(rc, 2, "there is no way to name another base")

    def test_sync_reports_a_conflict_and_rebase_stops_on_it(self):
        lab = self.lab
        s1, s2 = lab.chain(2)
        lab.upstream_commit("next 2", shared__txt=shared(l02="line02 upstream"))
        out = lab.ok("sync")
        self.assertIn("CONFLICT with upstream/next in: shared.txt", out)
        self.assertIn("stack sync --rebase", out)
        self.assertEqual((lab.sha(S1), lab.sha(S2)), (s1, s2))
        before = self.refs()
        rc, out, err = lab.stack("sync", "--rebase", "--no-fetch")
        self.assertEqual(rc, 3, err)
        self.assertEqual(self.refs(), before)
        lab.write("shared.txt", shared(l02="line02 upstream s1"))
        lab.git("add", "shared.txt")
        rc, out, err = lab.stack("fix", "--continue")
        while rc == 3:
            lab.write("shared.txt", shared(l02="line02 upstream s1", l08="line08 s2"))
            lab.git("add", "shared.txt")
            rc, out, err = lab.stack("fix", "--continue")
        self.assertEqual(rc, 0, err)
        nxt = lab.sha("upstream/next")
        self.assertEqual(lab.sha((S1 + "^")), nxt)
        self.assertEqual(lab.sha("refs/stack/E/base"), nxt)
        self.assertTrue(lab.status()["chain_ok"])

    def test_sync_rebase_abort_restores_everything(self):
        lab = self.lab
        lab.chain(2)
        lab.upstream_commit("next 2", shared__txt=shared(l02="line02 upstream"))
        before, tip = self.refs(), lab.sha("HEAD")
        rc, out, err = lab.stack("sync", "--rebase")
        self.assertEqual(rc, 3)
        lab.ok("fix", "--abort")
        self.assertEqual({k: v for k, v in self.refs().items()}, before)
        self.assertEqual(lab.sha("HEAD"), tip)

    def test_sync_rebase_needs_yes_when_a_pr_in_review_must_be_force_pushed(self):
        lab = self.lab
        s1, s2 = lab.chain(2)
        lab.ok("push", "s1", "s2")
        lab.set_pr(S1, 11, draft=False)
        lab.set_pr(S2, 12)
        lab.upstream_commit("next 2", upstream_b__txt="b\n")
        self.refuse("sync", "--rebase", contains=["force push", "s1 (in review, PR #11)", "--yes"])
        self.assertEqual(lab.sha(S1), s1)
        lab.ok("sync", "--rebase", "--yes")
        self.assertEqual(lab.sha((S1 + "^")), lab.sha("upstream/next"))
        before = (lab.fork_sha(S1), lab.fork_sha(S2))
        self.refuse("push", "--all", contains=["s1 (in review, PR #11)", "--yes", "Nothing was pushed"])
        self.assertEqual((lab.fork_sha(S1), lab.fork_sha(S2)), before)
        out = lab.ok("push", "--all", "--yes")
        self.assertIn("warning: force push to a PR that is not a draft: s1 (in review, PR #11)", out)
        self.assertEqual(lab.fork_sha(S1), lab.sha(S1))
        self.assertEqual(lab.fork_sha(S2), lab.sha(S2))

    def test_sync_rebase_refuses_a_dirty_tree(self):
        lab = self.lab
        lab.chain(1)
        lab.upstream_commit("next 2", upstream_b__txt="b\n")
        lab.write("loose.txt", "x\n")
        self.refuse("sync", "--rebase", contains="stack park")

    def test_merge_race_stops(self):
        lab = self.lab
        s1, s2 = lab.chain(2)
        lab.ok("push", "s1", "s2")
        merged_at = s1
        # The local slice is amended after the push; upstream then merges the pushed SHA.
        lab.edit_line(4, "line04 late fix")
        lab.git("add", "shared.txt")
        lab.ok("fix", "s1", "--squash")
        local = lab.sha(S1)
        lab.upstream_merge(merged_at, 11)
        lab.set_pr(S1, 11, state="MERGED", draft=False, oid=merged_at)
        err = self.refuse("sync", contains=["merge race", merged_at[:9], local[:9]])
        self.assertEqual(lab.sha(S1), local)
        self.assertIn("merge race", " ".join(lab.status()["problems"]))
        lab.edit_line(5, "line05 again")
        lab.git("add", "shared.txt")
        self.refuse("fix", "s1", contains="merge race")
        self.refuse("fix", "s1", "--squash", contains="merge race")


# --------------------------------------------------------------------------- adopt


class Adopt(StackTest):
    def test_adopt_takes_commits_a_maintainer_appended(self):
        lab = self.lab
        s1, s2 = lab.chain(2)
        lab.slice(3)
        lab.ok("push", "s1", "s2")
        theirs = lab.maintainer_push(S1)
        p2 = lab.patch_id(s2)
        out = lab.ok("adopt", "s1")
        self.assertEqual(lab.sha(S1), theirs)
        self.assertEqual(lab.sha((S2 + "^")), theirs)
        self.assertEqual(lab.sha((S3 + "^")), lab.sha(S2))
        self.assertEqual(lab.sha("E"), lab.sha(S3))
        self.assertEqual(lab.patch_id(S2), p2)
        self.assertEqual(lab.sha("refs/stack/E/pushed/s1"), theirs)
        data = lab.status()
        self.assertTrue(data["chain_ok"])
        self.assertEqual(data["problems"], [])
        self.assertTrue((lab.moose / "maint.txt").is_file())
        # Slice 1 is now what the fork holds; only slice 2 is behind.
        self.assertIn("deferred: s2", lab.ok("push"))

    def test_adopt_on_the_top_slice_fast_forwards_the_branch(self):
        lab = self.lab
        (s1,) = lab.chain(1)
        lab.ok("push", "s1")
        theirs = lab.maintainer_push(S1)
        lab.ok("adopt", "s1")
        self.assertEqual((lab.sha(S1), lab.sha("E")), (theirs, theirs))
        self.assertEqual(lab.status()["problems"], [])

    def test_adopt_diverged_refuses_and_ours_keeps_the_local_slice(self):
        lab = self.lab
        s1, s2 = lab.chain(2)
        lab.ok("push", "s1", "s2")
        theirs = lab.maintainer_push(S1, amend=True)
        before = self.refs()
        self.refuse("adopt", "s1", contains=["diverged", theirs, s1, "--ours"])
        self.assertEqual({k: v for k, v in self.refs().items() if "remotes" not in k}, before)
        lab.ok("adopt", "s1", "--ours")
        self.assertEqual(lab.sha(S1), s1)
        self.assertEqual(lab.sha("refs/stack/E/foreign/s1"), theirs, "their commit is kept")
        self.assertEqual(lab.status()["problems"], [push_pending("s1")])
        lab.ok("push", "s1")
        self.assertEqual(lab.fork_sha(S1), s1)

    def test_adopt_refuses_an_update_branch_merge(self):
        lab = self.lab
        s1, s2 = lab.chain(2)
        lab.ok("push", "s1", "s2")
        lab.maintainer_push(S2, merge_next=True)
        self.refuse("adopt", "s2", contains=["merge commit", "--ours"])
        self.assertEqual(lab.sha(S2), s2)


# --------------------------------------------------------------------------- the real layout


class LinkedWorktree(StackTest):
    def test_works_in_a_linked_worktree_as_the_factory_makes_them(self):
        """A feature's moose/ is a `git worktree` of the main moose repository: its git
        directory, its rebase state and its HEAD are per worktree; its refs are shared."""
        lab = self.lab
        main = lab.moose
        lab.git("switch", "-q", "--detach")
        root = lab.tmp / "wt2"
        (root / "specs").mkdir(parents=True)
        (root / "specs" / "epic.md").write_text("---\nepic: G\n---\n")
        lab.git("worktree", "add", "-q", "--no-track", "-b", "G", root / "moose", "upstream/devel")
        lab.moose, lab.wt = root / "moose", root
        self.assertTrue((lab.moose / ".git").is_file())
        s1, s2 = lab.chain(2)
        self.assertEqual(lab.sha(sref(2, "G"), cwd=main), s2, "slice refs live in the shared repository")
        rc, out, err = lab.stack("status", "--json", "--no-gh", cwd=lab.moose)
        self.assertEqual(json.loads(out)["epic"], "G")
        lab.edit_line(18, "line18 wip")
        lab.ok("park")
        lab.edit_line(8, "line08 FIX")
        lab.git("add", "shared.txt")
        rc, out, err = lab.stack("fix", "s1", "--squash")
        self.assertEqual(rc, 3, err)
        self.assertEqual((lab.sha(sref(1, "G")), lab.sha(sref(2, "G"))), (s1, s2))
        self.assertTrue(lab.status()["rebase_in_progress"])
        lab.ok("fix", "--abort")
        self.assertEqual((lab.sha(sref(1, "G")), lab.sha(sref(2, "G"))), (s1, s2))
        lab.git("restore", "--staged", "--worktree", "shared.txt")
        lab.edit_line(4, "line04 fixed")
        lab.git("add", "shared.txt")
        lab.ok("fix", "s1", "--squash")
        lab.ok("unpark")
        self.assertEqual(lab.sha((sref(2, "G") + "^")), lab.sha(sref(1, "G")))
        self.assertTrue(lab.status()["chain_ok"])
        lab.ok("push", "s1", "s2")
        self.assertEqual(lab.fork_sha(sref(2, "G")), lab.sha(sref(2, "G")))
        # The lease is read from the root of this worktree, not of the main checkout.
        other = subprocess.Popen(["sleep", "60"])
        try:
            (root / ".factory-lease").mkdir()
            (root / ".factory-lease" / "lease.json").write_text(json.dumps({"pid": other.pid}))
            self.refuse("push", "--all", contains="another session holds the lease")
        finally:
            other.kill()
            other.wait()


# --------------------------------------------------------------------------- lease


class Lease(StackTest):
    def _lease(self, record):
        d = self.lab.wt / ".factory-lease"
        d.mkdir(exist_ok=True)
        (d / "lease.json").write_text(json.dumps(record))

    def test_lease_held_by_a_live_foreign_pid_refuses(self):
        lab = self.lab
        lab.chain(2)
        other = subprocess.Popen(["sleep", "60"])
        try:
            self._lease({"pid": other.pid, "session_id": "abc", "bg_id": None})
            lab.edit_line(4, "line04 fixed")
            lab.git("add", "shared.txt")
            tip = lab.sha("HEAD")
            for verb in (["fix", "s1", "--squash"], ["push", "s1"], ["adopt", "s1"]):
                self.refuse(*verb, contains=["another session holds the lease", str(other.pid)])
            lab.git("restore", "--staged", "--worktree", "shared.txt")
            lab.upstream_commit("next 2", upstream_b__txt="b\n")
            self.refuse("sync", "--rebase", contains="another session holds the lease")
            self.assertEqual(lab.sha("HEAD"), tip)
            lab.ok("status", "--no-gh")
            lab.ok("sync")
        finally:
            other.kill()
            other.wait()

    def test_lease_of_this_session_a_dead_owner_and_an_unknown_owner(self):
        lab = self.lab
        lab.chain(2)
        self._lease({"pid": os.getpid(), "session_id": "mine"})
        lab.ok("push", "s1")                       # the test process is an ancestor of stack
        dead = subprocess.Popen(["true"])
        dead.wait()
        self._lease({"pid": dead.pid})
        rc, out, err = lab.stack("push", "s2")
        self.assertEqual(rc, 0, err)
        self.assertIn("stale", err)
        self._lease({"note": "no pid"})
        lab.write("s2.txt", "slice 2 fixed\n")
        lab.git("add", "s2.txt")
        self.refuse("fix", "s2", "--squash", contains="names no owner")

    def test_lease_owner_found_through_the_session_file(self):
        lab = self.lab
        lab.chain(1)
        other = subprocess.Popen(["sleep", "60"])
        try:
            dead = subprocess.Popen(["true"])
            dead.wait()
            sessions = Path(lab.env["STACK_CLAUDE_HOME"]) / "sessions"
            sessions.mkdir(parents=True)
            (sessions / "x.json").write_text(json.dumps({"sessionId": "abc", "pid": other.pid}))
            self._lease({"pid": dead.pid, "session_id": "abc"})   # the launcher pid is gone
            self.refuse("push", "s1", contains="another session holds the lease")
        finally:
            other.kill()
            other.wait()


# --------------------------------------------------------------------------- slice names


class Names(StackTest):
    def test_slice_names_come_from_one_place_and_parse_strictly(self):
        m = NAMING
        self.assertEqual(m.slice_branch("modal", 2), "epic/modal/s2")
        self.assertEqual(S2, "epic/E/s2")
        self.assertEqual(m.parse_slice_branch("epic/modal/s2", "modal"), ("modal", 2))
        self.assertEqual(m.parse_slice_branch("epic/a/b/s12"), ("a/b", 12))
        self.assertEqual(m.parse_slice_branch("epic/a/b/s12", "a/b"), ("a/b", 12))
        for name in ("epic/foo-bar/s1", "epic/foox/s1", "epic/foo/s01", "epic/foo/s0",
                     "epic/foo/s1x", "epic/foo/s1/x", "epic/foo/s", "foo-s1", "xepic/foo/s1",
                     "epic/foo/s1\n"):
            self.assertIsNone(m.parse_slice_branch(name, "foo"), name)
        self.assertIsNone(m.parse_slice_branch("epic/fxo/s1", "f.o"), "the epic name is literal")
        self.assertEqual(m.slice_namespace("modal"), ["epic", "epic/modal"])

    def test_the_branch_and_the_fork_carry_the_slice_name_and_ids_stay_short(self):
        lab = self.lab
        s1, s2 = lab.chain(2)
        self.assertEqual(lab.sha("refs/heads/epic/E/s2"), s2)
        lab.ok("push", "s1", "s2")
        self.assertEqual(lab.fork_sha("epic/E/s1"), s1)
        row = lab.row("s2")
        self.assertEqual((row["id"], row["ref"]), ("s2", "epic/E/s2"))
        for spelling in ("s2", "2", S2):
            self.assertEqual(lab.ok("base", spelling).strip(), S1)
        self.assertRegex(lab.ok("status", "--no-gh"), r"\n +s2 +%s " % s2[:9])

    def test_look_alike_branches_are_not_slices(self):
        lab = self.lab
        s1, s2 = lab.chain(2)
        nxt = lab.sha("upstream/next")
        for other in (S2 + "x", sref(1, "Efoo"), "E-s2", "E-s3", "E-s1"):
            lab.git("branch", other, nxt)                    # none is built on the chain
        data = lab.status()
        self.assertTrue(data["chain_ok"])
        self.assertEqual([r["id"] for r in data["slices"]], ["s1", "s2"])
        lab.commit("feat: slice 3", three__txt="3\n")
        self.assertEqual(lab.ok("seal").strip(), "s3")
        lab.ok("push", "s1", "s2", "s3")

    def test_a_foreign_branch_with_a_slice_name_is_named_in_the_refusal(self):
        lab = self.lab
        lab.chain(1)
        lab.git("branch", S2, "upstream/next")               # made by hand, not a slice
        lab.commit("feat: slice two", two__txt="x\n")
        tip = lab.sha("HEAD")
        for verb in (["seal"], ["push", "s1"]):
            self.refuse(*verb, contains=["the chain is broken", S2, "is not built on " + S1,
                                         "git branch -m " + S2])
        self.assertEqual(lab.sha("HEAD"), tip)
        self.assertIsNone(lab.fork_sha(S1))

    def test_seal_refuses_when_a_branch_blocks_the_slice_namespace(self):
        lab = self.lab
        lab.git("branch", "epic", "upstream/devel")
        lab.commit("feat: slice 1", one__txt="1\n")
        self.refuse("seal", contains=["the branch epic exists", S1, "git branch -m epic"])
        self.assertEqual(lab.git("for-each-ref", "refs/heads/epic/"), "")
        lab.git("branch", "-m", "epic", "epic/E")
        self.refuse("seal", contains=["the branch epic/E exists", "git branch -m epic/E"])
        lab.git("branch", "-m", "epic/E", "elsewhere")
        self.assertEqual(lab.ok("seal").strip(), "s1")

    def test_first_push_refuses_when_the_fork_blocks_the_slice_namespace(self):
        lab = self.lab
        (s1,) = lab.chain(1)
        lab.git("push", "-q", lab.fork, "%s:refs/heads/epic" % lab.sha("upstream/devel"))
        self.refuse("push", "s1", contains=["the fork has a branch epic", "Nothing was pushed",
                                            "--delete epic"])
        self.assertIsNone(lab.fork_sha(S1))
        self.assertIsNone(lab.git("for-each-ref", "refs/stack/E/pushed") or None)
        lab.git("push", "-q", lab.fork, "--delete", "epic")
        lab.git("push", "-q", lab.fork, "%s:refs/heads/epic/E" % lab.sha("upstream/devel"))
        self.refuse("push", "s1", contains="the fork has a branch epic/E")
        lab.git("push", "-q", lab.fork, "--delete", "epic/E")
        lab.ok("push", "s1")
        self.assertEqual(lab.fork_sha(S1), s1)

    def test_seal_expect(self):
        lab = self.lab
        lab.chain(1)
        lab.commit("feat: slice two", two__txt="x\n")
        rc, out, err = lab.stack("seal", "--expect", "s3")
        self.assertEqual((rc, out), (1, ""))
        self.assertIn("the next slice id is s2, not s3", err)
        self.assertEqual(lab.git("for-each-ref", "refs/heads/" + S2), "")
        rc, out, err = lab.stack("seal", "--expect", "s2")
        self.assertEqual((rc, out.strip()), (0, "s2"))
        self.assertEqual(lab.sha(S2), lab.sha("HEAD"))


# --------------------------------------------------------------------------- the review round


class NoSilentForcePush(StackTest):
    """A rewrite of a PR head that is in review, or whose state is not known, needs --yes."""

    def _two_in_review(self):
        lab = self.lab
        s1, s2 = lab.chain(2)
        lab.ok("push", "s1", "s2")
        lab.set_pr(S1, 11, draft=False)
        lab.set_pr(S2, 12, draft=False)
        return s1, s2

    def test_fix_that_rewrites_a_slice_in_review_above_needs_yes(self):
        lab = self.lab
        s1, s2 = self._two_in_review()
        lab.write("s1.txt", "slice 1\nreview fix\n")
        lab.git("add", "-A")
        tip = lab.sha("HEAD")
        self.refuse("fix", "s1", "-m", "review: s1",
                    contains=["s2 (in review, PR #12)", "force push", "--yes"])
        self.assertEqual((lab.sha(S1), lab.sha(S2), lab.sha("HEAD")), (s1, s2, tip))
        self.assertEqual(lab.git("diff", "--cached", "--name-only"), "s1.txt")
        self.assertEqual(lab.status()["problems"], [])
        lab.ok("fix", "s1", "-m", "review: s1", "--yes")
        # The append to slice 1 is a fast-forward: it needs no --yes.
        out = lab.ok("push")
        self.assertIn("fast-forward", out)
        self.assertIn("deferred: s2", out)
        self.assertEqual(lab.fork_sha(S2), s2)

    def test_plain_push_never_rewrites_a_pr_in_review(self):
        lab = self.lab
        s1, s2 = self._two_in_review()
        lab.write("s1.txt", "slice 1\nreview fix\n")
        lab.git("add", "-A")
        lab.ok("fix", "s1", "-m", "review: s1", "--yes")
        lab.ok("push")
        lab.write("s2.txt", "slice 2\nreview fix\n")
        lab.git("add", "-A")
        lab.ok("fix", "s2", "-m", "review: s2")          # nothing above slice 2: no --yes
        for verb in (["push"], ["push", "--all"], ["push", "s2"]):
            self.refuse(*verb, contains=["s2 (in review, PR #12)", "--yes", "Nothing was pushed"])
            self.assertEqual(lab.fork_sha(S2), s2, "the PR in review was not rewritten")
        self.assertEqual(lab.sha("refs/stack/E/pushed/s2"), s2)
        out = lab.ok("push", "--yes")
        self.assertIn("warning: force push to a PR that is not a draft: s2", out)
        self.assertEqual(lab.fork_sha(S2), lab.sha(S2))

    def test_unknown_pr_state_counts_as_in_review(self):
        lab = self.lab
        s1, s2 = self._two_in_review()
        lab.write("s1.txt", "slice 1\nreview fix\n")
        lab.git("add", "-A")
        lab.ok("fix", "s1", "-m", "review: s1", "--yes")
        down = {"FAKE_GH_FAIL": "1"}
        self.refuse("push", "--all", env=down, contains=["s2 (unknown)", "--yes"])
        self.assertEqual((lab.fork_sha(S1), lab.fork_sha(S2)), (s1, s2), "all or nothing")
        rc, out, err = lab.stack("push", "--all", "--yes", env=down)
        self.assertEqual(rc, 0, err)
        self.assertEqual((lab.fork_sha(S1), lab.fork_sha(S2)), (lab.sha(S1), lab.sha(S2)))
        # A fast-forward alone needs no --yes, also when gh does not answer.
        lab.write("s2.txt", "slice 2\nmore\n")
        lab.git("add", "-A")
        lab.ok("fix", "s2", "--append", "-m", "review: s2", env=down)
        rc, out, err = lab.stack("push", env=down)
        self.assertEqual(rc, 0, err)
        self.assertIn("fast-forward", out)

    def test_squash_below_a_slice_in_review_needs_yes(self):
        lab = self.lab
        s1, s2 = lab.chain(2)
        lab.ok("push", "s1", "s2")
        lab.set_pr(S1, 11, draft=True)
        lab.set_pr(S2, 12, draft=False)
        lab.write("s1.txt", "slice 1\nfix\n")
        lab.git("add", "-A")
        self.refuse("fix", "s1", contains=["s2 (in review, PR #12)", "--yes"])
        self.assertEqual((lab.sha(S1), lab.sha(S2)), (s1, s2))
        lab.ok("fix", "s1", "--yes")
        # An explicit squash of a slice that is itself in review also needs --yes.
        lab.write("s2.txt", "slice 2\nfix\n")
        lab.git("add", "-A")
        self.refuse("fix", "s2", "--squash", contains=["s2 (in review, PR #12)", "--yes"])
        lab.ok("fix", "s2", "--squash", "--yes")


class ContentIdentity(StackTest):
    def test_whitespace_mode_binary_and_blank_line_fixes_count_as_changes(self):
        lab = self.lab
        (lab.moose / "bin.dat").write_bytes(bytes(range(256)) * 4)
        lab.write("run.sh", "#!/bin/sh\necho hi\n")
        lab.git("add", "-A")
        lab.git("commit", "-q", "-m", "feat: slice 1")
        lab.ok("seal")
        lab.slice(2)
        lab.ok("push", "s1", "s2")
        lab.set_pr(S1, 11)
        lab.set_pr(S2, 12)
        s2_on_fork = lab.fork_sha(S2)

        def whitespace():
            lab.write("run.sh", "#!/bin/sh\n\techo   hi\n")

        def binary():
            (lab.moose / "bin.dat").write_bytes(bytes(reversed(range(256))) * 4)

        def mode():
            os.chmod(lab.moose / "run.sh", 0o755)

        def blank_lines():
            lab.write("run.sh", "#!/bin/sh\n\n\n\techo   hi\n")

        for mutate in (whitespace, binary, mode, blank_lines):
            with self.subTest(change=mutate.__name__):
                mutate()
                lab.git("add", "-A")
                out = lab.ok("fix", "s1")
                self.assertRegex(out, r"s2 +moved .*content unchanged")
                out = lab.ok("push")
                self.assertIn("push %s" % S1, out)
                self.assertEqual(lab.fork_sha(S1), lab.sha(S1), "the changed slice is published")
                self.assertEqual(lab.fork_sha(S2), s2_on_fork, "the untouched draft is deferred")

    def test_user_git_config_cannot_blind_or_derail_the_restack(self):
        lab = self.lab
        s1, s2 = lab.chain(2)
        s3 = lab.slice(3)
        lab.ok("push", "s1", "s2", "s3")
        lab.git("branch", "other", S2)
        cfg = lab.tmp / "gitconfig"
        cfg.write_text(
            "[color]\n\tui = always\n[rebase]\n\tupdateRefs = true\n\tautoSquash = true\n"
            "\tautoStash = true\n\trebaseMerges = true\n[pull]\n\trebase = true\n"
            "[diff]\n\tnoprefix = true\n\trenames = copies\n[merge]\n\tconflictStyle = zdiff3\n"
            "[sequence]\n\teditor = false\n[core]\n\teditor = false\n\tpager = false\n")
        env = {"GIT_CONFIG_GLOBAL": str(cfg), "GIT_SEQUENCE_EDITOR": "false",
               "GIT_EDITOR": "false", "LANG": "de_DE.UTF-8", "LC_ALL": "de_DE.UTF-8"}
        lab.write("s1.txt", "slice 1\nreal change\n")
        lab.git("add", "-A")
        rc, out, err = lab.stack("fix", "s1", "--squash", env=env)
        self.assertEqual(rc, 0, err)
        self.assertRegex(out, r"s2 +moved .*content unchanged")
        self.assertEqual(lab.sha("other"), s2, "another branch in the range does not move")
        self.assertEqual(lab.sha(S3 + "^"), lab.sha(S2))
        rc, out, err = lab.stack("push", env=env)
        self.assertEqual(rc, 0, err)
        self.assertIn("push %s" % S1, out)
        self.assertIn("deferred: s2", out)
        self.assertIn("deferred: s3", out)
        self.assertEqual(lab.fork_sha(S1), lab.sha(S1))
        rc, out, err = lab.stack("status", "--json", "--no-gh", env=env)
        self.assertTrue(json.loads(out)["chain_ok"])

    def test_a_failing_signer_or_hook_leaves_nothing_behind(self):
        lab = self.lab
        lab.chain(2)
        cfg = lab.tmp / "gitconfig"
        cfg.write_text("[commit]\n\tgpgsign = true\n[gpg]\n\tprogram = false\n")
        env = {"GIT_CONFIG_GLOBAL": str(cfg)}
        tip, before = lab.sha("HEAD"), self.refs()
        lab.write("s1.txt", "slice 1\nreal change\n")
        lab.git("add", "-A")
        self.refuse("fix", "s1", env=env, contains="the fix commit failed, and nothing changed")
        self.assertEqual(self.refs(), before)
        self.assertEqual(lab.git("diff", "--cached", "--name-only"), "s1.txt")
        self.assertEqual(lab.status()["problems"], [])
        lab.write("loose.txt", "x\n")
        porcelain = lab.git("status", "--porcelain")
        self.refuse("park", env=env, contains="nothing changed")
        self.assertEqual((lab.sha("HEAD"), lab.git("status", "--porcelain")), (tip, porcelain))
        # A pre-commit hook that says no.
        hooks = lab.tmp / "hooks"
        hooks.mkdir()
        (hooks / "pre-commit").write_text("#!/bin/sh\necho hook says no >&2\nexit 1\n")
        os.chmod(hooks / "pre-commit", 0o755)
        lab.git("config", "core.hooksPath", str(hooks))
        (lab.moose / "loose.txt").unlink()
        self.refuse("fix", "s1", contains=["the fix commit failed", "hook says no"])
        self.assertEqual(self.refs(), before)
        self.assertEqual(lab.status()["problems"], [])
        lab.write("loose.txt", "x\n")
        lab.ok("park")                                   # park does not run the hook
        lab.ok("unpark")


class RaceAndRecovery(StackTest):
    def test_merge_race_is_seen_without_github(self):
        lab = self.lab
        s1, s2 = lab.chain(2)
        lab.ok("push", "s1", "s2")
        lab.set_pr(S1, 11, draft=False)
        lab.set_pr(S2, 12)
        lab.write("s1.txt", "slice 1\nlate local change\n")
        lab.git("add", "-A")
        lab.ok("fix", "s1", "--squash", "--yes")
        local = lab.sha(S1)
        lab.upstream_merge(s1, 11)
        down = {"FAKE_GH_FAIL": "1"}
        before = self.refs()
        for verb in (["sync"], ["sync", "--rebase"], ["sync", "--rebase", "--yes"]):
            self.refuse(*verb, env=down, contains=["merge race", s1[:9], local[:9]])
        self.assertEqual({k: v for k, v in self.refs().items() if "remotes" not in k}, before)
        rc, out, err = lab.stack("status", "--json", "--no-gh")
        data = json.loads(out)
        self.assertEqual(data["slices"][0]["state"], "merge-race")
        self.assertIn("merge race", " ".join(data["problems"]))

    def test_continue_survives_a_deleted_cxx_file_and_a_formatter_failure(self):
        lab = self.lab
        odd = "int   f( int a,int b ){return a+b;}"
        lab.write("old.C", "int old;\n")
        lab.write("keep.C", "int keep;\n")
        lab.git("add", "-A")
        lab.git("commit", "-q", "-m", "feat: slice 1")
        lab.ok("seal")
        lab.git("rm", "-q", "old.C")                     # slice 2 deletes a C++ file
        lab.write("keep.C", "int keep;\n%s\n" % odd)
        lab.edit_line(8, "line08 s2")
        lab.git("add", "-A")
        lab.git("commit", "-q", "-m", "feat: slice 2")
        lab.ok("seal")
        lab.edit_line(8, "line08 FIX")
        lab.write("keep.C", "int keep;\n%s\nint fix;\n" % odd)
        lab.git("add", "-A")
        rc, out, err = lab.stack("fix", "s1", "--squash")
        self.assertEqual(rc, 3, err)
        # Stop 1, at the fixup. The formatter fails: the file is named, the restack goes on.
        lab.write("shared.txt", shared(l08="line08 FIX"))
        lab.write("keep.C", "int keep;\nint fix;\n")
        lab.git("add", "-A")
        rc, out, err = lab.stack("fix", "--continue", env={"FAKE_FMT_FAIL": "1"})
        self.assertEqual(rc, 3, "the next stop is slice 2, not the same stop again\n" + err)
        self.assertIn("git clang-format failed on keep.C", err)
        # Stop 2, at slice 2, which deletes old.C. A deleted file never reaches the formatter.
        self.assertEqual(lab.git("diff", "--cached", "--name-only", "--diff-filter=D"), "old.C")
        lab.write("shared.txt", shared(l08="line08 FIX s2"))
        lab.write("keep.C", "int keep;\n%s\nint fix;\n" % odd)
        lab.git("add", "-A")
        rc, out, err = lab.stack("fix", "--continue")
        self.assertEqual(rc, 0, err)
        self.assertNotIn("clang-format failed", err)
        self.assertEqual(lab.fmt_log.read_text().split(), ["keep.C"])
        self.assertFalse((lab.moose / "old.C").exists())
        self.assertIn(odd, lab.git("show", S2 + ":keep.C"))
        self.assertEqual(lab.status()["problems"], [])

    def test_half_park_is_undone(self):
        lab = self.lab
        lab.chain(1)
        lab.write("s1.txt", "slice 1\nedit\n")
        lab.git("add", "s1.txt")
        lab.write("new.txt", "untracked\n")
        lab.write("secret.txt", "x\n")
        os.chmod(lab.moose / "secret.txt", 0)
        try:
            tip, porcelain = lab.sha("HEAD"), lab.git("status", "--porcelain")
            self.refuse("park", contains=["park failed", "as they were"])
            self.assertEqual(lab.sha("HEAD"), tip, "the first park commit is undone")
            self.assertEqual(lab.git("status", "--porcelain"), porcelain)
            self.assertEqual(lab.git("diff", "--cached", "--name-only"), "s1.txt")
            self.assertEqual(lab.ok("unpark").strip(), "nothing parked")
        finally:
            os.chmod(lab.moose / "secret.txt", 0o644)
        lab.ok("park")
        self.assertEqual(lab.git("status", "--porcelain"), "")
        lab.ok("unpark")
        self.assertEqual(lab.git("status", "--porcelain"), porcelain)

    def test_dirty_submodule_content_is_not_dirty_work(self):
        lab = self.lab
        sub = lab.tmp / "subsrc"
        lab.git("init", "-q", "-b", "main", sub, cwd=lab.tmp)
        lab.commit("sub 1", cwd=sub, f__txt="a\n")
        lab.git("-c", "protocol.file.allow=always", "submodule", "add", "-q", str(sub), "petsc")
        lab.write("s1.txt", "slice 1\n")
        lab.git("add", "-A")
        lab.git("commit", "-q", "-m", "feat: slice 1 with a submodule")
        lab.ok("seal")
        lab.slice(2)
        (lab.moose / "petsc" / "f.txt").write_text("locally patched\n")
        tip = lab.sha("HEAD")
        self.assertEqual(lab.ok("park").strip(), "nothing to park")
        self.assertEqual(lab.sha("HEAD"), tip)
        self.assertEqual(lab.status()["wip"]["dirty"], 0)
        lab.write("s1.txt", "slice 1\nfix\n")
        lab.git("add", "s1.txt")
        lab.ok("fix", "s1")
        self.assertEqual(lab.ok("unpark").strip(), "nothing parked")
        self.assertEqual((lab.moose / "petsc" / "f.txt").read_text(), "locally patched\n")
        lab.upstream_commit("next 2", upstream_b__txt="b\n")
        lab.ok("sync", "--rebase")
        self.assertEqual(lab.sha(S1 + "^"), lab.sha("upstream/next"))

    def test_every_writing_verb_checks_the_lease(self):
        lab = self.lab
        lab.chain(2)
        lab.edit_line(8, "line08 FIX")
        lab.git("add", "-A")
        rc, out, err = lab.stack("fix", "s1")
        self.assertEqual(rc, 3)
        other = subprocess.Popen(["sleep", "60"])
        lease = lab.wt / ".factory-lease"
        try:
            lease.mkdir()
            (lease / "lease.json").write_text(json.dumps({"pid": other.pid}))
            held = "another session holds the lease"
            self.refuse("fix", "--continue", contains=held)
            self.refuse("fix", "--abort", contains=held)
            self.assertTrue(lab.status()["rebase_in_progress"])
            (lease / "lease.json").unlink()
            lease.rmdir()
            lab.ok("fix", "--abort")
            lab.git("restore", "--staged", "--worktree", ".")
            lab.write("loose.txt", "x\n")
            lab.ok("park")
            lease.mkdir()
            (lease / "lease.json").write_text(json.dumps({"pid": other.pid}))
            tip = lab.sha("HEAD")
            self.refuse("unpark", contains=held)
            self.assertEqual(lab.sha("HEAD"), tip)
            lab.write("more.txt", "x\n")
            self.refuse("park", contains=held)
            lab.git("add", "-A")
            lab.git("commit", "-q", "-m", "feat: three")
            self.refuse("seal", contains=held)
            self.assertEqual(lab.git("for-each-ref", "refs/heads/" + S3), "")
        finally:
            other.kill()
            other.wait()

    def _three_pushed_with_a_staged_fix(self):
        lab = self.lab
        lab.chain(2)
        lab.slice(3)
        lab.ok("push", "s1", "s2", "s3")
        lab.write("s1.txt", "slice 1\nfix\n")
        lab.git("add", "-A")
        return self.refs(), lab.sha("HEAD")

    def test_abort_after_the_rebase_finished_restores_the_branch_and_the_refs(self):
        lab = self.lab
        before, tip = self._three_pushed_with_a_staged_fix()
        self.crash(["fix", "s1"], "finish")              # killed after the rebase, before finish
        self.assertNotEqual(lab.sha(S1), before["refs/heads/" + S1])
        self.assertIn("restack-in-progress", " ".join(lab.status()["problems"]))
        self.refuse("push", contains=["interrupted", "stack fix --abort"])
        lab.ok("fix", "--abort")
        self.assertEqual(self.refs(), before, "the branch and every slice ref are back")
        self.assertEqual(lab.sha("HEAD"), tip)
        self.assertEqual(lab.git("diff", "--cached", "--name-only"), "s1.txt")
        self.assertEqual(lab.git("status", "--porcelain"), "M  s1.txt")
        self.refuse("fix", "--abort", contains="no stack restack")
        self.assertEqual(lab.status()["problems"], [])

    def test_continue_after_a_kill_before_finish_completes_the_restack(self):
        lab = self.lab
        before, tip = self._three_pushed_with_a_staged_fix()
        self.crash(["fix", "s1"], "finish")
        out = lab.ok("fix", "--continue")
        self.assertIn("CHANGED: this is the fix", out)
        self.assertIn("the tree at the tip is the same as before the restack", out)
        self.assertEqual(lab.status()["problems"], [push_pending("s1")])
        self.assertIn("fix", lab.git("show", S1 + ":s1.txt"))

    def test_a_kill_between_the_fix_commit_and_the_rebase_can_be_undone(self):
        lab = self.lab
        lab.chain(2)
        for recover in ("--abort", "--continue"):
            with self.subTest(recover=recover):
                before, tip = self.refs(), lab.sha("HEAD")
                lab.write("s1.txt", "slice 1\nfix %s\n" % recover)
                lab.git("add", "-A")
                self.crash(["fix", "s1", "--squash"], "run_rebase")
                self.assertTrue(lab.subjects("-1")[0].startswith("fixup! stack fix s1"),
                                "the loose fix commit is on the tip")
                problems = " ".join(lab.status()["problems"])
                self.assertIn("restack-in-progress", problems)
                self.assertIn("stack fix --abort", problems)
                self.refuse("fix", "s1", "--squash", contains="stack fix --abort")
                self.refuse("push", "s1", contains="stack fix --abort")
                lab.ok("fix", recover)
                self.assertEqual(self.refs(), before)
                self.assertEqual(lab.sha("HEAD"), tip)
                self.assertEqual(lab.git("diff", "--cached", "--name-only"), "s1.txt")
                self.assertEqual(lab.status()["problems"], [])
                lab.git("restore", "--staged", "--worktree", ".")

    def test_sync_rebase_killed_before_finish_then_abort_restores_the_base(self):
        lab = self.lab
        lab.chain(2)
        lab.upstream_commit("next 2", upstream_b__txt="x\n")
        lab.git("fetch", "-q", "upstream")
        before, tip = self.refs(), lab.sha("HEAD")
        self.crash(["sync", "--rebase", "--no-fetch"], "finish")
        self.assertNotEqual(lab.sha("HEAD"), tip)
        lab.ok("fix", "--abort")
        self.assertEqual({k: v for k, v in self.refs().items() if "remotes" not in k}, before)
        self.assertEqual(lab.sha("refs/stack/E/base"), lab.sha("upstream/devel"))
        self.assertEqual(lab.status()["problems"], [])

    def test_a_skipped_fixup_is_not_reported_as_the_fix(self):
        lab = self.lab
        lab.chain(2)
        lab.slice(3)
        lab.write("s1.txt", "slice 1 changed by s4\n")
        lab.git("add", "-A")
        lab.git("commit", "-q", "-m", "feat: slice 4")
        lab.ok("seal")
        lab.write("s1.txt", "slice 1 changed by s4\nFIX LINE\n")
        lab.git("add", "-A")
        rc, out, err = lab.stack("fix", "s1", "--squash")
        self.assertEqual(rc, 3, "the fixup itself conflicts")
        fix = lab.sha("refs/heads/E")
        lab.git("rebase", "--skip", check=False)         # by hand: the fix is dropped
        rc, out, err = lab.stack("fix", "--continue")
        self.assertEqual(rc, 1)
        self.assertIn("NOT CHANGED: the fix is not in this slice", out)
        self.assertNotIn("this is the fix", out)
        self.assertIn("THE TREE AT THE TIP DIFFERS", out)
        self.assertIn("the fix is NOT in s1", err)
        self.assertIn("git cherry-pick -n %s" % fix[:9], err)
        self.assertNotIn("FIX LINE", lab.git("show", "E:s1.txt"))
        self.assertTrue(lab.status()["chain_ok"])

    def test_abort_after_the_user_finished_the_rebase_by_hand(self):
        lab = self.lab
        s1, s2 = lab.chain(2)
        s3 = lab.slice(3)
        lab.edit_line(8, "line08 FIXED")
        lab.git("add", "-A")
        rc, out, err = lab.stack("fix", "s1", "--squash")
        self.assertEqual(rc, 3)
        for _ in range(4):                               # the user does it all with plain git
            if not (lab.moose / ".git" / "rebase-merge").exists():
                break
            at_s2 = (lab.moose / "s2.txt").exists()
            lab.write("shared.txt", shared(l02="line02 s1",
                                           l08="line08 FIXED s2" if at_s2 else "line08 FIXED"))
            lab.git("add", "-A")
            lab.git("-c", "core.editor=true", "rebase", "--continue", check=False)
        self.assertFalse((lab.moose / ".git" / "rebase-merge").exists())
        self.assertNotEqual(lab.sha(S2), s2, "the hand-run rebase moved the refs")
        lab.ok("fix", "--abort")
        self.assertEqual((lab.sha(S1), lab.sha(S2), lab.sha(S3)), (s1, s2, s3))
        self.assertEqual(lab.sha("HEAD"), s3)
        self.assertEqual(lab.git("diff", "--cached", "--name-only"), "shared.txt")
        self.assertIn("line08 FIXED", lab.git("show", ":shared.txt"))

    def test_push_sends_the_planned_sha_when_a_ref_moves_after_the_plan(self):
        lab = self.lab
        s1, s2 = lab.chain(2)
        lab.ok("push", "s1")
        wip = lab.commit("WIP sneaked", wip__txt="x\n")
        module = load_stack(lab.env)
        real = module.Git.run

        def racy(git, *args, **kw):
            if "push" in args:
                real(git, "update-ref", "refs/heads/" + S2, wip)   # a concurrent writer
            return real(git, *args, **kw)

        with mock.patch.dict(os.environ, lab.env, clear=True), \
                mock.patch.object(module.Git, "run", racy), \
                contextlib.redirect_stdout(io.StringIO()):
            rc = module.main(["-C", str(lab.moose), "push", "s2"])
        self.assertEqual(rc, 0)
        self.assertEqual(lab.fork_sha(S2), s2, "the fork got the commit that was checked")
        self.assertEqual(lab.sha("refs/stack/E/pushed/s2"), s2, "the record names what was pushed")

    def test_unreadable_restack_record(self):
        lab = self.lab
        lab.chain(2)
        record = lab.moose / ".git" / "stack-op.json"
        record.write_text("")
        for verb in (["push", "s1"], ["park"], ["fix", "--continue"], ["seal"]):
            self.refuse(*verb, contains=["unreadable", "stack fix --abort"])
        self.assertIn("stack fix --abort", " ".join(lab.status()["problems"]))
        rc, out, err = lab.stack("fix", "--abort")
        self.assertEqual(rc, 0, err)
        self.assertIn("NOT restored", out)
        self.assertFalse(record.exists())
        self.assertEqual(lab.status()["problems"], [])
        lab.ok("push", "s1")
        # The same during a stopped restack: the rebase is aborted and the fix is staged again.
        before, tip = self.refs(), lab.sha("HEAD")
        lab.edit_line(8, "line08 FIX")
        lab.git("add", "-A")
        rc, out, err = lab.stack("fix", "s1", "--squash")
        self.assertEqual(rc, 3)
        record.write_text("{ not json")
        rc, out, err = lab.stack("fix", "--abort")
        self.assertEqual(rc, 0, err)
        self.assertEqual(self.refs(), before)
        self.assertEqual(lab.sha("HEAD"), tip)
        self.assertEqual(lab.git("diff", "--cached", "--name-only"), "shared.txt")
        self.assertFalse(lab.status()["rebase_in_progress"])

    def test_a_fix_that_empties_its_slice_stops_and_says_so(self):
        lab = self.lab
        lab.chain(2)
        lab.slice(3)
        lab.git("rm", "-q", "s2.txt")
        lab.edit_line(8, "line08")
        lab.git("add", "-A")
        rc, out, err = lab.stack("fix", "s2", "--squash")
        if rc == 3:
            self.assertIn("no file is in conflict", err)
            rc, out, err = lab.stack("fix", "--continue")
        self.assertEqual(rc, 0, err)
        self.assertIn("HOLDS AN EMPTY COMMIT", out)
        self.assertTrue(lab.status()["chain_ok"])


class NotAnEpic(StackTest):
    def test_meta_worktree_without_a_moose_checkout_is_refused(self):
        lab = self.lab
        meta = lab.tmp / "meta"
        lab.git("init", "-q", "-b", "F", meta, cwd=lab.tmp)
        lab.commit("meta 1", cwd=meta, readme__txt="meta\n")
        (meta / "moose").mkdir()                          # the submodule directory, still empty
        (meta / "specs").mkdir()
        (meta / "specs" / "epic.md").write_text("---\nepic: F\n---\n")
        (meta / "notes.txt").write_text("a dirty file of the meta repository\n")
        tip = lab.sha("HEAD", cwd=meta)
        for verb in (["status", "--no-gh"], ["park"], ["seal"], ["sync", "--rebase"]):
            for how in ({"cwd": meta}, {"cwd": meta / "moose"}, {"cwd": meta / "specs"}):
                self.refuse(*verb, contains=["meta worktree", "never acts on the meta repository"],
                            **how)
            rc, out, err = lab.stack("-C", meta, *verb, cwd=lab.tmp)
            self.assertEqual(rc, 1)
            self.assertIn("meta worktree", err)
        self.assertEqual(lab.sha("HEAD", cwd=meta), tip)
        self.assertIn("notes.txt", lab.git("status", "--porcelain", cwd=meta))

    def test_a_plain_feature_branch_is_not_an_epic(self):
        lab = self.lab
        (lab.wt / "specs" / "epic.md").unlink()
        lab.commit("feat: a", a__txt="a\n")
        lab.commit("feat: b", b__txt="b\n")
        lab.upstream_commit("next 2", upstream_b__txt="b\n")
        lab.write("loose.txt", "x\n")
        tip, porcelain = lab.sha("HEAD"), lab.git("status", "--porcelain")
        for verb in (["sync", "--rebase"], ["sync"], ["park"], ["unpark"], ["seal"],
                     ["push", "--all"], ["fix", "s1"], ["adopt", "s1"]):
            self.refuse(*verb, contains=["is not an epic", "specs/epic.md"])
        self.assertEqual((lab.sha("HEAD"), lab.git("status", "--porcelain")), (tip, porcelain))
        data = lab.status()
        self.assertIn("not an epic", " ".join(data["problems"]))

    def test_seal_of_the_first_slice_needs_the_epic_file(self):
        lab = self.lab
        (lab.wt / "specs" / "epic.md").unlink()
        lab.commit("feat: slice 1", one__txt="1\n")
        self.refuse("seal", contains=["is not an epic", "/moose-epic new"])
        self.assertEqual(lab.git("for-each-ref", "refs/heads/epic/"), "")
        (lab.wt / "specs" / "epic.md").write_text("---\nepic: E\n---\n")
        self.assertEqual(lab.ok("seal").strip(), "s1")
        # Once a slice exists, the branch is an epic even when the file is gone.
        (lab.wt / "specs" / "epic.md").unlink()
        lab.ok("park")

    def test_detached_head_is_refused(self):
        lab = self.lab
        lab.chain(1)
        lab.git("switch", "-q", "--detach")
        for verb in (["status", "--no-gh"], ["park"], ["base"], ["push", "s1"]):
            self.refuse(*verb, contains="HEAD is detached")


class AdoptMessages(StackTest):
    def test_adopt_when_the_fork_is_only_behind(self):
        lab = self.lab
        s1, s2 = lab.chain(2)
        lab.ok("push", "s1", "s2")
        lab.set_pr(S1, 11, draft=False)
        lab.write("s1.txt", "slice 1\nfix\n")
        lab.git("add", "-A")
        lab.ok("fix", "s1", "-m", "review")
        local = lab.sha(S1)
        out = lab.ok("adopt", "s1")
        self.assertIn("is behind the local slice", out)
        self.assertIn("stack push s1", out)
        self.assertNotIn("diverged", out)
        self.assertEqual((lab.sha(S1), lab.fork_sha(S1)), (local, s1))

    def test_the_diverged_recovery_makes_no_commit(self):
        lab = self.lab
        s1, s2 = lab.chain(2)
        lab.ok("push", "s1", "s2")
        lab.maintainer_push(S1, amend=True)
        err = self.refuse("adopt", "s1", contains=["have diverged", "stack adopt s1 --ours",
                                                   "git cherry-pick -n"])
        self.assertNotRegex(err, r"git cherry-pick <sha>")
        self.assertLess(err.index("--ours"), err.index("cherry-pick"), "--ours is named first")


class AwkwardFiles(StackTest):
    def test_park_round_trip_and_conflict_names_with_awkward_files(self):
        lab = self.lab
        lab.write(".gitignore", "*.o\nbuild/\n")
        lab.write("old name.txt", "to be renamed\n" * 5)
        lab.write("gone.txt", "to be deleted\n")
        lab.write("run.sh", "#!/bin/sh\n")
        (lab.moose / "bin.dat").write_bytes(bytes(range(256)))
        odd = "ünï cödé.txt"
        lab.write(odd, "a\n")
        lab.git("add", "-A")
        lab.git("commit", "-q", "-m", "feat: slice 1")
        lab.ok("seal")
        lab.slice(2)
        lab.git("mv", "old name.txt", "new name.txt")                # a staged rename
        (lab.moose / "gone.txt").unlink()                            # an unstaged delete
        os.chmod(lab.moose / "run.sh", 0o755)                        # an unstaged mode change
        (lab.moose / "bin.dat").write_bytes(bytes(reversed(range(256))))
        lab.git("add", "bin.dat")
        (lab.moose / "bin.dat").write_bytes(b"\x00\x01again")        # staged, then changed again
        lab.write(odd, "a\nb\n")
        lab.write("dir with space/new file.txt", "untracked\n")
        lab.write("x.o", "ignored\n")
        lab.write("build/out.txt", "ignored dir\n")
        snap = lambda: (lab.git("status", "--porcelain", "--ignored"),
                        lab.git("ls-files", "-s"))
        before = snap()
        lab.ok("park")
        self.assertEqual(lab.git("status", "--porcelain"), "")
        lab.ok("unpark")
        self.assertEqual(snap(), before)
        # A fix that conflicts with the parked work in the oddly named file.
        lab.ok("park")
        lab.write(odd, "a\nfix\n")
        lab.git("add", "-A")
        rc, out, err = lab.stack("fix", "s1")
        self.assertEqual(rc, 3, err)
        self.assertIn("conflict: " + odd, err, "the name is printed as it is, not quoted")
        while rc == 3:
            text = (lab.moose / odd).read_text()
            lab.write(odd, "a\nfix\n" + ("b\n" if "b\n" in text else ""))
            lab.git("add", "-A")
            rc, out, err = lab.stack("fix", "--continue")
        self.assertEqual(rc, 0, err)
        lab.ok("unpark")
        self.assertEqual(snap()[0], before[0], "the same paths are staged, unstaged and untracked")



# --------------------------------------------------------------------------- the final round


class FinalRound(StackTest):
    def test_the_lowest_open_slice_is_never_deferred(self):
        lab = self.lab
        s1, s2 = lab.chain(2)
        lab.slice(3)
        lab.ok("push", "s1", "s2")
        lab.set_pr(S1, 11)
        lab.set_pr(S2, 12)
        lab.write("s1.txt", "slice 1\ndraft fix\n")
        lab.git("add", "-A")
        lab.ok("fix", "s1")
        self.assertEqual(lab.status()["problems"], [push_pending("s1")])
        self.assertIn("deferred: s2", lab.ok("push"))
        self.assertEqual(lab.fork_sha(S2), s2, "slice 2 only moved: its push is deferred")
        self.assertEqual(lab.status()["problems"], [], "slice 1 is level; slice 2 is not lowest")
        # Slice 1 merges. Slice 2 is now the next PR, and the fork holds its old copy,
        # which still carries the old slice 1.
        lab.upstream_merge(lab.fork_sha(S1), 11)
        lab.set_pr(S1, 11, state="MERGED", draft=False, oid=lab.fork_sha(S1))
        wanted = ("push-pending: s2 is the lowest open slice and the fork holds an older copy; "
                  "run stack push before the PR is marked ready")
        self.assertEqual(push_pending("s2"), wanted)
        out = lab.ok("sync")
        self.assertIn("problem: " + wanted, out)
        data = lab.status()
        self.assertEqual(data["problems"], [wanted])
        self.assertEqual({r["id"]: r["behind"] for r in data["slices"]},
                         {"s1": False, "s2": True, "s3": False})
        self.assertIn("problem: " + wanted, lab.ok("status"))
        self.assertEqual(lab.subjects("upstream/next..%s" % lab.fork_sha(S2)),
                         ["feat: slice 1", "feat: slice 2"], "the stale copy of slice 1")
        # A plain push brings it level while the PR is still a draft: no --yes.
        out = lab.ok("push")
        self.assertIn("push %s" % S2, out)
        self.assertEqual(lab.fork_sha(S2), lab.sha(S2))
        self.assertEqual(lab.subjects("upstream/next..%s" % lab.fork_sha(S2)), ["feat: slice 2"])
        self.assertEqual(lab.status()["problems"], [])
        self.assertNotIn("push-pending", lab.ok("sync"))

    def test_the_lowest_open_slice_in_review_still_needs_yes_for_a_rewrite(self):
        lab = self.lab
        s1, s2 = lab.chain(2)
        lab.ok("push", "s1", "s2")
        lab.set_pr(S1, 11)
        lab.set_pr(S2, 12)
        lab.write("s1.txt", "slice 1\ndraft fix\n")
        lab.git("add", "-A")
        lab.ok("fix", "s1")
        lab.ok("push")
        lab.upstream_merge(lab.fork_sha(S1), 11)
        lab.ok("sync")
        lab.set_pr(S2, 12, draft=False)                  # marked ready before the push
        self.refuse("push", contains=["s2 (in review, PR #12)", "--yes"])
        self.assertEqual(lab.fork_sha(S2), s2)
        lab.ok("push", "--yes")
        self.assertEqual(lab.fork_sha(S2), lab.sha(S2))

    def test_fixes_that_a_diff_normaliser_can_hide_are_published(self):
        many = b"".join(b"line%02d\n" % i for i in range(1, 31))

        def ins(at):
            return b"".join(b"line%02d\n" % i + (b"NEW LINE\n" if i == at else b"")
                            for i in range(1, 31))

        cases = [
            ("a line moved within the file", {"f.txt": many}, {"f.txt": ins(3)},
             lambda lab: (lab.moose / "f.txt").write_bytes(ins(20))),
            ("trailing whitespace added on the last line", None, {"zlast.txt": b"alpha\nomega\n"},
             lambda lab: (lab.moose / "zlast.txt").write_bytes(b"alpha\nomega   \n")),
            ("trailing whitespace removed", None, {"zlast.txt": b"alpha\nomega \t\n"},
             lambda lab: (lab.moose / "zlast.txt").write_bytes(b"alpha\nomega\n")),
            ("CRLF to LF", None, {"crlf.txt": b"alpha\r\nomega\r\n"},
             lambda lab: (lab.moose / "crlf.txt").write_bytes(b"alpha\nomega\n")),
            ("a form feed removed", None, {"ff.txt": b"int a;\x0c\nint b;\n"},
             lambda lab: (lab.moose / "ff.txt").write_bytes(b"int a;\nint b;\n")),
            ("a pure rename", None, {"old.txt": b"same\n" * 5},
             lambda lab: lab.git("mv", "old.txt", "new.txt")),
            ("no newline at the end of the file", None, {"nl.txt": b"alpha\nomega\n"},
             lambda lab: (lab.moose / "nl.txt").write_bytes(b"alpha\nomega")),
        ]
        for name, base_files, files, fix in cases:
            with self.subTest(case=name), tempfile.TemporaryDirectory() as tmp:
                lab = Lab(os.path.realpath(tmp))
                if base_files:
                    for k, v in base_files.items():
                        (lab.moose / k).write_bytes(v)
                    lab.git("add", "-A")
                    lab.git("commit", "-q", "-m", "feat: slice 0")
                    lab.ok("seal")
                for k, v in files.items():
                    (lab.moose / k).write_bytes(v)
                lab.git("add", "-A")
                lab.git("commit", "-q", "-m", "feat: slice A")
                a = lab.ok("seal").strip()
                lab.commit("feat: slice B", zz__txt="top\n")
                b = lab.ok("seal").strip()
                lab.ok("push", a, b)
                target = sref(int(a[1:]))
                lab.set_pr(target, 11)
                lab.set_pr(sref(int(b[1:])), 12)
                fix(lab)
                lab.git("add", "-A")
                out = lab.ok("fix", a)
                self.assertIn("CHANGED: this is the fix", out)
                self.assertRegex(out, r"%s +moved .*content unchanged" % b)
                out = lab.ok("push")
                self.assertIn("push %s" % target, out)
                self.assertIn("deferred: %s" % b, out)
                self.assertEqual(lab.fork_sha(target), lab.sha(target))

    def test_content_id_ignores_how_lines_group_into_hunks(self):
        lab = self.lab
        many = "".join("line%02d\n" % i for i in range(1, 11))
        change = lambda text: text.replace("line05\n", "line05 B\n").replace("line07\n", "line07 B\n")
        lab.commit("base", f__txt=many)
        two_hunks = lab.commit("change", f__txt=change(many))
        lab.git("reset", "-q", "--keep", "HEAD~2")
        joined = many.replace("line06\n", "")            # lines 5 and 7 are now neighbours
        lab.commit("base without line 6", f__txt=joined)
        one_hunk = lab.commit("change", f__txt=change(joined))
        other = lab.commit("another change", f__txt=change(joined).replace("line05 B", "line05 C"))
        module = load_stack(lab.env)
        with mock.patch.dict(os.environ, lab.env, clear=True):
            ctx = module.Ctx(lab.moose)
            self.assertEqual(ctx.content_id(two_hunks), ctx.content_id(one_hunk))
            self.assertNotEqual(ctx.content_id(one_hunk), ctx.content_id(other))

    def test_restore_knows_the_fix_commit_by_its_sha(self):
        lab = self.lab
        lab.chain(2)
        lab.slice(3)
        lab.ok("push", "s1", "s2", "s3")
        lab.set_pr(S1, 11, draft=False)
        lab.write("s1.txt", "slice 1\nfix\n")
        lab.git("add", "-A")
        before, tip = self.refs(), lab.sha("HEAD")
        # git cleans this message (the space at the end of the subject): the commit subject
        # is not the text that was asked for.
        self.crash(["fix", "s1", "-m", "review fix \n\nbody"], "todo_for")
        self.assertEqual(lab.subjects("-1"), ["review fix"])
        self.assertEqual(lab.sha("HEAD^"), tip)
        lab.ok("fix", "--abort")
        self.assertEqual(self.refs(), before)
        self.assertEqual(lab.sha("HEAD"), tip)
        self.assertEqual(lab.git("status", "--porcelain"), "M  s1.txt", "the fix is staged again")
        self.assertEqual((lab.moose / "s1.txt").read_text(), "slice 1\nfix\n")

    def test_seal_expect_rejects_an_empty_or_malformed_id(self):
        lab = self.lab
        lab.chain(1)
        lab.commit("feat: two", two__txt="2\n")
        for bad in ("", "s02", "S2", "ss2", "s0", "two", sref(2, "other")):
            rc, out, err = lab.stack("seal", "--expect", bad)
            self.assertEqual((rc, out), (2, ""), "--expect %r" % bad)
            self.assertIn("usage", err)
        self.assertEqual(lab.git("for-each-ref", "refs/heads/" + S2), "")
        rc, out, err = lab.stack("seal", "--expect", S2)
        self.assertEqual((rc, out.strip()), (0, "s2"))

    def test_merged_on_github_before_the_fetch_is_merged_and_not_a_race(self):
        lab = self.lab
        s1, s2 = lab.chain(2)
        lab.ok("push", "s1", "s2")
        lab.set_pr(S1, 11, draft=False)
        lab.set_pr(S2, 12)
        lab.upstream_merge(s1, 11)                        # the work checkout has not fetched
        lab.set_pr(S1, 11, state="MERGED", draft=False, oid=s1)
        data = lab.status()
        self.assertEqual(data["slices"][0]["state"], "merged")
        self.assertEqual(data["notes"], ["s1: merged on GitHub; run stack sync to fetch"])
        self.assertEqual(data["problems"], [])
        self.assertIn("note: s1: merged on GitHub; run stack sync to fetch", lab.ok("status"))
        lab.write("s1.txt", "slice 1\nlate\n")
        lab.git("add", "-A")
        self.refuse("fix", "s1", contains=["merged on GitHub", "stack sync"])
        self.refuse("fix", "s1", "--squash", "--yes", contains="merged on GitHub")
        lab.git("restore", "--staged", "--worktree", ".")
        self.refuse("sync", "--rebase", "--no-fetch", contains=["merged on GitHub", "stack sync"])
        self.assertIn("s1: merged on GitHub", lab.ok("sync", "--no-fetch"))
        self.assertIn("s1 is merged: its commit is in upstream/next", lab.ok("sync"))
        self.assertEqual(lab.status()["notes"], [])

    def test_push_never_touches_a_merged_pr_head(self):
        lab = self.lab
        s1, s2 = lab.chain(2)
        lab.ok("push", "s1", "s2")
        lab.set_pr(S1, 11, draft=False)
        lab.set_pr(S2, 12)
        lab.write("s1.txt", "slice 1\nlate\n")
        lab.git("add", "-A")
        lab.ok("fix", "s1", "--squash", "--yes")
        lab.upstream_merge(s1, 11)
        lab.git("fetch", "-q", "upstream")
        for env in ({"FAKE_GH_FAIL": "1"}, {}):
            for verb in (["push", "--all", "--yes"], ["push", "s1", "--yes"], ["push", "--yes"]):
                self.refuse(*verb, env=env, contains=["s1 (merge-race)", "never pushed again",
                                                      "stack sync"])
        self.assertEqual((lab.fork_sha(S1), lab.fork_sha(S2)), (s1, s2))

    def test_github_is_asked_for_our_own_prs_only(self):
        lab = self.lab
        lab.chain(1)
        log = lab.tmp / "gh.log"
        lab.ok("slots", env={"FAKE_GH_LOG": str(log)})
        args = json.loads(log.read_text().splitlines()[0])
        self.assertEqual(args[args.index("--author") + 1], "@me")
        self.assertEqual(args[args.index("--head") + 1], S1)

    def test_a_branch_with_the_old_slice_name_gets_a_hint_and_is_not_a_slice(self):
        lab = self.lab
        one = lab.commit("feat: one", one__txt="1\n")
        lab.git("branch", "E-s1", one)
        lab.git("branch", "E-s12", one)
        lab.git("branch", "E-s1x", one)                   # never was a slice name
        data = lab.status()
        self.assertEqual(data["slices"], [])
        self.assertEqual(len(data["notes"]), 2)
        self.assertIn("the branch E-s1 has the slice name of an earlier version", data["notes"][0])
        self.assertIn("note: the branch E-s1 has the slice name", lab.ok("status", "--no-gh"))
        rc, out, err = lab.stack("seal")
        self.assertEqual((rc, out.strip()), (0, "s1"))
        self.assertIn("hint: the branch E-s1 has the slice name of an earlier version", err)
        self.assertNotIn("E-s1x", err)
        self.assertEqual(lab.sha(S1), one)



if __name__ == "__main__":
    unittest.main()
