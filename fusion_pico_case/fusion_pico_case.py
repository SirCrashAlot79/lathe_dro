"""Create a two-piece 3D-printable case for a Pico 2, two DE-9 (DB9) female connectors and a
rocker power switch, sized to fit the 150 x 85 mm face of an ATX PSU (drill your own mount holes).

Run as a Fusion 360 script in an empty design (Z-up). Units below are millimeters.
DB9 connectors and switch are on the front wall (Y=0), Pico 2 on standoffs with its micro-USB
facing the left wall (X=0), power cord hole in the back wall. The Dell 90 W charger is
zip-tied on top of the lid through slots in the lid's front/back ears. The lid is built flat
beside the base, lip up; flip it over (about the Y axis) to close the case.
Check cutouts against your actual parts before printing.
"""

import math
import traceback
import adsk.core
import adsk.fusion


# Case geometry.
WALL = 2.4
FLOOR = 2.4
INNER_X = 130.0
INNER_Y = 64.0
INNER_Z = 24.0
OUTER_X = INNER_X + 2 * WALL
OUTER_Y = INNER_Y + 2 * WALL
OUTER_Z = FLOOR + INNER_Z

# Lid.
LID_THICKNESS = 2.4
LIP_HEIGHT = 2.0
LIP_WIDTH = 1.6
LIP_CLEARANCE = 0.3
LID_Y_OFFSET = OUTER_Y + 12.0 + 8.0

# Lid screw posts: holes sized for M3 heat-set inserts (about 5.7 mm long).
POST_HALF = 4.5
POST_PILOT_DIAMETER = 4.0
POST_PILOT_DEPTH = 7.0
LID_SCREW_HOLE = 3.4
POST_CENTERS = [
    (WALL + 42.0, WALL + 4.0),
    (WALL + INNER_X - 4.0, WALL + 4.0),
    (WALL + 4.0, WALL + INNER_Y - 4.0),
    (WALL + INNER_X / 2.0, WALL + INNER_Y - 4.0),
    (WALL + INNER_X - 4.0, WALL + INNER_Y - 4.0),
]

# Power cord hole in the back wall, in line with the switch.
CORD_HOLE = 12.0
CORD_HOLE_X = WALL + 105.0
CORD_HOLE_Z = FLOOR + 11.0

# Rocker switch panel cutout (KCD1-style snap-in) on the front wall.
SWITCH_X = WALL + 105.0
SWITCH_Z = FLOOR + 11.0
SWITCH_CUT_WIDTH = 20.2
SWITCH_CUT_HEIGHT = 13.2

# Lid ears (outside the walls) carry zip-tie slots for the charger; total Y stays under 85 mm.
EAR = 8.0
TIE_SLOT_X_CENTERS = [30.0, OUTER_X - 30.0]
TIE_SLOT_LENGTH = 7.0
TIE_SLOT_WIDTH = 3.0

# DE-9 female panel cutout (wide side up) and 4-40 mounting holes.
DB9_CENTERS_X = [WALL + 21.0, WALL + 63.0]
DB9_CENTER_Z = FLOOR + 11.0
DB9_CUT_TOP_WIDTH = 24.8
DB9_CUT_HEIGHT = 12.6
DB9_CUT_SIDE_ANGLE = 10.0
DB9_SCREW_SPACING = 25.0
DB9_SCREW_HOLE = 3.2

# Pico 2: 51 x 21 mm, holes 2.0 mm from short ends, 11.4 x 47 mm spacing.
PICO_LENGTH = 51.0
PICO_WIDTH = 21.0
PICO_HOLE_X_INSET = 2.0
PICO_HOLE_SPACING_X = 47.0
PICO_HOLE_SPACING_Y = 11.4
PICO_X0 = WALL + 0.3
PICO_CENTER_Y = WALL + 44.0
STANDOFF_HEIGHT = 4.0
STANDOFF_DIAMETER = 5.5
STANDOFF_PILOT = 1.8
PCB_THICKNESS = 1.6
USB_CUT_WIDTH = 11.0
USB_CUT_HEIGHT = 7.5
USB_CENTER_Z = FLOOR + STANDOFF_HEIGHT + PCB_THICKNESS + 1.4

