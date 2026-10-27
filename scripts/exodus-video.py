#!/usr/bin/env python3
"""exodus-video: render an Exodus II result to an MP4 (and optionally a GIF) with ParaView.

Usage:
  exodus-video.py FILE.e OUT.mp4 [--var NAME] [--fps N] [--size WxH] [--view V]
                  [--range all|step|MIN,MAX] [--cmap NAME] [--warp [SCALE]] [--edges]
                  [--orbit DEG] [--max-frames N] [--hold S] [--no-clock] [--gif]
                  [--keep-frames DIR] [--still] [--font F] [--title-size N]
                  [--label-size N] [--bold none|title|all] [--bar-width N]

The front end runs under any python3. It finds pvpython, renders one PNG per frame
offscreen into a temporary directory, then encodes with ffmpeg (libx264, yuv420p,
+faststart, so it plays in Safari, Obsidian and a GitHub PR comment). The style
obeys the moose-figure rules: white background, no axes, no in-image title, and a
colour bar labelled with the quantity only. A small clock in the lower left shows
the simulation time, because a video with no time reads as a loop of nothing.

Defaults: the first nodal variable, a colour range fixed over all steps (so the
colours mean the same value in every frame), 12 fps, 1280x720, an isometric view
for a 3D mesh and a top view for a flat one, every timestep up to 240 frames.

--view       iso | top | front | right | auto (default)
--range      all (default) fixes the range over all steps; step rescales every frame
--warp       warp by the displacement vector (disp_x/y/z); SCALE defaults to 1
--orbit DEG  turn the camera DEG degrees about the vertical over the whole video
--hold S     repeat the last frame for S seconds (default 1), so the end state reads
--gif        also write OUT.gif beside the MP4 (palette-optimized, 640 px wide)
--still      write one PNG of the last step to OUT instead of a video

The colour bar defaults to Arial Bold from its font file (heavier than ParaView's
bold Arial), a 28 px horizontal title, 20 px labels and a 36 px wide bar. The clock
uses the same font. Pass --font Arial --bold none --bar-width 16 for ParaView's look.

Find pvpython through $PVPYTHON, PATH, or /Applications/ParaView-*.app.
"""

import argparse
import glob
import os
import shutil
import subprocess
import sys
import tempfile

