"""Extract CAD construction guides from the source FBX mesh (all in CAD U).

Output: data/myvi_v2_guides.json, consumed by src/myvi_v2.py.
Every guide is measured from the assembled source mesh; nothing here is a
reconstruction assumption except the sampling choices noted inline.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import shapely
from shapely.geometry import LineString, Polygon, box
from shapely.ops import unary_union

sys.path.insert(0, str(Path(__file__).parent))
from fbx_read import load  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FBX = ROOT / "source" / "2005 perodua myvi.fbx"
OUT = ROOT / "data" / "myvi_v2_guides.json"

MIRROR_BOX = ((310.0, 183.0, 264.0), (362.0, 253.0, 313.0))


def sel(mesh, mats=None, exclude=None, keep=None):
    """Triangle coordinates (m,3,3) of a mesh filtered by material / predicate."""
    t = mesh.verts[mesh.tris]
    mask = np.ones(len(t), bool)
    names = np.array(mesh.mats)[mesh.tri_mat] if mesh.mats else np.array([""] * len(t))
    if mats is not None:
        mask &= np.isin(names, mats)
    if exclude is not None:
        mask &= ~np.isin(names, exclude)
    if keep is not None:
        mask &= keep(t)
    return t[mask]


def in_box(t, lo, hi):
    c = t.mean(1)
    return np.all((c >= lo) & (c <= hi), axis=1)


def plane_segments(tris, axis, value):
    """Intersect triangles with plane coord[axis]=value -> (k,2,3) segments."""
    d = tris[:, :, axis] - value
    s = np.sign(d)
    cross = (s.max(1) > 0) & (s.min(1) < 0)
    segs = []
    for tri, dd in zip(tris[cross], d[cross]):
        pts = []
        for i, j in ((0, 1), (1, 2), (2, 0)):
            if (dd[i] > 0) != (dd[j] > 0):
                f = dd[i] / (dd[i] - dd[j])
                pts.append(tri[i] + f * (tri[j] - tri[i]))
        if len(pts) == 2:
            segs.append(pts)
    return np.array(segs).reshape(-1, 2, 3)


def ray_envelope(seg2d, center, angles):
    """Farthest intersection of rays from `center` with 2D segments, per angle.
    Returns (n,2) points; NaN where no hit."""
    a, b = seg2d[:, 0], seg2d[:, 1]
    out = np.full((len(angles), 2), np.nan)
    for k, th in enumerate(angles):
        dvec = np.array([math.cos(th), math.sin(th)])
        e = b - a
        w = a - center
        den = dvec[0] * e[:, 1] - dvec[1] * e[:, 0]
        ok = np.abs(den) > 1e-12
        t = np.where(ok, (w[:, 0] * e[:, 1] - w[:, 1] * e[:, 0]) / np.where(ok, den, 1), -1)
        u = np.where(ok, (w[:, 0] * dvec[1] - w[:, 1] * dvec[0]) / np.where(ok, den, 1), -1)
        hit = ok & (t > 0) & (u >= 0) & (u <= 1)
        if hit.any():
            out[k] = center + dvec * t[hit].max()
    return out


def fill_nan(pts):
    idx = np.arange(len(pts))
    good = ~np.isnan(pts[:, 0])
    for c in range(2):
        pts[:, c] = np.interp(idx, idx[good], pts[good, c])
    return pts


def half_section(segs_yz, n_rays=72):
    """Right-half outer envelope (y>=0) in YZ, bottom-centre -> top-centre,
    sampled by rays from the section's mid-height on the symmetry plane."""
    z = segs_yz[:, :, 1]
    zc = 0.5 * (z.min() + z.max())
    # rays from straight down (-90deg) through +Y to straight up (+90deg)
    ang = np.linspace(-math.pi / 2, math.pi / 2, n_rays)
    pts = ray_envelope(segs_yz, np.array([0.0, zc]), ang)
    pts = fill_nan(pts)
    pts[0, 0] = 0.0
    pts[-1, 0] = 0.0
    return pts