CUT = adsk.fusion.FeatureOperations.CutFeatureOperation
JOIN = adsk.fusion.FeatureOperations.JoinFeatureOperation
NEW_BODY = adsk.fusion.FeatureOperations.NewBodyFeatureOperation


def _cm(value_mm):
    return value_mm / 10.0


def _point(x_mm, y_mm):
    return adsk.core.Point3D.create(_cm(x_mm), _cm(y_mm), 0)


def _offset_plane(component, z_mm):
    plane_input = component.constructionPlanes.createInput()
    plane_input.setByOffset(
        component.xYConstructionPlane,
        adsk.core.ValueInput.createByReal(_cm(z_mm)),
    )
    return component.constructionPlanes.add(plane_input)


def _new_sketch(component, z_mm, name):
    sketch = component.sketches.add(_offset_plane(component, z_mm))
    sketch.name = name
    return sketch


def _wall_sketch(component, base_plane, axis, position_mm, name):
    # Offset sign relative to the base plane normal is not assumed; verify and flip if needed.
    axis_index = {"x": 0, "y": 1}[axis]
    for sign in (1.0, -1.0):
        plane_input = component.constructionPlanes.createInput()
        plane_input.setByOffset(
            base_plane, adsk.core.ValueInput.createByReal(sign * _cm(position_mm)))
        plane = component.constructionPlanes.add(plane_input)
        origin = plane.geometry.origin
        if abs((origin.x, origin.y)[axis_index] - _cm(position_mm)) < 1e-4:
            break
        plane.deleteMe()
    sketch = component.sketches.add(plane)
    sketch.name = name
    return sketch


def _model_point(sketch, x_mm, y_mm, z_mm):
    return sketch.modelToSketchSpace(
        adsk.core.Point3D.create(_cm(x_mm), _cm(y_mm), _cm(z_mm))
    )


def _add_polygon(sketch, points):
    lines = sketch.sketchCurves.sketchLines
    for index, point in enumerate(points):
        nxt = points[(index + 1) % len(points)]
        lines.addByTwoPoints(point_or(sketch, point), point_or(sketch, nxt))


def point_or(sketch, point):
    if isinstance(point, adsk.core.Point3D):
        return point
    return _point(point[0], point[1])


def _add_rectangle(sketch, x1, y1, x2, y2):
    sketch.sketchCurves.sketchLines.addTwoPointRectangle(_point(x1, y1), _point(x2, y2))


def _add_circle(sketch, x, y, diameter):
    sketch.sketchCurves.sketchCircles.addByCenterRadius(_point(x, y), _cm(diameter / 2.0))


def _all_profiles(sketch):
    profiles = adsk.core.ObjectCollection.create()
    for index in range(sketch.profiles.count):
        profiles.add(sketch.profiles.item(index))
    return profiles


def _extrude(component, profiles, depth_mm, operation, name):
    extrudes = component.features.extrudeFeatures
    feature_input = extrudes.createInput(profiles, operation)
    feature_input.setDistanceExtent(False, adsk.core.ValueInput.createByReal(_cm(depth_mm)))
    feature = extrudes.add(feature_input)
    feature.name = name
    if operation == NEW_BODY and feature.bodies.count:
        feature.bodies.item(0).name = name
    return feature


def _cut_through_wall(component, sketch, thickness_mm, name):
    # Sketch plane sits on the wall's outer face; cut symmetrically so direction doesn't matter.
    extrudes = component.features.extrudeFeatures
    feature_input = extrudes.createInput(_all_profiles(sketch), CUT)
    feature_input.setSymmetricExtent(adsk.core.ValueInput.createByReal(_cm(thickness_mm * 2.0)), True)
    extrudes.add(feature_input).name = name


