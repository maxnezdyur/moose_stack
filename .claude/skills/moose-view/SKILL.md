---
name: moose-view
description: Shows a MOOSE Exodus result in the browser through scripts/exodus-view.py as one embedded figure (mesh, blocks, a field, the deformed shape, a cut, a boundary), a PNG in chat, or an HTML report with prose and figures in specs/gallery/. Use when the user wants to see a mesh, a field, the deformed shape, or the results of an input, wants a picture in chat, or wants the results written up as a report; or /moose-view <file.e|input.i> [look|snap|report] [what to show].
argument-hint: "<file.e | input.i> [look | snap | report] [what to show]"
effort: high
---

# moose-view

Three verbs on one machinery. `look` opens one figure in a browser tab and writes nothing.
`snap` renders one figure to a PNG and shows it in chat. `report` writes
`specs/gallery/<name>.html` with prose and figures, plus a section per figure in `gallery.md`.
Default to `look` when the user is at the screen, `snap` in a background session or when they
ask for a picture, `report` when they ask to write something up. This is a strategic glance, not
a ParaView replacement: a figure shows one thing and carries only the controls that thing needs.

## Server

    bash scripts/conda-run.sh -C moose -- python scripts/exodus-view.py [<file.e>] [--open]

Run it from the meta-repo root or the worktree root, every time: one server per machine on port
8765, and a second launch reuses the running one and prints its URL. It needs only numpy and
scipy, opens any file through `?file=<abs path>`, and rereads a file that changed on disk. On an
INL HPC host start it on the login node and give the user the
`ssh -L 8765:127.0.0.1:8765 <host>` line. The viewer itself is not edited inside this skill; a
missing feature is a follow-up in the reply.

## Find the file

An `.e` path is used as given. An `.i` path resolves through its `[Outputs]` block: `file_base`
names `<file_base>.e`, otherwise the file is `<stem>_out.e` beside the input; the test spec's
`exodiff` line names the same file. For a test input whose output is absent, `gold/<file>` is
the expected result and serves in its place; say which one was shown. Otherwise run the input
with the built binary of its scope from the scope root, never build one, and never write results
into a `gold/` directory. A run over two minutes goes through `run_in_background`.

| Scope | Root | Binary |
|---|---|---|
| framework test | `moose/test` | `moose_test-opt` |
| module `<m>` | `moose/modules/<m>` | `<m>-opt` |
| cross-module | `moose/modules/combined` | `combined-opt` |
| blackbear | `blackbear` | `blackbear-opt` |
| isopod | `isopod` | `isopod-opt` |

## Read before composing

    curl -s "http://127.0.0.1:8765/api/meta?file=<abs path>"

lists the variables, blocks, side sets, node sets, times, and displacement prefixes. Every name
in a figure spec comes from that list: an unknown variable falls back to a plain mesh and an
unknown block name hides everything, with no error you will see.

## Request to spec

The parameter grammar is `references/viewer-grammar.md`. The mapping that matters:

| The user asks for | Spec |
|---|---|
| the mesh | no `var`, edges on; `view=iso` for 3D, top and pan-locked for 2D (the default) |
| the blocks | `var=block` |
| a field, at the end | `var=<name>&step=last` |
| how it evolves | add `controls=time` |
| displacement, the deformed shape | `var=mag:<prefix>&warp=1&wscale=auto`, a component when they name one |
| inside | `cut=<axis>:<pos>:<sign>` at the plane of interest, `controls=cut` |
| a boundary | `ss=<name>` on the mesh; a node set is `ns=<name>` |
| one block or surface | `blocks=<names>`; mortar and other lower-d surfaces read best with `view=top` |
| a value at a point | `probe=<node>[,<elem>]`, or `controls=probe` to let them click |
| a signed field | `cmap=coolwarm` |

One idea per figure: pick the view that shows it, hide what hides it, and leave everything else
default.

## look

Compose the URL with `embed=1` and the `controls=` the question needs, then `open "<url>"`.
Reply with one line saying what is on screen. The frame's "full viewer" link is the escape
hatch, so the full viewer opens only when the user asks to poke around.

## snap

    bash scripts/exodus-view/snap.sh <name> <dir> "<url without snap=>"

writes `<dir>/<name>.png` and `<name>.json` (the view state, including any probe values). Then
Read the PNG. A picture reaches the user only after it was looked at this session: a collapsed
colour range, an all-zero field, a cut that removed everything, or a mesh seen edge-on gets fixed
and rendered again first. Scratch snaps go to `$CLAUDE_JOB_DIR/tmp` when set, else
`/tmp/exodus-view`; report figures go beside the report.

## report

A report is `specs/gallery/<name>.html` in the worktree, `<name>` being the input stem unless
the user names it, built from `references/report-template.html`: title and lead, Mesh, Problem,
Results, and Postprocessors when the file has globals worth showing. The prose comes from the
input file: the mesh from `[Mesh]`, loads and constraints from `[BCs]`, `[Contact]`, or
`[Constraints]`, time from `[Executioner]`, materials only where they explain the result. Nothing
the input does not state. `<exo-input>` and `<exo-globals>` go in only when the user asks for the
listing or the table.

Three to six figures, each an `<exo-view>` with a `png=` fallback rendered through `snap.sh` into
the same directory, so the report still reads when the server is gone. Height follows the point:
a detail 260 px, the main result 380 px, two related fields side by side in a `grid2` div. Every
PNG is Read before the report is announced.

Figure files are `<name>-<slug>.png` and match `^[A-Za-z0-9][A-Za-z0-9._ -]{0,95}$`, because the
board refuses any other name. `gallery.md` (create it as `# Gallery: <name>` when absent) gets
one `## Figure N. <title>` section per figure in the figure agent's shape: the `![](<file.png>)`
line first, one or two sentences on what is in the picture, a `Look at:` line, and a `Source:`
line naming the input and `exodus-view`. Below the figures one line points at the report:
`Report: [<title>](<name>.html)`. A re-rendered figure rewrites its section rather than adding a
second one. Finish with `open specs/gallery/<name>.html`.

The one case to hand off is a report whose results still have to be computed by a long run:
spawn a general-purpose subagent with these steps and the exact run command, and stay with the
user.

## Reply

Say what is shown or written and where: the URL for look, the PNG for snap, the report path and
the gallery sections for report. Numbers only when they change what the user does next.
