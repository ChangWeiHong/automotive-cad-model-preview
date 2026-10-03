"""2005 Perodua Myvi - exterior reconstruction from the measurement spec.

Geometry is authored in normalized units U (overall length = 1000 U) in the
spec's CAD frame (X front->rear, Y left->right, Z ground->roof, Y=0 symmetry
plane, Z=0 ground) and scaled to nominal millimetres by S at the end.

Reconstruction assumptions (not measured values) are marked ASSUMPTION.
"""
from __future__ import annotations

from cadgen import build123d as bd
from cadgen import glb, srgb, step

S = 4.5474294878  # mm per U

# ---------------------------------------------------------------- body sections
# Each station: x, bottom-centre z, top-centre z, then 8 right-half (y, z)
# points ordered bottom -> top:
#   sill corner, sill, lower side, shoulder, belt, greenhouse, roof edge, crown.
# Values come from spec sections E/F/G/J; points between samples are ASSUMPTION.
STATIONS = [
    # nose (tangency stations; X=0 is a point, so start just behind it)
    (0.0, 44.0, 120.0, [(60, 44), (90, 46), (110, 60), (115, 85), (105, 105), (85, 113), (60, 117), (30, 119.5)]),
    (8, 41.5, 150.0, [(108, 42), (120, 46), (150, 80), (150, 115), (140, 135), (120, 143), (90, 147), (45, 149.5)]),
    (25, 40.0, 192.0, [(150, 40.5), (165, 44), (180, 80), (178, 140), (165, 170), (140, 182), (100, 188), (50, 191)]),
    (50, 40.5, 216.79, [(170, 41), (182.95, 50), (187.69, 75), (175.34, 150), (150, 185), (102.79, 200), (70, 210), (35, 215)]),
    (100, 42.0, 245.40, [(190, 42.5), (205, 48), (218.55, 100), (216.40, 150), (205, 195), (185, 220), (150, 235), (80, 243)]),
    (150, 43.0, 259.0, [(200, 43.5), (215, 48), (221, 100), (222.08, 150), (212, 200), (190, 235), (160, 250), (85, 257.5)]),
    (200, 44.0, 271.18, [(202, 44.5), (216, 50), (220, 100), (222.08, 160), (209.77, 200), (191.74, 250), (165, 262), (85, 269.5)]),
    (250, 45.0, 284.88, [(203, 45.5), (217, 50), (220, 100), (221.59, 150), (206.71, 200), (199.40, 250), (175, 276), (90, 282)]),
    # cabin
    (300, 45.89, 319.54, [(205, 46.2), (217.74, 50), (211.50, 100), (208.64, 200), (194.83, 250), (184.57, 300), (168, 312), (90, 317.5)]),
    (350, 45.7, 351.24, [(205, 46), (217.72, 50), (213.0, 100), (208.66, 200), (196.0, 250), (179.0, 300), (160, 342), (88, 349)]),
    (400, 45.53, 378.52, [(205, 45.8), (217.71, 50), (214.45, 100), (208.67, 200), (197.39, 250), (179.73, 300), (157.71, 350), (85, 376)]),
    (450, 45.35, 397.24, [(205, 45.6), (217.37, 50), (214.87, 100), (208.75, 200), (199.40, 250), (178.63, 300), (163.67, 350), (85, 395)]),
    (500, 45.16, 405.05, [(205, 45.4), (217.88, 50), (215.22, 100), (208.85, 200), (201.26, 250), (178.75, 300), (152, 390), (100, 401)]),
    (550, 44.98, 408.45, [(205, 45.2), (219.40, 50), (215.65, 100), (208.86, 200), (204.07, 250), (179.31, 300), (151.14, 400), (85, 407)]),
    (600, 44.80, 410.97, [(206, 45.0), (220.12, 50), (216.74, 100), (208.63, 200), (208.99, 250), (173.76, 300), (154.33, 400), (85, 409.5)]),
    (650, 44.62, 411.42, [(206, 44.8), (219.59, 50), (216.32, 100), (207.21, 200), (208.52, 250), (180.63, 300), (154.19, 400), (80, 410.5)]),
    (700, 44.44, 411.95, [(206, 44.6), (219.08, 50), (215.55, 100), (206.64, 200), (207.04, 250), (181.13, 300), (153.77, 400), (56.18, 411.6)]),
    (750, 44.5, 409.5, [(206, 44.7), (219.0, 50), (215.0, 100), (206.6, 200), (205.0, 250), (181.5, 300), (150.0, 400), (60, 409)]),
    (800, 46.0, 406.27, [(200, 46.2), (214, 52), (214.0, 100), (206.48, 200), (203.15, 250), (181.82, 300), (146.66, 400), (54.70, 405.8)]),
    (851.7, 48.0, 397.08, [(195, 48.2), (210, 55), (212.0, 100), (207.28, 200), (204.72, 250), (194.96, 300), (150, 385), (80, 394)]),
    (900, 52.0, 380.68, [(190, 52.2), (205, 60), (210.0, 100), (202.72, 200), (195.76, 250), (184.65, 300), (135, 368), (75, 377)]),
    # rear
    (950, 56.5, 313.65, [(190, 56.8), (210.31, 75), (215.55, 100), (209.43, 150), (181.43, 200), (160, 260), (94.17, 300), (50, 311)]),
    (975, 58.0, 262.0, [(185, 58.5), (200, 68), (208, 100), (203, 160), (188, 200), (160, 235), (115, 252), (60, 259)]),
    (990, 60.0, 225.0, [(170, 60.5), (188, 70), (198, 100), (195, 150), (180, 190), (150, 210), (100, 220), (50, 224)]),
    (1000.0, 70.0, 150.0, [(115, 70.5), (135, 80), (148, 100), (148, 125), (138, 138), (110, 145), (70, 148.5), (35, 149.8)]),
]