def _make_base(component):
    outer = _new_sketch(component, 0, "Base outer")
    _add_rectangle(outer, 0, 0, OUTER_X, OUTER_Y)
    _extrude(component, _all_profiles(outer), OUTER_Z, NEW_BODY, "Case base")

    pocket = _new_sketch(component, FLOOR, "Base pocket")
    _add_rectangle(pocket, WALL, WALL, WALL + INNER_X, WALL + INNER_Y)
    _extrude(component, _all_profiles(pocket), INNER_Z + 1.0, CUT, "Base pocket")

    posts = _new_sketch(component, FLOOR, "Lid screw posts")
    for cx, cy in POST_CENTERS:
        _add_rectangle(posts, cx - POST_HALF, cy - POST_HALF, cx + POST_HALF, cy + POST_HALF)
    _extrude(component, _all_profiles(posts), INNER_Z, JOIN, "Lid screw posts")

    standoffs = _new_sketch(component, FLOOR, "Pico standoffs")
    hole_points = _pico_hole_points()
    for x, y in hole_points:
        _add_circle(standoffs, x, y, STANDOFF_DIAMETER)
    _extrude(component, _all_profiles(standoffs), STANDOFF_HEIGHT, JOIN, "Pico standoffs")

    pilots = _new_sketch(component, FLOOR + 1.0, "Pico pilot holes")
    for x, y in hole_points:
        _add_circle(pilots, x, y, STANDOFF_PILOT)
    _extrude(component, _all_profiles(pilots), STANDOFF_HEIGHT, CUT, "Pico pilot holes")

    post_pilots = _new_sketch(component, OUTER_Z - POST_PILOT_DEPTH, "Post pilot holes")
    for cx, cy in POST_CENTERS:
        _add_circle(post_pilots, cx, cy, POST_PILOT_DIAMETER)
    _extrude(component, _all_profiles(post_pilots), POST_PILOT_DEPTH + 1.0, CUT, "Post pilot holes")

    _cut_db9_openings(component)
    _cut_usb_opening(component)
    _cut_cord_hole(component)


def _pico_hole_points():
    xs = [PICO_X0 + PICO_HOLE_X_INSET, PICO_X0 + PICO_HOLE_X_INSET + PICO_HOLE_SPACING_X]
    ys = [PICO_CENTER_Y - PICO_HOLE_SPACING_Y / 2.0, PICO_CENTER_Y + PICO_HOLE_SPACING_Y / 2.0]
    return [(x, y) for x in xs for y in ys]


def _cut_db9_openings(component):
    sketch = _wall_sketch(component, component.xZConstructionPlane, "y", 0, "DB9 and switch openings")
    lines = sketch.sketchCurves.sketchLines
    inset = DB9_CUT_HEIGHT * math.tan(math.radians(DB9_CUT_SIDE_ANGLE))
    half_top = DB9_CUT_TOP_WIDTH / 2.0
    half_bottom = half_top - inset
    z_top = DB9_CENTER_Z + DB9_CUT_HEIGHT / 2.0
    z_bottom = DB9_CENTER_Z - DB9_CUT_HEIGHT / 2.0
    for cx in DB9_CENTERS_X:
        corners = [
            (cx - half_top, z_top),
            (cx + half_top, z_top),
            (cx + half_bottom, z_bottom),
            (cx - half_bottom, z_bottom),
        ]
        model = [_model_point(sketch, x, 0, z) for x, z in corners]
        for index in range(4):
            lines.addByTwoPoints(model[index], model[(index + 1) % 4])
        for offset in (-DB9_SCREW_SPACING / 2.0, DB9_SCREW_SPACING / 2.0):
            center = _model_point(sketch, cx + offset, 0, DB9_CENTER_Z)
            sketch.sketchCurves.sketchCircles.addByCenterRadius(center, _cm(DB9_SCREW_HOLE / 2.0))
    sketch.sketchCurves.sketchLines.addTwoPointRectangle(
        _model_point(sketch, SWITCH_X - SWITCH_CUT_WIDTH / 2.0, 0, SWITCH_Z - SWITCH_CUT_HEIGHT / 2.0),
        _model_point(sketch, SWITCH_X + SWITCH_CUT_WIDTH / 2.0, 0, SWITCH_Z + SWITCH_CUT_HEIGHT / 2.0))
    _cut_through_wall(component, sketch, WALL, "DB9 and switch openings")


