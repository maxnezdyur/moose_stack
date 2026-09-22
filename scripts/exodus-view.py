#!/usr/bin/env python3
"""exodus-view: serve an Exodus II result file to a browser viewer.

Usage:
  exodus-view.py [FILE.e ...] [--port N] [--open] [--snap-dir DIR]

Reads the file with scipy (classic netCDF), extracts the visible surface,
and serves a small JSON/binary API that scripts/exodus-view/viewer.html
consumes. Needs only numpy and scipy. Binds to 127.0.0.1 only.

API (all GET unless noted; every call takes ?file=<path>):
  /api/files                       loaded files
  /api/meta                        dims, blocks, sets, times, variable names
  /api/nodes                       node coordinates, f4 (nnodes,3)
  /api/surface?blocks=1,2&cut=x:0.5:+   visible surface: tri, triElem, edges
  /api/var?name=u&step=3           one field at one step, f4 (nnodes|nelem);
                                   also name=block (block index) and name=mag:disp
  /api/range?name=u                min/max over all steps
  /api/globals                     global variables vs time
  /api/sideset?id=2                triangles/edges/points of one side set
  /api/nodeset?id=2                node ids of one node set
  /api/probe?node=N&elem=E&step=S  every variable at one node and element
  /api/text?path=<file>            a text file (input listing for reports)
  POST /api/snapshot               {name, png, state, dir?} -> files in dir or --snap-dir
  /embed.js                        <exo-view>, <exo-input>, <exo-globals> for reports

Viewer URL parameters (viewer.html): file, var (name|block|mag:<prefix>), step (N|last),
cmap, range (step|all|min,max), warp=1, wprefix, wscale (number|auto), blocks, ss, ns (ids or
names), cut=axis:pos:sign, edges=0, opacity, up (z|y), bg,
view (iso|top|bottom|front|back|left|right), cam, probe=node[,elem], lock2d, embed=1,
controls=var,time,warp,cut,probe (embed only), snap=<name>, snapdir=<dir>.

Binary payloads: u32 header length, JSON header (padded to 4 bytes), then
the arrays listed in header.arrays back to back, each padded to 4 bytes.
"""

import argparse
import base64
import json
import os
import re
import socket
import struct
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlparse

import numpy as np
from scipy.io import netcdf_file

HERE = os.path.dirname(os.path.abspath(__file__))
VIEWER = os.path.join(HERE, "exodus-view", "viewer.html")
EMBED = os.path.join(HERE, "exodus-view", "embed.js")