FRONT_AXLE_X, REAR_AXLE_X = 190.808, 851.694
WHEEL_R, WHEEL_W = 76.296, 47.392
RIM_R = 104.72 / 2
FRONT_TRACK, REAR_TRACK = 400.259, 400.248
FRONT_WHEEL_Z, REAR_WHEEL_Z = 76.296, 76.566
FRONT_ARCH = (189.762, 79.695, 92.664)  # fitted circle X, Z, R
REAR_ARCH = (848.740, 76.091, 94.233)


def _v(x, y, z):
    return bd.Vector(x, y, z)


def _section(x, zb, zt, half):
    """Flat floor edge plus one spline over the top (avoids floor overshoot)."""
    w0 = half[0][0]
    pts = [_v(x, w0, zb)] + [_v(x, y, z) for y, z in half[1:]] + [_v(x, 0, zt)]
    pts += [_v(x, -y, z) for y, z in reversed(half[1:])] + [_v(x, -w0, zb)]
    floor = bd.Edge.make_line(_v(x, -w0, zb), _v(x, w0, zb))
    return bd.Wire([floor, bd.Edge.make_spline(pts)])


def _prism_xz(pts_xz, y0, y1):
    """Side-view outline (x, z) extruded laterally from y0 to y1."""
    face = bd.Face(bd.Wire.make_polygon([_v(x, y0, z) for x, z in pts_xz], close=True))
    return bd.Solid.extrude(face, _v(0, y1 - y0, 0))


def _prism_xy(pts_xy, z0, z1):
    """Plan outline (x, y) extruded vertically from z0 to z1."""
    face = bd.Face(bd.Wire.make_polygon([_v(x, y, z0) for x, y in pts_xy], close=True))
    return bd.Solid.extrude(face, _v(0, 0, z1 - z0))


def _slab(p0, p1, below, above, half_w=260.0):
    """Region between offsets of the line p0->p1 (XZ), used to keep only a
    near-surface layer of the body for glazing."""
    import math

    dx, dz = p1[0] - p0[0], p1[1] - p0[1]
    n = math.hypot(dx, dz)
    ux, uz = dx / n, dz / n
    nx, nz = -uz, ux
    if nz < 0:
        nx, nz = -nx, -nz
    ext = 30.0
    a = (p0[0] - ux * ext, p0[1] - uz * ext)
    b = (p1[0] + ux * ext, p1[1] + uz * ext)
    poly = [
        (a[0] - nx * below, a[1] - nz * below),
        (b[0] - nx * below, b[1] - nz * below),
        (b[0] + nx * above, b[1] + nz * above),
        (a[0] + nx * above, a[1] + nz * above),
    ]
    return _prism_xz(poly, -half_w, half_w)


def _inter(a, b):
    r = a.intersect(b)
    if isinstance(r, bd.ShapeList):
        r = r[0] if len(r) == 1 else bd.Compound(list(r))
    return r


def _cyl(r, h, origin, direction):
    return bd.Solid.make_cylinder(r, h, bd.Plane(origin=origin, z_dir=direction))