def section_fields(seg_yz, zg, yg):
    """Outer envelope fields of one section: max |y| per z, max/min z per |y|."""
    a, b = seg_yz[:, 0], seg_yz[:, 1]
    n = np.maximum(2, (np.linalg.norm(b - a, axis=1) / 0.25).astype(int) + 2)
    pts = np.concatenate([a[i] + np.linspace(0, 1, n[i])[:, None] * (b[i] - a[i]) for i in range(len(a))])
    y, z = np.abs(pts[:, 0]), pts[:, 1]
    ymax = np.full(len(zg), np.nan)
    zi = np.clip(np.round(z).astype(int), 0, len(zg) - 1)
    np.fmax.at(ymax, zi, y)
    yi = np.clip(np.round(y).astype(int), 0, len(yg) - 1)
    zmax = np.full(len(yg), np.nan); np.fmax.at(zmax, yi, z)
    zmin = np.full(len(yg), np.nan); np.fmin.at(zmin, yi, z)
    return ymax, zmax, zmin


def fields_to_half(ymax, zmax, zmin, zg, yg, close_max=4.0):
    """Intersect the 'below top / above floor' and 'inside side' regions;
    return the right-half outline from bottom centre to top centre."""
    gy = ~np.isnan(zmax)
    if gy.sum() < 2:
        return None
    # floor never higher, roof never lower, than anything further outboard
    zmin = zmin.copy(); zmax = zmax.copy()
    zmin[gy] = np.minimum.accumulate(zmin[gy][::-1])[::-1]
    zmax[gy] = np.maximum.accumulate(zmax[gy][::-1])[::-1]
    ys = yg[gy]
    A = Polygon(list(zip(ys, zmin[gy])) + list(zip(ys[::-1], zmax[gy][::-1]))).buffer(0)
    gz = ~np.isnan(ymax)
    zs = zg[gz]
    B = Polygon([(0, zs[0] - 1)] + list(zip(ymax[gz], zs)) + [(0, zs[-1] + 1)]).buffer(0)
    R = A.intersection(B)
    R = max(getattr(R, "geoms", [R]), key=lambda g: g.area)
    close = min(close_max, 0.15 * min(R.bounds[2] - R.bounds[0], R.bounds[3] - R.bounds[1]))
    R = R.buffer(close, join_style=1).buffer(-close, join_style=1)  # SAMPLING: close slits < 8 U
    R = max(getattr(R, "geoms", [R]), key=lambda g: g.area)
    R = R.simplify(0.15)
    ring = np.asarray(R.exterior.coords)[:-1]
    # walk from the lowest point on y~0 through +y to the highest point on y~0
    on_axis = ring[:, 0] < 1.2
    lo = int(np.argmin(np.where(on_axis, ring[:, 1], np.inf)))
    hi = int(np.argmax(np.where(on_axis, ring[:, 1], -np.inf)))
    ring = np.roll(ring, -lo, axis=0)
    hi = (hi - lo) % len(ring)
    path = ring[: hi + 1]
    if np.mean(path[:, 0]) < np.mean(ring[hi:, 0]):  # wrong direction: take the other arc
        path = np.vstack([ring[hi:], ring[:1]])[::-1]
    path[0, 0] = 0.0
    path[-1, 0] = 0.0
    return path


def plane_frame(tris):
    """Area-weighted best plane of a patch, normal pointing away from the cabin."""
    cr = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    area = np.linalg.norm(cr, axis=1)
    c = (tris.mean(1) * area[:, None]).sum(0) / area.sum()
    out = c - np.array([500.0, 0.0, 150.0])
    cr = np.where((cr @ out)[:, None] < 0, -cr, cr)  # orient all facets outward
    n = cr.sum(0); n /= np.linalg.norm(n)
    ref = np.array([0, 0, 1.0]) if abs(n[2]) < 0.9 else np.array([1.0, 0, 0])
    u = np.cross(ref, n); u /= np.linalg.norm(u)
    v = np.cross(n, u)
    return c, u, v, n


def ray_heights(tris, c, u, v, n, pts2):
    """Outermost hit height along n above each (a, b) plane point."""
    o = c + pts2[:, :1] * u + pts2[:, 1:] * v
    p0, e1, e2 = tris[:, 0], tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0]
    pv = np.cross(n, e2)
    det = (e1 * pv).sum(1)
    ok = np.abs(det) > 1e-12
    inv = np.where(ok, 1 / np.where(ok, det, 1), 0)
    h = np.full(len(o), np.nan)
    for i, oi in enumerate(o):
        tv = oi - p0
        uu = (tv * pv).sum(1) * inv
        qv = np.cross(tv, e1)
        vv = (qv @ n) * inv
        t = (e2 * qv).sum(1) * inv
        hit = ok & (uu >= 0) & (vv >= 0) & (uu + vv <= 1)
        if hit.any():
            h[i] = t[hit].max()
    return h


