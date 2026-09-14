# factory

The projector that writes `~/projects/moose-factory`. One board, one next move per card.

```sh
~/projects/moose_stack/factory/factory board          # regenerate the vault
~/projects/moose_stack/factory/factory next <feature> # the single next move
~/projects/moose_stack/factory/factory doctor         # what is misconfigured
```

The vault is a build artifact. This package is its only writer. Code lives here, data lives
there. That split copies `analysis/` verbatim.

## Layout

```
factory/
  factory            launcher: picks a python3 that imports yaml, sets PYTHONPATH
  glyphs.json        every display glyph, so tool/*.py stays 7-bit ASCII
  tool/config.py     the config.toml reader, paths, SAFE_ID, caps, thresholds, the hostname guard
  tool/model.py      dataclasses, lane ranks, the flag and posture vocabularies, Ctx
  tool/probe.py      every read of the world; each probe returns (value, ok)
  tool/derive.py     pure: lane, flags, posture, next action
  tool/render.py     four-marker fencing, atomic writes, Home.md, Features.base
  tool/snapshot.py   the probe cache, carry-forward, nag memory, stamps, manifest
  tool/timeline.py   flock'd NDJSON append against the vault
  tool/gates.py      four monotonic attributed records per feature
  tool/cli.py        the verbs
  tool/ext_config.py     the `config` verb: the resolved settings and where each came from
  tool/ext_artifacts.py  rescue build records and reviews into Artifacts/; Elsewhere; Since yesterday
  tool/ext_board_html.py Board.html: the six-column kanban, written through the outputs hook
  tool/ext_dispatch.py   the lease; start, stop, attach, logs, release, reset
  tool/ext_refresh.py    refresh-pipeline: the canonical .claude against a worktree's frozen copy
  tool/ext_studies.py    read-only adapter over analysis/studies/*/card.yaml; Studies/<id>.md
  tool/ext_handoff.py    rescue specs/handoff.md into Artifacts/; the ## Handoff card section; handoff-stale
  tool/ext_gallery.py    the specs/gallery/ listing, the Gallery/<feature> symlink, the ## Gallery card section
  tool/ext_teardown.py   teardown and archive, plus the reclaimable-bytes number
  tool/ext_tick.py       the loop's policy: change gate, notifier, tick-status, doctor checks
  install.sh             install or remove the launchd agent; --status, --uninstall
  moose-factory-tick.sh  the 120 s tick, installed to ~/.local/bin/
  com.moose-factory.plist.in   the agent template; install.sh renders it into ~/Library/LaunchAgents/
  state/             GITIGNORED cache. `rm -rf state && factory board` repairs everything.
```

## The verbs

| verb | does | writes |
|---|---|---|
| `board [--du]` | one probe round, derive, write the whole vault | the vault, including `Board.html` |
| `status [<feature>] [--head]` | print `Home.md`, or one note; `--head` prints only the note's head block | nothing |
| `next <feature>` | the single next move, the lane, the flags and why | nothing |
| `set <feature> key=value` | record one namespaced annotation; `lane` and the other projector fields are refused | `state/` |
| `abandon <feature> "<reason>"` | record that you have given up on a card, with a reason | `.factory/timeline/` |
| `grant <feature> <gate>` | grant one gate, monotonic and attributed | `.factory/gates/` |
| `config [--json\|--sh\|--get K]` | the resolved per-machine settings and where each came from | nothing |
| `doctor` | say what is misconfigured, core plus every extension | nothing |
| `commit` | stage and commit the vault when it is dirty, no trailers; refused while `Home.md` is absent | the vault repo |
| `dump-obs <feature> [--out P]` | one card's probe snapshot, for debugging | `state/dump/`, or the named path |
| `version` | the version, the resolved paths, the discovered extensions | nothing |
| `start <feature> [--prompt P] [--force]` | take the lease, launch one `claude --bg` into the workspace | the lease, `state/` |
| `stop <feature>` | stop the background session, then release the lease | the lease |
| `attach <feature>` | print the attach command plus the session's state, detail and needs | nothing |
| `logs <feature>` | relay `claude logs` (needs a live service) | nothing |
| `release <feature>` | remove a stale lease, interactively, once the owner is proven gone | the lease |
| `reset <feature>` | diff the blueprint back to `approved`, free the lease, log the reason | a worktree file, on a typed yes |
| `teardown <feature> [--yes]` | print the teardown recipe; `--yes` runs it in a terminal | worktrees, on a typed yes |
| `archive <feature>` | `git mv` the note into `Archive/` once the worktree and the PR are gone | the vault |
| `refresh-pipeline <feature>` | diff the canonical `.claude` against a worktree's frozen copy | a worktree, on `--confirm` |
| `studies [<id>]` | the analysis studies, by lane | nothing |
| `tick-status` | what the 120 s loop looks like right now | nothing |

Every verb that writes accepts `--dry-run`.

`set` records an annotation, nothing more. The projector never reads it as a fact. Each value
renders in the card's `## Annotations` section, so a recorded note is visible and never silently
dropped.

`abandon` is the one input channel for a lane the probes cannot prove. It appends one timeline
line in the vault, which is committed, so the record survives `rm -rf factory/state`. The next
board moves the card to lane `abandoned` and posture `done`. To undo it, append an
`unabandoned` line.

## Exit codes

| code | meaning |
|---|---|
| 0 | ok |
| 1 | a human should look (a doctor check failed, or a card carries `error`) |
| 2 | a refused write (a missing marker, an input path, an owned field) |
| 3 | a missing path, a malformed `config.toml`, or the wrong host |

The hostname guard is the first statement of every entry point. On a refused host every verb exits
3. The refused hosts default to `sawtooth*`, `lemhi*`, `bitterroot*`, `hoodoo*` and `teton*`, and
the `refuse_hosts` key changes them.

## Configuration

No file in this repository names a user, a home directory, a vault or a machine. Every
machine-specific value comes from one file:

```
~/.config/moose-factory/config.toml        $MOOSE_FACTORY_CONFIG overrides the location
```

The file is optional for the python side. Each key falls back to a default derived from `$HOME`, so
a fresh clone runs with no file at all. Precedence, per key: the key's environment variable, then
the file, then the default. A file that does not parse, or a value of the wrong type, is exit 3 and
names the file and the parser's own message. A value may start with `~`; every reader expands it,
the three shell readers included.

