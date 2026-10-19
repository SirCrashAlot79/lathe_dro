"""Create a split landscape cradle for a bare Dell Latitude 7285 in Fusion 360.

Run this as a Fusion 360 script in an empty design. The nominal tablet footprint
is approximate: measure the actual bare tablet and edit the constants below.
The script creates editable sketches/extrusions as three separate bodies: left
frame, right frame, and a center arm hub. Each side frame has upper and lower
L-shaped corner wraps with short front lips to retain the tablet.
"""

import math
import traceback
import adsk.core
import adsk.fusion


# Nominal bare-tablet footprint, in millimeters. Edit after measuring the tablet.
TABLET_WIDTH = 275.0
TABLET_HEIGHT = 210.0
TABLET_THICKNESS = 10.0
FIT_CLEARANCE = 0.8

# Frame and corner-wrap geometry.
FRAME_THICKNESS = 8.0
SIDE_RAIL_WIDTH = 14.0
STRUT_WIDTH = 16.0
CORNER_MARGIN = 3.0
CORNER_REACH = 26.0
CLIP_WALL_THICKNESS = 3.2
FRONT_LIP_OVERLAP = 3.5
FRONT_LIP_HEIGHT = 2.4

# Center hub and fasteners.
HUB_WIDTH = 108.0
HUB_HEIGHT = 126.0
HUB_THICKNESS = 16.0
HUB_BOLT_X = 42.0
HUB_BOLT_Y = 50.0
HUB_OVERLAP = 10.0
M4_CLEARANCE = 4.4
M4_NUT_AF = 7.2
M4_NUT_DEPTH = 3.8
QUARTER20_CLEARANCE = 6.8
QUARTER20_NUT_AF = 11.4
QUARTER20_NUT_DEPTH = 6.8
TETHER_HOLE_DIAMETER = 5.0


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


def _add_polygon(sketch, points):
    lines = sketch.sketchCurves.sketchLines
    for index, point in enumerate(points):
        next_point = points[(index + 1) % len(points)]
        lines.addByTwoPoints(_point(point[0], point[1]), _point(next_point[0], next_point[1]))


def _add_rectangle(sketch, x1, y1, x2, y2):
    sketch.sketchCurves.sketchLines.addTwoPointRectangle(_point(x1, y1), _point(x2, y2))


def _add_circle(sketch, x, y, diameter):
    sketch.sketchCurves.sketchCircles.addByCenterRadius(_point(x, y), _cm(diameter / 2.0))


def _add_hex(sketch, x, y, across_flats):
    radius = across_flats / math.sqrt(3.0)
    points = []
    for index in range(6):
        angle = math.radians(30.0 + index * 60.0)
        points.append((x + radius * math.cos(angle), y + radius * math.sin(angle)))
    _add_polygon(sketch, points)


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
    if operation == adsk.fusion.FeatureOperations.NewBodyFeatureOperation and feature.bodies.count:
        feature.bodies.item(0).name = name
    return feature


def _frame_outline(side):
    # The plate extends under the full corner wrap footprint so the wrap walls join it.
    outer_x = TABLET_WIDTH / 2.0 + FIT_CLEARANCE + CLIP_WALL_THICKNESS
    inner_x = outer_x - SIDE_RAIL_WIDTH
    attach_x = HUB_BOLT_X - HUB_OVERLAP
    half_strut = STRUT_WIDTH / 2.0
    y_min = -(TABLET_HEIGHT / 2.0 + FIT_CLEARANCE + CLIP_WALL_THICKNESS)
    y_max = TABLET_HEIGHT / 2.0 + FIT_CLEARANCE + CLIP_WALL_THICKNESS
    y_low = -HUB_BOLT_Y
    y_high = HUB_BOLT_Y
    points = [
        (outer_x, y_min),
        (outer_x, y_max),
        (inner_x, y_max),
        (inner_x, y_high + half_strut),
        (attach_x, y_high + half_strut),
        (attach_x, y_high - half_strut),
        (inner_x, y_high - half_strut),
        (inner_x, y_low + half_strut),
        (attach_x, y_low + half_strut),
        (attach_x, y_low - half_strut),
        (inner_x, y_low - half_strut),
        (inner_x, y_min),
    ]
    return [(side * x, y) for x, y in points]


