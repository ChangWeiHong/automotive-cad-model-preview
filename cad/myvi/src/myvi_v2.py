"""2005 Perodua Myvi - exterior reconstruction, version 2.

All construction guides are measured from the source FBX mesh by
tools/extract_guides.py -> data/myvi_v2_guides.json (CAD frame, units U,
overall length 1000 U). Geometry is authored in U and scaled to nominal
millimetres (S mm per U) at the end.

Changes from v1:
  * body = lower-body loft + greenhouse loft (split at the measured beltline),
    each through ~70 dense mesh-derived sections incl. close end stations
  * glazing = thin curved surfaces filled from the measured 3D glass loops
  * wheel arches cut from the measured arch outlines, with lips and liners
  * hood, bumpers, hatch, doors and skirt split along source-mesh outlines
  * lamps / grille from source boundary loops; mirrors, spoiler, handles,
    rims and tyres from source sections/profiles; antenna ends at its tip
Reconstruction assumptions are marked ASSUMPTION.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from cadgen import build123d as bd
from cadgen import glb, srgb, step

S = 4.5474294878  # mm per U
GUIDES = Path(__file__).resolve().parents[1] / "data" / "myvi_v2_guides.json"

N_RING = 64              # SAMPLING: points per section ring
GH_X0, GH_X1 = 250.0, 880.0
REAR_MERGE = (790.0, 880.0)  # lower body grows to full height over this X range
BELT_OVERLAP = 4.0       # greenhouse loft starts this far below the beltline
# beltline (glass/body boundary) from spec K/N and the measured glass loops
BELT = [(240, 274.0), (300, 262.0), (344.24, 253.13), (564.13, 259.97), (610.87, 264.09),
        (769.42, 271.56), (822.44, 278.13), (870, 273.0), (950.82, 270.47), (965, 269.0)]

# spec D right-side arch control points (x, y, z), measured
FRONT_ARCH = [(98.20, 214.87, 75.43), (102.29, 220.06, 110.49), (117.68, 221.54, 139.29),
              (143.56, 221.54, 161.28), (170.81, 221.54, 169.96), (190.22, 221.54, 171.87),
              (209.62, 221.54, 169.95), (242.21, 221.54, 155.81), (268.19, 221.54, 128.72),
              (280.84, 216.47, 92.83), (283.38, 211.53, 73.44)]
REAR_ARCH = [(753.88, 211.43, 73.28), (756.46, 216.37, 96.52), (773.22, 221.54, 131.70),
             (789.07, 221.54, 150.25), (825.65, 221.54, 164.35), (862.90, 221.54, 168.33),
             (878.37, 221.54, 166.74), (908.72, 221.54, 152.60), (927.65, 220.23, 127.40),
             (938.38, 216.96, 99.53), (941.65, 205.61, 60.96)]
ARCH_INNER_Y = 150.0     # ASSUMPTION: inboard wall of the wheel wells
LIP_R = 2.2              # ASSUMPTION: arch lip roll radius (spec: lip depth U)
LINER_T = 2.5            # ASSUMPTION: well liner thickness

GLASS_T = 1.2            # ASSUMPTION: glazing thickness (spec: panel thickness U)
OPEN_IN, OPEN_OUT = 30.0, 40.0
FRONT_FLAT_X = 14.0      # stations ahead of this are replaced by the flat fascia
FRONT_HULL_X = 131.0     # front-bumper stations are convex-hulled up to here
FRONT_FASCIA = ((1.0, 0.86, 0.90), (5.0, 0.95, 0.97))  # (x, y scale, z scale)
PATCH_UV = (8, 24)       # body surface patches per loft face (U, V)
MIN_PIECE = 20.0         # U^3; boolean slivers below this are dropped


def _v(x, y, z):
    return bd.Vector(float(x), float(y), float(z))


def _belt(x):
    for (x0, z0), (x1, z1) in zip(BELT, BELT[1:]):
        if x <= x1:
            return z0 + (z1 - z0) * max(0.0, (x - x0)) / (x1 - x0)
    return BELT[-1][1]


# ------------------------------------------------------------------ helpers
def _bop(kind, a, tools):
    """Parallel OCCT boolean -> list of result solids."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Common, BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
    from OCP.TopTools import TopTools_ListOfShape

    op = {"cut": BRepAlgoAPI_Cut, "common": BRepAlgoAPI_Common, "fuse": BRepAlgoAPI_Fuse}[kind]()
    args, tl = TopTools_ListOfShape(), TopTools_ListOfShape()
    args.Append(a.wrapped)
    for t in tools:
        tl.Append(t.wrapped)
    op.SetArguments(args)
    op.SetTools(tl)
    op.SetRunParallel(True)
    op.Build()
    if not op.IsDone():
        raise RuntimeError(f"boolean {kind} failed")
    return [s for s in bd.Compound(op.Shape()).solids() if s.volume > 1e-6]


