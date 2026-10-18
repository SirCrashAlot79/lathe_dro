"""Fusion 360 generator for the Raspberry Pi DRO mount and electronics enclosure.

Run inside a new Fusion design. It creates separate editable bodies in the root
component so it works in Part Design documents. Measure the screen's outside
case before printing and edit the dimensions below. Geometry has not been
physically fit-tested; print small fit coupons first.
"""

import math
import traceback
import adsk.core
import adsk.fusion

# Screen outer case dimensions in mm. Replace with caliper measurements.
SCREEN_WIDTH = 165.0
SCREEN_HEIGHT = 100.0
SCREEN_THICKNESS = 7.0
SCREEN_Y_CENTER = 36.0

# Screen backplate and arm hub.
PLATE_MARGIN_X = 17.0
PLATE_MARGIN_Y_TOP = 8.0
PLATE_MARGIN_Y_BOTTOM = 75.0
PLATE_THICKNESS = 5.0
STRAP_SLOT_WIDTH = 4.5
STRAP_SLOT_LENGTH = 18.0
SCREEN_STRAP_EDGE_INSET = 10.0
PI_CASE_WIDTH = 90.0
PI_CASE_HEIGHT = 60.0
PI_CASE_Y_CENTER = -59.0
PI_STRAP_SLOT_WIDTH = 4.5
PI_STRAP_SLOT_LENGTH = 20.0
ARM_BOSS_SIZE = 30.0
ARM_BOSS_DEPTH = 10.0
QUARTER20_HOLE_D = 6.8
QUARTER20_NUT_AF = 11.4
QUARTER20_NUT_DEPTH = 6.8

# Pico + signal-interface enclosure.
BOX_WIDTH = 110.0
BOX_HEIGHT = 80.0
BOX_FLOOR = 3.0
BOX_WALL = 3.0
BOX_WALL_HEIGHT = 20.0
BOX_END_CABLE_GAP = 25.0
BOX_POST_SIZE = 9.0
BOX_LID_THICKNESS = 3.0
M3_CLEARANCE = 3.4
M3_NUT_AF = 5.7
M3_NUT_DEPTH = 2.6
BOARD_TIE_SLOT_WIDTH = 4.0
BOARD_TIE_SLOT_LENGTH = 18.0


def _cm(mm):
    return mm / 10.0


def _point(x, y):
    return adsk.core.Point3D.create(_cm(x), _cm(y), 0)


def _sketch(root, z, name):
    plane_input = root.constructionPlanes.createInput()
    plane_input.setByOffset(
        root.xYConstructionPlane,
        adsk.core.ValueInput.createByReal(_cm(z)),
    )
    sketch = root.sketches.add(root.constructionPlanes.add(plane_input))
    sketch.name = name
    return sketch


def _rect(sketch, x1, y1, x2, y2):
    sketch.sketchCurves.sketchLines.addTwoPointRectangle(_point(x1, y1), _point(x2, y2))


def _circle(sketch, x, y, diameter):
    sketch.sketchCurves.sketchCircles.addByCenterRadius(_point(x, y), _cm(diameter / 2.0))


def _polygon(sketch, points):
    lines = sketch.sketchCurves.sketchLines
    for index, point in enumerate(points):
        next_point = points[(index + 1) % len(points)]
        lines.addByTwoPoints(_point(*point), _point(*next_point))


def _hex(sketch, x, y, across_flats):
    radius = across_flats / math.sqrt(3.0)
    points = []
    for index in range(6):
        angle = math.radians(index * 60.0 + 30.0)
        points.append((x + radius * math.cos(angle), y + radius * math.sin(angle)))
    _polygon(sketch, points)


def _profiles(sketch):
    collection = adsk.core.ObjectCollection.create()
    for index in range(sketch.profiles.count):
        collection.add(sketch.profiles.item(index))
    return collection


def _extrude(root, sketch, distance, operation, name):
    feature_input = root.features.extrudeFeatures.createInput(_profiles(sketch), operation)
    feature_input.setDistanceExtent(False, adsk.core.ValueInput.createByReal(_cm(distance)))
    feature = root.features.extrudeFeatures.add(feature_input)
    feature.name = name
    if operation == adsk.fusion.FeatureOperations.NewBodyFeatureOperation:
        for index in range(feature.bodies.count):
            feature.bodies.item(index).name = name if feature.bodies.count == 1 else f"{name} {index + 1}"
    return feature


def _cut(root, body, sketch, distance, name):
    feature_input = root.features.extrudeFeatures.createInput(
        _profiles(sketch), adsk.fusion.FeatureOperations.CutFeatureOperation
    )
    participants = adsk.core.ObjectCollection.create()
    participants.add(body)
    feature_input.participantBodies = participants
    feature_input.setDistanceExtent(False, adsk.core.ValueInput.createByReal(_cm(distance)))
    feature = root.features.extrudeFeatures.add(feature_input)
    feature.name = name
    return feature