One key is not optional in practice: `meta_repo`. `tool/config.py` derives it by walking up from its
own file, but the `/factory` skill, the SessionStart hook and the launchd tick do not sit inside the
checkout they have to find, so their last resort is the literal `$HOME/projects/moose_stack`. A
checkout at any other path needs the key. `install.sh` writes it when it is absent, and
`zsh factory/install.sh --config` writes it and nothing else.

```sh
factory config              # every setting, its value, and where the value came from
factory config --json       # the same, as JSON
factory config --sh         # shell assignments; the tick evals these
factory config --get vault  # one raw value
factory doctor              # the same block, above the checks
```

| key | default | what it is |
|---|---|---|
| `vault` | `$HOME/projects/moose-factory` | the board this projector writes |
| `worktrees_root` | `$HOME/projects/moose-worktrees` | where a legitimate feature worktree lives |
| `meta_repo` | this checkout, else `$HOME/projects/moose_stack` | the moose_stack that owns the code and `factory/state/` |
| `python` | the interpreter the launcher resolved | must import `yaml` |
| `claude_bin` | `$HOME/.local/bin/claude` | the binary `start`, `stop` and `logs` run |
| `claude_home` | `$HOME/.claude` | where the session files are read |
| `obsidian_vault` | the vault directory's basename | the name an `obsidian://` link carries |
| `notifier` | `/opt/homebrew/bin/terminal-notifier` | the banner binary; `""` uses the osascript fallback |
| `refuse_hosts` | the five INL families | hostname globs every entry point refuses, matched lowercased |
| `studies_dir` | `<meta_repo>/analysis/studies` | the analysis studies the `studies` verb reads; not the vault's `Studies/` |
| `path_extra` | `""` | extra PATH prefixes the launchd tick prepends, colon separated |
| `gallery_max_mb` | `5` | the per-file cap in `specs/gallery/`; a bigger file is named on the note and never linked |
| `gallery_thumbs` | `3` | how many thumbnails one `Board.html` card shows |
| the caps and thresholds | the values in `tool/config.py` | `max_concurrent_sessions`, `max_builds_per_day`, `min_free_gb`, `stall_seconds`, `nag_days`, `park_idle_days`, `triage_dirty`, `gh_cache_ttl`, `gh_limit`, `gh_parallel`, `subprocess_timeout`, `stale_ref_days`, `needs_you_cap`, `head_churn_budget`, `timeline_on_home` |

Every key has an environment variable: `MOOSE_FACTORY_VAULT`, `FACTORY_WORKTREE_ROOT`,
`FACTORY_REPO_ROOT`, `FACTORY_PYTHON`, `FACTORY_CLAUDE_BIN`, `FACTORY_CLAUDE_HOME`,
`FACTORY_STUDIES_DIR`, and `MOOSE_FACTORY_<KEY>` for the rest. An empty variable is not an
override. The launchd tick reads no shell profile, so a value it needs belongs in the file, not in
an exported variable.

## Second machine

The code is shared and the state is not. Follow these steps on the second Mac.

1. Clone the meta-repo:

   ```sh
   git clone git@github.com:<you>/moose_stack.git ~/projects/moose_stack
   ```

2. Create the vault directory and make it a git repository:

   ```sh
   mkdir -p ~/projects/moose-factory && git -C ~/projects/moose-factory init
   ```

3. Write `~/.config/moose-factory/config.toml`. Change every path that differs on this machine:

   ```toml
   vault = "~/projects/moose-factory"
   worktrees_root = "~/projects/moose-worktrees"
   meta_repo = "~/projects/moose_stack"
   python = "/opt/homebrew/bin/python3"
   claude_bin = "~/.local/bin/claude"
   claude_home = "~/.claude"
   obsidian_vault = "moose-factory"
   notifier = "/opt/homebrew/bin/terminal-notifier"
   refuse_hosts = ["sawtooth*", "lemhi*", "bitterroot*", "hoodoo*", "teton*"]

   # Optional. The analysis studies root, and PATH prefixes for the launchd tick
   # (launchd hands a job a minimal PATH; gh outside the usual prefixes needs this).
   # studies_dir = "~/research/studies"
   # path_extra = "/opt/local/bin"

   max_concurrent_sessions = 2
   max_builds_per_day = 3
   min_free_gb = 50
   stall_seconds = 1200
   nag_days = [14, 45]
   park_idle_days = 7
   triage_dirty = 10
   gh_cache_ttl = 300
   gh_limit = 50
   gh_parallel = 10
   subprocess_timeout = 25
   stale_ref_days = 14
   needs_you_cap = 5
   head_churn_budget = 520
   timeline_on_home = 5
   gallery_max_mb = 5
   gallery_thumbs = 3
   ```

4. Install the tick:

   ```sh
   zsh ~/projects/moose_stack/factory/install.sh
   ```

   The script writes `meta_repo` into the config file first, if the key is absent, so that the
   skill, the hook and the tick all resolve this checkout wherever it is.

   The script renders the plist from the template, boots out any older agent, bootstraps
   `com.moose-factory`, then waits for one tick and prints its verdict.

5. Open the vault in Obsidian. Point Obsidian at the `vault` directory. Keep the vault name equal
   to `obsidian_vault`, or an `obsidian://` link opens the wrong vault.

6. Check the machine:

   ```sh
   ~/projects/moose_stack/factory/factory config
   ~/projects/moose_stack/factory/factory doctor
   ```

   `config` prints the resolved values and their sources. `doctor` prints the same block, then the
   checks. Correct every FAIL line before you trust the board.

### What is per machine, and what is shared

| per machine | shared |
|---|---|
| the vault, and its git history | the code in `moose_stack/factory/` |
| `factory/state/` (the probe cache; delete it to repair) | the skills and the hooks in `moose_stack/.claude/` |
| `.factory/gates/`, `.factory/timeline/`, `Artifacts/` | the pull requests on GitHub |
| `~/.config/moose-factory/config.toml` | |
| `~/Library/Logs/moose-factory*`, the launchd agent | |
| the worktrees, and the Claude sessions in them | |