# Exodus side ordering, 0-based corner nodes, one row per side.
FACES = {
    "HEX": [[0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [0, 4, 7, 3], [0, 3, 2, 1], [4, 5, 6, 7]],
    "TET": [[0, 1, 3], [1, 2, 3], [0, 3, 2], [0, 2, 1]],
    "WEDGE": [[0, 1, 4, 3], [1, 2, 5, 4], [0, 3, 5, 2], [0, 2, 1], [3, 4, 5]],
    "PYRAMID": [[0, 1, 4], [1, 2, 4], [2, 3, 4], [0, 4, 3], [0, 3, 2, 1]],
    "QUAD": [[0, 1], [1, 2], [2, 3], [3, 0]],
    "TRI": [[0, 1], [1, 2], [2, 0]],
    "EDGE": [[0], [1]],
}
CORNERS = {"HEX": 8, "TET": 4, "WEDGE": 6, "PYRAMID": 5, "QUAD": 4, "TRI": 3, "EDGE": 2}
DIM = {"HEX": 3, "TET": 3, "WEDGE": 3, "PYRAMID": 3, "QUAD": 2, "TRI": 2, "EDGE": 1}
ALIAS = {
    "TETRA": "TET", "TETRAHEDRON": "TET", "PRISM": "WEDGE", "SHELL": "QUAD", "TRISHELL": "TRI",
    "BAR": "EDGE", "BEAM": "EDGE", "TRUSS": "EDGE", "TRIANGLE": "TRI", "HEXAHEDRON": "HEX",
    "PYRA": "PYRAMID", "PYR": "PYRAMID",
}


def family(elem_type):
    letters = "".join(c for c in elem_type.upper() if c.isalpha())
    letters = ALIAS.get(letters, letters)
    for fam in CORNERS:
        if letters.startswith(fam):
            return fam
    return None


def padded_table(fam):
    """Side table as an (nsides, 4) int array, -1 where a side has fewer nodes."""
    rows = FACES[fam]
    tbl = -np.ones((len(rows), 4), dtype=np.int64)
    for i, r in enumerate(rows):
        tbl[i, : len(r)] = r
    return tbl


def decode_names(var, n):
    if var is None:
        return [""] * n
    data = np.array(var.data)
    out = []
    for row in data:
        out.append(b"".join(row.tolist()).decode("utf-8", "replace").strip("\x00 "))
    while len(out) < n:
        out.append("")
    return out


def pack(header, arrays):
    """Binary payload: header JSON + little-endian 4-byte arrays."""
    hdr = dict(header)
    hdr["arrays"] = []
    blobs = []
    for name, a in arrays:
        a = np.ascontiguousarray(a)
        code = {"f": "f4", "u": "u4", "i": "i4"}[a.dtype.kind]
        a = a.astype("<" + code, copy=False)
        hdr["arrays"].append({"name": name, "dtype": code, "shape": list(a.shape)})
        b = a.tobytes()
        blobs.append(b + b"\0" * ((-len(b)) % 4))
    hj = json.dumps(hdr).encode()
    hj += b" " * ((-len(hj)) % 4)
    return struct.pack("<I", len(hj)) + hj + b"".join(blobs)


class Exodus:
    def __init__(self, path):
        self.path = path
        self.mtime = os.path.getmtime(path)
        self.lock = threading.Lock()
        self.nc = netcdf_file(path, "r", mmap=True)
        v = self.nc.variables
        d = self.nc.dimensions
        self.dim = int(d.get("num_dim") or 3)
        nn = int(d["num_nodes"])

        if "coord" in v:
            xyz = np.array(v["coord"].data, dtype=np.float64).T
        else:
            cols = [np.array(v[k].data, dtype=np.float64) for k in ("coordx", "coordy", "coordz") if k in v]
            xyz = np.stack(cols, axis=1)
        if xyz.shape[1] < 3:
            xyz = np.concatenate([xyz, np.zeros((nn, 3 - xyz.shape[1]))], axis=1)
        self.xyz = xyz
        self.times = np.array(v["time_whole"].data, dtype=np.float64) if "time_whole" in v else np.zeros(1)
        if self.times.ndim == 0:
            self.times = self.times.reshape(1)
        self.nsteps = max(1, int(self.times.shape[0]))

        # Element blocks
        nblk = int(d.get("num_el_blk") or 0)
        ids = np.array(v["eb_prop1"].data) if "eb_prop1" in v else np.arange(1, nblk + 1)
        names = decode_names(v.get("eb_names"), nblk)
        self.blocks = []
        offset = 0
        for j in range(nblk):
            key = f"connect{j + 1}"
            nelem = int(d.get(f"num_el_in_blk{j + 1}") or 0)
            if key not in v or nelem == 0:
                self.blocks.append(dict(idx=j, id=int(ids[j]), name=names[j] or f"block_{ids[j]}", type="EMPTY",
                                        fam=None, dim=0, nelem=0, offset=offset, nf=0))
                continue
            var = v[key]
            et = var.elem_type
            et = et.decode() if isinstance(et, bytes) else str(et)
            et = et.strip("\x00 ")
            conn = np.array(var.data, dtype=np.int64) - 1
            fam = family(et)
            nc = CORNERS.get(fam, 0)
            corners = conn[:, :nc]
            ext = np.concatenate([corners, -np.ones((nelem, 1), dtype=np.int64)], axis=1)
            b = dict(idx=j, id=int(ids[j]), name=names[j] or f"block_{ids[j]}", type=et, fam=fam,
                     dim=DIM.get(fam, 0), nelem=nelem, offset=offset, corners=corners, ext=ext)
            if fam and nc:
                b["centroid"] = xyz[corners].mean(axis=1)
                tbl = padded_table(fam)
                tbl_ix = np.where(tbl < 0, nc, tbl)  # -1 -> sentinel column
                b["tbl"] = tbl_ix
                b["nf"] = len(tbl)
                if b["dim"] == 3:
                    faces = ext[:, tbl_ix]  # (nelem, nf, 4)
                    b["faces"] = faces.reshape(-1, 4)
                    b["face_elem"] = np.repeat(offset + np.arange(nelem), len(tbl))
            else:
                b["nf"] = 0
            self.blocks.append(b)
            offset += nelem
        self.nelem = offset
        self.offsets = np.array([b["offset"] for b in self.blocks] + [offset])

        # Variables
        self.nodal = decode_names(v.get("name_nod_var"), int(d.get("num_nod_var") or 0))
        self.elemental = decode_names(v.get("name_elem_var"), int(d.get("num_elem_var") or 0))
        self.globals = decode_names(v.get("name_glo_var"), int(d.get("num_glo_var") or 0))
        if "elem_var_tab" in v:
            self.elem_tab = np.array(v["elem_var_tab"].data)
        else:
            self.elem_tab = np.ones((nblk, len(self.elemental)), dtype=np.int64)

        # Sets
        nss = int(d.get("num_side_sets") or 0)
        ss_ids = np.array(v["ss_prop1"].data) if "ss_prop1" in v else np.arange(1, nss + 1)
        ss_names = decode_names(v.get("ss_names"), nss)
        self.sidesets = []
        for i in range(nss):
            n = int(d.get(f"num_side_ss{i + 1}") or 0)
            self.sidesets.append(dict(idx=i, id=int(ss_ids[i]), name=ss_names[i] or str(ss_ids[i]), n=n))
        nns = int(d.get("num_node_sets") or 0)
        ns_ids = np.array(v["ns_prop1"].data) if "ns_prop1" in v else np.arange(1, nns + 1)
        ns_names = decode_names(v.get("ns_names"), nns)
        self.nodesets = []
        for i in range(nns):
            n = int(d.get(f"num_nod_ns{i + 1}") or 0)
            self.nodesets.append(dict(idx=i, id=int(ns_ids[i]), name=ns_names[i] or str(ns_ids[i]), n=n))

    # -- metadata -------------------------------------------------------
    def meta(self):
        lo = self.xyz.min(axis=0).tolist() if len(self.xyz) else [0, 0, 0]
        hi = self.xyz.max(axis=0).tolist() if len(self.xyz) else [0, 0, 0]
        return dict(
            file=self.path,
            dim=self.dim,
            nnodes=int(self.xyz.shape[0]),
            nelem=int(self.nelem),
            bbox=[lo, hi],
            times=self.times.tolist(),
            blocks=[dict(id=b["id"], name=b["name"], type=b["type"], nelem=b["nelem"], dim=b["dim"]) for b in self.blocks],
            sidesets=[dict(id=s["id"], name=s["name"], n=s["n"]) for s in self.sidesets],
            nodesets=[dict(id=s["id"], name=s["name"], n=s["n"]) for s in self.nodesets],
            nodal=self.nodal,
            elemental=self.elemental,
            globals=self.globals,
            displacements=self.displacement_prefixes(),
        )

    def displacement_prefixes(self):
        names = set(self.nodal)
        out = []
        for n in self.nodal:
            if n.endswith("_x"):
                p = n[:-2]
                comps = [c for c in ("x", "y", "z") if f"{p}_{c}" in names]
                if len(comps) >= min(2, self.dim):
                    out.append(p)
        out.sort(key=lambda p: (p != "disp", p))
        return out

    # -- geometry -------------------------------------------------------
    def nodes(self):
        return pack({}, [("xyz", self.xyz.astype(np.float32))])

    def _elem_mask(self, b, cut):
        if cut is None or "centroid" not in b:
            return None
        axis, pos, sign = cut
        return sign * (b["centroid"][:, axis] - pos) >= 0

    def surface(self, block_ids=None, cut=None):
        """Visible geometry. Triangles come 3D skin first, then lower-d polygons
        (header ntri3 splits them so the client can offset the latter); 1D
        elements come back as `line` segments with their element ids.
        block_ids may hold ids or names."""
        faces3, felem3, polys2, pelem2, lines1, lelem1 = [], [], [], [], [], []
        for b in self.blocks:
            if b["nelem"] == 0 or not b.get("fam"):
                continue
            if block_ids is not None and b["id"] not in block_ids and b["name"] not in block_ids:
                continue
            mask = self._elem_mask(b, cut)
            if b["dim"] == 3:
                f, fe = b["faces"], b["face_elem"]
                if mask is not None:
                    m = np.repeat(mask, b["nf"])
                    f, fe = f[m], fe[m]
                faces3.append(f)
                felem3.append(fe)
            elif b["dim"] == 2:
                p = b["ext"][:, [0, 1, 2, 3 if b["corners"].shape[1] >= 4 else b["corners"].shape[1]]]
                e = b["offset"] + np.arange(b["nelem"])
                if mask is not None:
                    p, e = p[mask], e[mask]
                polys2.append(p)
                pelem2.append(e)
            elif b["dim"] == 1:
                c = b["corners"][:, :2]
                e = b["offset"] + np.arange(b["nelem"])
                if mask is not None:
                    c, e = c[mask], e[mask]
                lines1.append(c)
                lelem1.append(e)

        def polys_to_tris(B, BE):
            isq = B[:, 3] >= 0
            tri = np.concatenate([B[:, [0, 1, 2]], B[isq][:, [0, 2, 3]]])
            tri_elem = np.concatenate([BE, BE[isq]])
            ed = [B[:, [0, 1]], B[:, [1, 2]], B[~isq][:, [2, 0]], B[isq][:, [2, 3]], B[isq][:, [3, 0]]]
            return tri, tri_elem, np.concatenate(ed)

        empty4 = np.zeros((0, 4), dtype=np.int64)
        empty1 = np.zeros((0,), dtype=np.int64)
        B3, BE3 = empty4, empty1
        if faces3:
            F = np.concatenate(faces3)
            E = np.concatenate(felem3)
            keys = np.ascontiguousarray(np.sort(F, axis=1))
            void = keys.view(np.dtype((np.void, keys.dtype.itemsize * 4))).ravel()
            _, idx, counts = np.unique(void, return_index=True, return_counts=True)
            keep = idx[counts == 1]
            B3, BE3 = F[keep], E[keep]
        B2 = np.concatenate(polys2) if polys2 else empty4
        BE2 = np.concatenate(pelem2) if polys2 else empty1

        tri3, te3, ed3 = polys_to_tris(B3, BE3)
        tri2, te2, ed2 = polys_to_tris(B2, BE2)
        tri = np.concatenate([tri3, tri2])
        tri_elem = np.concatenate([te3, te2])
        Ed = np.concatenate([ed3, ed2])
        if len(Ed):
            Ed = np.unique(np.sort(Ed, axis=1), axis=0)
        line = np.concatenate(lines1) if lines1 else np.zeros((0, 2), dtype=np.int64)
        line_elem = np.concatenate(lelem1) if lines1 else empty1
        hdr = dict(ntri=int(len(tri)), ntri3=int(len(tri3)), nedge=int(len(Ed)), nline=int(len(line)))
        return pack(hdr, [("tri", tri.astype(np.uint32)), ("triElem", tri_elem.astype(np.uint32)),
                          ("edges", Ed.astype(np.uint32)), ("line", line.astype(np.uint32)),
                          ("lineElem", line_elem.astype(np.uint32))])

    def _side_nodes(self, elems0, sides0):
        """(n,4) corner node ids of the given sides, -1 padded, plus the side dims."""
        blk = np.searchsorted(self.offsets, elems0, side="right") - 1
        out = -np.ones((len(elems0), 4), dtype=np.int64)
        dims = np.zeros(len(elems0), dtype=np.int64)
        for jb in np.unique(blk):
            b = self.blocks[jb]
            if not b.get("fam"):
                continue
            m = blk == jb
            local = elems0[m] - b["offset"]
            tbl = b["tbl"]
            s = np.clip(sides0[m], 0, len(tbl) - 1)
            out[m] = b["ext"][local[:, None], tbl[s]]
            dims[m] = b["dim"]
        return out, dims

    def sideset(self, ssid):
        s = next((s for s in self.sidesets if s["id"] == ssid or s["name"] == str(ssid)), None)
        if s is None or s["n"] == 0:
            return pack(dict(ntri=0, nedge=0, npoint=0), [])
        v = self.nc.variables
        elems0 = np.array(v[f"elem_ss{s['idx'] + 1}"].data, dtype=np.int64) - 1
        sides0 = np.array(v[f"side_ss{s['idx'] + 1}"].data, dtype=np.int64) - 1
        F, dims = self._side_nodes(elems0, sides0)
        f3 = F[dims == 3]
        isq = f3[:, 3] >= 0
        tri = np.concatenate([f3[:, [0, 1, 2]], f3[isq][:, [0, 2, 3]]])
        ed = [f3[:, [0, 1]], f3[:, [1, 2]], f3[~isq][:, [2, 0]], f3[isq][:, [2, 3]], f3[isq][:, [3, 0]],
              F[dims == 2][:, [0, 1]]]
        Ed = np.concatenate(ed)
        pts = F[dims == 1][:, 0]
        return pack(dict(ntri=int(len(tri)), nedge=int(len(Ed)), npoint=int(len(pts))),
                    [("tri", tri.astype(np.uint32)), ("edges", Ed.astype(np.uint32)), ("points", pts.astype(np.uint32))])

    def nodeset(self, nsid):
        s = next((s for s in self.nodesets if s["id"] == nsid or s["name"] == str(nsid)), None)
        if s is None or s["n"] == 0:
            return pack(dict(npoint=0), [])
        pts = np.array(self.nc.variables[f"node_ns{s['idx'] + 1}"].data, dtype=np.int64) - 1
        return pack(dict(npoint=int(len(pts))), [("points", pts.astype(np.uint32))])

    # -- fields ---------------------------------------------------------
    def _nodal(self, i, step):
        v = self.nc.variables
        key = f"vals_nod_var{i + 1}"
        if key in v:
            return np.array(v[key].data[step], dtype=np.float32)
        return np.array(v["vals_nod_var"].data[step, i], dtype=np.float32)

    def _elemental(self, i, step):
        v = self.nc.variables
        out = np.full(self.nelem, np.nan, dtype=np.float32)
        for b in self.blocks:
            if b["nelem"] == 0:
                continue
            key = f"vals_elem_var{i + 1}eb{b['idx'] + 1}"
            if key in v and (b["idx"] >= len(self.elem_tab) or i >= self.elem_tab.shape[1] or self.elem_tab[b["idx"], i]):
                out[b["offset"]: b["offset"] + b["nelem"]] = v[key].data[step]
        return out

    def field(self, name, step):
        """One field at one step. Besides file variables: `block` (elemental block
        index, categorical) and `mag:<prefix>` (nodal magnitude of <prefix>_x/y/z)."""
        step = int(np.clip(step, 0, self.nsteps - 1))
        if name in self.nodal:
            return "nodal", self._nodal(self.nodal.index(name), step)
        if name in self.elemental:
            return "elemental", self._elemental(self.elemental.index(name), step)
        if name == "block":
            out = np.full(self.nelem, np.nan, dtype=np.float32)
            for k, b in enumerate(self.blocks):
                out[b["offset"]: b["offset"] + b["nelem"]] = k
            return "elemental", out
        if name.startswith("mag:"):
            comps = [f"{name[4:]}_{c}" for c in "xyz" if f"{name[4:]}_{c}" in self.nodal]
            if not comps:
                raise KeyError(name)
            sq = sum(self._nodal(self.nodal.index(c), step).astype(np.float64) ** 2 for c in comps)
            return "nodal", np.sqrt(sq).astype(np.float32)
        raise KeyError(name)

    def var(self, name, step):
        with self.lock:
            kind, a = self.field(name, step)
        finite = a[np.isfinite(a)]
        lo, hi = (float(finite.min()), float(finite.max())) if finite.size else (0.0, 0.0)
        hdr = dict(kind=kind, name=name, step=step, min=lo, max=hi)
        if name == "block":
            hdr["categories"] = [b["name"] for b in self.blocks]
        return pack(hdr, [("values", a)])

    def range(self, name):
        lo, hi = np.inf, -np.inf
        with self.lock:
            for s in range(self.nsteps):
                _, a = self.field(name, s)
                f = a[np.isfinite(a)]
                if f.size:
                    lo, hi = min(lo, float(f.min())), max(hi, float(f.max()))
        if not np.isfinite(lo):
            lo, hi = 0.0, 0.0
        return dict(name=name, min=lo, max=hi)

    def global_vars(self):
        v = self.nc.variables
        if not self.globals or "vals_glo_var" not in v:
            return dict(names=[], times=self.times.tolist(), values=[])
        vals = np.array(v["vals_glo_var"].data, dtype=np.float64)
        if vals.ndim == 1:
            vals = vals.reshape(-1, len(self.globals))
        return dict(names=self.globals, times=self.times.tolist(), values=vals.tolist())

    def probe(self, node, elem, step):
        step = int(np.clip(step, 0, self.nsteps - 1))
        out = dict(step=step, time=float(self.times[step]))
        with self.lock:
            if node is not None and 0 <= node < len(self.xyz):
                vals = {n: float(self._nodal(i, step)[node]) for i, n in enumerate(self.nodal)}
                out["node"] = dict(id=int(node), xyz=self.xyz[node].tolist(), values=vals)
            if elem is not None and 0 <= elem < self.nelem:
                jb = int(np.searchsorted(self.offsets, elem, side="right") - 1)
                b = self.blocks[jb]
                vals = {}
                v = self.nc.variables
                local = elem - b["offset"]
                for i, n in enumerate(self.elemental):
                    key = f"vals_elem_var{i + 1}eb{b['idx'] + 1}"
                    if key in v:
                        vals[n] = float(v[key].data[step, local])
                out["elem"] = dict(id=int(elem), block=b["id"], block_name=b["name"], type=b["type"],
                                   local=int(local), nodes=b["corners"][local].tolist(), values=vals)
        return out


# ---------------------------------------------------------------------------
FILES = {}
FILES_LOCK = threading.Lock()
DEFAULT_FILE = [None]
SNAP_DIR = [os.path.join(os.getcwd(), "exodus-snapshots")]


def get_file(path):
    if not path:
        path = DEFAULT_FILE[0]
    if not path:
        raise FileNotFoundError("no file given; pass ?file=<path> or start the server with a file")
    path = os.path.abspath(os.path.expanduser(path))
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    with FILES_LOCK:
        ex = FILES.get(path)
        if ex is None or os.path.getmtime(path) != ex.mtime:
            ex = Exodus(path)
            FILES[path] = ex
        return ex


def parse_cut(s):
    if not s:
        return None
    axis, pos, sign = s.split(":")
    return "xyz".index(axis.lower()), float(pos), (1 if sign in ("+", "1", "") else -1)


def parse_ids(s):
    """Comma list of ids and/or names -> set holding ints for ids and strings for names."""
    if s is None or s == "":
        return None
    out = set()
    for x in s.split(","):
        if x == "":
            continue
        out.add(int(x) if x.lstrip("-").isdigit() else x)
    return out


def parse_id(s):
    return int(s) if s.lstrip("-").isdigit() else s


class Handler(BaseHTTPRequestHandler):
    server_version = "exodus-view/1"

    def log_message(self, fmt, *args):
        if "/api/" not in (args[0] if args else ""):
            sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        # Reports are opened as file:// pages and fetch from here; allow that.
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj).encode(), "application/json")

    def _bin(self, blob):
        self._send(200, blob, "application/octet-stream")

    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            if u.path in ("/", "/index.html"):
                with open(VIEWER, "rb") as f:
                    return self._send(200, f.read(), "text/html; charset=utf-8")
            if u.path == "/embed.js":
                with open(EMBED, "rb") as f:
                    return self._send(200, f.read(), "application/javascript; charset=utf-8")
            if not u.path.startswith("/api/"):
                return self._json({"error": "not found"}, 404)
            ep = u.path[5:]
            if ep == "files":
                with FILES_LOCK:
                    return self._json(dict(files=sorted(FILES), default=DEFAULT_FILE[0], snap_dir=SNAP_DIR[0]))
            if ep == "text":
                p = os.path.abspath(os.path.expanduser(q["path"]))
                if not os.path.isfile(p):
                    raise FileNotFoundError(p)
                if os.path.getsize(p) > 2_000_000:
                    return self._json({"error": "file larger than 2 MB"}, 413)
                with open(p, "rb") as f:
                    return self._send(200, f.read(), "text/plain; charset=utf-8")
            ex = get_file(q.get("file"))
            if ep == "meta":
                return self._json(ex.meta())
            if ep == "nodes":
                return self._bin(ex.nodes())
            if ep == "surface":
                return self._bin(ex.surface(parse_ids(q.get("blocks")), parse_cut(q.get("cut"))))
            if ep == "var":
                return self._bin(ex.var(q["name"], int(q.get("step", 0))))
            if ep == "range":
                return self._json(ex.range(q["name"]))
            if ep == "globals":
                return self._json(ex.global_vars())
            if ep == "sideset":
                return self._bin(ex.sideset(parse_id(q["id"])))
            if ep == "nodeset":
                return self._bin(ex.nodeset(parse_id(q["id"])))
            if ep == "probe":
                node = int(q["node"]) if "node" in q else None
                elem = int(q["elem"]) if "elem" in q else None
                return self._json(ex.probe(node, elem, int(q.get("step", 0))))
            return self._json({"error": f"unknown endpoint {ep}"}, 404)
        except FileNotFoundError as e:
            return self._json({"error": f"file not found: {e}"}, 404)
        except (KeyError, ValueError) as e:
            return self._json({"error": f"{type(e).__name__}: {e}"}, 400)
        except Exception as e:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            return self._json({"error": f"{type(e).__name__}: {e}"}, 500)

    def do_POST(self):
        u = urlparse(self.path)
        try:
            n = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(n) or b"{}")
            if u.path == "/api/snapshot":
                name = re.sub(r"[^A-Za-z0-9._-]+", "_", body.get("name") or "snapshot").strip("_") or "snapshot"
                snap_dir = os.path.abspath(os.path.expanduser(body.get("dir") or SNAP_DIR[0]))
                os.makedirs(snap_dir, exist_ok=True)
                png_path = os.path.join(snap_dir, name + ".png")
                json_path = os.path.join(snap_dir, name + ".json")
                png = body.get("png", "")
                png = png.split(",", 1)[1] if "," in png else png
                with open(png_path, "wb") as f:
                    f.write(base64.b64decode(png))
                with open(json_path, "w") as f:
                    json.dump(body.get("state", {}), f, indent=1)
                print(f"snapshot: {png_path}", flush=True)
                return self._json(dict(png=png_path, state=json_path))
            return self._json({"error": "not found"}, 404)
        except Exception as e:  # noqa: BLE001
            return self._json({"error": f"{type(e).__name__}: {e}"}, 500)