def _create_screen_plate(root):
    plate_w = SCREEN_WIDTH + 2.0 * PLATE_MARGIN_X
    plate_h = SCREEN_HEIGHT + PLATE_MARGIN_Y_TOP + PLATE_MARGIN_Y_BOTTOM
    y_min = SCREEN_Y_CENTER - SCREEN_HEIGHT / 2.0 - PLATE_MARGIN_Y_BOTTOM
    y_max = SCREEN_Y_CENTER + SCREEN_HEIGHT / 2.0 + PLATE_MARGIN_Y_TOP

    outline = _sketch(root, 0, "Screen plate outline")
    _rect(outline, -plate_w / 2.0, y_min, plate_w / 2.0, y_max)
    plate_feature = _extrude(root, outline, PLATE_THICKNESS,
                              adsk.fusion.FeatureOperations.NewBodyFeatureOperation,
                              "Screen arm plate")
    plate = plate_feature.bodies.item(0)

    # Four slots let hook-and-loop straps retain a range of touchscreen cases.
    straps = _sketch(root, 0, "Screen strap slots")
    slot_x = SCREEN_WIDTH / 2.0 - 2.0
    slot_y = SCREEN_HEIGHT / 2.0 - SCREEN_STRAP_EDGE_INSET
    for x in (-slot_x, slot_x):
        for y in (SCREEN_Y_CENTER - slot_y, SCREEN_Y_CENTER + slot_y):
            _rect(straps, x - STRAP_SLOT_WIDTH / 2.0, y - STRAP_SLOT_LENGTH / 2.0,
                  x + STRAP_SLOT_WIDTH / 2.0, y + STRAP_SLOT_LENGTH / 2.0)

    # Two pairs of slots attach an off-the-shelf ventilated Pi 4 case behind
    # the touchscreen plate with reusable zip ties.
    pi_x = PI_CASE_WIDTH / 2.0 + 4.0
    pi_y = PI_CASE_HEIGHT / 2.0 - 12.0
    for x in (-pi_x, pi_x):
        for y in (PI_CASE_Y_CENTER - pi_y, PI_CASE_Y_CENTER + pi_y):
            _rect(straps, x - PI_STRAP_SLOT_WIDTH / 2.0, y - PI_STRAP_SLOT_LENGTH / 2.0,
                  x + PI_STRAP_SLOT_WIDTH / 2.0, y + PI_STRAP_SLOT_LENGTH / 2.0)
    _cut(root, plate, straps, PLATE_THICKNESS, "Screen and Pi case tie slots")

    # Arm boss is on the rear (negative Z) side. Print with the boss facing up.
    boss_sketch = _sketch(root, -ARM_BOSS_DEPTH, "1-4-20 arm boss")
    _rect(boss_sketch, -ARM_BOSS_SIZE / 2.0, -ARM_BOSS_SIZE / 2.0,
          ARM_BOSS_SIZE / 2.0, ARM_BOSS_SIZE / 2.0)
    boss_input = root.features.extrudeFeatures.createInput(
        _profiles(boss_sketch), adsk.fusion.FeatureOperations.JoinFeatureOperation
    )
    boss_input.setDistanceExtent(False, adsk.core.ValueInput.createByReal(_cm(ARM_BOSS_DEPTH)))
    boss_feature = root.features.extrudeFeatures.add(boss_input)
    boss_feature.name = "Arm boss"

    through = _sketch(root, -ARM_BOSS_DEPTH, "Arm screw through hole")
    _circle(through, 0, 0, QUARTER20_HOLE_D)
    _cut(root, plate, through, ARM_BOSS_DEPTH + PLATE_THICKNESS, "Arm screw bore")

    nut = _sketch(root, -ARM_BOSS_DEPTH, "Captured 1-4-20 nut pocket")
    _hex(nut, 0, 0, QUARTER20_NUT_AF)
    _cut(root, plate, nut, QUARTER20_NUT_DEPTH, "Captured 1-4-20 nut pocket")


