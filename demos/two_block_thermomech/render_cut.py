# pvpython render_cut.py <in.e> <frames_dir> [orbit]
# The block cut at y = 0, colored by stress_xx (the first component of the stress_x vector
# that ParaView builds from stress_xx/xy/xz), over every timestep. With "orbit": the last step
# only, the camera turning 360 degrees. Encode the frames with ffmpeg afterwards.
import math
import os
import sys

from paraview.simple import *

src_file, frames = sys.argv[1], sys.argv[2]
orbit = len(sys.argv) > 3 and sys.argv[3] == "orbit"
LIMIT = 2.1e8
FONT = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"

reader = ExodusIIReader(FileName=[src_file])
reader.ElementVariables = ["stress_x"]  # ParaView merges stress_xx/xy/xz into one vector
reader.PointVariables = ["disp_x", "disp_y", "disp_z"]
reader.UpdatePipeline()
times = list(reader.TimestepValues)

merged = MergeBlocks(Input=reader)
clip = Clip(Input=merged)
clip.ClipType = "Plane"
clip.ClipType.Origin = [0.0, 0.0, 0.0]
clip.ClipType.Normal = [0.0, -1.0, 0.0]  # keep y >= 0: the cut face looks to -y
clip.Crinkleclip = 0
surf = ExtractSurface(Input=clip)

view = GetActiveViewOrCreate("RenderView")
view.ViewSize = [1280, 720]
view.OrientationAxesVisibility = 0
view.Background = [1, 1, 1]
try:
    view.UseColorPaletteForBackground = 0
except AttributeError:
    pass

disp = Show(surf, view)
disp.Representation = "Surface With Edges"
disp.EdgeColor = [0.25, 0.25, 0.25]
ColorBy(disp, ("CELLS", "stress_x", "X"))
lut = GetColorTransferFunction("stress_x")
lut.VectorMode = "Component"
lut.VectorComponent = 0
lut.ApplyPreset("Cool to Warm", True)
lut.RescaleTransferFunction(-LIMIT, LIMIT)
lut.AutomaticRescaleRangeMode = "Never"
disp.SetScalarBarVisibility(view, True)
bar = GetScalarBar(lut, view)
bar.Title = "stress_xx [Pa]"
bar.ComponentTitle = ""
bar.TitleColor = bar.LabelColor = [0.1, 0.1, 0.1]
for part, size in (("Title", 24), ("Label", 20)):
    setattr(bar, part + "FontFamily", "File")
    setattr(bar, part + "FontFile", FONT)
    setattr(bar, part + "FontSize", size)
bar.RangeLabelFormat = "%-.3g"
bar.WindowLocation = "Any Location"
bar.Position = [0.88, 0.15]
bar.ScalarBarLength = 0.7
bar.ScalarBarThickness = 36
bar.HorizontalTitle = 1

clock = Text(Text="")
cdisp = Show(clock, view)
cdisp.Color = [0.1, 0.1, 0.1]
cdisp.FontFamily = "File"
cdisp.FontFile = FONT
cdisp.FontSize = 22
cdisp.WindowLocation = "Lower Left Corner"

note = Text(Text="cut at y = 0; block A below z = 0")
ndisp = Show(note, view)
ndisp.Color = [0.35, 0.35, 0.35]
ndisp.FontFamily = "File"
ndisp.FontFile = FONT
ndisp.FontSize = 18
ndisp.WindowLocation = "Upper Left Corner"

view.ViewTime = times[-1]
Render(view)
c = [0.0, 0.03, 0.0]
dist = 0.42
d = (0.55, -1.0, 0.5)
n = math.sqrt(sum(x * x for x in d))
view.CameraFocalPoint = c
view.CameraPosition = [c[i] + d[i] / n * dist for i in range(3)]
view.CameraViewUp = [0, 0, 1]
view.CameraViewAngle = 30
pos0 = list(view.CameraPosition)

steps = [times[-1]] * 120 if orbit else times
os.makedirs(frames, exist_ok=True)
for i, t in enumerate(steps):
    view.ViewTime = t
    clock.Text = "t = %.4g s" % t
    if orbit:
        ang = 2 * math.pi * i / len(steps)
        dx, dy = pos0[0] - c[0], pos0[1] - c[1]
        view.CameraPosition = [c[0] + dx * math.cos(ang) - dy * math.sin(ang),
                               c[1] + dx * math.sin(ang) + dy * math.cos(ang), pos0[2]]
    Render(view)
    SaveScreenshot(os.path.join(frames, "f%05d.png" % i), view, ImageResolution=[1280, 720],
                   TransparentBackground=0)
print("frames", len(steps))
