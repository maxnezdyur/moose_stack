#!/usr/bin/env python3
"""Pack specs/blueprint-page.html into specs/blueprint.html.

Two steps:

1. ``doc-math``. Every ``<doc-math>…</doc-math>`` block holds markdown with ``$$ … $$`` display
   math and ``$ … $`` inline math (pipe tables for a symbol table are fine). pandoc turns each one
   into HTML with MathML, so the packed page needs no network and renders in Safari from
   ``file://``. The tag stays ``<doc-math>`` with the rendered HTML inside; ``pack.mjs`` counts it as an exhibit (one-token patch, see NOTICE.md). Without pandoc the block is
   left as the raw markdown in a ``<pre>`` and a warning is printed; the page still packs.

2. ``pack.mjs``. The html-plan packer lints every block, embeds ``src=`` code slices from the
   worktree, inlines the runtime, and writes one self-contained file. Its errors stop the write;
   its warnings print and are the author's to fix.

Usage::

    pack-blueprint.py <specs/blueprint-page.html> [--root <worktree>]... [-o <out.html>] [--lint-only]

The default output is ``blueprint.html`` beside the source. Exit code is pack's.
"""

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MATH_CSS = """<style data-doc-math>
doc-math { display: block; margin: 10px 0 12px; font-size: 15px; line-height: 1.5; }
doc-math math[display="block"] { margin: 8px 0; font-size: 1.08em; }
doc-math table { border-collapse: collapse; font-size: 13.5px; margin: 8px 0; }
doc-math th, doc-math td { padding: 3px 10px 3px 0; text-align: left; vertical-align: top; }
doc-math th { font-weight: 600; border-bottom: 1px solid rgba(0,0,0,.15); }
doc-math pre { font-size: 12.5px; white-space: pre-wrap; }
</style>"""

MATH_RE = re.compile(r"<doc-math(?P<attrs>[^>]*)>(?P<body>.*?)</doc-math>", re.S)


def render_math(body: str, pandoc: str) -> str:
    text = body
    # Allow the markdown to sit in a text/plain script, like the other blocks.
    m = re.match(r'\s*<script type="text/plain">(.*?)</script>\s*$', text, re.S)
    if m:
        text = m.group(1)
    text = re.sub(r"^\n+", "", text)
    try:
        out = subprocess.run(
            [pandoc, "-f", "markdown", "-t", "html", "--mathml"],
            input=text, capture_output=True, text=True, check=True,
        ).stdout
    except subprocess.CalledProcessError as exc:
        sys.stderr.write("pack-blueprint: pandoc failed on a doc-math block: %s\n" % exc.stderr.strip())
        return "<pre>%s</pre>" % text.replace("&", "&amp;").replace("<", "&lt;")
    return out


def main(argv):
    if len(argv) < 2 or argv[1] in ("-h", "--help"):
        print(__doc__)
        return 2
    src = Path(argv[1]).resolve()
    rest = argv[2:]
    out = None
    if "-o" in rest:
        i = rest.index("-o")
        out = Path(rest[i + 1]).resolve()
        del rest[i:i + 2]
    if out is None:
        out = src.parent / "blueprint.html"
    if not src.is_file():
        sys.stderr.write("pack-blueprint: %s not found\n" % src)
        return 2

    html = src.read_text(encoding="utf-8")
    pandoc = shutil.which("pandoc")
    n_math = 0

    def sub(m):
        nonlocal n_math
        n_math += 1
        attrs = m.group("attrs") or ""
        if pandoc:
            inner = render_math(m.group("body"), pandoc)
        else:
            inner = "<pre>%s</pre>" % m.group("body").replace("&", "&amp;").replace("<", "&lt;")
        return "<doc-math%s>%s</doc-math>" % (attrs, inner)

    html = MATH_RE.sub(sub, html)
    if n_math and not pandoc:
        sys.stderr.write("pack-blueprint: pandoc not installed; %d doc-math block(s) left as text\n" % n_math)
    if n_math and "data-doc-math" not in html:
        html = re.sub(r"(<body[^>]*>)", r"\1\n" + MATH_CSS, html, count=1) if "<body" in html else MATH_CSS + html

    # Pack from a temp copy in the same directory, so relative src= and image paths resolve
    # the way they do for the source page.
    tmp = str(src.parent / ".blueprint-page.tmp.html")
    try:
        Path(tmp).write_text(html, encoding="utf-8")
        cmd = ["node", str(HERE / "pack.mjs"), tmp, "-o", str(out)] + rest
        proc = subprocess.run(cmd)
        return proc.returncode
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


if __name__ == "__main__":
    sys.exit(main(sys.argv))