def _create_electronics_box(root):
    half_w = BOX_WIDTH / 2.0
    half_h = BOX_HEIGHT / 2.0
    floor_sketch = _sketch(root, 0, "Pico box floor")
    _rect(floor_sketch, -half_w, -half_h, half_w, half_h)
    floor = _extrude(root, floor_sketch, BOX_FLOOR,
                     adsk.fusion.FeatureOperations.NewBodyFeatureOperation,
                     "Pico and shifter box base").bodies.item(0)

    # Long side rails, with openings at both short ends for cable entries.
    long_walls = _sketch(root, BOX_FLOOR, "Pico box long walls")
    for y in (-half_h + BOX_WALL / 2.0, half_h - BOX_WALL / 2.0):
        _rect(long_walls, -half_w, y - BOX_WALL / 2.0,
              half_w, y + BOX_WALL / 2.0)
    wall_input = root.features.extrudeFeatures.createInput(
        _profiles(long_walls), adsk.fusion.FeatureOperations.JoinFeatureOperation
    )
    wall_input.setDistanceExtent(False, adsk.core.ValueInput.createByReal(_cm(BOX_WALL_HEIGHT)))
    wall_feature = root.features.extrudeFeatures.add(wall_input)
    wall_feature.name = "Pico box side walls"

    # Four screw pillars in the corners support a removable lid.
    pillars = _sketch(root, BOX_FLOOR, "Lid screw pillars")
    post_x = half_w - BOX_POST_SIZE / 2.0 - 2.0
    post_y = half_h - BOX_POST_SIZE / 2.0 - 2.0
    for x in (-post_x, post_x):
        for y in (-post_y, post_y):
            _rect(pillars, x - BOX_POST_SIZE / 2.0, y - BOX_POST_SIZE / 2.0,
                  x + BOX_POST_SIZE / 2.0, y + BOX_POST_SIZE / 2.0)
    pillar_input = root.features.extrudeFeatures.createInput(
        _profiles(pillars), adsk.fusion.FeatureOperations.JoinFeatureOperation
    )
    pillar_input.setDistanceExtent(False, adsk.core.ValueInput.createByReal(_cm(BOX_WALL_HEIGHT)))
    root.features.extrudeFeatures.add(pillar_input).name = "Lid screw pillars"

    # Lid screws pass through the lid and thread into captive M3 nuts in the
    # corner posts. The pockets open at the top face of the posts.
    post_holes = _sketch(root, BOX_FLOOR, "Lid screw post bores")
    for x in (-post_x, post_x):
        for y in (-post_y, post_y):
            _circle(post_holes, x, y, M3_CLEARANCE)
    post_bore_input = root.features.extrudeFeatures.createInput(
        _profiles(post_holes), adsk.fusion.FeatureOperations.CutFeatureOperation
    )
    post_bore_participants = adsk.core.ObjectCollection.create()
    post_bore_participants.add(floor)
    post_bore_input.participantBodies = post_bore_participants
    post_bore_input.setDistanceExtent(False, adsk.core.ValueInput.createByReal(_cm(BOX_WALL_HEIGHT)))
    root.features.extrudeFeatures.add(post_bore_input).name = "Lid screw post bores"

    nut_pockets = _sketch(root, BOX_FLOOR + BOX_WALL_HEIGHT - M3_NUT_DEPTH,
                          "Lid M3 nut pockets")
    for x in (-post_x, post_x):
        for y in (-post_y, post_y):
            _hex(nut_pockets, x, y, M3_NUT_AF)
    nut_input = root.features.extrudeFeatures.createInput(
        _profiles(nut_pockets), adsk.fusion.FeatureOperations.CutFeatureOperation
    )
    nut_participants = adsk.core.ObjectCollection.create()
    nut_participants.add(floor)
    nut_input.participantBodies = nut_participants
    nut_input.setDistanceExtent(False, adsk.core.ValueInput.createByReal(_cm(M3_NUT_DEPTH)))
    root.features.extrudeFeatures.add(nut_input).name = "Lid M3 nut pockets"

    # Tie slots secure the Pico and TXS board without depending on their hole pattern.
    ties = _sketch(root, 0, "Electronics tie slots")
    for x in (-25.0, 25.0):
        for y in (-14.0, 14.0):
            _rect(ties, x - 2.0, y - BOARD_TIE_SLOT_LENGTH / 2.0,
                  x + 2.0, y + BOARD_TIE_SLOT_LENGTH / 2.0)
    _cut(root, floor, ties, BOX_FLOOR, "Electronics tie slots")

    lid_sketch = _sketch(root, 0, "Pico box lid outline")
    _rect(lid_sketch, -half_w, -half_h, half_w, half_h)
    lid = _extrude(root, lid_sketch, BOX_LID_THICKNESS,
                   adsk.fusion.FeatureOperations.NewBodyFeatureOperation,
                   "Pico and shifter box lid").bodies.item(0)
    lid_holes = _sketch(root, 0, "Lid holes and ventilation")
    for x in (-post_x, post_x):
        for y in (-post_y, post_y):
            _circle(lid_holes, x, y, M3_CLEARANCE)
    for x in (-24.0, -12.0, 0.0, 12.0, 24.0):
        _rect(lid_holes, x - 2.0, -20.0, x + 2.0, 20.0)
    _cut(root, lid, lid_holes, BOX_LID_THICKNESS, "Lid holes and vents")


def run(context):
    app = adsk.core.Application.get()
    ui = app.userInterface
    try:
        design = adsk.fusion.Design.cast(app.activeProduct)
        if design is None:
            ui.messageBox("Open a new Fusion design before running this script.")
            return
        root = design.rootComponent
        _create_screen_plate(root)
        _create_electronics_box(root)
        ui.messageBox(
            "Pi DRO mount bodies created. Export the screen plate, Pi case strap mount, and electronics box bodies separately.\n\n"
            "Before printing, edit SCREEN_WIDTH/HEIGHT/THICKNESS to measured case dimensions and confirm arm and Pi-case clearances.\n"
            "Use a commercial ventilated Pi 4 case on the plate. The Pico/TXS box has open cable gaps at both ends."
        )
    except Exception:
        if ui:
            ui.messageBox("Pi DRO hardware generation failed:\n{}".format(traceback.format_exc()))


def stop(context):
    pass