def _cut_usb_opening(component):
    sketch = _wall_sketch(component, component.yZConstructionPlane, "x", 0, "USB opening")
    corner_a = _model_point(
        sketch, 0, PICO_CENTER_Y - USB_CUT_WIDTH / 2.0, USB_CENTER_Z - USB_CUT_HEIGHT / 2.0)
    corner_b = _model_point(
        sketch, 0, PICO_CENTER_Y + USB_CUT_WIDTH / 2.0, USB_CENTER_Z + USB_CUT_HEIGHT / 2.0)
    sketch.sketchCurves.sketchLines.addTwoPointRectangle(corner_a, corner_b)
    _cut_through_wall(component, sketch, WALL, "USB opening")


def _cut_cord_hole(component):
    sketch = _wall_sketch(component, component.xZConstructionPlane, "y", OUTER_Y, "Cord hole")
    center = _model_point(sketch, CORD_HOLE_X, OUTER_Y, CORD_HOLE_Z)
    sketch.sketchCurves.sketchCircles.addByCenterRadius(center, _cm(CORD_HOLE / 2.0))
    _cut_through_wall(component, sketch, WALL, "Cord hole")


def _make_lid(component):
    y0 = LID_Y_OFFSET
    plate = _new_sketch(component, 0, "Lid plate")
    _add_rectangle(plate, 0, y0 - EAR, OUTER_X, y0 + OUTER_Y + EAR)
    _extrude(component, _all_profiles(plate), LID_THICKNESS, NEW_BODY, "Case lid")

    lip_out = LIP_CLEARANCE
    lip_in = LIP_CLEARANCE + LIP_WIDTH
    lip = _new_sketch(component, LID_THICKNESS, "Lid lip outer")
    _add_rectangle(lip, WALL + lip_out, y0 + WALL + lip_out,
                   WALL + INNER_X - lip_out, y0 + WALL + INNER_Y - lip_out)
    _extrude(component, _all_profiles(lip), LIP_HEIGHT, JOIN, "Lid lip")

    hollow = _new_sketch(component, LID_THICKNESS, "Lid lip inner")
    _add_rectangle(hollow, WALL + lip_in, y0 + WALL + lip_in,
                   WALL + INNER_X - lip_in, y0 + WALL + INNER_Y - lip_in)
    _extrude(component, _all_profiles(hollow), LIP_HEIGHT + 1.0, CUT, "Lid lip hollow")

    notches = _new_sketch(component, LID_THICKNESS, "Lid post notches")
    margin = POST_HALF + 0.4
    for cx, cy in POST_CENTERS:
        _add_rectangle(notches, cx - margin, y0 + cy - margin, cx + margin, y0 + cy + margin)
    _extrude(component, _all_profiles(notches), LIP_HEIGHT + 1.0, CUT, "Lid post notches")

    holes = _new_sketch(component, 0, "Lid screw holes")
    for cx, cy in POST_CENTERS:
        _add_circle(holes, cx, y0 + cy, LID_SCREW_HOLE)
    _extrude(component, _all_profiles(holes), LID_THICKNESS + 0.5, CUT, "Lid screw holes")

    ties = _new_sketch(component, 0, "Lid tie slots")
    for cx in TIE_SLOT_X_CENTERS:
        for slot_y in (y0 - EAR / 2.0, y0 + OUTER_Y + EAR / 2.0):
            _add_rectangle(ties, cx - TIE_SLOT_LENGTH / 2.0, slot_y - TIE_SLOT_WIDTH / 2.0,
                           cx + TIE_SLOT_LENGTH / 2.0, slot_y + TIE_SLOT_WIDTH / 2.0)
    _extrude(component, _all_profiles(ties), LID_THICKNESS + 0.5, CUT, "Lid tie slots")


def run(context):
    app = adsk.core.Application.get()
    ui = app.userInterface
    try:
        design = adsk.fusion.Design.cast(app.activeProduct)
        if not design:
            ui.messageBox("Open a new Fusion 360 design, then run this script again.")
            return
        root = design.rootComponent
        _make_base(root)
        _make_lid(root)
        app.activeViewport.fit()
        ui.messageBox(
            "Pico 2 + dual DB9 case created.\n"
            "Base and lid are separate bodies; flip the lid about the Y axis to close.")
    except Exception:
        if ui:
            ui.messageBox("Case generation failed:\n{}".format(traceback.format_exc()))