Every board lists every pull request authored by `@me`, on both machines. A feature worked on the
other Mac has no worktree and no gates here, so it appears here as a PR-only card. That is by
design: the pull request is the shared fact, and the card says what you can still act on from this
machine. Do not tear down, reset or dispatch a PR-only card from the machine that does not own its
worktree.

## The four axes

The model never conflates these four.

### Lane: monotonic pipeline position

| rank | lane | proved by | owner of the exit |
|---|---|---|---|
| 0 | idea | an `Ideas.md` line whose slug matches no worktree, branch or PR | max |
| 1 | scaffolded | the path appears in `git worktree list --porcelain` | max |
| 2 | blueprint-draft | `specs/blueprint.md` exists with a status | max |
| 3 | approved | `status: approved`, zero unticked clarifications, the work-plan JSON parses | max (gate) |
| 4 | building | `status: building`, or a live session whose cwd is at or under the worktree | agent |
| 5 | built | a `moose-build-*.json` with `status: GOAL_MET`, no older than `blueprint.md` | agent |
| 6 | shipped | an open PR with `isDraft: true` | max (gate) |
| 7 | pr-ready | an open PR with `isDraft: false` | reviewers |
| 8 | merged | a merged PR and no open PR | max (gate) |
| 9 | archived | no worktree and no PR | none |

`abandoned` and `closed-unmerged` are off-pipeline terminals. Max sets them with a reason.

There is no `reviewed` lane. `/moose-build` runs the clean-context review in the same run and
writes one record, so no on-disk signal separates built from reviewed. A review is a rescued
artifact plus a count, and `required > 0` raises `review-findings`.

**The clamp.** `lane = max(rank(derived), rank(last_seen))`. A lane moves backwards only for a
named cause: `NEEDS_DESIGN` in the build record, a PR closed unmerged, `invalid-blueprint` at
rank 2, `abandoned`, or `factory reset`. Every demotion appends a timeline line that names the
probe. Otherwise the stored lane holds and the card gets `signal-regression`.

**The debounce.** A lane move driven by a non-durable signal (a session row, a CI rollup) must
hold across two consecutive runs. A move driven by a durable artifact (a file, a PR number, a
commit sha) applies at once.

### Flags: wiped and rebuilt every run

A flag can never move a lane. CIVET colour, review decision and mergeability are flags
*because* they oscillate.

`ci-red`, `ci-pending`, `conflicting`, `changes-requested`, `review-findings`, `blocked`,
`stalled`, `build-stale`, `invalid-blueprint`, `view-stale`, `stale-pipeline`,
`pr-closed-unmerged`, `branch-mismatch`, `foreign-worktree`, `partial-ship`, `two-sessions`,
`handoff-stale`,
`lease-stale`, `marker-missing`, `probe-stale`, `signal-regression`, `burning`, `error`.

`mergeable: UNKNOWN` is unknown, not clean and not conflicting. GitHub computes mergeability
lazily and returns UNKNOWN on every merged or closed PR. The probe re-polls once, then records
`mergeable_unknown`, and the note says "not yet computed". Never set `conflicting` from it.

A rollup proves nothing about a head it was not computed for. Every repo state carries its
current sha, and a rollup whose `headRefOid` differs is discarded: no colour, no `conflicting`,
and one line in the note that says so.

### Posture: derived, stored nowhere, the grouping axis

| posture | rule |
|---|---|
| needs-you | a gate that is due now, or `review-findings`, `changes-requested`, `ci-red` or `conflicting` on an open PR, or `blocked`, `branch-mismatch`, `foreign-worktree`, `partial-ship`, `invalid-blueprint`, `marker-missing` |
| running | a live session, or lane `building` with a fresh pulse |
| ready | lane `built` with no findings and `ship` pending; or lane `approved` with the gate granted and nothing dispatched |
| waiting | an open PR with green or pending CI and no requested changes |
| parked | everything else below `shipped`, plus `stalled`. A `scaffolded` workspace is parked only after `park_idle_days` of silence |
| done | `merged`, `archived`, `abandoned`, `closed-unmerged` |

Order decides the board. Three precedences are load bearing. A live session outranks a gate, so
a burning build reads as running and not as "act today". Lane `built` with `ship` pending is
ready, not needs-you: it is one command away. A `scaffolded` workspace that has been quiet for
less than a week is needs-you, because it is work in flight, not backlog.

A gate is **due** only when the work it gates exists, and only in its own lane window:
`blueprint_approved` needs a `specs/blueprint.md` below lane `built`, `ship` needs a build,
`pr_ready` needs a green draft PR, `teardown` needs a merge. The highest window wins, so a gate
for finished work never masks the gate for the work in flight. A generated
`specs/blueprint.html` is a view, not a plan: there is nothing in it to approve.

Needs-you is capped at five rows. The rest become one `Backlog, triage once` line. The order is
`conflicting`, `ci-red`, `changes-requested`, `pr-closed-unmerged`, `review-findings`,
`blocked`, `branch-mismatch`, `foreign-worktree`, `partial-ship`, `stalled`, a due gate,
`invalid-blueprint`, `marker-missing`.

One qualification: `conflicting` and `ci-red` on a card with no checkout rank last. The facts
are true, and you cannot fix a CIVET context in a worktree you do not have, so a red
pull-request-only card never displaces a branch mismatch or a review from the table.

### Gates: four monotonic attributed records

`blueprint_approved`, `ship`, `pr_ready`, `teardown`, each `{state, when, by, via}` in
`.factory/gates/<feature>.json`. Three channels, all human and all durable: the `grant` verb, a
ticked box in the note's head block, and an observed GitHub fact (an open PR proves `ship`;
`isDraft: false` proves `pr_ready`). A gate never ungrants, so a double tick or an Obsidian
conflict copy is harmless. `pr_ready` is human-only and `/moose-ship` must never set it.

A blueprint file is not a channel. Any agent with `Edit` can write `status: approved` into
`specs/blueprint.md`, and a grant from that file would be recorded as yours. The file proves the
lane. Only your verb or your ticked box proves the gate.

A ticked box registers on the next run, because the renderer reads the boxes before it composes.
The worst case is a grant that is one tick late. It is never wrong.

## Identity

`<feature>` is one name in five places: the worktree directory under
`~/projects/moose-worktrees/`, the branch on the meta-repo and all three submodules, the PR head
branch, and the note basename. Pull requests join on the feature name and on every repository's
actual HEAD branch, so a legacy checkout still finds its PR.