def _mirror_y(shape):
    return bd.mirror(shape, about=bd.Plane.XZ)


def _box(lo, hi):
    return bd.Solid.make_box(hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2], bd.Plane(origin=lo))


def _both_sides(shape):
    return [shape, _mirror_y(shape)]


def _wheel_right(cx, cy, cz):
    """Right-side wheel centred at (cx, cy, cz), axle along Y, outer face at +Y.
    Built in place: bd.scale() does not scale a shape's Location."""
    h = WHEEL_W / 2

    def c(r, ht, y0, x=0.0, z=0.0):
        return _cyl(r, ht, (cx + x, cy + y0, cz + z), (0, 1, 0))

    tire = c(WHEEL_R, WHEEL_W, -h)
    tire = tire.fillet(14.0, tire.edges())  # ASSUMPTION: tyre shoulder radius
    recess = c(RIM_R + 1.5, 10.0, h - 8)
    tire = tire.cut(recess)
    rim = c(RIM_R, 24.0, h - 30)  # ASSUMPTION: face 6 U inboard
    holes = []
    import math

    for i in range(5):  # ASSUMPTION: 5-window rim face
        a = math.radians(90 + 72 * i)
        holes.append(
            c(9.5, 10.0, h - 12, 30 * math.cos(a), 30 * math.sin(a))
        )
    rim = rim.cut(*holes)
    return tire, rim


