#!/usr/bin/env python3
"""Validate and slice a specs/blueprint.html for /moose-blueprint and /moose-build.

usage: slice_blueprint.py --check <blueprint.html>
       slice_blueprint.py --slice <blueprint.html>
       slice_blueprint.py --check --slice <blueprint.html>

--check  prints "OK" or one problem per line; exit 0 when the blueprint is
         usable, 1 when it is not.
--slice  prints one JSON object with the seven contract blocks as plain text
         plus the work-plan units and deps. The check runs first; a failing
         blueprint prints the problems and exits 1 so /moose-build refuses
         with the validator's message. With both flags only the JSON prints
         on success.

Exit 2 = bad arguments or unreadable file. Python 3 stdlib only.

Why a real HTML parser and not regexes: the blueprint is 500 KB+ of inlined
KaTeX fonts and nested <span> soup. Every rendered equation carries its source
TeX in <annotation encoding="application/x-tex">; the text extractor swaps the
whole .katex span for that TeX so agents receive "$\\lambda$" instead of the
MathML and the HTML render side by side.
"""
import json
import os
import re
import sys
from html.parser import HTMLParser

CONTRACT_IDS = ("summary", "physics", "reuse-decisions", "test-plan",
                "doc-plan", "out-of-scope", "work-plan")
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
        "meta", "source", "track", "wbr"}
# Tags whose open element is closed implicitly when the key tag opens.
IMPLICIT_CLOSE = {"p": {"p"}, "li": {"li"}, "tr": {"tr", "td", "th"},
                  "td": {"td", "th"}, "th": {"td", "th"},
                  "dt": {"dt", "dd"}, "dd": {"dt", "dd"}}
BLOCK = {"p", "div", "section", "article", "h1", "h2", "h3", "h4", "h5", "h6",
         "ul", "ol", "li", "table", "tr", "dl", "dt", "dd", "pre", "blockquote",
         "figure", "figcaption", "details", "summary", "header", "footer",
         "thead", "tbody"}
SKIP = {"script", "style", "template"}
HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
# Short junk that a template leaves behind; "none" is excluded because an
# out-of-scope or doc-plan block may legitimately say it.
JUNK = re.compile(r"^(tbd|todo|tba|placeholder|fill in|xxx|\?+|-+|\.{3})\.?$", re.I)


class Node(object):
    __slots__ = ("tag", "attrs", "children", "parent")

    def __init__(self, tag, attrs):
        self.tag = tag
        self.attrs = dict(attrs)
        self.children = []
        self.parent = None

    def append(self, child):
        if isinstance(child, Node):
            child.parent = self
        self.children.append(child)

    def classes(self):
        return (self.attrs.get("class") or "").split()


class TreeBuilder(HTMLParser):
    """Minimal DOM: elements are Node, text is str, comments are dropped.

    Dropping comments is deliberate: the template's image-slot tokens
    ({{HERO_IMAGE ...}}) live inside comments and are allowed to remain.
    """

    def __init__(self):
        HTMLParser.__init__(self, convert_charrefs=True)
        self.root = Node("#root", [])
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        if self.stack[-1].tag in IMPLICIT_CLOSE.get(tag, ()):
            self.stack.pop()
        node = Node(tag, attrs)
        self.stack[-1].append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.stack[-1].append(Node(tag, attrs))

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        self.stack[-1].append(data)


def walk(node):
    for child in node.children:
        if isinstance(child, Node):
            yield child
            for sub in walk(child):
                yield sub


def find_id(root, ident):
    for node in walk(root):
        if node.attrs.get("id") == ident:
            return node
    return None


def block_of(root, ident):
    """The element carrying a contract id, or, when the id sits on a heading
    (some blueprints write <h3 id="out-of-scope">), a synthetic box holding
    that heading and its following siblings up to the next heading of the
    same or a higher level."""
    node = find_id(root, ident)
    if node is None or node.tag not in HEADINGS or node.parent is None:
        return node
    level = int(node.tag[1])
    box = Node("div", [])
    box.children.append(node)
    seen = False
    for sib in node.parent.children:
        if sib is node:
            seen = True
            continue
        if not seen:
            continue
        if isinstance(sib, Node) and sib.tag in HEADINGS and int(sib.tag[1]) <= level:
            break
        box.children.append(sib)
    return box


def find_all(node, tag):
    return [n for n in walk(node) if n.tag == tag]