A repository whose HEAD is not `<feature>` raises `branch-mismatch`. A worktree outside
the configured worktree root raises `foreign-worktree`. Such a checkout is torn down by hand.
No script removes a worktree.

## Determinism

Delete `Home.md`, `Board.html`, `Features/*.md` and `Studies/*.md`, run `factory board`, and the
files come back byte-identical. The test is in the vault's `CLAUDE.md`.

Three rules make that true.

1. No generated file reads the clock. Every stamp is a **content stamp**: `snapshot.Store.stamp`
   returns the stored time when the content digest is unchanged. `.factory/last-sync.json`
   carries the wall-clock truth and is gitignored.
2. No generated file prints an age in days. It prints the date. An age would change daily with
   no change in the facts.
3. No generated file prints a pid. A pid is wall-clock truth: the Elsewhere docs-server line names
   the scope and the port, which survive a restart, and `factory doctor` knows the pid. Printing
   one made `Home.md` differ between two boards eight seconds apart, so the tick committed on
   nearly every run.
4. No generated file prints a moving "as of". A healthy GitHub payload is bounded by the cache
   TTL, so the masthead prints the bound, which is a constant. The session stamp comes from the
   newest file in `~/.claude/sessions/`, so it moves only when a session does. Only an unknown
   probe prints a timestamp, and that one is frozen while the probe is down, which is when the
   reader needs it. A clock-derived stamp is rule 3 again in a different sentence: it rewrote
   `Home.md` on every cache refresh.

`Features.base` is the exception, and deliberately: `render.write_base` writes it once when absent
and **never** overwrites it, because Obsidian owns it afterwards. Measured on this vault, Obsidian
rewrote the seeded `groupBy` scalar into a mapping and added a `columnSize` for a column Max had
dragged. Neither is recomputable. The seed is therefore written in the shape Obsidian normalises to,
so a fresh vault gives it no reason to rewrite; delete it and you get a working seed back, not the
same bytes.

The seed's `Board` view is a `cards` view grouped by `posture`, which is the native fallback for
`Board.html`. Obsidian 1.13.7 registers `table`, `cards` and `list`; it serializes a `groupBy`
property without the `note.` prefix, so the seed is written that way and Obsidian has no reason to
rewrite it. The `Needs you` and `Open PRs` views stay tables.

## One writer per thing

Two writers with different overwrite rules is the defect class this package keeps closing. The
current assignments, each with the duplicate that was removed:

| thing | the one writer | what was removed |
|---|---|---|
| `Artifacts/` | `tool/ext_artifacts.py` | `probe.rescue_build`, which overwrote an archived record under the same label; `probe.rescue_review` now only lists |
| `## Since yesterday`, `## Elsewhere` | `tool/ext_artifacts.py` | core's own blocks in `compose_home`, which rendered the heading twice |
| `Studies/*.md` | `tool/ext_studies.py`, through the `outputs` hook | a write as a side effect of `home_sections` |
| the `.tmp` of every state write | `config.write_text_atomic`, a unique `mkstemp` name | the shared `<name>.tmp`, which made two concurrent boards collide in `os.replace` |
| the pipeline doctor row | `tool/ext_refresh.py` | core's `no worktree has a frozen pipeline`, a third row about the same nine worktrees |
| `Board.html` | `tool/ext_board_html.py`, through the `outputs` hook | nothing: the page is new, and it reuses `render.atomic_write`, `render.guard_path` and `snapshot.Store.stamp` rather than copying them |
| `Artifacts/<feature>/handoff.md` | `tool/ext_handoff.py`, in `collect` | nothing: the skills write the worktree copy and this extension only rescues it |
| `Gallery/<feature>` | `tool/ext_gallery.py`, in `collect` | nothing: the symlink is new, and `Artifacts/<feature>/gallery/` is written only by `factory teardown`, through `ext_gallery.preserve` |

A note has **two** human regions, not one: the `## Notes` section between `head:end` and
`body:begin`, and the tail after `body:end`. A cursor at the end of the file lands in the tail,
so both are preserved byte for byte. Keeping only the first deleted an appended paragraph with
all four markers intact, so the marker refusal never fired and nothing was logged.

## Unknown is a third value

Every probe returns `(value, ok)`. On `ok=False` the projector carries the last snapshot value
forward, sets `probe-stale`, and says so in the masthead. Only a successful probe that says
"absent" may demote anything. A failed probe can never register as a manifest change; that exact
bug caused phantom `/digest` runs in the Work vault on 2026-09-10.

Unknown means the sessions directory is unreadable, a file does not parse, or `ps` is
unavailable. A daemon that is down is **not** unknown.

Three mechanics make the rule hold, and each closed a hole where unknown read as absence.

- `_ps_lstart` has three outcomes: a stamp, "no such process" for rc 1 with no output, and
  unknown for a timeout, a missing binary or a fork failure. Two outcomes made a live session
  read as gone, which emptied the Running table and let `factory start` double-book a workspace.
- `snapshot.Store.CARRY` maps each probe name to the observation keys it owns. A probe's name is
  not always its key: `github` fills `prs`, `du` fills `reclaimable_kb`, `sessions` fills both
  the list and the singular row. Comparing names against keys carried nothing forward for the
  two most volatile facts on the board.
- An unknown *enumeration* re-creates its cards from the last good snapshot. A failed
  `git worktree list` is not proof that nine worktrees were deleted, so `probe._recover` brings
  those cards back and the masthead names them.

A failed GitHub pass is never cached. One repo answering 504 keeps that repo's last good list,
so its cards stay on the board, and the round still reports unknown. `--offline` serves a cache
past its TTL as carried forward, not as current.

## GitHub, two passes, both parallel

Pass A is three thin `gh pr list --author @me --state all --limit 50` calls at once. Pass B is
one `gh pr view` per open PR, in parallel. Both are cached in `state/gh-cache.json` for 300
seconds. Always pass `--author`, always cap `--limit` at 50: the one-shot full-field call with
`statusCheckRollup` and no author filter returns HTTP 504 on idaholab/moose, reproducibly.

## Extension contract