def build_car():
    body = bd.Solid.make_loft([_section(*st) for st in STATIONS])

    # wheel arches: open circular wells on each side (spec D fitted circles)
    wells = []
    for cx, cz, r in (FRONT_ARCH, REAR_ARCH):
        cyl = _cyl(r, 120.0, (cx, 150, cz), (0, 1, 0))
        wells += _both_sides(cyl)
    body = body.cut(*wells)

    # ---- glazing (body regions coloured as glass; outlines from spec K)
    ws_half = [(244.75, 0), (261.89, 169.34), (275.82, 173.21), (309.69, 168.12),
               (360.57, 157.81), (414.35, 148.54), (429.87, 145.61)]
    ws_plan = ws_half + [(x, -y) for x, y in reversed(ws_half[1:])]
    windshield = _inter(_inter(body, _prism_xy(ws_plan, 240, 430)),
        _slab((244.75, 281.07), (429.87, 392.31), 28, 40))

    fw = [(344.24, 253.13), (564.13, 259.97), (583.78, 387.71), (510.88, 382.46), (459.92, 373.47),
          (439.17, 366.52), (423.89, 361.39), (373.95, 336.45), (353.20, 320.82), (348.69, 286.74)]
    rw = [(630.56, 390.56), (610.87, 264.09), (769.42, 271.56), (814.03, 275.10), (822.44, 278.13),
          (830.49, 301.34), (835.00, 320.41), (833.77, 347.34), (824.42, 363.64), (806.80, 376.11),
          (774.12, 383.13), (710.28, 389.90)]
    side_glass = []
    for outline in (fw, rw):
        tool = _prism_xz(outline, 130, 260)
        side_glass += [_inter(body, tool), _inter(body, _mirror_y(tool))]

    rg_half = [(869.84, 131.50), (902.00, 144.06), (934.08, 156.46), (950.82, 159.73),
               (962.19, 98.29), (970.09, 0)]
    rg_plan = rg_half + [(x, -y) for x, y in reversed(rg_half[:-1])]
    rear_glass = _inter(_inter(body, _prism_xy(rg_plan, 255, 400)),
        _slab((869.84, 387.56), (970.09, 268.98), 28, 40))

    glass = [windshield, *side_glass, rear_glass]
    body = body.cut(*glass)

    # ---- lamps and grille (spec H/I boxes; ASSUMPTION: lens = body skin inside box)
    head = []
    for t in _both_sides(_box((45.91, 120, 171.2), (150.24, 194.83, 243.0))):
        head.append(_inter(body, t))
    fog = [_inter(body, t) for t in _both_sides(_box((40, 168.17, 99.45), (61.64, 189.54, 123.21)))]
    tail = [_inter(body, t) for t in _both_sides(_box((907.32, 152.10, 266.15), (960, 240, 332.96)))]
    tail_low = [_inter(body, t) for t in _both_sides(_box((918.52, 120, 213.82), (1000, 185.81, 259.16)))]
    reflect = [_inter(body, t) for t in _both_sides(_box((963.88, 140, 120.03), (1000, 193.62, 136.35)))]
    grille = _inter(body, _box((0, -147.10, 110.49), (51.46, 147.10, 173.05)))
    intake = _inter(body, _box((0, -120, 70), (59.24, 120, 100)))
    lights = head + fog + tail + tail_low + reflect
    trim = [grille, intake]
    body = body.cut(*lights, *trim)

    # ---- separate features
    def mirror_unit():
        arm = _box((312.18, 185.55, 268), (336, 212, 290))
        shell = _box((326, 205, 268), (360.75, 252.83, 311.78))
        shell = shell.fillet(8.0, shell.edges())
        return arm.fuse(shell)

    mirrors = _both_sides(mirror_unit())

    # ASSUMPTION: spoiler side profile inside the spec bounding box
    spoiler_profile = [(865.61, 392), (875, 400.62), (921.48, 389), (921.48, 377), (900, 375.22), (868, 384)]
    spoiler = _prism_xz(spoiler_profile, -154.28, 154.28)
    spoiler = spoiler.fillet(3.0, spoiler.edges().filter_by(bd.Axis.Y))

    handles = []
    for lo, hi in (((514.47, 200.16, 217.70), (573.06, 213.05, 229.18)),
                   ((760.80, 196.84, 230.98), (819.39, 209.74, 242.46))):
        handles += _both_sides(_box(lo, hi))

    import math

    ant_base, ant_tip = _v(790, 0, 403.5), _v(844.715, -1.248, 451.198)
    ant_dir = ant_tip - ant_base
    antenna = bd.Solid.make_cylinder(2.5, ant_dir.length, bd.Plane(origin=ant_base, z_dir=ant_dir))

    exhaust = _cyl(10.5, 65.0, (925, 111.57, 59.75), (1, 0, 0)).cut(
        _cyl(8.0, 70.0, (930, 111.57, 59.75), (1, 0, 0)))

    wheels = []
    for name, x, z, track in (("fl", FRONT_AXLE_X, FRONT_WHEEL_Z, FRONT_TRACK),
                              ("fr", FRONT_AXLE_X, FRONT_WHEEL_Z, FRONT_TRACK),
                              ("rl", REAR_AXLE_X, REAR_WHEEL_Z, REAR_TRACK),
                              ("rr", REAR_AXLE_X, REAR_WHEEL_Z, REAR_TRACK)):
        tire, rim = _wheel_right(x, track / 2, z)
        if name.endswith("l"):
            tire, rim = _mirror_y(tire), _mirror_y(rim)
        wheels.append((name, tire, rim))

    # ---- assemble in mm with labels and colours
    def part(shape, label, color):
        s = bd.scale(shape, S)
        s.label = label
        s.color = color
        return s

    paint = srgb("#B5121B")
    black = srgb("#16181B")
    glass_c = srgb("#1A232C", 0.9)
    lamp_c = srgb("#DDE4EA", 0.95)
    tail_c = srgb("#B01020", 0.85)
    chrome = srgb("#C8CCD0")

    gnames = ["windshield", "side_glass_fr", "side_glass_fl", "side_glass_rr", "side_glass_rl", "rear_glass"]
    children = [part(body, "body", paint)]
    children += [part(g, n, glass_c) for g, n in zip(glass, gnames)]
    children += [part(s, n, lamp_c) for s, n in zip(head + fog, ["headlamp_r", "headlamp_l", "fog_r", "fog_l"])]
    children += [part(s, n, tail_c) for s, n in zip(tail + tail_low + reflect,
                 ["taillamp_r", "taillamp_l", "rear_lamp_low_r", "rear_lamp_low_l", "reflector_r", "reflector_l"])]
    children += [part(grille, "grille", black), part(intake, "lower_intake", black)]
    children += [part(m, n, paint) for m, n in zip(mirrors, ["mirror_r", "mirror_l"])]
    children += [part(spoiler, "spoiler", paint), part(antenna, "antenna", black), part(exhaust, "exhaust_tip", chrome)]
    children += [part(h, f"door_handle_{i}", black) for i, h in enumerate(handles)]
    for name, tire, rim in wheels:
        children += [part(tire, f"tire_{name}", black), part(rim, f"rim_{name}", chrome)]
    return bd.Compound(children=children, label="perodua_myvi_2005")


@step(out="../../../models/STEP/myvi.step")
@glb(out="../GLB/myvi.glb")
def myvi():
    return build_car()


if __name__ == "__main__":
    myvi()