def _inter(a, b):
    r = [x for x in _bop("common", a, [b]) if x.volume > MIN_PIECE]
    if not r:
        return None
    return r[0] if len(r) == 1 else bd.Compound(r)


def _cut(a, *tools):
    tools = [t for t in tools if t is not None]
    if not tools:
        return a
    r = [x for x in _bop("cut", a, tools) if x.volume > MIN_PIECE]
    # keep every real piece: panel cuts legitimately split the shell into
    # regions; slivers below MIN_PIECE are boolean debris
    return r[0] if len(r) == 1 else bd.Compound(r)


def _connected(shape, keep=0.005):
    """Drop detached boolean debris: solids smaller than `keep` x the largest."""
    sols = shape.solids()
    if len(sols) <= 1:
        return shape
    big = max(x.volume for x in sols)
    sols = [x for x in sols if x.volume >= keep * big]
    return sols[0] if len(sols) == 1 else bd.Compound(sols)


def _mirror_y(shape):
    return bd.mirror(shape, about=bd.Plane.XZ)


def _both(shape):
    return [shape, _mirror_y(shape)]


def _prism(face, vec):
    return bd.Solid.extrude(face, _v(*vec))


def _poly_face(pts3):
    return bd.Face(bd.Wire.make_polygon([_v(*p) for p in pts3], close=True))


def _prism_xz(ring, y0, y1):
    return _prism(_poly_face([(x, y0, z) for x, z in ring]), (0, y1 - y0, 0))


def _prism_yz(ring, x0, x1):
    return _prism(_poly_face([(x0, y, z) for y, z in ring]), (x1 - x0, 0, 0))


def _prism_xy(ring, z0, z1):
    return _prism(_poly_face([(x, y, z0) for x, y in ring]), (0, 0, z1 - z0))


def _dedupe(pts, tol=0.05):
    out = []
    for p in pts:
        if not out or (p - out[-1]).length > tol:
            out.append(p)
    while len(out) > 3 and (out[0] - out[-1]).length <= tol:
        out.pop()
    return out


def _closed_spline(pts):
    return bd.Edge.make_spline(_dedupe([_v(*p) for p in pts]), periodic=True)


def _ring_wire(x, ring, anchors=None):
    """Periodic spline through a section ring, split at anchor indices into
    separate edges (smaller loft faces -> faster, local booleans)."""
    pts = [_v(x, y, z) for y, z in ring]
    edge = bd.Edge.make_spline(pts, periodic=True)
    if not anchors:
        return bd.Wire([edge])
    ps = sorted(edge.param_at_point(pts[i]) for i in anchors)
    ps = [0.0 if abs(p) < 1e-9 or abs(p - 1) < 1e-9 else p for p in ps]
    ps = sorted(set(ps))
    cuts = ps + [1.0]
    return bd.Wire([edge.trim(a, b) for a, b in zip(cuts, cuts[1:]) if b - a > 1e-6])


N_LO, N_HI = 8, 10      # SAMPLING: half-ring points bottom->widest, widest->top