def tex_of(node):
    for sub in walk(node):
        if sub.tag == "annotation" and sub.attrs.get("encoding") == "application/x-tex":
            return "".join(c for c in sub.children if isinstance(c, str)).strip()
    return None


def to_text(node):
    """Plain text of a subtree: block tags break lines, list items get "- ",
    table cells join with " | ", KaTeX spans collapse to their TeX source."""
    out = []

    def emit(n, in_pre):
        if isinstance(n, str):
            out.append(n if in_pre else re.sub(r"[ \t\r\n]+", " ", n))
            return
        if n.tag in SKIP:
            return
        if n.tag == "br":
            out.append("\n")
            return
        cls = n.classes()
        if "katex" in cls or "katex-display" in cls:
            tex = tex_of(n)
            if tex is not None:
                # A space before the TeX only when the preceding text has none.
                pad = "" if not out or out[-1][-1:].isspace() or out[-1] == "" else " "
                out.append(pad + ("$$%s$$" % tex if "katex-display" in cls else "$%s$" % tex))
                return
        block = n.tag in BLOCK
        if block:
            out.append("\n")
        if n.tag == "li":
            out.append("- ")
        if n.tag in ("td", "th") and out and not out[-1].endswith("\n"):
            out.append(" | ")
        for child in n.children:
            emit(child, in_pre or n.tag == "pre")
        if block:
            out.append("\n")

    emit(node, False)
    text = "".join(out)
    lines = [ln.strip() for ln in text.split("\n")]
    text = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def norm(text):
    return re.sub(r"\s+", " ", text).strip()


def body_text(node):
    """Block text without its first heading, for placeholder detection."""
    parts = []
    skipped = False
    for child in node.children:
        if not skipped and isinstance(child, Node) and child.tag in HEADINGS:
            skipped = True
            continue
        parts.append(to_text(child) if isinstance(child, Node) else child)
    return norm(" ".join(parts))


def code_texts(node):
    return [norm(to_text(c)) for c in find_all(node, "code")]


def table_rows(node):
    """[(header_texts, [(cell_node, cell_text), ...]), ...] for every data row."""
    rows = []
    for tr in find_all(node, "tr"):
        cells = [c for c in tr.children if isinstance(c, Node) and c.tag in ("td", "th")]
        if not cells:
            continue
        rows.append((tr, [(c, norm(to_text(c))) for c in cells]))
    header = []
    data = []
    for tr, cells in rows:
        if not header and all(c.tag == "th" for c, _ in cells):
            header = [t.lower() for _, t in cells]
        else:
            data.append(cells)
    return header, data


def test_plan_entries(block):
    """One entry per table row; columns are mapped by header keyword and fall
    back to position (name, tester, behavior, rationale)."""
    header, rows = table_rows(block)
    keys = ["name", "tester", "asserted_behavior", "mutation_rationale"]
    order = list(range(4))
    if header:
        for k, words in enumerate((("name", "test"), ("tester", "cases", "kind"),
                                   ("behavior", "asserted"), ("rationale", "mutation"))):
            for i, h in enumerate(header):
                if any(w in h for w in words):
                    order[k] = i
                    break
    entries = []
    for cells in rows:
        entry = {}
        for k, i in zip(keys, order):
            entry[k] = cells[i][1] if i < len(cells) else ""
        # Every name a test unit may reference: the cell text and each <code>.
        # The <code> form is the canonical name; the cell may add a tag like "v2".
        codes = code_texts(cells[0][0]) if cells else []
        if codes:
            entry["name"] = codes[0]
        entry["_names"] = ([cells[0][1]] if cells else []) + codes
        entries.append(entry)
    return entries


def reuse_entries(block):
    """One entry per table row or <li>; the decision word is taken from a
    'decision' column when there is one, else the first Reuse/Extend/Parallel/
    Abandon word in the entry."""
    word = re.compile(r"\b(Reuse|Extend|Parallel|Abandon|Discard)\b")
    header, rows = table_rows(block)
    entries = []
    if rows:
        dcol = next((i for i, h in enumerate(header) if "decision" in h), None)
        for cells in rows:
            text = " | ".join(t for _, t in cells)
            src = cells[dcol][1] if dcol is not None and dcol < len(cells) else text
            m = word.search(src)
            entries.append({"text": text, "decision": m.group(1) if m else None})
    else:
        items = find_all(block, "li") or [c for c in block.children
                                          if isinstance(c, Node) and c.tag == "p"]
        for item in items:
            text = norm(to_text(item))
            m = word.search(text)
            entries.append({"text": text, "decision": m.group(1) if m else None})
    return entries