Extensions are single files `tool/ext_<name>.py`, auto-discovered by `tool/cli.py` and
`tool/render.py` via `pkgutil` over the `tool` package, sorted by name. An extension may export
any of:

```python
VERBS: dict[str, Callable[[list[str], Ctx], int]]      # new CLI verbs, e.g. {"start": run_start}
HELP: dict[str, str]                                    # one line per verb
NO_CTX_VERBS: tuple[str, ...]                           # verbs that need no probe round: they get a bare Ctx
def card_flags(card, obs, ctx) -> list[str]             # extra flags for one card, applied after derive
def home_sections(ctx) -> list[tuple[str, str, int]]    # (title, markdown, order) appended to Home.md after the posture groups
def note_sections(card, ctx) -> list[tuple[str, str, int]]  # (title, markdown, order) inside the note's generated body
def doctor_checks(ctx) -> list[tuple[str, bool, str]]   # (name, ok, hint)
def collect(ctx) -> None                                # run during the probe round, before derive; may write only under state/ and the vault's durable dirs
def outputs(ctx) -> dict                                # write this extension's generated files; {"counts": {...}, "refused": [...]}
```

`outputs` is called by `render.sync` before `Features.base` and `Home.md`, so an extension's own
generated notes are written by the renderer rather than as a side effect of `home_sections`, and a
refused note reaches the board's exit code. `tool/ext_studies.py` uses it for `Studies/<id>.md`.

`NO_CTX_VERBS` exists because a probe round costs about 6.5 s. A verb that only reads a log should
not pay it: `tick-status` declares itself and gets a context with paths, state and the clock only.

`Ctx` (`tool/model.py`) carries: `config` (paths, caps, thresholds), `obs` (the probe snapshot
for every card id), `cards` (list of `FeatureCard` after derive), `state_dir`, `vault_dir`, `now`
(ISO string passed in, never computed inside derive), and helpers:
`ctx.timeline.append(feature, event: dict)`, `ctx.gates.get(feature)`,
`ctx.state.read(feature)` / `write(feature, dict)`, `ctx.log(msg)`.

`FeatureCard` fields (`tool/model.py`): `id`, `worktree` (path or None), `lane`, `lane_rank`,
`flags`, `posture`, `next_action` (verb, command, why), `prs` (list of `{repo, number, state,
isDraft, url, ci, mergeable, reviewDecision, updatedAt}`), `blueprint` (dict or None), `build`
(newest record dict or None), `session` (dict or None), `gates` (dict), `provenance`, `repos`
(dict repo -> `{branch, pushed, ahead, dirty, fetched}`), `errors` (list), and `extra` (a dict the
extensions publish per-card values into; core reads nothing from it).

Core verbs: `board`, `status [<feature>]`, `next <feature>`, `set <feature> key=value`,
`abandon <feature> "<reason>"`, `grant <feature> <gate>`, `doctor`, `commit`,
`dump-obs <feature>`, `version`. Every verb accepts
`--dry-run` where it writes.

An extension must not edit any core file. A needed core change is a request, not a patch.

## Dispatch and the lease

`factory start <feature>` is the only dispatching verb and nothing dispatches itself. It takes an
atomic `mkdir` lease at `<worktree>/.factory-lease` holding `{bg_id, session_id, pid, host,
acquired}`, then runs `claude --bg --name <feature> "<prompt>"` with cwd at the workspace, confirms
the short id against `~/.claude/sessions/*.json`, records `{bg_id, session_id, started, prompt}` in
`state/<feature>.json`, appends one timeline line and runs the board.

A lease whose owner is gone is **reported** as `lease-stale`, never stolen: auto-stealing is how two
builders end up in one tree, and two builds on one workspace is the single destructive failure in
this design. Only `factory release`, interactively, removes one.

`start` refuses for: a held lease, an unknown session probe, any live session at or under the
worktree, `foreign-worktree`, `branch-mismatch`, no card, a lane below `approved`, two working
background sessions, three launches in 24 h for the card, and under 50 GB free. `--force` overrides
the lane but never the lease.

`factory rm` does not exist and no factory code path ever passes `rm` to the claude binary: it can
remove a worktree. A test asserts that on the source.

## Teardown and refresh-pipeline

`factory teardown <feature>` prints by default. `--yes` runs it, and additionally requires an
interactive terminal: it refuses when `FACTORY_FROM_EVENT`, `FACTORY_TICK`, `FACTORY_NONINTERACTIVE`
or `CLAUDE_HOOK` is set, so it can never run from the launchd tick or a hook. The hard refusals are
the `teardown` gate, an OPEN PR, a live session in the worktree and a live lease; dirty trees and
unpushed commits refuse until `--force`.

The conda env is removed only when `<worktree>/specs/.factory-env` says `env_reused: false`. Envs
are shared per moose-dev pin (`moose-8.19` serves every worktree on that pin), so with no such file
the env is left alone. No worktree carries that file yet: `/new-feature` writes it from now on.

No script ever runs `rm -rf` on a worktree. If the directory survives `git worktree remove`, Max
inspects it and removes it by hand.

`factory archive <feature>` `git mv`s the note into `Archive/` and refuses while the worktree or an
open PR survives. Teardown and archive stay two verbs, so the note survives a partial teardown.

`factory refresh-pipeline <feature>` hashes `moose_stack/.claude/{skills,agents,hooks,settings.json}`
against the worktree's frozen copy and prints a per-entry table. Copying in needs `--confirm`, a
terminal and the typed feature name. It never deletes a worktree-only file, ignores
`settings.local.json` and `cache/`, and refuses a foreign checkout.

Reclaimable bytes come from `factory board --du` once and are then cached in
`state/<feature>.json`, which is what keeps the note's Teardown section byte-identical on a rebuild.
A run without `--du` reads that cache, so the note and the next-action why never disagree.

## Artifacts are rescued, never rewritten

`tool/ext_artifacts.py` is the single writer of `Artifacts/`. Every
`<worktree>/.claude/cache/moose-build-*.json` is copied into `Artifacts/<feature>/`, and so is
exactly `/tmp/moose-review-<feature>.md`, and only with a `/tmp/moose-review-<feature>-meta.json`
whose `.root` resolves under that feature's worktree. Never glob `/tmp/moose-review-*`: that
namespace is shared, `/moose-pr-review` writes `fc-syn`, `fc-test` and `pr-5` families there today,
and `*-issues.md` is a linked-issue digest, not a review.