def _half_path(sec):
    """Measured right-half outline, bottom centre -> top centre, clipped to the
    lower body and greenhouse regions at the beltline."""
    import numpy as np

    h = np.asarray(sec["half"], float)
    x = sec["x"]
    if x < GH_X0:
        return h, None
    # rear: the lower-body clip rises smoothly from the beltline to above the
    # roof so the C-pillar, hatch and tail are one continuous loft
    belt = _belt(x)
    t = min(max((x - REAR_MERGE[0]) / (REAR_MERGE[1] - REAR_MERGE[0]), 0.0), 1.0)
    t = t * t * (3 - 2 * t)
    zs = belt + t * (h[:, 1].max() + 2.0 - belt)
    if zs >= h[:, 1].max() - 0.5:
        return h, None

    def split_at(z):
        k = next(i for i in range(1, len(h)) if (h[i - 1, 1] - z) * (h[i, 1] - z) <= 0)
        a, b = h[k - 1], h[k]
        f = (z - a[1]) / ((b[1] - a[1]) or 1.0)
        return k, a + f * (b - a)

    k, p = split_at(zs)
    lower = np.vstack([h[:k], p, [0.0, zs]])
    if x > GH_X1:
        return lower, None
    k2, p2 = split_at(belt - BELT_OVERLAP)
    upper = np.vstack([[0.0, belt - BELT_OVERLAP], p2, h[k2:]])
    return lower, upper


def _hull_half(half):
    """Convex hull of a right-half section, bottom centre -> top centre."""
    import numpy as np
    from shapely.geometry import Polygon
    from shapely.geometry.polygon import orient

    h = np.asarray(half, float)
    poly = Polygon(np.vstack([h, [[0.0, h[-1, 1]], [0.0, h[0, 1]]]])).buffer(0)
    ring = np.asarray(orient(poly.convex_hull, 1.0).exterior.coords)[:-1]
    # CCW in (y, z) runs bottom -> +y side -> top; start at the bottom centre
    k = int(np.argmin(np.where(ring[:, 0] < 0.5, ring[:, 1], np.inf)))
    ring = np.roll(ring, -k, axis=0)
    top = int(np.argmax(np.where(ring[:, 0] < 0.5, ring[:, 1], -np.inf)))
    path = ring[: top + 1].copy()
    path[0, 0] = path[-1, 0] = 0.0
    return path.tolist()


def _flatten_front(secs):
    """ASSUMPTION (user request "make it more flat", front bumper): front-end
    sections are convex-hulled (no grille recess / wrinkles) and the narrow
    plate-mount rib stations ahead of FRONT_FLAT_X are replaced by a near-flat
    fascia: scaled copies of the first full section."""
    out = []
    base = None
    for sc in secs:
        if sc["x"] < FRONT_FLAT_X:
            continue
        if sc["x"] <= FRONT_HULL_X:
            sc = {"x": sc["x"], "half": _hull_half(sc["half"])}
        if base is None:
            base = sc
        out.append(sc)
    z0 = min(z for _, z in base["half"])
    fascia = []
    for x, sy, sz in FRONT_FASCIA:
        fascia.append({"x": x, "half": [(y * sy, z0 + (z - z0) * sz) for y, z in base["half"]]})
    return fascia + out


def _anchored(half):
    """Resample a half path with anchors at bottom centre, widest point and top
    centre so that sections correspond feature-to-feature along the loft."""
    import numpy as np

    def arc(seg, n, endpoint):
        d = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(seg, axis=0), axis=1))])
        t = np.linspace(0, d[-1], n, endpoint=endpoint)
        return np.stack([np.interp(t, d, seg[:, 0]), np.interp(t, d, seg[:, 1])], 1)

    k = int(np.argmax(half[:, 0]))
    k = min(max(k, 1), len(half) - 2)
    return np.vstack([arc(half[: k + 1], N_LO, False), arc(half[k:], N_HI, True)])


