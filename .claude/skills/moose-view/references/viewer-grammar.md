# exodus-view grammar

Server: `scripts/exodus-view.py` (numpy + scipy, port 8765, binds 127.0.0.1). Page:
`scripts/exodus-view/viewer.html`. Report elements: `scripts/exodus-view/embed.js`. Headless
render: `scripts/exodus-view/snap.sh`. A URL is `http://127.0.0.1:8765/?file=<abs path>&...`.
Percent-encode: `#` in colours is `%23`, a space in a path is `%20`.

## URL parameters

| Parameter | Values | Meaning |
|---|---|---|
| `file` | absolute path | the Exodus file; the server opens it on first use |
| `var` | variable name, `block`, `mag:<prefix>` | colour field. `block` colours by block with a legend; `mag:disp` is the magnitude of `disp_x/y/z` |
| `step` | `N` or `last` | time step index, `last` by default |
| `cmap` | `viridis` `plasma` `inferno` `coolwarm` `turbo` `jet` `gray` | colour map |
| `range` | `step` `all` `min,max` | colour range: this step (default), over all steps, or fixed |
| `warp` | `1` | deform by a displacement field |
| `wprefix` | prefix | which vector to warp with; default the first of the meta's `displacements`, `disp` first when present |
| `wscale` | number or `auto` | warp factor; `auto` makes the peak displacement a tenth of the bounding box diagonal |
| `blocks` | names or ids, comma list | show only these blocks |
| `ss`, `ns` | names or ids, comma list | side sets drawn as coloured faces or edges, node sets as points |
| `cut` | `<x|y|z>:<pos>:<+|->` | keep elements whose centroid is on that side of the plane; interior element values become visible |
| `edges` | `0` | hide element edges |
| `opacity` | 0.05 to 1 | surface opacity |
| `up` | `z` or `y` | up axis; `z` for 3D and `y` for 2D by default |
| `view` | `iso` `top` `bottom` `front` `back` `left` `right` | named camera direction, in the up-axis frame |
| `cam` | `px,py,pz,tx,ty,tz` | exact camera; overrides `view`. The viewer writes it back into the URL as the user orbits |
| `bg` | `%23ffffff` `%23e9ecf0` `%23202428` | background |
| `lock2d` | `1` or `0` | left drag pans instead of orbits; on for 2D meshes |
| `probe` | `<node>[,<elem>]` | open the probe panel on that node and element |
| `embed` | `1` | no sidebar; only `controls=` rows appear in a bottom bar, plus a "full viewer" link |
| `controls` | `time` `warp` `var` `cut` `probe` `all` | which controls the embed shows (rotate is always on) |
| `snap` | name | save `<name>.png` and `<name>.json` through the server once the first frame is drawn |
| `snapdir` | absolute dir | where `snap` writes; default the server's `--snap-dir` |

The URL holds the whole view state, so a URL the user pastes back says exactly what they see.

## Report elements

```html
<script src="http://127.0.0.1:8765/embed.js"></script>
<meta name="exo-root" content="<worktree root>">   <!-- relative file= paths resolve here -->

<exo-view file="..." var="..." warp wscale="auto" step="last" view="iso"
          controls="time" height="360" png="<name>-<slug>.png">caption html</exo-view>
<exo-input file="<input.i>" [open]></exo-input>
<exo-globals file="<out.e>" step="last|all|N"></exo-globals>
```

Every `<exo-view>` attribute except `height`, `png`, and `controls` is a URL parameter above; a
bare `warp` or `probe` attribute means `1`. The element shows the live frame when the server
answers and the `png` otherwise. The `png` path is relative to the report.

## Read-side API

| Call | Returns |
|---|---|
| `/api/meta?file=` | dim, node and element counts, bbox, times, blocks (id, name, type, nelem), sidesets, nodesets, nodal, elemental, globals, displacements |
| `/api/range?file=&name=` | min and max of a field over all steps |
| `/api/probe?file=&node=&elem=&step=` | every variable at one node and one element |
| `/api/globals?file=` | postprocessor names, times, and values per step |

## snap.sh

    bash scripts/exodus-view/snap.sh <name> <dir> "<url>"

Appends `snap=<name>&snapdir=<dir>`, loads the URL in a headless Chromium (`$EXODUS_VIEW_CHROME`,
the Playwright cache, Google Chrome, or chromium on PATH), and prints the PNG path. The PNG is the
frame plus the colour bar plus a caption line naming the file, field, step, time, and warp. The
JSON beside it holds the state and any probe result.

## Examples

    ?file=F&embed=1                                   the mesh, rotate only
    ?file=F&var=block&embed=1                          blocks with a legend
    ?file=F&var=mag:disp&warp=1&wscale=auto&embed=1&controls=time
    ?file=F&var=stress_xx&cut=y:0.5:-&cmap=coolwarm&embed=1&controls=cut
    ?file=F&blocks=bottom_block,secondary_lower&var=mortar_normal_lm&view=top&edges=0&embed=1
    ?file=F&ss=left,right&embed=1                      two boundaries on the mesh
    ?file=F&var=u&probe=42&embed=1                     one nodal value

Limits: NetCDF-4 (HDF5) Exodus files do not open; higher-order elements draw corner nodes only;
the cut is element-wise, there is no slice or isosurface; 1D elements draw as 1 px lines.