# ---------------------------------------------------------------------------
# Renderer: runs inside pvpython. Reads its arguments from a JSON file.
# ---------------------------------------------------------------------------
RENDER = r'''
import json, math, os, sys
from paraview.simple import *

a = json.load(open(sys.argv[1]))
reader = ExodusIIReader(FileName=[a["file"]])
reader.PointVariables = reader.PointVariables.Available
reader.ElementVariables = reader.ElementVariables.Available
reader.UpdatePipeline()
times = list(reader.TimestepValues) if reader.TimestepValues else [0.0]
if isinstance(reader.TimestepValues, float):
    times = [reader.TimestepValues]

pvars = list(reader.PointVariables)
evars = list(reader.ElementVariables)
var = a["var"]
if var is None:
    pick = [v for v in pvars if not v.startswith("disp")] or pvars or evars
    if not pick:
        sys.exit("exodus-video: the file has no nodal or elemental variable")
    var = pick[0]
if var in pvars:
    assoc = "POINTS"
elif var in evars:
    assoc = "CELLS"
else:
    sys.exit("exodus-video: unknown variable %r; nodal: %s; elemental: %s" % (var, pvars, evars))

src = reader
if a["warp"] is not None:
    disp = [v for v in pvars if v.lower() in ("disp", "displacement", "disp_")]
    if not disp:
        comps = [c for c in ("disp_x", "disp_y", "disp_z") if c in pvars]
        if not comps:
            sys.exit("exodus-video: --warp needs disp_x/disp_y/disp_z")
        expr = "+".join("%s*%s" % (c, u) for c, u in zip(comps, ("iHat", "jHat", "kHat")))
        calc = Calculator(Input=reader, ResultArrayName="warpvec", Function=expr)
        vec = "warpvec"
        src = calc
    else:
        vec = disp[0]
    src = WarpByVector(Input=src, Vectors=["POINTS", vec], ScaleFactor=float(a["warp"]))

surf = MergeBlocks(Input=src)

# Fixed colour range over every step.
lo, hi = float("inf"), float("-inf")
if a["range"] == "all":
    for t in times:
        surf.UpdatePipeline(t)
        arrs = surf.PointData if assoc == "POINTS" else surf.CellData
        r = arrs[var].GetRange(-1 if arrs[var].GetNumberOfComponents() > 1 else 0)
        lo, hi = min(lo, r[0]), max(hi, r[1])
elif a["range"] != "step":
    lo, hi = a["range"]
# Solver round-off (5.6e-13 where the answer is 0) prints as noise on the bar: snap it to 0.
span = max(abs(lo), abs(hi)) if lo != float("inf") else 0.0
if span and abs(lo) < 1e-9 * span:
    lo = 0.0
if span and abs(hi) < 1e-9 * span:
    hi = 0.0
if lo == hi and lo != float("inf"):
    lo, hi = lo - 0.5, hi + 0.5

view = CreateView("RenderView")
view.ViewSize = a["size"]
view.OrientationAxesVisibility = 0
try:
    view.UseColorPaletteForBackground = 0
except AttributeError:
    pass
view.Background = [1.0, 1.0, 1.0]
view.EnableRenderOnInteraction = 0

disp = Show(surf, view)
disp.Representation = "Surface With Edges" if a["edges"] else "Surface"
disp.EdgeColor = [0.14, 0.2, 0.28]
ColorBy(disp, (assoc, var))
lut = GetColorTransferFunction(var)
lut.ApplyPreset(a["cmap"], True)
if a["range"] != "step":
    lut.RescaleTransferFunction(lo, hi)
    lut.AutomaticRescaleRangeMode = "Never"
disp.SetScalarBarVisibility(view, True)
bar = GetScalarBar(lut, view)
bar.Title = var
bar.ComponentTitle = ""
bar.TitleColor = bar.LabelColor = [0.1, 0.1, 0.1]
bar.TitleFontSize = 16
bar.LabelFontSize = 14
bar.RangeLabelFormat = "%-#.3g"
bar.WindowLocation = "Any Location"
bar.Orientation = "Vertical"
bar.Position = [0.88, 0.15]
bar.ScalarBarLength = 0.7
bar.HorizontalTitle = 1                 # read the quantity without turning your head
fam, fil = (("File", a["font"]) if a["font"].lower().endswith((".ttf", ".otf", ".ttc"))
            else (a["font"], None))
for part, size in (("Title", a["title_size"]), ("Label", a["label_size"])):
    setattr(bar, part + "FontFamily", fam)
    if fil:
        setattr(bar, part + "FontFile", fil)
    setattr(bar, part + "FontSize", size)
    setattr(bar, part + "Bold", int(part == "Title" and a["bold"] in ("title", "all")
                                    or part == "Label" and a["bold"] == "all"))
bar.ScalarBarThickness = a["bar_width"]

clock = None
if a["clock"]:
    clock = Text(Text="")
    cdisp = Show(clock, view)
    cdisp.Color = [0.1, 0.1, 0.1]
    cdisp.FontSize = a["label_size"] + 2
    cdisp.FontFamily = fam
    if fil:
        cdisp.FontFile = fil
    cdisp.WindowLocation = "Lower Left Corner"

# Camera: a flat mesh looks from +z, a solid from an isometric corner.
surf.UpdatePipeline(times[-1])
b = surf.GetDataInformation().GetBounds()
ext = [b[1] - b[0], b[3] - b[2], b[5] - b[4]]
flat = ext[2] <= 1e-9 * max(max(ext), 1e-300)
mode = a["view"]
if mode == "auto":
    mode = "top" if flat else "iso"
cx, cy, cz = (b[0] + b[1]) / 2, (b[2] + b[3]) / 2, (b[4] + b[5]) / 2
dirs = {"top": ((0, 0, 1), (0, 1, 0)), "front": ((0, -1, 0), (0, 0, 1)),
        "right": ((1, 0, 0), (0, 0, 1)), "iso": ((1, -1, 0.8), (0, 0, 1))}
d, up = dirs[mode]
# paraview.simple.Render resets the camera on a view's first render, so render once
# before placing the camera, then place it from the bounds (no ResetCamera after).
view.ViewTime = times[-1]
Render(view)
radius = 0.5 * math.sqrt(sum(e * e for e in ext)) or 1.0
norm = math.sqrt(sum(c * c for c in d))
dist = radius / math.sin(math.radians(15.0)) / a["zoom"]   # 30 degree view angle
view.CameraViewAngle = 30.0
view.CameraFocalPoint = [cx, cy, cz]
view.CameraPosition = [cx + d[0] / norm * dist, cy + d[1] / norm * dist, cz + d[2] / norm * dist]
view.CameraViewUp = list(up)
view.CameraParallelProjection = 1 if flat else 0
view.CameraParallelScale = radius * 1.05 / a["zoom"]
pos0 = list(view.CameraPosition)

steps = times
if len(steps) > a["max_frames"]:
    n = a["max_frames"]
    steps = [times[round(i * (len(times) - 1) / (n - 1))] for i in range(n)]
if a["still"]:
    steps = [times[-1]]
elif a["orbit"] and len(steps) == 1:
    steps = steps * min(72, a["max_frames"])   # a steady result: the camera is the motion

os.makedirs(a["frames"], exist_ok=True)
nframes = len(steps)
for i, t in enumerate(steps):
    view.ViewTime = t
    if clock is not None:
        clock.Text = "t = %.4g" % t
    if a["orbit"]:
        ang = math.radians(a["orbit"] * i / max(nframes - 1, 1))
        dx, dy = pos0[0] - cx, pos0[1] - cy
        view.CameraPosition = [cx + dx * math.cos(ang) - dy * math.sin(ang),
                               cy + dx * math.sin(ang) + dy * math.cos(ang), pos0[2]]
    if a["range"] == "step":
        disp.RescaleTransferFunctionToDataRange(False, True)
    Render(view)
    SaveScreenshot(os.path.join(a["frames"], "f%05d.png" % i), view,
                   ImageResolution=a["size"], TransparentBackground=0)
print(json.dumps({"var": var, "frames": nframes, "steps": len(times),
                  "t0": times[0], "t1": times[-1], "view": mode,
                  "range": None if a["range"] == "step" else [lo, hi]}))
'''


