"""Minimal binary FBX (7.x) reader: meshes in world space, converted to the
spec's CAD frame in normalized units U (overall length 1000 U)."""
from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass, field

import numpy as np


@dataclass
class Node:
    name: str
    props: list
    children: list = field(default_factory=list)

    def find(self, name):
        return next((c for c in self.children if c.name == name), None)

    def findall(self, name):
        return [c for c in self.children if c.name == name]


def _read_prop(buf, o):
    t = chr(buf[o]); o += 1
    scalar = {"Y": "<h", "C": "<?", "I": "<i", "F": "<f", "D": "<d", "L": "<q"}
    if t in scalar:
        fmt = scalar[t]
        return struct.unpack_from(fmt, buf, o)[0], o + struct.calcsize(fmt)
    if t in "fdlib":
        n, enc, clen = struct.unpack_from("<III", buf, o); o += 12
        raw = buf[o:o + clen]; o += clen
        if enc == 1:
            raw = zlib.decompress(raw)
        dt = {"f": "<f4", "d": "<f8", "l": "<i8", "i": "<i4", "b": "?"}[t]
        return np.frombuffer(raw, dtype=dt, count=n), o
    if t in "SR":
        n = struct.unpack_from("<I", buf, o)[0]; o += 4
        v = bytes(buf[o:o + n]); o += n
        return (v.decode("utf-8", "replace") if t == "S" else v), o
    raise ValueError(f"unknown FBX property type {t!r}")


def _read_node(buf, o, wide):
    if wide:
        end, nprops, _plen = struct.unpack_from("<QQQ", buf, o); o += 24
    else:
        end, nprops, _plen = struct.unpack_from("<III", buf, o); o += 12
    nlen = buf[o]; o += 1
    if end == 0:
        return None, o
    name = bytes(buf[o:o + nlen]).decode(); o += nlen
    props = []
    for _ in range(nprops):
        v, o = _read_prop(buf, o)
        props.append(v)
    node = Node(name, props)
    sentinel = 25 if wide else 13
    while o < end - sentinel or (o < end and end - o > sentinel):
        child, o = _read_node(buf, o, wide)
        if child is None:
            break
        node.children.append(child)
    return node, end


def parse(path):
    buf = memoryview(open(path, "rb").read())
    assert bytes(buf[:20]) == b"Kaydara FBX Binary  "
    version = struct.unpack_from("<I", buf, 23)[0]
    wide = version >= 7500
    o, top = 27, []
    while o < len(buf) - 200:
        n, o = _read_node(buf, o, wide)
        if n is None:
            break
        top.append(n)
    return Node("root", [], top)


def _p70(model):
    out = {}
    p70 = model.find("Properties70")
    if p70:
        for p in p70.findall("P"):
            out[p.props[0]] = p.props[4:]
    return out


def _euler_xyz(r):
    rx, ry, rz = np.radians(r)
    cx, sx, cy, sy, cz, sz = np.cos(rx), np.sin(rx), np.cos(ry), np.sin(ry), np.cos(rz), np.sin(rz)
    Rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    Ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    Rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    return Rz @ Ry @ Rx


def _local(props):
    def v(k, d):
        return np.array(props.get(k, d), dtype=float)
    T = v("Lcl Translation", (0, 0, 0))
    R = _euler_xyz(v("Lcl Rotation", (0, 0, 0)))
    pre = _euler_xyz(v("PreRotation", (0, 0, 0)))
    post = _euler_xyz(v("PostRotation", (0, 0, 0)))
    S = np.diag(v("Lcl Scaling", (1, 1, 1)))
    M = np.eye(4)
    M[:3, :3] = pre @ R @ post.T @ S
    M[:3, 3] = T
    G = np.eye(4)  # geometric (non-inherited) offset
    G[:3, :3] = _euler_xyz(v("GeometricRotation", (0, 0, 0))) @ np.diag(v("GeometricScaling", (1, 1, 1)))
    G[:3, 3] = v("GeometricTranslation", (0, 0, 0))
    return M, G


L_CM = 454.74294878
def world_to_cad(p):
    """World cm (FBX Y-up, front +Z) -> CAD U per spec section A."""
    p = np.asarray(p, float)
    return np.stack([(244.88681665 - p[:, 2]) * 1000 / L_CM,
                     -p[:, 0] * 1000 / L_CM,
                     (p[:, 1] + 91.34872001) * 1000 / L_CM], axis=1)


@dataclass
class Mesh:
    name: str
    verts: np.ndarray        # (n,3) CAD U
    tris: np.ndarray         # (m,3) int
    tri_mat: np.ndarray      # (m,) material name index into mats
    mats: list


def load(path):
    root = parse(path)
    objs = root.find("Objects")
    conns = root.find("Connections")
    by_id = {n.props[0]: n for n in objs.children}
    parent, children = {}, {}
    for c in conns.findall("C"):
        kind, child, par = c.props[:3]
        if kind == "OO":
            children.setdefault(par, []).append(child)
            if by_id.get(child) is not None and by_id[child].name == "Model":
                parent[child] = par
    world = {}

    def wm(mid):
        if mid in world:
            return world[mid]
        M, _ = _local(_p70(by_id[mid]))
        p = parent.get(mid, 0)
        W = (wm(p) if p in by_id and by_id[p].name == "Model" else np.eye(4)) @ M
        world[mid] = W
        return W

    meshes = {}
    for mid, n in by_id.items():
        if n.name != "Model":
            continue
        mname = n.props[1].split("\x00")[0]
        kids = [by_id[k] for k in children.get(mid, []) if k in by_id]
        geo = next((k for k in kids if k.name == "Geometry"), None)
        if geo is None:
            continue
        mats = [k.props[1].split("\x00")[0] for k in kids if k.name == "Material"]
        _, G = _local(_p70(n))
        W = wm(mid) @ G
        v = geo.find("Vertices").props[0].reshape(-1, 3)
        vw = (W[:3, :3] @ v.T).T + W[:3, 3]
        idx = geo.find("PolygonVertexIndex").props[0]
        polys, cur = [], []
        for i in idx:
            if i < 0:
                cur.append(~i); polys.append(cur); cur = []
            else:
                cur.append(i)
        lem = geo.find("LayerElementMaterial")
        pm = np.zeros(len(polys), int)
        if lem is not None:
            arr = lem.find("Materials").props[0]
            mapping = lem.find("MappingInformationType").props[0]
            pm = np.full(len(polys), arr[0]) if mapping == "AllSame" else np.asarray(arr)
        tris, tm = [], []
        for p, m in zip(polys, pm):
            for k in range(1, len(p) - 1):
                tris.append((p[0], p[k], p[k + 1])); tm.append(m)
        meshes[mname] = Mesh(mname, world_to_cad(vw), np.array(tris), np.array(tm), mats)
    return meshes


if __name__ == "__main__":
    import sys
    ms = load(sys.argv[1])
    allv = np.concatenate([m.verts for m in ms.values()])
    print("meshes", len(ms), "verts", len(allv), "tris", sum(len(m.tris) for m in ms.values()))
    print("CAD bbox U", allv.min(0).round(3), allv.max(0).round(3))
    for m in ms.values():
        print(f"{m.name:16s} {m.verts.min(0).round(2)} {m.verts.max(0).round(2)} mats={m.mats}")