def list_items(block):
    items = [norm(to_text(li)) for li in find_all(block, "li")]
    if items:
        return items
    return [ln for ln in body_text(block).split("\n") if ln.strip()]


def is_path(s):
    """A repo path: has a slash, no spaces, and ends in an extension or a
    trailing slash, so "modules/solid_mechanics" or "dataStore/dataLoad" in
    prose do not count. Brace groups like include/x/{A,B}.h are kept."""
    return ("/" in s and " " not in s and re.match(r"^[\w.\-{},+/~]+$", s) is not None
            and re.search(r"(\.\w+|/)$", s) is not None)


def load_island(root):
    node = find_id(root, "work-plan-data")
    if node is None or node.tag != "script":
        return None, "#work-plan-data island is missing"
    raw = "".join(c for c in node.children if isinstance(c, str))
    try:
        data = json.loads(raw)
    except ValueError as exc:
        return None, "#work-plan-data does not parse: %s" % exc
    if not isinstance(data, dict) or not isinstance(data.get("units"), list):
        return None, "#work-plan-data has no \"units\" list"
    return data, None


def check_units(units, test_names):
    problems = []
    by_id = {}
    for i, u in enumerate(units):
        if not isinstance(u, dict) or not isinstance(u.get("id"), str) or not u["id"]:
            problems.append("unit %d has no string id" % i)
            continue
        if u["id"] in by_id:
            problems.append("duplicate unit id %s" % u["id"])
            continue
        by_id[u["id"]] = u
        if not isinstance(u.get("deps", []), list):
            problems.append("unit %s: deps is not a list" % u["id"])
    deps = {}
    for uid, u in by_id.items():
        deps[uid] = [d for d in (u.get("deps") or []) if isinstance(d, str)]
        for d in deps[uid]:
            if d not in by_id:
                problems.append("unit %s depends on unknown unit %s" % (uid, d))
    # Cycle detection: iterative DFS with a colored stack; the first back edge
    # found is reported as the cycle path.
    color = {}
    for start in by_id:
        if color.get(start):
            continue
        stack = [(start, iter(deps[start]))]
        color[start] = 1
        path = [start]
        while stack:
            node, it = stack[-1]
            nxt = next(it, None)
            if nxt is None:
                color[node] = 2
                stack.pop()
                path.pop()
                continue
            if nxt not in by_id:
                continue
            if color.get(nxt) == 1:
                cyc = path[path.index(nxt):] + [nxt]
                problems.append("dependency cycle: %s" % " -> ".join(cyc))
                color[nxt] = 2
            elif not color.get(nxt):
                color[nxt] = 1
                path.append(nxt)
                stack.append((nxt, iter(deps[nxt])))
    # Units that share a file must be ordered by the graph. Reachability in
    # either direction counts, not only a direct edge: the loop only runs
    # units concurrently when nothing orders them, and U8 -> U9 -> U7 already
    # keeps U8 and U7 apart. Trailing slashes are ignored so "dir/" == "dir".
    reach = {}
    for uid in by_id:
        seen = set()
        todo = list(deps[uid])
        while todo:
            d = todo.pop()
            if d in seen or d not in by_id:
                continue
            seen.add(d)
            todo.extend(deps[d])
        reach[uid] = seen
    files = {}
    for uid, u in by_id.items():
        payload = u.get("payload") or {}
        fl = payload.get("files") if isinstance(payload, dict) else None
        files[uid] = set(f.rstrip("/") for f in (fl or []) if isinstance(f, str))
    ids = sorted(by_id)
    for a_i, a in enumerate(ids):
        for b in ids[a_i + 1:]:
            shared = files[a] & files[b]
            if shared and b not in reach[a] and a not in reach[b]:
                problems.append("units %s and %s both list %s but no dependency orders them"
                                % (a, b, ", ".join(sorted(shared))))
    for uid, u in by_id.items():
        if u.get("kind") != "test":
            continue
        payload = u.get("payload") or {}
        ref = payload.get("test_plan_ref") if isinstance(payload, dict) else None
        if not isinstance(ref, str) or norm(ref) not in test_names:
            problems.append("unit %s: test_plan_ref %r names no #test-plan row" % (uid, ref))
    return problems, deps