The rescue is idempotent and never overwrites a differing copy: that one gets a numbered suffix. The
probe reads the rescued copy once the original is gone, which is the whole point, because
`.claude/cache/` is gitignored and dies with the worktree and `/tmp` is purged at boot.

## The handoff

`<worktree>/specs/handoff.md` is what one session leaves for the next. It carries seven sections:
`## State` and `## Next` and `## Map` are rewritten every session; `## Do not repeat`, `## Decisions`,
`## Gotchas` and `## Sessions` are append only. The skills write it: `/handoff` at any time,
`/moose-blueprint` at write time, `/moose-build` in its final report, `/moose-ship` after the PR, and
`moose-feature-loop` hands `/moose-build` a `HANDOFF:` block on STALLED or BLOCKED. The template and
the rules live in `moose_stack/.claude/skills/handoff/references/`.
`.claude/hooks/session-context.sh` prints State and Next at the start of every session in the
worktree, capped at 40 lines.

`tool/ext_handoff.py` reads that file and never writes it. `collect` copies the worktree's copy into
`Artifacts/<feature>/handoff.md` on every board run. The copy is idempotent: identical bytes are
never copied twice, and `shutil.copy2` carries the mtime over, so the next run reports `same`.

This rescue overwrites, and it is the one rescue in the package that does not give a differing copy a
numbered suffix. A build record is one immutable record per label, so a suffix protects it. The
handoff is a single living document that is rewritten every session and whose append-only sections
only grow, so the newest copy supersedes the one before it, and a suffix would bury
`Artifacts/<feature>/` under a hundred near-identical files in a week.

The feature note gets `## Handoff` (order 40, between `## Session` and `## Build and review`): the
State paragraph, the Next list capped at six steps, and the last three Do-not-repeat lines. The
section reads the worktree copy while it exists and the rescued copy once the worktree is gone.

Two disciplines on that projection, each a closed hole.

1. The Next steps print as **plain bullets**. A `- [ ]` in the generated body is a trap: the body is
   recomposed on every board run, so a tick Max makes in Obsidian is erased within 120 s, and
   `probe.note` reads ticked boxes out of the head block only, so it is never read back either. Same
   rule as the two analysis gates in `## Studies`.