def _make_frame(component, side):
    frame_name = "Left frame" if side < 0 else "Right frame"
    sketch = _new_sketch(component, -FRAME_THICKNESS, frame_name + " outline")
    _add_polygon(sketch, _frame_outline(side))
    profiles = adsk.core.ObjectCollection.create()
    profiles.add(sketch.profiles.item(0))
    _extrude(component, profiles, FRAME_THICKNESS,
             adsk.fusion.FeatureOperations.NewBodyFeatureOperation,
             frame_name)

    # Hub holes align each side frame to the captured nuts in the center hub.
    cut_sketch = _new_sketch(component, -FRAME_THICKNESS, frame_name + " hub holes")
    for y in (-HUB_BOLT_Y, HUB_BOLT_Y):
        _add_circle(cut_sketch, side * HUB_BOLT_X, y, M4_CLEARANCE)
    _extrude(component, _all_profiles(cut_sketch), FRAME_THICKNESS,
             adsk.fusion.FeatureOperations.CutFeatureOperation,
             "Hub bolt holes")

    # Each side frame wraps its two tablet corners. A single concave L profile
    # per corner keeps the clip open across the long sides for ports/buttons.
    wall_sketch = _new_sketch(component, 0, frame_name + " corner walls")
    x_edge = TABLET_WIDTH / 2.0
    y_edge = TABLET_HEIGHT / 2.0
    x_inner = x_edge + FIT_CLEARANCE - 0.2
    y_inner = y_edge + FIT_CLEARANCE - 0.2
    x_outer = x_edge + FIT_CLEARANCE + CLIP_WALL_THICKNESS
    y_outer = y_edge + FIT_CLEARANCE + CLIP_WALL_THICKNESS
    for y_side in (-1, 1):
        points = [
            (x_inner, y_edge - CORNER_REACH),
            (x_outer, y_edge - CORNER_REACH),
            (x_outer, y_outer),
            (x_edge - CORNER_REACH, y_outer),
            (x_edge - CORNER_REACH, y_inner),
            (x_inner, y_inner),
        ]
        _add_polygon(wall_sketch, [(side * x, y_side * y) for x, y in points])
    _extrude(component, _all_profiles(wall_sketch),
             TABLET_THICKNESS + FIT_CLEARANCE,
             adsk.fusion.FeatureOperations.JoinFeatureOperation,
             frame_name + " wrap walls")

    # Small front lips overlap only the outer corner margins, not the screen.
    lip_sketch = _new_sketch(
        component,
        TABLET_THICKNESS + FIT_CLEARANCE - 0.2,
        frame_name + " corner lips",
    )
    x_min = x_edge - CORNER_REACH
    y_min = y_edge - CORNER_REACH
    x_lip_inner = x_edge - FRONT_LIP_OVERLAP
    y_lip_inner = y_edge - FRONT_LIP_OVERLAP
    for y_side in (-1, 1):
        points = [
            (x_lip_inner, y_min),
            (x_outer, y_min),
            (x_outer, y_outer),
            (x_min, y_outer),
            (x_min, y_lip_inner),
            (x_lip_inner, y_lip_inner),
        ]
        _add_polygon(lip_sketch, [(side * x, y_side * y) for x, y in points])
    _extrude(component, _all_profiles(lip_sketch), FRONT_LIP_HEIGHT,
             adsk.fusion.FeatureOperations.JoinFeatureOperation,
             frame_name + " front retaining lips")


def _make_hub(component):
    hub_back_z = -(FRAME_THICKNESS + HUB_THICKNESS)
    outline = _new_sketch(component, hub_back_z, "Hub outline")
    _add_rectangle(outline, -HUB_WIDTH / 2.0, -HUB_HEIGHT / 2.0,
                   HUB_WIDTH / 2.0, HUB_HEIGHT / 2.0)
    profiles = adsk.core.ObjectCollection.create()
    profiles.add(outline.profiles.item(0))
    _extrude(component, profiles, HUB_THICKNESS,
             adsk.fusion.FeatureOperations.NewBodyFeatureOperation,
             "1-4-20 arm hub")

    # Through holes for four M4 screws and the arm stud.
    through_sketch = _new_sketch(component, hub_back_z, "Hub through holes")
    for sx in (-1, 1):
        for sy in (-1, 1):
            _add_circle(through_sketch, sx * HUB_BOLT_X, sy * HUB_BOLT_Y, M4_CLEARANCE)
    _add_circle(through_sketch, 0, 0, QUARTER20_CLEARANCE)
    for x in (-16.0, 16.0):
        _add_circle(through_sketch, x, 0, TETHER_HOLE_DIAMETER)
    _extrude(component, _all_profiles(through_sketch), HUB_THICKNESS,
             adsk.fusion.FeatureOperations.CutFeatureOperation,
             "Hub through holes")

    # Captured nut pockets open toward the arm. Insert nuts before assembly.
    m4_pockets = _new_sketch(component, hub_back_z, "M4 nut pockets")
    for sx in (-1, 1):
        for sy in (-1, 1):
            _add_hex(m4_pockets, sx * HUB_BOLT_X, sy * HUB_BOLT_Y, M4_NUT_AF)
    _extrude(component, _all_profiles(m4_pockets), M4_NUT_DEPTH,
             adsk.fusion.FeatureOperations.CutFeatureOperation,
             "M4 captured nut pockets")

    quarter20_pocket = _new_sketch(component, hub_back_z, "1-4-20 nut pocket")
    _add_hex(quarter20_pocket, 0, 0, QUARTER20_NUT_AF)
    _extrude(component, _all_profiles(quarter20_pocket), QUARTER20_NUT_DEPTH,
             adsk.fusion.FeatureOperations.CutFeatureOperation,
             "Captured 1-4-20 nut")


def run(context):
    app = adsk.core.Application.get()
    ui = app.userInterface
    try:
        design = adsk.fusion.Design.cast(app.activeProduct)
        if design is None:
            ui.messageBox("Open a new Fusion 360 design, then run this script again.")
            return

        # Part Design documents permit one component, so create three separate
        # bodies in the root component rather than child components/occurrences.
        root = design.rootComponent
        _make_frame(root, -1)
        _make_frame(root, 1)
        _make_hub(root)

        ui.messageBox(
            "Cradle created as three separate bodies in the root component. In the Browser, right-click each body and choose Save as Mesh to export separate STLs.\n"
            "Measure the tablet and adjust the constants at the top of the script before printing. Check the corner lips clear the bezel and do not press controls.\n\n"
            "Hardware: 4 x M4 x 25 screws, 4 x M4 hex nuts, and 1 x 1/4-20 hex nut. Add thin rubber pads at the tablet contact points.\n"
            "Thread a separate safety tether through the two hub holes and secure it to the arm.\n"
            "Proof-test the cradle before mounting it over a person or machine."
        )
    except Exception:
        if ui:
            ui.messageBox("Cradle generation failed:\n{}".format(traceback.format_exc()))


def stop(context):
    pass