def patch_entry(tris, grid=0, simplify=0.3):
    """Plane frame + projected outline (+ optional height grid) of a patch."""
    from scipy.interpolate import griddata

    c, u, v, n = plane_frame(tris)
    rel = tris - c
    uv = np.stack([rel @ u, rel @ v], -1)
    polys = [Polygon(t).buffer(0.05) for t in uv if Polygon(t).area > 1e-6]
    # SAMPLING: bridge gaps < 6 U between islands of one pane (split source glass)
    merged = unary_union(polys).buffer(3.0, join_style=2).buffer(-3.05, join_style=2)
    poly = max(getattr(merged, "geoms", [merged]), key=lambda g: g.area)
    poly = poly.simplify(simplify)
    poly = max(getattr(poly, "geoms", [poly]), key=lambda g: g.area)
    e = {"origin": c.round(4).tolist(), "u": u.round(6).tolist(), "v": v.round(6).tolist(),
         "n": n.round(6).tolist(), "outline_uv": np.asarray(poly.exterior.coords)[:-1].round(3).tolist(),
         "area": round(poly.area, 2)}
    if grid:
        a0, b0, a1, b1 = poly.bounds
        A, B = np.meshgrid(np.linspace(a0 - 4, a1 + 4, grid), np.linspace(b0 - 4, b1 + 4, grid), indexing="ij")
        p2 = np.stack([A.ravel(), B.ravel()], 1)
        h = ray_heights(tris, c, u, v, n, p2)
        good = ~np.isnan(h)
        h[~good] = griddata(p2[good], h[good], p2[~good], method="nearest")
        # replace nearest-fill outside the patch with a linear extrapolation of the plane fit
        H = h.reshape(A.shape)
        e["grid"] = {"a": A[:, 0].round(3).tolist(), "b": B[0].round(3).tolist(), "h": H.round(3).tolist()}
    return e


def hull_ring(seg2d, n):
    """SAMPLING: convex hull of a section's intersection points, resampled to
    n points starting at its lowest-x point (smooth, consistent loft guide)."""
    from shapely.geometry import MultiPoint
    h = MultiPoint(seg2d.reshape(-1, 2)).convex_hull
    ring = np.asarray(h.exterior.coords)
    k = int(np.argmin(ring[:-1, 0]))
    ring = np.vstack([np.roll(ring[:-1], -k, axis=0), np.roll(ring[:-1], -k, axis=0)[:1]])
    return resample(ring, n).round(3).tolist()


def resample(poly_xy, n, start=None):
    """Closed polyline -> n points evenly spaced by arc length, starting at the
    vertex nearest `start`."""
    p = np.asarray(poly_xy, float)
    if np.allclose(p[0], p[-1]):
        p = p[:-1]
    if start is not None:
        k = int(np.argmin(np.linalg.norm(p - start, axis=1)))
        p = np.roll(p, -k, axis=0)
    q = np.vstack([p, p[:1]])
    seg = np.linalg.norm(np.diff(q, axis=0), axis=1)
    s = np.concatenate([[0], np.cumsum(seg)])
    t = np.linspace(0, s[-1], n, endpoint=False)
    return np.stack([np.interp(t, s, q[:, 0]), np.interp(t, s, q[:, 1])], 1)


def boundary_loops(tris):
    """Boundary loops (lists of 3D points) of a triangle soup, largest first."""
    v = tris.reshape(-1, 3)
    key = np.round(v, 4)
    uniq, inv = np.unique(key, axis=0, return_inverse=True)
    f = inv.reshape(-1, 3)
    edges = {}
    for a, b, c in f:
        for i, j in ((a, b), (b, c), (c, a)):
            k = (min(i, j), max(i, j))
            edges[k] = edges.get(k, 0) + 1
    bnd = [k for k, n in edges.items() if n == 1]
    adj = {}
    for i, j in bnd:
        adj.setdefault(i, []).append(j)
        adj.setdefault(j, []).append(i)
    seen, loops = set(), []
    for start in adj:
        if start in seen:
            continue
        loop, prev, cur = [start], None, start
        seen.add(start)
        while True:
            nxt = [n for n in adj[cur] if n != prev and n not in seen]
            if not nxt:
                break
            prev, cur = cur, nxt[0]
            seen.add(cur)
            loop.append(cur)
        if len(loop) > 5:
            loops.append(uniq[loop])
    loops.sort(key=lambda L: -np.linalg.norm(np.diff(L, axis=0), axis=1).sum())
    return loops