def existing_server(port):
    """Return /api/files of an exodus-view already on this port, else None."""
    import urllib.request
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/files", timeout=1) as r:
            if r.headers.get("Server", "").startswith("exodus-view"):
                return json.loads(r.read())
    except Exception:  # noqa: BLE001
        pass
    return None


def free_port(start):
    for p in range(start, start + 50):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", p))
                return p
            except OSError:
                continue
    raise RuntimeError("no free port")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("files", nargs="*", help="exodus files to preload; the first is the default")
    ap.add_argument("--port", type=int, default=0, help="port (default: first free from 8765)")
    ap.add_argument("--open", action="store_true", help="open the viewer in a browser")
    ap.add_argument("--snap-dir", default=SNAP_DIR[0], help="where /api/snapshot writes PNG + JSON")
    ap.add_argument("--query", default="", help="extra query string for the opened URL, e.g. 'var=u&step=last'")
    ap.add_argument("--new", action="store_true", help="start a new server even if one is already running on the port")
    a = ap.parse_args()

    SNAP_DIR[0] = os.path.abspath(a.snap_dir)

    # Reuse a viewer that is already serving on the requested port: any file
    # can be opened through ?file=, so a second launch only needs the URL.
    running = existing_server(a.port or 8765)
    if running is not None and not a.new:
        url = f"http://127.0.0.1:{a.port or 8765}/"
        if a.files:
            url += "?file=" + quote(os.path.abspath(os.path.expanduser(a.files[0])))
            if a.query:
                url += "&" + a.query
        print(f"exodus-view: {url}  (server already running)", flush=True)
        print(f"snapshots: {running.get('snap_dir')}", flush=True)
        if a.open:
            webbrowser.open(url)
        return

    for f in a.files:
        ex = get_file(f)
        if DEFAULT_FILE[0] is None:
            DEFAULT_FILE[0] = ex.path
        m = ex.meta()
        print(f"loaded {ex.path}: dim={m['dim']} nodes={m['nnodes']} elems={m['nelem']} steps={len(m['times'])} "
              f"blocks={len(m['blocks'])} nodal={m['nodal']} elemental={len(m['elemental'])} globals={len(m['globals'])}",
              flush=True)

    port = a.port or free_port(8765)
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    srv.daemon_threads = True
    url = f"http://127.0.0.1:{port}/"
    if DEFAULT_FILE[0]:
        url += "?file=" + quote(DEFAULT_FILE[0])
        if a.query:
            url += "&" + a.query
    print(f"exodus-view: {url}", flush=True)
    print(f"snapshots: {SNAP_DIR[0]}", flush=True)
    if a.open:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