def _smooth(stack, passes_long=2, passes_tr=1):
    """Light smoothing across stations (axis 0) and around each half (axis 1)."""
    import numpy as np

    a = np.array(stack, float)
    for _ in range(passes_long):
        a[1:-1] = 0.25 * a[:-2] + 0.5 * a[1:-1] + 0.25 * a[2:]
    for _ in range(passes_tr):
        a[:, 1:-1] = 0.25 * a[:, :-2] + 0.5 * a[:, 1:-1] + 0.25 * a[:, 2:]
    a[:, 0, 0] = 0.0
    a[:, -1, 0] = 0.0
    # restore each station's measured width and height range after smoothing
    raw = np.array(stack, float)
    for i in range(len(a)):
        a[i, :, 0] *= raw[i, :, 0].max() / max(a[i, :, 0].max(), 1e-9)
        z0, z1 = a[i, :, 1].min(), a[i, :, 1].max()
        r0, r1 = raw[i, :, 1].min(), raw[i, :, 1].max()
        a[i, :, 1] = r0 + (a[i, :, 1] - z0) * (r1 - r0) / max(z1 - z0, 1e-9)
    return a


def _ring(half):
    """Right half (bottom->top) -> full closed ring list, mirrored in Y."""
    pts = [tuple(p) for p in half]
    return pts + [(-y, z) for y, z in reversed(pts[1:-1])]


def _frame(e):
    return [bd.Vector(*e[k]) for k in ("origin", "u", "v", "n")]


def _outline_prism(e, below, above):
    """Measured patch outline (in its plane) extruded along the patch normal."""
    c, u, v, n = _frame(e)
    base = [c + u * a + v * b - n * below for a, b in e["outline_uv"]]
    face = bd.Face(bd.Wire.make_polygon(base, close=True))
    return _prism(face, n * (below + above))


def _grid_surface(e, offset=0.0):
    """B-spline surface through the height grid sampled from the mesh."""
    c, u, v, n = _frame(e)
    g = e["grid"]
    pts = [[c + u * a + v * b + n * (h + offset) for b, h in zip(g["b"], row)] for a, row in zip(g["a"], g["h"])]
    return bd.Face.make_surface_from_array_of_points(pts)


def _glass_pane(e):
    """Thin curved pane: fitted surface, thickened outward, trimmed to the
    measured outline. Returns (pane, opening tool for the body)."""
    n = _frame(e)[3]
    clip = _outline_prism(e, 200.0, 200.0)
    pane = _inter(_prism(_grid_surface(e), n * GLASS_T), clip)
    opening = _inter(_prism(_grid_surface(e, -OPEN_IN), n * (OPEN_IN + OPEN_OUT)), clip)
    return pane, opening


def _arch_profile(pts):
    """Closed XZ outline of a wheel opening: measured arch + ground closure."""
    xz = [(x, z) for x, _, z in pts]
    return [(xz[0][0], -20.0)] + xz + [(xz[-1][0], -20.0)]


def _arch_tool(pts):
    xz = _arch_profile(pts)
    edge = bd.Edge.make_spline([_v(x, 0, z) for x, z in xz[1:-1]])
    wire = bd.Wire([bd.Edge.make_line(_v(xz[0][0], 0, -20), _v(*edge.start_point())), edge,
                    bd.Edge.make_line(_v(*edge.end_point()), _v(xz[-1][0], 0, -20)),
                    bd.Edge.make_line(_v(xz[-1][0], 0, -20), _v(xz[0][0], 0, -20))])
    face = bd.Face(wire).moved(bd.Location((0, ARCH_INNER_Y, 0)))
    return _prism(face, (0, 270 - ARCH_INNER_Y, 0)), xz


def _lip(pts):
    path = bd.Wire([bd.Edge.make_spline([_v(*p) for p in pts])])
    p0 = path.position_at(0)
    t0 = path.tangent_at(0)
    prof = bd.Wire([bd.Edge.make_circle(LIP_R, bd.Plane(origin=p0, z_dir=t0))])
    return bd.Solid.sweep(bd.Face(prof), path)