def islands(tris):
    """Split a triangle soup into vertex-connected components."""
    v = np.round(tris.reshape(-1, 3), 4)
    _, inv = np.unique(v, axis=0, return_inverse=True)
    f = inv.reshape(-1, 3)
    parent = list(range(inv.max() + 1))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for a, b, c in f:
        ra, rb, rc = find(a), find(b), find(c)
        parent[rb] = ra
        parent[find(rc)] = ra
    comp = np.array([find(a) for a in f[:, 0]])
    return [tris[comp == c] for c in np.unique(comp)]


def projected_outline(tris, drop_axis, simplify=0.4, min_area=1.0):
    """Union of triangles projected along `drop_axis` -> exterior ring(s)."""
    keep = [i for i in range(3) if i != drop_axis]
    polys = []
    for t in tris[:, :, keep]:
        p = Polygon(t)
        if p.area > 1e-6:
            polys.append(p.buffer(0.05))
    u = unary_union(polys).buffer(-0.05).simplify(simplify)
    geoms = getattr(u, "geoms", [u])
    rings = [np.asarray(g.exterior.coords)[:-1].tolist() for g in geoms if g.area >= min_area]
    rings.sort(key=lambda r: -Polygon(r).area)
    return rings


def simplify_loop(loop, tol=0.6):
    ls = LineString(np.vstack([loop, loop[:1]])[:, :3])
    # simplify in 3D by Douglas-Peucker on the 2D projection with max spread
    spread = np.ptp(loop, axis=0)
    drop = int(np.argmin(spread))
    keep = [i for i in range(3) if i != drop]
    idx = []
    s2 = LineString(np.vstack([loop, loop[:1]])[:, keep]).simplify(tol)
    pts2 = np.asarray(s2.coords)[:-1]
    for p in pts2:
        idx.append(int(np.argmin(np.linalg.norm(loop[:, keep] - p, axis=1))))
    idx = sorted(set(idx))
    del ls
    return loop[idx]