# Arial Bold from its file draws heavier than ParaView's own bold Arial; fall back off a Mac.
DEFAULT_FONT = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
if not os.path.isfile(DEFAULT_FONT):
    DEFAULT_FONT = "Arial"


def find_pvpython():
    cand = [os.environ.get("PVPYTHON"), shutil.which("pvpython")]
    cand += sorted(glob.glob("/Applications/ParaView-*.app/Contents/bin/pvpython"), reverse=True)
    for c in cand:
        if c and os.access(c, os.X_OK):
            return c
    sys.exit("exodus-video: pvpython not found; set PVPYTHON or install ParaView")


def parse_range(s):
    if s in ("all", "step"):
        return s
    lo, hi = (float(x) for x in s.split(","))
    return [lo, hi]


def main():
    p = argparse.ArgumentParser(description="Render an Exodus result to MP4 with ParaView.")
    p.add_argument("file")
    p.add_argument("out", help="output .mp4 path")
    p.add_argument("--var")
    p.add_argument("--fps", type=int, default=12)
    p.add_argument("--size", default="1280x720")
    p.add_argument("--view", default="auto", choices=["auto", "iso", "top", "front", "right"])
    p.add_argument("--range", default="all", type=parse_range)
    p.add_argument("--cmap", default="Viridis (matplotlib)")
    p.add_argument("--warp", nargs="?", const=1.0, type=float)
    p.add_argument("--edges", action="store_true")
    p.add_argument("--orbit", type=float, default=0.0)
    p.add_argument("--zoom", type=float, default=1.0)
    p.add_argument("--max-frames", type=int, default=240)
    p.add_argument("--hold", type=float, default=1.0)
    p.add_argument("--no-clock", dest="clock", action="store_false")
    p.add_argument("--gif", action="store_true")
    p.add_argument("--still", action="store_true", help="write one PNG of the last step to OUT")
    p.add_argument("--font", default=DEFAULT_FONT, help="Arial | Courier | Times | a .ttf path")
    p.add_argument("--title-size", type=int, default=28)
    p.add_argument("--label-size", type=int, default=20)
    p.add_argument("--bold", default="all", choices=["none", "title", "all"])
    p.add_argument("--bar-width", type=int, default=36)
    p.add_argument("--keep-frames")
    a = p.parse_args()

    if not os.path.isfile(a.file):
        sys.exit("exodus-video: no such file: %s" % a.file)
    if not shutil.which("ffmpeg"):
        sys.exit("exodus-video: ffmpeg not found on PATH")
    w, h = (int(x) for x in a.size.lower().split("x"))
    w, h = w - w % 2, h - h % 2  # libx264 with yuv420p needs even sides
    out = os.path.abspath(a.out)
    os.makedirs(os.path.dirname(out), exist_ok=True)

    tmp = tempfile.mkdtemp(prefix="exodus-video-")
    frames = os.path.abspath(a.keep_frames) if a.keep_frames else os.path.join(tmp, "frames")
    try:
        import json

        spec = os.path.join(tmp, "args.json")
        script = os.path.join(tmp, "render.py")
        with open(spec, "w") as f:
            json.dump({"file": os.path.abspath(a.file), "var": a.var, "size": [w, h],
                       "view": a.view, "range": a.range, "cmap": a.cmap, "warp": a.warp,
                       "edges": a.edges, "orbit": a.orbit, "zoom": a.zoom,
                       "max_frames": max(a.max_frames, 2), "clock": a.clock,
                       "still": a.still, "font": a.font, "title_size": a.title_size,
                       "label_size": a.label_size, "bold": a.bold, "bar_width": a.bar_width,
                       "frames": frames}, f)
        with open(script, "w") as f:
            f.write(RENDER)
        r = subprocess.run([find_pvpython(), "--force-offscreen-rendering", script, spec],
                           capture_output=True, text=True)
        info = None
        for line in reversed(r.stdout.splitlines()):
            if line.startswith("{"):
                info = json.loads(line)
                break
        if r.returncode != 0 or info is None:
            sys.stderr.write(r.stdout[-2000:] + r.stderr[-4000:])
            sys.exit("exodus-video: pvpython failed (exit %d)" % r.returncode)

        if a.still:
            shutil.copyfile(os.path.join(frames, "f00000.png"), out)
            info["files"] = [{"path": out, "bytes": os.path.getsize(out)}]
            print(json.dumps(info, indent=1))
            return
        hold = ["-vf", "tpad=stop_mode=clone:stop_duration=%g" % a.hold] if a.hold > 0 else []
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", str(a.fps),
                        "-i", os.path.join(frames, "f%05d.png"), *hold,
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "23",
                        "-movflags", "+faststart", out], check=True)
        made = [out]
        if a.gif:
            gif = os.path.splitext(out)[0] + ".gif"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", out, "-vf",
                            "fps=%d,scale=640:-1:flags=lanczos,split[a][b];"
                            "[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=bayer"
                            % min(a.fps, 12), gif], check=True)
            made.append(gif)
        for m in made:
            info.setdefault("files", []).append({"path": m, "bytes": os.path.getsize(m)})
        print(json.dumps(info, indent=1))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