2. Every projected string passes through `_clip`, which **escapes `<!--`**. A handoff that names one
   of `probe.MARKERS` in prose ("the board refused the note because it lost its
   `<!-- factory:body:end -->` marker") would otherwise plant a second fence inside the generated
   body. `render.compose_note` splits the existing note at the *first* `body:end`, so the real
   remainder would be preserved as a human tail and re-appended after the fresh body: the note grew
   by its own length on every run, with all four markers present, nothing refused and nothing logged.
   The escape is idempotent, so the note still rebuilds byte for byte.

`rescue` logs every outcome, `too-large` and a failed `stat` included: the worktree copy is the only
other copy and `factory teardown` removes it, so a silent miss loses the record. `factory doctor`
carries three handoff rows: the template is present, every handoff keeps its seven headings, and
every handoff is rescued into `Artifacts/`.

The flag `handoff-stale` fires when `specs/blueprint.md` or the newest build record is more than two
days newer than `handoff.md`. It compares three mtimes against each other and never against the
clock, so a deleted note rebuilds byte for byte. It runs no git command in a worktree. Extension
flags are applied after `derive`, so this flag can never move a lane or a posture.

The first `## Next` step is published as `handoff_next`, beside `handoff_state`, `handoff_updated`,
`handoff_sessions` and `handoff_stale` (the module's `PUBLISHED` tuple), in
`ctx.meta["handoff"][<feature>]` and in `ctx.obs[<feature>]["handoff"]`. Read it through
`ext_handoff.handoff_next(ctx, card_or_feature)`, which falls back to a direct read when a verb runs
without a probe round. `card_flags` copies the same five keys into `card.extra`.

## The gallery

`<worktree>/specs/gallery/` holds anything a session makes for a human to look at: a PNG, an SVG, a
GIF, a small MP4, a CSV, a small HTML page. Large outputs stay where the example wrote them; an
exodus file and a checkpoint never belong here.

`specs/gallery/gallery.md` is the figure page, and it is the source of truth. The `moose-figure`
agent writes it. It has this format:

```
# Gallery: <feature>
## Figure 1. <title>
![](<file.png>)
<one or two sentences: what it shows>
Look at: <one sentence>
Source: <input, test or gold path>; rendered with <tool>.
```

Write one `## ` section per figure. The heading text is the figure title. The first image embed in
the section names the figure file. Both spellings work: `![](file)` and `![[file]]`. The page sets
the order of the figures.

`captions.md` is retired. The projector ignores it and never reads it. A gallery filename starts
with a letter or a digit and carries only letters, digits, dot, underscore, space and hyphen, at
most 96 characters; the projector spells it into a wikilink, an `img src` and a path, so it refuses
anything else. `specs/gallery/` is gitignored in the meta-repo, and `/new-feature` also writes the
pattern into the meta-repo's `info/exclude`, so a worktree branched from a commit older than that
`.gitignore` line is covered too and a figure never reaches a pull request by accident.

`tool/ext_gallery.py` reads that directory and never writes it. `collect` records the listing in
`ctx.obs[<feature>]["gallery"]`: the figures in page order first, then every eligible file the page
does not mention. It also maintains `<vault>/Gallery/<feature>` as a **symlink** into the
worktree folder. It creates the link, repairs a link that points at the wrong place, and removes a
dangling link whose worktree is gone. A feature that loses its card entirely is swept separately,
after the per-card loop: the loop only reaches features the probe still sees, so without the sweep
the one link the removal rule exists for would be the one link nothing revisits. `Artifacts/<feature>/gallery/` is the one exception: when the
worktree is gone and that rescued copy exists, the link points there instead. A real directory at
`Gallery/<feature>` is never touched; the note says so and a doctor row FAILs. `Gallery/` is
gitignored in the vault, so the board's git history stays text.

The cap is `gallery_max_mb`, five by default, per file. A bigger file is named on the note, is never
linked and is never copied. A zero byte file is refused the same way: an interrupted render leaves
the file and its page section behind, and publishing it would embed a broken image under a title
that claims it shows something. Two more files are refused for safety: a symlink inside the gallery,
which the projector will not follow, and a name no wikilink can spell. Each refusal prints one line
on the note, so nothing disappears in silence, and every name on those lines is escaped on the way
out: a filename is chosen by a session, it reaches the note before any validator has passed it, and
an unescaped one that spelled a body fence would make the note grow by its own length every run.

A gallery directory that resolves outside its worktree is refused whole, and the note says which
directory was refused and why rather than offering the "there is none, make one" placeholder.

The feature note gets `## Gallery` (order 45, between `## Handoff` and `## Build and review`). The
section prints one header line, which says how many files were read, their size, which directory
they came from and where they are linked. Below it the note transcludes the page itself, with
`![[Gallery/<feature>/gallery.md]]`. The page is the one writer of the order, the titles and the
prose, so the note never states a second, staler version of what a figure shows. Obsidian follows
the symlink, so the transclusion and every embed inside it resolve with no copy anywhere.

Without a `gallery.md` the note falls back to a plain listing: each image embeds as
`![[Gallery/<feature>/<file>]]` with its filename on the line below, each other file is a link, and
one muted line says that a figure page would be shown there instead. The skipped-file lines print in
both forms.

`Board.html` shows up to `gallery_thumbs` image thumbnails on a card, under the next move, with the
**relative** `src` `Gallery/<feature>/<file>`. The thumbnails are in page order and each one carries
its figure heading as the `alt` and the `title`. A file the page does not mention comes after the
ones it does, labelled by its filename. The relative form is correct, and it is the only form
that works. The HTML Reader plugin prepends `<base href="<vault.getResourcePath(Board.html)>">`
before it hands the page to its iframe, and Obsidian registers `app:` as a standard scheme, so
Chromium resolves the relative path against the vault directory and the handler serves the file
through the symlink. Two of the plugin's modes would still refuse the image: HighRestricted sets
`img-src 'self' data:` and TextMode sets `img-src 'none'`. Neither is the default, and a `file://`
`src` would not rescue either one.

`factory teardown` makes the one copy that is ever made. Before it removes anything, it copies the
capped gallery into `Artifacts/<feature>/gallery/` and repoints the symlink at the copy. The copy is
idempotent: identical bytes report `same`, and a differing figure gets a numbered suffix, so a
rescued figure is never overwritten. The index files are the exception, because an index is not an
exhibit: `gallery.md` always lands at `gallery.md`, a differing older one is moved aside to
`gallery-<n>.md` to keep its text, and every embed on the page is rewritten to the name its figure
landed under. A suffixed index would otherwise sit unread beside the stale one, and every rescued
figure would carry the title of whatever it replaced. A retired `captions.md` is rescued by the same
rule, because teardown is the last moment the worktree copy exists; no `gallery*.md` and no
`captions*.md` is ever listed as a gallery file. `factory archive` is unchanged. `factory doctor` carries two gallery
rows: every `Gallery/<feature>` is a link and not a directory, and no link dangles.

The pipeline that fills the folder runs beside the build. A blueprint may carry an optional
`## Showcase` section that names the example to build and one bullet per figure. It produces a
work-plan unit of kind `showcase` with agent `moose-figure`, whose `files` are the gallery outputs.
`/moose-build` and `moose-feature-loop` dispatch that unit like any other, and its evidence is that
the files exist and that `gallery.md` names them. **A showcase unit gates nothing.** It is not a
criterion, it cannot block C1 to C6, and a figure that fails to render is a `SHOWCASE:` line, not a
build failure.

`moose-figure` renders the figures for one feature and writes `gallery.md`. It runs the
example only when the output is missing, and only through an app binary that is already built; it
never builds. Exodus rendering has three paths, tried in order: `moose/python/chigger`, which needs
`vtk` and therefore does not import in the pinned conda env today; ParaView's
`pvpython --force-offscreen-rendering`; and `scipy.io.netcdf_file` with matplotlib on the Agg
backend, which needs no VTK and draws 2D meshes only. The agent probes chigger first every run, so
it switches back to the MOOSE-native renderer on the day `vtk` joins the env pin, with no edit.

## Board.html

The page is one generated file, written by `outputs(ctx)` like a study note. It reads nothing the
board has not already derived. Three rules keep it honest. It prints a content stamp, never the
clock, never an age, never a pid. It escapes every string through one function, because a
pull-request title is arbitrary text. It allows three URL schemes only: `obsidian://`, `file://` and
`https://github.com/`; any other scheme renders as plain text.

The six columns are `model.POSTURE` in order, so the page and `Home.md` can never disagree. The
needs-you column is sorted by `FeatureCard.priority_key` and is not capped: a column scrolls, a table
does not. Every other column sorts by id. Each study is one compact card in the column its posture
maps to. The done column is compact.

Flag colour is by severity, not by flag. Critical: `ci-red`, `conflicting`, `blocked`, `stalled`,
`changes-requested`, `review-findings`, `foreign-worktree`, `branch-mismatch`. Warning:
`probe-stale`, `lease-stale`, `build-stale`, `view-stale`, `stale-pipeline`, `handoff-stale`.
Everything else is neutral, so a new flag renders as a plain chip instead of shouting.

The reclaimable size appears only when the teardown gate is due, which means the lane is `merged` or
`archived`, or the checkout is foreign. The note's Teardown section is wider on purpose: the note is
where you read one card, and the board is where you decide today. Both print the same number, from
`ext_teardown.cached_kb`.

Three more rules, each one a defect that was live.

- **Nothing remote.** No webfont, no script, no image: the stacks are `Bricolage Grotesque` then
  `Avenir Next`, `Public Sans` then `Helvetica Neue`, `JetBrains Mono` then `SF Mono`, so a machine
  that has the first uses it and a machine offline loses nothing. Every other generated file in the
  vault is self-contained; the page Max opens on a plane is not the exception.
- **Per card, not per page.** Every row is rendered inside its own `try`, and a row that raises
  becomes a placeholder card that names itself plus one log line. The needs-you sort falls back to id
  order the same way. A note degrades per card in `render.sync`, and before this the page was the one
  all-or-nothing output: one odd-typed probe field on one card meant the whole kanban was not
  rewritten and the stale page stayed on disk unannounced. The hostile fields are coerced with `str`
  rather than trusted: a `sessionId`, a CI rollup and a flag all come from schemas this package does
  not own.
- **A refusal is reported, never re-raised.** `render.sync` catches `config.RefusedWrite` from an
  `outputs` hook, logs it and continues without counting it, so `outputs` returns
  `{"counts": {}, "refused": ["Board.html"]}` instead. That is what reaches exit code 2.

Three strings on a card are markdown a human wrote (the handoff's first Next step, a compact why, a
study's why), so they go through `esc_md`: escape first, then paired backticks become `<code>`. The
handoff template mandates a backticked command on every step, and raw backticks read as punctuation.
A PR title is cut on a word boundary with a visible `...`, because a silently cut title states a
title that does not exist. A PR-derived flag (`ci-red`, `conflicting`, `changes-requested`) is
dropped from the chips row whenever the PR row is on the same card: four red chips for two facts
dilute the colour that carries the severity.

`factory doctor` gains two rows: `Board.html` is in the vault, and the Obsidian HTML Reader plugin is
installed and listed in `community-plugins.json`. The plugin *code* is gitignored in the vault and is
installed through Obsidian's own community-plugin browser: a vendored, minified `main.js` runs inside
Obsidian with full filesystem access, and a copy with no recorded upstream release or checksum cannot
be told from a tampered one. Obsidian keeps the Restricted-mode switch in its own local storage, so
the hint says to turn it off by hand once.

## Studies

`tool/ext_studies.py` reads `analysis/studies/*/card.yaml` and nothing else, maps `StudyState` onto
posture, and renders `Studies/<id>.md`. It re-implements that schema rather than importing the
analysis package, so the board does not fail when the toolkit moves. The analysis toolkit stays the
only writer of a card, so a study row is exactly as fresh as Max's last reconcile, and the row
prints the card's own stamp plus a reconcile hint past a day. The two analysis gates are printed as
words, never as checkboxes: a tick the factory never reads back would be a trap.

## The tick

`factory/install.sh` installs two files: `~/.local/bin/moose-factory-tick.sh` and
`~/Library/LaunchAgents/com.moose-factory.plist`, rendered from
`factory/com.moose-factory.plist.in` (StartInterval 120, RunAtLoad,
ProcessType Background, NumberOfFiles 65536, no `MaterializeDatalessFiles`, because the vault is
outside iCloud). The tick never invokes Claude.

Each tick: hostname guard, `ulimit -n 65536`, an `mkdir` lock at
`~/Library/Logs/moose-factory.lock` with a pid file and stale takeover, a 300 s watchdog that kills
the board child with it, then `python -m tool.ext_tick check`. That check is the free gate: exit 0
means an input changed, 1 means nothing is new, and a failed probe records `"unknown"` and carries
the old value forward, so it can never count as a change. The board then runs only on a change, or
every tenth tick, or under `MOOSE_FACTORY_FORCE=1`; never twice in one tick, and never while
another `tool.cli board` is in flight. Then `python -m tool.ext_tick notify` raises one banner per
card that newly entered needs-you, read out of the note frontmatter rather than from a second probe
round; then `factory commit` if the vault is dirty; then one line to
`~/Library/Logs/moose-factory.last-check`.

`commit` refuses while `Home.md` is absent. A board run always recreates it, so an absent
`Home.md` means the view is half built, and a commit then would record the deletion of every
generated note under a message that reads like an ordinary board commit.

```sh
zsh factory/install.sh              # install or re-install and bootstrap
zsh factory/install.sh --status     # what is installed, and the last verdict
zsh factory/install.sh --uninstall  # bootout and remove both files; the logs are kept
factory tick-status                 # the same, without a probe round
factory doctor                      # six tick checks: loaded, executable, matching, lock, last check, notifier
```

Every step of the tick sets `PHASE`, and the watchdog's log line names the phase and the elapsed
seconds it killed. Without that a 300 s kill is unexplainable after the fact, because every step is
sub-second on a quiet machine.

Banners go through the `notifier` binary from the config (`/opt/homebrew/bin/terminal-notifier` by
default, `""` for the fallback) when macOS allows it, because only it carries
`-open obsidian://open?vault=<obsidian_vault>&file=Features%2F<id>`. It is installed but not
authorized on this machine (rc 3, "Notifications are not allowed for this application"), so banners
fall back to `osascript`, which delivers and loses only the click-through. One manual grant in
System Settings restores it with no code change.

## Teardown recipe

Remove the whole system, in this order. Nothing here touches a worktree.

```sh
# 1. Stop the loop.
launchctl bootout gui/$(id -u)/com.moose-factory 2>/dev/null
rm -f ~/Library/LaunchAgents/com.moose-factory.plist
rm -f ~/.local/bin/moose-factory-tick.sh
rm -f ~/Library/Logs/moose-factory*

# 2. Drop the cache. Costs one probe round to rebuild; nothing is lost.
rm -rf "$(factory config --get meta_repo)"/factory/state

# 3. Keep the data. Gates, timeline and artifacts are inputs no run can recompute.
cd ~/projects/moose-factory && git bundle create ~/moose-factory-backup.bundle --all

# 4. Drop the generated view only.
rm -f ~/projects/moose-factory/Home.md ~/projects/moose-factory/Board.html \
      ~/projects/moose-factory/Features/*.md ~/projects/moose-factory/Studies/*.md

# 5. Drop the vault, once the bundle is somewhere safe.
#    Obsidian prunes the registration at its next launch.
rm -rf ~/projects/moose-factory

# 6. Drop the code, and this machine's settings.
rm -rf "$(factory config --get meta_repo)"/factory
rm -rf ~/.config/moose-factory
```

A worktree is never removed by a script. `factory teardown <feature>` prints the recipe and
only runs it with `--yes`, by hand, never from a tick or a hook.

## Two rules that are easy to break

1. `$ANALYSIS_VAULT` must never point at `~/projects/moose-factory`. `analysis/tool/vault.py`
   has its own `write_home` and would fight `render.py` for `Home.md`.
2. The factory never runs `analysis reconcile` and never writes a study card. A study row is
   exactly as fresh as Max's last reconcile, so it prints the card's own stamp.