def _revolve(profile_xy, centre):
    """Profile given as (radius, axial y) pairs -> solid revolved about the
    wheel axis (parallel to Y through `centre`)."""
    cx, cy, cz = centre
    face = bd.Face(bd.Wire.make_polygon([_v(cx + r, cy + y, cz) for r, y in profile_xy], close=True))
    return bd.Solid.revolve(face, 360, bd.Axis((cx, cy, cz), (0, 1, 0)))


import os
import sys
import time

_T0 = [time.time()]


def _trace(msg, shape=None):
    """Stage timing to stderr when MYVI_TRACE is set (no effect on geometry)."""
    if os.environ.get("MYVI_TRACE"):
        extra = ""
        if shape is not None:
            vols = [round(x.volume) for x in shape.solids()]
            extra = f" solids={len(vols)} min={min(vols)} total={sum(vols)}"
        print(f"{time.time() - _T0[0]:7.1f}s {msg}{extra}", file=sys.stderr, flush=True)


# -------------------------------------------------------------------- body
def build_car():
    G = json.loads(GUIDES.read_text())

    lo_x, lo_h, up_x, up_h = [], [], [], []
    secs = _flatten_front(G["body_sections"])
    # SAMPLING: all end stations, every other station through the mid-body
    secs = [sc for i, sc in enumerate(secs) if i % 2 == 0 or i < 14 or i > len(secs) - 8]
    for sec in secs:
        lo, up = _half_path(sec)
        lo_x.append(sec["x"]); lo_h.append(_anchored(lo))
        if up is not None:
            up_x.append(sec["x"]); up_h.append(_anchored(up))
    lower = bd.Solid.make_loft([_ring_wire(x, _ring(h)) for x, h in zip(lo_x, _smooth(lo_h))])
    greenhouse = bd.Solid.make_loft([_ring_wire(x, _ring(h)) for x, h in zip(up_x, _smooth(up_h))])
    body = max(_bop("fuse", lower, [greenhouse]), key=lambda s: s.volume).clean()
    # split the few huge loft faces into a UV grid of patches: booleans stay
    # local and every trimmed face tessellates (no geometry change)
    from OCP.ShapeUpgrade import ShapeUpgrade_ShapeDivideArea

    div = ShapeUpgrade_ShapeDivideArea(body.wrapped)
    div.SetSplittingByNumber(True)
    div.SetNumbersUVSplits(*PATCH_UV)
    div.Perform()
    body = bd.Compound(div.Result()).solids()[0]
    _trace("body lofted", body)
    # ---- wheel openings, liners and lips (measured outlines, spec D)
    from shapely.geometry import Polygon

    liners, lips, wells = [], [], []
    for pts in (FRONT_ARCH, REAR_ARCH):
        tool, xz = _arch_tool(pts)
        # liner = thin shell lining the opening wall, built in the void: no
        # boolean against the body surface is needed
        outer = Polygon(xz).buffer(-0.05, join_style=1).simplify(0.3)
        inner = Polygon(xz).buffer(-LINER_T, join_style=1).simplify(0.3)
        liner = _prism_xz(list(outer.exterior.coords)[:-1], ARCH_INNER_Y, 200.0).cut(
            _prism_xz(list(inner.exterior.coords)[:-1], ARCH_INNER_Y - 5.0, 205.0))
        # keep only the arch wall above ground clearance
        liner = _inter(liner, bd.Solid.make_box(400, 60, 200, bd.Plane(origin=(xz[0][0] - 50, ARCH_INNER_Y - 5, 45))))
        wells.append(tool)
        wells.append(_mirror_y(tool))
        liners += _both(liner)
        lips += _both(_lip(pts))
    body = _cut(body, *wells)

    _trace("arches done", body)
    # ---- glazing: thin surfaces on the measured loops, openings behind them
    glass, openings = [], []
    for name, e in G["glass"].items():
        pane, opening = _glass_pane(e)
        glass.append((name, pane))
        openings.append(opening)
        _trace(f"glass {name}")
    body = _cut(body, *openings)

    _trace("glazing done", body)
    # ---- lamps (source lens loops) and grille / trim (source outlines)
    lamp_parts, lamp_tools = [], []
    for i, lamp in enumerate(G["lamps"]):
        tool = _outline_prism(lamp, 40.0, 40.0)
        piece = _inter(body, tool)
        if piece is not None:
            lamp_parts.append((f"{lamp['kind']}_lamp_{lamp['side']}{i}", lamp["kind"], piece))
            lamp_tools.append(tool)
    body = _cut(body, *lamp_tools)

    _trace("lamps done", body)
    trim, trim_tools = [], []
    for name, rings, x0, x1 in (("grille", G["grille_yz"][:1], 0.0, 70.0),
                                ("rear_lower_trim", G["rear_insert_yz"], 930.0, 1000.0)):
        for k, ring in enumerate(rings):
            tool = _prism_yz(ring, x0, x1)
            piece = _inter(body, tool)
            if piece is not None:
                trim.append((f"{name}_{k}", piece))
                trim_tools.append(tool)
    body = _cut(body, *trim_tools)

    _trace("trim done", body)
    # ---- panels split along the source mesh outlines (no gap widths: spec U)
    P = G["panels"]
    tools = [
        ("hood", [_prism_xy(P["hood_xy"], 185.0, 300.0)]),
        ("front_bumper", [_prism_yz(P["front_bumper_yz"], -1.0, 131.0)]),
        ("hatch", [_prism_yz(P["hatch_yz"], 866.0, 1001.0)]),
        ("rear_bumper", [_prism_yz(P["rear_bumper_yz"], 898.0, 1001.0)]),
        ("door_rf", [_prism_xz(P["front_door_xz"], 140.0, 260.0)]),
        ("door_lf", [_mirror_y(_prism_xz(P["front_door_xz"], 140.0, 260.0))]),
        ("door_rr", [_prism_xz(P["rear_door_xz"], 140.0, 260.0)]),
        ("door_lr", [_mirror_y(_prism_xz(P["rear_door_xz"], 140.0, 260.0))]),
        ("skirt", _both(_prism_xz(P["skirt_xz"], 150.0, 260.0))),
    ]
    panels = []
    for name, ts in tools:
        tool = ts[0] if len(ts) == 1 else ts[0].fuse(*ts[1:])
        piece = _inter(body, tool)
        _trace(f"panel {name}", body)
        if piece is not None:
            panels.append((name, _connected(piece)))
            body = _cut(body, tool)

    _trace("panels done")
    # ---- mirrors from source sections (right), mirrored
    mir_w = [bd.Wire([_closed_spline([(x, s["y"], z) for x, z in s["xz"]])])
             for s in G["mirror_sections_right"]]
    mirror_r = bd.Solid.make_loft(mir_w)
    mirrors = _both(mirror_r)

    # ---- spoiler: measured centre-line profile across the width, trimmed to
    # the measured plan outline (source blade is too thin for a section loft)
    prof = G["spoiler_sections_right"][0]["xz"]
    blade = _prism_xz(prof, -160.0, 160.0)
    spoiler = _inter(blade, _prism_xy(G["spoiler_xy"], 300.0, 450.0))

    # ---- door handles from source outlines
    handles = []
    for h in G["handles_right"]:
        handles += _both(_prism_xz(h["xz"], h["y_min"], h["y_max"]))

    _trace("mirror/spoiler/handles done")
    # ---- wheels: revolved source profiles, 6-window rim face from source
    W = G["wheel"]
    tire_prof = W["tire_profile_y_rmax_rmin"]
    rim_prof = W["rim_profile_r_ymax_ymin"]
    r_out = max(r for r, _, _ in rim_prof)
    # the source tyre is a surface: make it solid from the rim seat outward
    tire_xy = [(r, y) for y, r, _ in tire_prof] + [(r_out - 1.0, tire_prof[-1][0]), (r_out - 1.0, tire_prof[0][0])]
    y_back = min(ymin for _, _, ymin in rim_prof)
    rim_xy = [(0.0, rim_prof[0][1])] + [(r, ymax) for r, ymax, _ in rim_prof] + [(r_out, y_back), (0.0, y_back)]
    y_face = max(ymax for _, ymax, _ in rim_prof)
    wheels = []
    for key, tag in (("wheel_1", "fr"), ("wheel_3", "rr"), ("wheel", "fl"), ("wheel_2", "rl")):
        cx, cy, cz = W[f"centre_{key}"]
        c = (cx, abs(cy), cz)
        tire = _revolve(tire_xy, c)
        rim = _revolve(rim_xy, c)
        # windows run through the rim dish (source face holes)
        pockets = [_prism(_poly_face([(cx + hx, c[1] + y_back + 2.0, cz + hz) for hx, hz in hole]),
                          (0, y_face - y_back + 4.0, 0))
                   for hole in W["rim_face_holes_xz"]]
        rim = _cut(rim, *pockets)
        if cy < 0:
            tire, rim = _mirror_y(tire), _mirror_y(rim)
        wheels.append((tag, tire, rim))

    _trace("wheels done")
    # ---- antenna: tapered mast ending exactly at the measured tip
    A = G["antenna"]
    base, tip = _v(*A["base_centre"]), _v(*A["tip"])
    axis = tip - base
    mast = bd.Solid.make_cone(2.6, 0.5, axis.length + 1.0, bd.Plane(origin=base, z_dir=axis))
    lo, hi = A["bbox"]
    z0 = lo[2] - 10.0
    antenna = _inter(mast, bd.Solid.make_box(200, 40, tip.Z - z0, bd.Plane(origin=(700, -20, z0))))

    # ---- exhaust tip (source bbox; one-sided per spec O)
    ex = bd.Solid.make_cylinder(11.0, 60.0, bd.Plane(origin=(925.18, 111.57, 59.75), z_dir=(1, 0, 0)))
    ex = _cut(ex, bd.Solid.make_cylinder(8.5, 70.0, bd.Plane(origin=(930.0, 111.57, 59.75), z_dir=(1, 0, 0))))

    _trace("details done")
    # ----------------------------------------------------- assemble in mm
    def part(shape, label, color):
        sols = []
        for sol in shape.solids():
            if sol.volume < 0:  # never export an inside-out solid
                sol = bd.Solid(sol.wrapped.Reversed())
            sols.append(sol)
        shape = sols[0] if len(sols) == 1 else bd.Compound(sols)
        s = bd.scale(shape, S)
        s.label = label
        s.color = color
        return s

    paint = srgb("#B5121B")
    black = srgb("#16181B")
    dark = srgb("#2A2D31")
    glass_c = srgb("#151C23", 0.92)
    head_c = srgb("#DDE4EA", 0.95)
    tail_c = srgb("#B01020", 0.9)
    chrome = srgb("#C8CCD0")

    ch = [part(_connected(body), "body_shell", paint)]
    ch += [part(p, n, paint) for n, p in panels]
    ch += [part(g, n, glass_c) for n, g in glass]
    ch += [part(p, n, head_c if kind == "front" else tail_c) for n, kind, p in lamp_parts]
    ch += [part(p, n, black) for n, p in trim]
    ch += [part(l, f"wheel_well_liner_{i}", dark) for i, l in enumerate(liners) if l is not None]
    ch += [part(l, f"arch_lip_{i}", paint) for i, l in enumerate(lips)]
    ch += [part(m, f"mirror_{s}", paint) for m, s in zip(mirrors, "rl")]
    ch += [part(spoiler, "spoiler", paint), part(antenna, "antenna", black), part(ex, "exhaust_tip", chrome)]
    ch += [part(h, f"door_handle_{i}", black) for i, h in enumerate(handles)]
    for tag, tire, rim in wheels:
        ch += [part(tire, f"tire_{tag}", black), part(rim, f"rim_{tag}", chrome)]
    return bd.Compound(children=ch, label="perodua_myvi_2005_v2")


@step(out="../../../models/STEP/myvi_v2.step")
@glb(out="../GLB/myvi_v2.glb")
def myvi_v2():
    return build_car()


if __name__ == "__main__":
    myvi_v2()