def run_check(root, tests):
    problems = []
    for ident in CONTRACT_IDS:
        node = block_of(root, ident)
        if node is None:
            problems.append("#%s is missing" % ident)
            continue
        text = body_text(node)
        # The work plan's authoritative content is the JSON island, which is
        # script text and therefore invisible to body_text; a block that holds
        # one is not empty even before the unit cards are rendered.
        if ident == "work-plan" and not text and find_id(node, "work-plan-data") is not None:
            text = "island"
        if not text or "{{" in text or JUNK.match(text):
            problems.append("#%s is a placeholder" % ident)
    data, err = load_island(root)
    if err:
        problems.append(err)
        return problems, None, {}
    names = set()
    for t in tests:
        names.update(norm(n) for n in t["_names"])
    unit_problems, deps = check_units(data["units"], names)
    return problems + unit_problems, data, deps


def run_slice(root, path, tests, data, deps):
    def block(ident):
        node = block_of(root, ident)
        return node if node is not None else Node("div", [])

    summary = block("summary")
    summary_text = to_text(summary)
    flat = norm(summary_text)
    m = re.search(r"Repo:\s*(moose/modules/\w+|moose|blackbear|isopod)\b", flat)
    repo = m.group(1) if m else None
    m = re.search(r"Object kind:\s*(.+?)(?:\.\s|\s*\|\s|\s+User-facing|$)", flat)
    object_kind = m.group(1).strip()[:200] if m else None
    files = []
    sources = [summary]
    files_node = find_id(root, "files")
    if files_node is not None and all(files_node is not n for n in walk(summary)):
        sources.append(block_of(root, "files"))
    for src in sources:
        files.extend(c for c in code_texts(src) if is_path(c))
    for u in data["units"]:
        payload = u.get("payload") or {}
        if isinstance(payload, dict):
            files.extend(f for f in payload.get("files") or [] if isinstance(f, str))
    seen = set()
    files = [f for f in files if not (f in seen or seen.add(f))]
    doc = block("doc-plan")
    doc_text = to_text(doc)
    m = re.search(r"Needed:\s*(yes|no)\b", doc_text, re.I)
    needed = (m.group(1).lower() == "yes") if m else None
    pages = [c for c in code_texts(doc) if c.endswith(".md")]
    pages += re.findall(r"\S*doc/content/\S+\.md", doc_text)
    seen = set()
    pages = [p for p in pages if not (p in seen or seen.add(p))]
    reuse = reuse_entries(block("reuse-decisions"))
    decisions = [r["decision"] for r in reuse if r["decision"]]
    unit_on = (any(u.get("agent") == "moose-unit-test-writer" for u in data["units"])
               or any("gtest" in t["tester"].lower() for t in tests)
               or any(f.startswith("unit/") or "/unit/" in f for f in files))
    return {
        "repo": repo,
        "object_kind": object_kind,
        "scope": repo.split("/")[0] if repo else None,
        "files_to_touch": files,
        "summary": summary_text,
        "physics": to_text(block("physics")),
        "reuse_decisions": reuse,
        "test_plan": [{k: v for k, v in t.items() if not k.startswith("_")} for t in tests],
        "doc_plan": {"needed": needed, "pages": pages},
        "out_of_scope": list_items(block("out-of-scope")),
        "units": data["units"],
        "deps": deps,
        "unit_on": unit_on,
        # scouts-found-nothing is not reuse-only: it needs at least one decision.
        "reuse_only": bool(decisions) and all(d == "Reuse" for d in decisions),
        "blueprint_path": os.path.abspath(path),
    }


def main(argv):
    flags = [a for a in argv if a.startswith("--")]
    paths = [a for a in argv if not a.startswith("--")]
    if len(paths) != 1 or not flags or any(f not in ("--check", "--slice") for f in flags):
        sys.stderr.write("usage: slice_blueprint.py --check|--slice [--check --slice] <blueprint.html>\n")
        return 2
    path = paths[0]
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            html = fh.read()
    except (IOError, OSError) as exc:
        sys.stderr.write("cannot read %s: %s\n" % (path, exc))
        return 2
    parser = TreeBuilder()
    parser.feed(html)
    parser.close()
    root = parser.root
    tp = block_of(root, "test-plan")
    tests = test_plan_entries(tp) if tp is not None else []
    problems, data, deps = run_check(root, tests)
    if problems:
        print("\n".join(problems))
        return 1
    if "--slice" in flags:
        print(json.dumps(run_slice(root, path, tests, data, deps), indent=2, ensure_ascii=True))
    else:
        print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