def main():
    ms = load(FBX)
    G = {"units": "U", "mm_per_U": 4.5474294878}

    # ------------------------------------------------------------ body sections
    door_names = ["door_lf_ok", "door_rf_ok", "door_lr_ok", "door_rr_ok"]
    no_mirror = lambda t: ~in_box(t, *MIRROR_BOX) & ~in_box(t, (310, -253, 264), (362, -183, 313))
    shell = [sel(ms[n]) for n in ("chassis", "bonnet_ok", "bump_front_ok", "bump_rear_ok", "skirt",
                                  "windscreen_ok", "light", "l_gls")]
    shell.append(sel(ms["boot_ok"]))
    for n in door_names:
        shell.append(sel(ms[n], exclude=["door_lf_ok_4"], keep=no_mirror))
    shell = np.concatenate(shell)

    stations = [0.25, 0.8, 1.8, 3.2, 5.0, 7.5, 10.5, 14.5, 19.5, 26, 34, 43, 55, 70, 85, 95]
    stations += list(np.arange(110, 951, 20.0))
    stations += [960, 968, 975, 981, 986, 990, 993.5, 996, 998, 999.2, 999.75]
    zg = np.arange(0.0, 460.0, 1.0)
    yg = np.arange(0.0, 260.0, 1.0)
    raw = []
    for x in stations:
        segs = plane_segments(shell, 0, x)
        if len(segs) == 0:
            continue
        raw.append((float(x), *section_fields(segs[:, :, 1:], zg, yg)))
    # bridge the open wheel wells with the neighbouring closed sections
    for lo, hi in ((97.0, 285.0), (752.0, 944.0)):
        xs = [r[0] for r in raw]
        left = max(i for i, x in enumerate(xs) if x < lo)
        right = min(i for i, x in enumerate(xs) if x > hi)
        for i in range(left + 1, right):
            f = (raw[i][0] - raw[left][0]) / (raw[right][0] - raw[left][0])
            mix = lambda k: (1 - f) * raw[left][k] + f * raw[right][k]
            x, ymax, zmax, zmin = raw[i]
            ymax = np.fmax(ymax, mix(1))
            zmin = np.fmin(zmin, mix(3))
            raw[i] = (x, ymax, zmax, zmin)
    sections = []
    for x, ymax, zmax, zmin in raw:
        # SAMPLING: bumper ends bridge plate/grille recesses (< 24 U); lamps and
        # grille are rebuilt from their own outlines afterwards
        half = fields_to_half(ymax, zmax, zmin, zg, yg, 12.0 if (x < 60 or x > 960) else 4.0)
        if half is not None:
            sections.append({"x": x, "half": half.round(3).tolist()})
    G["body_sections"] = sections

    # ---------------------------------------------------------------- glazing
    glass = {}
    ws = sel(ms["windscreen_ok"], mats=["glass_001"])
    glass["windshield"] = ws
    for n in door_names:
        glass[n.replace("_ok", "").replace("door", "side_glass")] = sel(ms[n], mats=["glass_001"])
    glass["rear_glass"] = sel(ms["boot_ok"], mats=["glass_001"])
    G["glass"] = {}
    for name, t in glass.items():
        isl = sorted((i for i in islands(t) if len(i) >= 2), key=lambda i: i[:, :, 0].min())
        if name.startswith("side_glass_l") and name[-1] == "r" and len(isl) == 2:
            # rear door: main pane + fixed quarter pane split by a trim divider
            G["glass"][name] = patch_entry(isl[0], grid=14)
            G["glass"][name.replace("side_glass", "quarter_glass")] = patch_entry(isl[1], grid=10)
        elif name.startswith("side_glass_r") and name[-1] == "r" and len(isl) == 2:
            G["glass"][name] = patch_entry(isl[0], grid=14)
            G["glass"][name.replace("side_glass", "quarter_glass")] = patch_entry(isl[1], grid=10)
        else:
            G["glass"][name] = patch_entry(t, grid=14)

    # ------------------------------------------------- lamps / lenses / grille
    lamps = []
    for t in islands(sel(ms["l_gls"])):
        n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
        area = 0.5 * np.linalg.norm(n, axis=1).sum()
        if len(t) < 6 or area < 30:
            continue
        e = patch_entry(t)
        c = e["origin"]
        e["kind"] = "front" if c[0] < 500 else "rear"
        e["side"] = "r" if c[1] > 0 else "l"
        lamps.append(e)
    G["lamps"] = lamps

    def outline_entry(tris, axis, **kw):
        return projected_outline(tris, axis, **kw)

    G["grille_yz"] = outline_entry(sel(ms["bump_front_ok"], mats=["bump_front_ok_1"]), 0)
    G["front_inset_yz"] = outline_entry(sel(ms["bump_front_ok"], mats=["bump_front_ok_2"]), 0)
    G["rear_insert_yz"] = outline_entry(sel(ms["bump_rear_ok"], mats=["bump_rear_ok_3"]), 0)

    # --------------------------------------------------------------- panels
    G["panels"] = {
        "hood_xy": outline_entry(sel(ms["bonnet_ok"]), 2)[0],
        "front_bumper_yz": outline_entry(sel(ms["bump_front_ok"]), 0)[0],
        "front_bumper_side_xz": outline_entry(
            sel(ms["bump_front_ok"], keep=lambda t: t.mean(1)[:, 1] > 150), 1)[0],
        "rear_bumper_yz": outline_entry(sel(ms["bump_rear_ok"]), 0)[0],
        "rear_bumper_side_xz": outline_entry(
            sel(ms["bump_rear_ok"], keep=lambda t: t.mean(1)[:, 1] > 150), 1)[0],
        "hatch_yz": outline_entry(sel(ms["boot_ok"]), 0)[0],
        "front_door_xz": outline_entry(sel(ms["door_rf_ok"], exclude=["door_lf_ok_4"], keep=no_mirror), 1)[0],
        "rear_door_xz": outline_entry(sel(ms["door_rr_ok"], exclude=["door_lf_ok_4"]), 1)[0],
        "skirt_xz": outline_entry(sel(ms["skirt"], keep=lambda t: t.mean(1)[:, 1] > 0), 1)[0],
    }

    # ----------------------------------------------------------------- mirror
    mir = sel(ms["door_rf_ok"], keep=lambda t: in_box(t, *MIRROR_BOX))
    msec = []
    for y in np.linspace(187.0, 252.0, 9):
        segs = plane_segments(mir, 1, y)
        lo, hi = MIRROR_BOX
        inside = np.all((segs[:, :, 0] >= lo[0]) & (segs[:, :, 0] <= hi[0]) &
                        (segs[:, :, 2] >= lo[2]) & (segs[:, :, 2] <= hi[2]), axis=1)
        segs = segs[inside]
        if len(segs) < 3:
            continue
        hull = hull_ring(segs[:, :, [0, 2]], 40)
        msec.append({"y": float(y), "xz": hull})
    G["mirror_sections_right"] = msec

    # ---------------------------------------------------------------- spoiler
    sp = sel(ms["emb_001"], mats=["primary"], keep=lambda t: t.mean(1)[:, 2] > 370)
    ssec = []
    for y in [0, 40, 80, 110, 130, 145, 152]:
        segs = plane_segments(sp, 1, y)
        if len(segs) < 3:
            continue
        ssec.append({"y": float(y), "xz": hull_ring(segs[:, :, [0, 2]], 48)})
    G["spoiler_sections_right"] = ssec
    G["spoiler_xy"] = projected_outline(sp, 2, simplify=0.4)[0]

    # ---------------------------------------------------------------- handles
    hs = []
    for lo, hi in (((514.0, 199.0, 217.0), (574.0, 214.0, 230.0)), ((760.0, 196.0, 230.0), (820.0, 211.0, 243.0))):
        t = sel(ms["door_rf_ok"] if lo[0] < 600 else ms["door_rr_ok"], keep=lambda t, lo=lo, hi=hi: in_box(t, lo, hi))
        ring = projected_outline(t, 1, simplify=0.8)[0]
        hs.append({"xz": ring, "y_min": float(t[:, :, 1].min()), "y_max": float(t[:, :, 1].max())})
    G["handles_right"] = hs

    # ----------------------------------------------------------------- wheels
    wm = ms["wheel_1"]  # front-right
    v = wm.verts
    centre = (v.min(0) + v.max(0)) / 2
    def cyl(tris):
        p = tris.reshape(-1, 3) - centre
        return np.stack([p[:, 1], np.hypot(p[:, 0], p[:, 2])], 1)  # (axial y, radius)
    tire = cyl(sel(wm, mats=["wheel_0", "wheel_1"]))
    rim = cyl(sel(wm, mats=["wheel_2"]))
    def env(pr, bins, axis_key):
        out = []
        edges = np.linspace(pr[:, axis_key].min(), pr[:, axis_key].max(), bins + 1)
        for a, b in zip(edges[:-1], edges[1:]):
            m = (pr[:, axis_key] >= a) & (pr[:, axis_key] <= b)
            if m.any():
                other = 1 - axis_key
                out.append([float((a + b) / 2), float(pr[m, other].max()), float(pr[m, other].min())])
        return out
    G["wheel"] = {
        "centre_fr": centre.round(3).tolist(),
        "tire_profile_y_rmax_rmin": env(tire, 24, 0),
        "rim_profile_r_ymax_ymin": env(rim, 24, 1),
    }
    # rim face pattern: rim triangles on the outer face projected along Y
    rt = sel(wm, mats=["wheel_2"])
    face = rt[rt[:, :, 1].mean(1) > centre[1] + 0.25 * (rt[:, :, 1].max() - centre[1])]
    polys = [Polygon(t[:, [0, 2]] - centre[[0, 2]]).buffer(0.05) for t in face if Polygon(t[:, [0, 2]]).area > 1e-6]
    u = unary_union(polys).buffer(-0.05)
    g = max(getattr(u, "geoms", [u]), key=lambda p: p.area)
    G["wheel"]["rim_face_holes_xz"] = [np.asarray(i.coords)[:-1].round(3).tolist()
                                       for i in g.interiors if Polygon(i).area > 20]
    for k in ("wheel", "wheel_1", "wheel_2", "wheel_3"):
        vv = ms[k].verts
        G["wheel"][f"centre_{k}"] = ((vv.min(0) + vv.max(0)) / 2).round(3).tolist()

    # ---------------------------------------------------------------- antenna
    a = ms["antena"].verts
    top = a[np.argmax(a[:, 2])]
    G["antenna"] = {"tip": top.round(3).tolist(), "bbox": [a.min(0).round(3).tolist(), a.max(0).round(3).tolist()]}
    base = a[a[:, 2] < a[:, 2].min() + 4]
    G["antenna"]["base_centre"] = base.mean(0).round(3).tolist()

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(G))
    print("wrote", OUT, "sections", len(sections), "lamps", len(lamps),
          "glass", {k: v["area"] for k, v in G["glass"].items()},
          "mirror", len(msec), "spoiler", len(ssec),
          "rim holes", len(G["wheel"]["rim_face_holes_xz"]))


if __name__ == "__main__":
    main()
