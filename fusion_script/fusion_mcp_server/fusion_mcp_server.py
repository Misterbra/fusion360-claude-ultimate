# fusion_mcp_server.py - v 0.8.0
#
# MCP Server Add-in for Autodesk Fusion 360
# Connects Fusion 360 to Claude Desktop via file-based JSON communication.

import adsk.core, adsk.fusion, traceback
import threading
import time
import os
import math
import json
import ast
import io
from contextlib import redirect_stdout

# --- Global Variables ---
_app = None
_ui = None
_command_file_path = os.path.join(os.path.expanduser('~'), 'Documents', 'fusion_command.txt')
_response_file_path = os.path.join(os.path.expanduser('~'), 'Documents', 'fusion_response.txt')
_file_watcher_thread = None
_stop_flag = None
_command_received_event_id = 'FusionMCPCommandReceived_JSON_Final'
_command_received_event = None
_event_handler = None
_handlers = []
_mcp_panel = None
_is_running = False
_start_cmd_def = None
_stop_cmd_def = None
_start_cmd_control = None
_stop_cmd_control = None

# --- Helper Functions ---
def log_debug(message):
    try:
        if _ui:
            text_palette = _ui.palettes.itemById('TextCommands')
            if text_palette:
                text_palette.writeText(f"[MCP-PY] {message}")
    except Exception:
        pass

def get_fusion_unit_scale():
    return 0.1  # mm to cm conversion factor

def get_construction_plane(root: adsk.fusion.Component, plane_str: str):
    plane_map = {'yz': root.yZConstructionPlane, 'xz': root.xZConstructionPlane, 'xy': root.xYConstructionPlane}
    return plane_map.get(str(plane_str).lower(), root.xYConstructionPlane)

def get_unique_body_name(root: adsk.fusion.Component, base_name: str) -> str:
    if not base_name:
        base_name = "Body"
    existing_names = {body.name for body in root.bRepBodies}
    if base_name not in existing_names:
        return base_name
    counter = 2
    while True:
        new_name = f"{base_name}_{counter}"
        if new_name not in existing_names:
            return new_name
        counter += 1

def extrude_profile(root, profile, height_cm, direction='positive', taper_angle=0, taper_direction='inward'):
    """Common extrusion logic used by create_cube, create_cylinder, create_box, create_polygon_prism."""
    extrudes = root.features.extrudeFeatures
    ext_input = extrudes.createInput(profile, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
    distance = adsk.core.ValueInput.createByReal(height_cm)
    if direction.lower() == 'positive':
        ext_input.setDistanceExtent(False, distance)
    else:
        extent_definition = adsk.fusion.DistanceExtentDefinition.create(distance)
        ext_input.setOneSideExtent(extent_definition, adsk.fusion.ExtentDirections.NegativeExtentDirection)
    if taper_angle != 0:
        final_taper = abs(taper_angle) * (-1 if taper_direction.lower() == 'inward' else 1)
        taper_angle_input = adsk.core.ValueInput.createByString(f"{final_taper} deg")
        ext_input.taperAngle = taper_angle_input
    return extrudes.add(ext_input).bodies.item(0)

def rotate_body_to_plane(root, body, plane, xz_args, yz_args):
    """Rotate a body to the target construction plane.
    xz_args: (angle_degrees, axis_vector) rotation for xz plane
    yz_args: (angle_degrees, axis_vector) rotation for yz plane
    """
    plane_lower = plane.lower()
    if plane_lower == 'xy':
        return
    if plane_lower == 'xz':
        angle_deg, axis = xz_args
    elif plane_lower == 'yz':
        angle_deg, axis = yz_args
    else:
        return
    transform = adsk.core.Matrix3D.create()
    transform.setToRotation(math.radians(angle_deg), axis, adsk.core.Point3D.create(0, 0, 0))
    move_features = root.features.moveFeatures
    move_input = move_features.createInput(adsk.core.ObjectCollection.createWithArray([body]), transform)
    move_features.add(move_input)
    adsk.doEvents()

VALID_BOOLEAN_OPS = {
    'join': adsk.fusion.FeatureOperations.JoinFeatureOperation,
    'cut': adsk.fusion.FeatureOperations.CutFeatureOperation,
    'intersect': adsk.fusion.FeatureOperations.IntersectFeatureOperation,
}

def validate_boolean_operation(operation: str):
    """Validate and return the Fusion boolean operation enum."""
    op = VALID_BOOLEAN_OPS.get(operation.lower())
    if op is None:
        raise ValueError(f"Invalid operation '{operation}'. Must be one of: {', '.join(VALID_BOOLEAN_OPS.keys())}")
    return op

def move_body_to_absolute_position(body: adsk.fusion.BRepBody, target_cm_pt: adsk.core.Point3D):
    if not body: return
    current_center_pt = body.physicalProperties.centerOfMass
    move_vec = current_center_pt.vectorTo(target_cm_pt)
    if move_vec.length < 1e-6: return
    transform = adsk.core.Matrix3D.create()
    transform.translation = move_vec
    root = _app.activeProduct.rootComponent
    move_features = root.features.moveFeatures
    move_input = move_features.createInput(adsk.core.ObjectCollection.createWithArray([body]), transform)
    move_features.add(move_input)

def move_body_with_placement(body, cx_cm, cy_cm, cz_cm, z_placement, x_placement, y_placement, direction='positive'):
    """Place a body using intuitive placement anchors (top/center/bottom × left/center/right × front/center/back)."""
    if not body:
        return

    bbox = body.boundingBox
    current_centroid = body.physicalProperties.centerOfMass

    # Z-axis placement
    if z_placement == 'bottom':
        target_centroid_z = cz_cm + (current_centroid.z - bbox.minPoint.z)
    elif z_placement == 'top':
        target_centroid_z = cz_cm + (current_centroid.z - bbox.maxPoint.z)
    else:
        target_centroid_z = cz_cm

    # X-axis placement
    if x_placement == 'left':
        target_centroid_x = cx_cm + (current_centroid.x - bbox.minPoint.x)
    elif x_placement == 'right':
        target_centroid_x = cx_cm + (current_centroid.x - bbox.maxPoint.x)
    else:
        target_centroid_x = cx_cm

    # Y-axis placement (Fusion 360: -Y = Front, +Y = Back)
    if y_placement == 'front':
        target_centroid_y = cy_cm + (current_centroid.y - bbox.minPoint.y)
    elif y_placement == 'back':
        target_centroid_y = cy_cm + (current_centroid.y - bbox.maxPoint.y)
    else:
        target_centroid_y = cy_cm

    target_point = adsk.core.Point3D.create(target_centroid_x, target_centroid_y, target_centroid_z)
    move_body_to_absolute_position(body, target_point)

def find_entity_by_name(name: str):
    if not name: return None
    root = _app.activeProduct.rootComponent
    entity = next((b for b in root.bRepBodies if b.name == name), None)
    if entity: return entity
    return next((occ for occ in root.occurrences if occ.name.split(':', 1)[0] == name), None)

def _finalize_body(body, root, body_name, cx_cm, cy_cm, cz_cm, z_placement, x_placement, y_placement, direction='positive'):
    """Common post-creation logic: placement + naming."""
    move_body_with_placement(body, cx_cm, cy_cm, cz_cm, z_placement, x_placement, y_placement, direction)
    if body_name:
        body.name = get_unique_body_name(root, body_name)
    return body.name

# --- Debug Functions ---
def debug_body_placement(body_name: str, **kwargs):
    body = find_entity_by_name(body_name)
    if not body:
        return f"Body '{body_name}' not found."

    bbox = body.boundingBox
    centroid = body.physicalProperties.centerOfMass
    scale = get_fusion_unit_scale()

    info = f"=== Placement info for '{body_name}' ===\n"
    info += f"Center of mass: ({centroid.x/scale:.2f}, {centroid.y/scale:.2f}, {centroid.z/scale:.2f}) mm\n"
    info += f"Bounding box:\n"
    info += f"  Min: ({bbox.minPoint.x/scale:.2f}, {bbox.minPoint.y/scale:.2f}, {bbox.minPoint.z/scale:.2f}) mm\n"
    info += f"  Max: ({bbox.maxPoint.x/scale:.2f}, {bbox.maxPoint.y/scale:.2f}, {bbox.maxPoint.z/scale:.2f}) mm\n"
    info += f"Size:\n"
    info += f"  Width  (X): {(bbox.maxPoint.x - bbox.minPoint.x)/scale:.2f} mm\n"
    info += f"  Depth  (Y): {(bbox.maxPoint.y - bbox.minPoint.y)/scale:.2f} mm\n"
    info += f"  Height (Z): {(bbox.maxPoint.z - bbox.minPoint.z)/scale:.2f} mm\n"
    info += f"Edges:\n"
    info += f"  Left   (X-): {bbox.minPoint.x/scale:.2f} mm\n"
    info += f"  Right  (X+): {bbox.maxPoint.x/scale:.2f} mm\n"
    info += f"  Front  (Y-): {bbox.minPoint.y/scale:.2f} mm\n"
    info += f"  Back   (Y+): {bbox.maxPoint.y/scale:.2f} mm\n"
    info += f"  Bottom (Z-): {bbox.minPoint.z/scale:.2f} mm\n"
    info += f"  Top    (Z+): {bbox.maxPoint.z/scale:.2f} mm\n"

    return info

# --- Shape Creation Functions ---
def create_cube(size: float=50, body_name: str=None, plane: str='xy', cx: float=0, cy: float=0, cz: float=0, z_placement: str='center', x_placement: str='center', y_placement: str='center', taper_angle: float=0, taper_direction: str='inward', direction: str='positive', **kwargs):
    scale = get_fusion_unit_scale()
    size_cm = size * scale
    cx_cm, cy_cm, cz_cm = cx * scale, cy * scale, cz * scale
    root = _app.activeProduct.rootComponent
    sketch = root.sketches.add(get_construction_plane(root, plane))
    sketch.sketchCurves.sketchLines.addTwoPointRectangle(adsk.core.Point3D.create(-size_cm/2, -size_cm/2, 0), adsk.core.Point3D.create(size_cm/2, size_cm/2, 0))
    prof = sketch.profiles.item(0)
    new_body = extrude_profile(root, prof, size_cm, direction, taper_angle, taper_direction)
    sketch.isVisible = False
    return _finalize_body(new_body, root, body_name, cx_cm, cy_cm, cz_cm, z_placement, x_placement, y_placement, direction)

def create_cylinder(radius: float=25, height: float=50, body_name: str=None, plane: str='xy', cx: float=0, cy: float=0, cz: float=0, z_placement: str='center', x_placement: str='center', y_placement: str='center', taper_angle: float=0, taper_direction: str='inward', direction: str='positive', **kwargs):
    scale = get_fusion_unit_scale()
    radius_cm, height_cm = radius * scale, height * scale
    cx_cm, cy_cm, cz_cm = cx * scale, cy * scale, cz * scale
    root = _app.activeProduct.rootComponent
    sketch = root.sketches.add(get_construction_plane(root, plane))
    sketch.sketchCurves.sketchCircles.addByCenterRadius(adsk.core.Point3D.create(0, 0, 0), radius_cm)
    prof = sketch.profiles.item(0)
    new_body = extrude_profile(root, prof, height_cm, direction, taper_angle, taper_direction)
    sketch.isVisible = False
    return _finalize_body(new_body, root, body_name, cx_cm, cy_cm, cz_cm, z_placement, x_placement, y_placement, direction)

def create_box(width: float=50, depth: float=30, height: float=20, body_name: str=None, plane: str='xy', cx: float=0, cy: float=0, cz: float=0, z_placement: str='center', x_placement: str='center', y_placement: str='center', taper_angle: float=0, taper_direction: str='inward', direction: str='positive', **kwargs):
    scale = get_fusion_unit_scale()
    width_cm, depth_cm, height_cm = width * scale, depth * scale, height * scale
    cx_cm, cy_cm, cz_cm = cx * scale, cy * scale, cz * scale
    root = _app.activeProduct.rootComponent
    sketch = root.sketches.add(get_construction_plane(root, plane))
    sketch.sketchCurves.sketchLines.addTwoPointRectangle(adsk.core.Point3D.create(-width_cm/2, -depth_cm/2, 0), adsk.core.Point3D.create(width_cm/2, depth_cm/2, 0))
    prof = sketch.profiles.item(0)
    new_body = extrude_profile(root, prof, height_cm, direction, taper_angle, taper_direction)
    sketch.isVisible = False
    return _finalize_body(new_body, root, body_name, cx_cm, cy_cm, cz_cm, z_placement, x_placement, y_placement, direction)

def create_sphere(radius: float=25, body_name: str=None, cx: float=0, cy: float=0, cz: float=0, **kwargs):
    scale = get_fusion_unit_scale()
    radius_cm = radius * scale
    cx_cm, cy_cm, cz_cm = cx * scale, cy * scale, cz * scale
    root = _app.activeProduct.rootComponent
    sketch = root.sketches.add(root.xYConstructionPlane)
    center_pt = adsk.core.Point3D.create(0, 0, 0)
    arc = sketch.sketchCurves.sketchArcs.addByCenterStartEnd(center_pt, adsk.core.Point3D.create(0, radius_cm, 0), adsk.core.Point3D.create(0, -radius_cm, 0))
    sketch.sketchCurves.sketchLines.addByTwoPoints(arc.startSketchPoint, arc.endSketchPoint)
    prof = sketch.profiles.item(0)
    revolves = root.features.revolveFeatures
    revolution_axis = root.yConstructionAxis
    revolve_input = revolves.createInput(prof, revolution_axis, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
    revolve_input.setAngleExtent(False, adsk.core.ValueInput.createByReal(math.pi * 2))
    new_body = revolves.add(revolve_input).bodies.item(0)
    sketch.isVisible = False
    move_body_to_absolute_position(new_body, adsk.core.Point3D.create(cx_cm, cy_cm, cz_cm))
    if body_name: new_body.name = get_unique_body_name(root, body_name)
    return new_body.name

def create_hemisphere(radius: float=25, body_name: str=None, plane: str='xy', cx: float=0, cy: float=0, cz: float=0, orientation: str='positive', z_placement: str='bottom', x_placement: str='center', y_placement: str='center', **kwargs):
    scale = get_fusion_unit_scale()
    radius_cm = radius * scale
    cx_cm, cy_cm, cz_cm = cx * scale, cy * scale, cz * scale
    root = _app.activeProduct.rootComponent
    sketch = root.sketches.add(root.xYConstructionPlane)
    arc = sketch.sketchCurves.sketchArcs.addByThreePoints(adsk.core.Point3D.create(-radius_cm, 0, 0), adsk.core.Point3D.create(0, radius_cm, 0), adsk.core.Point3D.create(radius_cm, 0, 0))
    axis_line = sketch.sketchCurves.sketchLines.addByTwoPoints(arc.startSketchPoint, arc.endSketchPoint)
    prof = sketch.profiles.item(0)
    revolves = root.features.revolveFeatures
    revolve_input = revolves.createInput(prof, axis_line, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
    angle = adsk.core.ValueInput.createByReal(math.pi * (-1 if orientation.lower() == 'negative' else 1))
    revolve_input.setAngleExtent(False, angle)
    new_body = revolves.add(revolve_input).bodies.item(0)
    sketch.isVisible = False
    rotate_body_to_plane(root, new_body, plane,
        xz_args=(90, adsk.core.Vector3D.create(1, 0, 0)),
        yz_args=(-90, adsk.core.Vector3D.create(0, 1, 0)))
    return _finalize_body(new_body, root, body_name, cx_cm, cy_cm, cz_cm, z_placement, x_placement, y_placement)

def create_cone(radius: float=25, height: float=50, body_name: str=None, plane: str='xy', cx: float=0, cy: float=0, cz: float=0, z_placement: str='center', x_placement: str='center', y_placement: str='center', **kwargs):
    scale = get_fusion_unit_scale()
    radius_cm, height_cm = radius * scale, height * scale
    cx_cm, cy_cm, cz_cm = cx * scale, cy * scale, cz * scale
    root = _app.activeProduct.rootComponent
    sketch = root.sketches.add(root.xYConstructionPlane)
    p1 = adsk.core.Point3D.create(0, 0, 0)
    p2 = adsk.core.Point3D.create(radius_cm, 0, 0)
    p3 = adsk.core.Point3D.create(0, 0, height_cm)
    lines = sketch.sketchCurves.sketchLines
    lines.addByTwoPoints(p1, p2)
    lines.addByTwoPoints(p2, p3)
    axis_line = lines.addByTwoPoints(p3, p1)
    prof = sketch.profiles.item(0)
    revolves = root.features.revolveFeatures
    revolve_input = revolves.createInput(prof, axis_line, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
    revolve_input.setAngleExtent(False, adsk.core.ValueInput.createByReal(math.pi * 2))
    new_body = revolves.add(revolve_input).bodies.item(0)
    sketch.isVisible = False
    rotate_body_to_plane(root, new_body, plane,
        xz_args=(-90, adsk.core.Vector3D.create(1, 0, 0)),
        yz_args=(90, adsk.core.Vector3D.create(0, 1, 0)))
    return _finalize_body(new_body, root, body_name, cx_cm, cy_cm, cz_cm, z_placement, x_placement, y_placement)

def create_polygon_prism(num_sides: int=6, radius: float=25, height: float=50, body_name: str=None, plane: str='xy', cx: float=0, cy: float=0, cz: float=0, z_placement: str='center', x_placement: str='center', y_placement: str='center', taper_angle: float=0, taper_direction: str='inward', direction: str='positive', **kwargs):
    if num_sides < 3: raise ValueError("Polygon must have at least 3 sides.")
    scale = get_fusion_unit_scale()
    radius_cm, height_cm = radius * scale, height * scale
    cx_cm, cy_cm, cz_cm = cx * scale, cy * scale, cz * scale
    root = _app.activeProduct.rootComponent
    sketch = root.sketches.add(get_construction_plane(root, plane))
    points = [adsk.core.Point3D.create(radius_cm * math.cos(i * 2 * math.pi / num_sides), radius_cm * math.sin(i * 2 * math.pi / num_sides), 0) for i in range(num_sides)]
    lines = sketch.sketchCurves.sketchLines
    for i in range(num_sides):
        lines.addByTwoPoints(points[i], points[(i + 1) % num_sides])
    prof = sketch.profiles.item(0)
    new_body = extrude_profile(root, prof, height_cm, direction, taper_angle, taper_direction)
    sketch.isVisible = False
    return _finalize_body(new_body, root, body_name, cx_cm, cy_cm, cz_cm, z_placement, x_placement, y_placement, direction)

def create_torus(major_radius=30, minor_radius=10, cx=0, cy=0, cz=0, plane='xy', z_placement='center', x_placement='center', y_placement='center', body_name=None, **kwargs):
    scale = get_fusion_unit_scale()
    major_radius_cm, minor_radius_cm = major_radius * scale, minor_radius * scale
    cx_cm, cy_cm, cz_cm = cx * scale, cy * scale, cz * scale
    root = _app.activeProduct.rootComponent
    sketch = root.sketches.add(root.xZConstructionPlane)
    sketch.sketchCurves.sketchCircles.addByCenterRadius(
        adsk.core.Point3D.create(major_radius_cm, 0, 0), minor_radius_cm)
    prof = sketch.profiles.item(0)
    revolves = root.features.revolveFeatures
    revolve_input = revolves.createInput(prof, root.zConstructionAxis, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
    revolve_input.setAngleExtent(False, adsk.core.ValueInput.createByReal(math.pi * 2))
    new_body = revolves.add(revolve_input).bodies.item(0)
    sketch.isVisible = False
    rotate_body_to_plane(root, new_body, plane,
        xz_args=(90, adsk.core.Vector3D.create(1, 0, 0)),
        yz_args=(90, adsk.core.Vector3D.create(0, 1, 0)))
    # Torus is created on XZ plane, so 'xz' is the default — rotation only needed for xy and yz
    # But rotate_body_to_plane skips 'xy', and torus needs rotation FOR xy. Override:
    if plane.lower() == 'xy':
        # No rotation needed — torus on XZ is already correct for XY viewing in Z-up
        pass
    return _finalize_body(new_body, root, body_name, cx_cm, cy_cm, cz_cm, z_placement, x_placement, y_placement)

def create_half_torus(major_radius=30, minor_radius=10, cx=0, cy=0, cz=0, plane='xy', z_placement='center', x_placement='center', y_placement='center', body_name=None, orientation: str='back', plane_rotation_angle: float=0, opening_extrude_distance: float=0, **kwargs):
    scale = get_fusion_unit_scale()
    major_radius_cm, minor_radius_cm = major_radius * scale, minor_radius * scale
    cx_cm, cy_cm, cz_cm = cx * scale, cy * scale, cz * scale
    root = _app.activeProduct.rootComponent
    move_features = root.features.moveFeatures

    # --- Create half torus body ---
    sketch = root.sketches.add(root.xZConstructionPlane)
    sketch.sketchCurves.sketchCircles.addByCenterRadius(
        adsk.core.Point3D.create(major_radius_cm, 0, 0), minor_radius_cm)
    prof = sketch.profiles.item(0)
    revolves = root.features.revolveFeatures
    revolve_input = revolves.createInput(prof, root.zConstructionAxis, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
    revolve_input.setAngleExtent(False, adsk.core.ValueInput.createByReal(math.pi))
    new_body = revolves.add(revolve_input).bodies.item(0)
    sketch.isVisible = False

    # --- Rotation ---
    transform_matrix = adsk.core.Matrix3D.create()
    plane_normal = adsk.core.Vector3D.create(0, 0, 1)

    plane_lower = plane.lower()
    if plane_lower == 'xz':
        transform_matrix.setToRotation(math.pi / 2, adsk.core.Vector3D.create(1, 0, 0), adsk.core.Point3D.create(0, 0, 0))
        plane_normal = adsk.core.Vector3D.create(0, 1, 0)
    elif plane_lower == 'yz':
        transform_matrix.setToRotation(-math.pi / 2, adsk.core.Vector3D.create(0, 1, 0), adsk.core.Point3D.create(0, 0, 0))
        plane_normal = adsk.core.Vector3D.create(1, 0, 0)

    orientation_angle_deg = 0
    orientation_lower = orientation.lower()
    # Orientation mapping is the same for all planes
    if orientation_lower == 'back': orientation_angle_deg = 180
    elif orientation_lower == 'left': orientation_angle_deg = 90
    elif orientation_lower == 'right': orientation_angle_deg = -90

    total_rotation_angle_rad = math.radians(orientation_angle_deg + plane_rotation_angle)

    if total_rotation_angle_rad != 0:
        orientation_matrix = adsk.core.Matrix3D.create()
        orientation_matrix.setToRotation(total_rotation_angle_rad, plane_normal, adsk.core.Point3D.create(0, 0, 0))
        transform_matrix.transformBy(orientation_matrix)

    if not transform_matrix.isEqualTo(adsk.core.Matrix3D.create()):
        move_input = move_features.createInput(adsk.core.ObjectCollection.createWithArray([new_body]), transform_matrix)
        move_features.add(move_input)
        adsk.doEvents()

    # --- Final placement ---
    move_body_with_placement(new_body, cx_cm, cy_cm, cz_cm, z_placement, x_placement, y_placement, 'positive')

    # --- Opening face extrusion ---
    if opening_extrude_distance != 0:
        extrude_faces = adsk.core.ObjectCollection.create()
        for face in new_body.faces:
            if face.geometry.objectType == adsk.core.Plane.classType():
                extrude_faces.add(face)

        if extrude_faces.count == 2:
            extrudes = root.features.extrudeFeatures
            distance = adsk.core.ValueInput.createByReal(opening_extrude_distance * get_fusion_unit_scale())
            extrude_input = extrudes.createInput(extrude_faces, adsk.fusion.FeatureOperations.JoinFeatureOperation)
            extrude_input.setDistanceExtent(False, distance)
            extrudes.add(extrude_input)
            log_debug(f"Extruded opening faces by {opening_extrude_distance}mm.")
        else:
            log_debug(f"Warning: Expected 2 planar faces for extrusion, but found {extrude_faces.count}. Skipping extrusion.")

    if body_name:
        new_body.name = get_unique_body_name(root, body_name)
    return new_body.name

def create_pipe(x1: float=0, y1: float=0, z1: float=0, x2: float=50, y2: float=0, z2: float=50, radius: float=5, body_name: str=None, **kwargs):
    scale = get_fusion_unit_scale()
    radius_cm = radius * scale
    p1 = adsk.core.Point3D.create(x1 * scale, y1 * scale, z1 * scale)
    p2 = adsk.core.Point3D.create(x2 * scale, y2 * scale, z2 * scale)
    root = _app.activeProduct.rootComponent
    direction = p1.vectorTo(p2)
    length = direction.length
    direction.normalize()
    center = adsk.core.Point3D.create(
        (p1.x + p2.x) / 2,
        (p1.y + p2.y) / 2,
        (p1.z + p2.z) / 2
    )
    sketch = root.sketches.add(root.xYConstructionPlane)
    sketch.sketchCurves.sketchCircles.addByCenterRadius(adsk.core.Point3D.create(0, 0, 0), radius_cm)
    prof = sketch.profiles.item(0)
    extrudes = root.features.extrudeFeatures
    ext_input = extrudes.createInput(prof, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
    ext_input.setTwoSidesExtent(
        adsk.fusion.DistanceExtentDefinition.create(adsk.core.ValueInput.createByReal(length/2)),
        adsk.fusion.DistanceExtentDefinition.create(adsk.core.ValueInput.createByReal(length/2))
    )
    extrude_feature = extrudes.add(ext_input)
    new_body = extrude_feature.bodies.item(0)
    sketch.isVisible = False
    z_axis = adsk.core.Vector3D.create(0, 0, 1)
    dot_product = direction.dotProduct(z_axis)
    if abs(dot_product) < 0.999:
        rotation_axis = z_axis.crossProduct(direction)
        rotation_axis.normalize()
        angle = z_axis.angleTo(direction)
        transform = adsk.core.Matrix3D.create()
        transform.setToRotation(angle, rotation_axis, adsk.core.Point3D.create(0, 0, 0))
        move_features = root.features.moveFeatures
        move_input = move_features.createInput(adsk.core.ObjectCollection.createWithArray([new_body]), transform)
        move_features.add(move_input)
        adsk.doEvents()
    elif dot_product < 0:
        transform = adsk.core.Matrix3D.create()
        transform.setToRotation(math.pi, adsk.core.Vector3D.create(1, 0, 0), adsk.core.Point3D.create(0, 0, 0))
        move_features = root.features.moveFeatures
        move_input = move_features.createInput(adsk.core.ObjectCollection.createWithArray([new_body]), transform)
        move_features.add(move_input)
        adsk.doEvents()

    current_center = new_body.physicalProperties.centerOfMass
    move_vector = current_center.vectorTo(center)

    if move_vector.length > 1e-6:
        transform2 = adsk.core.Matrix3D.create()
        transform2.translation = move_vector
        move_features = root.features.moveFeatures
        move_input2 = move_features.createInput(adsk.core.ObjectCollection.createWithArray([new_body]), transform2)
        move_features.add(move_input2)

    if body_name:
        new_body.name = get_unique_body_name(root, body_name)
    return new_body.name

def create_polygon_sweep(cx=0, cy=0, cz=0, path_radius=30, sweep_angle=360,
                        profile_sides=6, profile_radius=10, plane="xy",
                        x_placement="center", y_placement="center", z_placement="center",
                        twist_rotations=0, body_name=None, **kwargs):
    """Sweep a polygon profile along a circular path."""
    if sweep_angle != 360:
        raise ValueError(f"sweep_angle must be 360. Got: {sweep_angle}")

    if not (0 <= twist_rotations <= 10):
        raise ValueError(f"twist_rotations must be between 0 and 10. Got: {twist_rotations}")

    twist_angle = twist_rotations * 360

    if path_radius <= profile_radius:
        raise ValueError(f"path_radius ({path_radius}) must be greater than profile_radius ({profile_radius}) to avoid self-intersection.")

    root = _app.activeProduct.rootComponent
    scale = get_fusion_unit_scale()

    path_radius_cm = path_radius * scale
    profile_radius_cm = profile_radius * scale
    cx_cm, cy_cm, cz_cm = cx * scale, cy * scale, cz * scale

    log_debug(f"Creating polygon sweep: path_radius={path_radius}mm, profile_radius={profile_radius}mm, twist_rotations={twist_rotations}")

    # 1. Path sketch on XZ plane
    path_sketch = root.sketches.add(root.xZConstructionPlane)
    path_curve = path_sketch.sketchCurves.sketchCircles.addByCenterRadius(
        adsk.core.Point3D.create(0, 0, 0), path_radius_cm)

    # 2. Profile sketch on XY plane (perpendicular to path start)
    profile_sketch = root.sketches.add(root.xYConstructionPlane)
    profile_center_pt = adsk.core.Point3D.create(path_radius_cm, 0, 0)

    profile_points = []
    for i in range(profile_sides):
        angle = (2 * math.pi * i) / profile_sides
        x = profile_center_pt.x + profile_radius_cm * math.cos(angle)
        y = profile_center_pt.y + profile_radius_cm * math.sin(angle)
        profile_points.append(adsk.core.Point3D.create(x, y, 0))

    lines = profile_sketch.sketchCurves.sketchLines
    for i in range(profile_sides):
        lines.addByTwoPoints(profile_points[i], profile_points[(i + 1) % profile_sides])

    try:
        profile = profile_sketch.profiles.item(0)
    except Exception:
        raise RuntimeError("Failed to create closed polygon profile.")

    # 3. Execute sweep
    path_obj = adsk.fusion.Path.create(path_curve, adsk.fusion.ChainedCurveOptions.connectedChainedCurves)
    sweeps = root.features.sweepFeatures
    sweep_input = sweeps.createInput(profile, path_obj, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)

    if twist_angle != 0:
        twist_angle_rad = math.radians(twist_angle)
        twist_angle_value = adsk.core.ValueInput.createByReal(twist_angle_rad)
        try:
            sweep_input.twistAngle = twist_angle_value
        except Exception as e:
            log_debug(f"Warning: Failed to set twist angle: {e}")

    new_body = sweeps.add(sweep_input).bodies.item(0)
    path_sketch.isVisible = False
    profile_sketch.isVisible = False

    # 4. Rotate body to target plane
    plane_lower = plane.lower()
    if plane_lower == 'xy':
        transform = adsk.core.Matrix3D.create()
        transform.setToRotation(-math.pi / 2, adsk.core.Vector3D.create(1, 0, 0), adsk.core.Point3D.create(0, 0, 0))
        move_features = root.features.moveFeatures
        move_input = move_features.createInput(adsk.core.ObjectCollection.createWithArray([new_body]), transform)
        move_features.add(move_input)
        adsk.doEvents()
    elif plane_lower == 'yz':
        transform = adsk.core.Matrix3D.create()
        transform.setToRotation(math.pi / 2, adsk.core.Vector3D.create(0, 0, 1), adsk.core.Point3D.create(0, 0, 0))
        move_features = root.features.moveFeatures
        move_input = move_features.createInput(adsk.core.ObjectCollection.createWithArray([new_body]), transform)
        move_features.add(move_input)
        adsk.doEvents()

    # 5. Final placement
    move_body_with_placement(new_body, cx_cm, cy_cm, cz_cm, z_placement, x_placement, y_placement, 'positive')

    if body_name:
        new_body.name = get_unique_body_name(root, body_name)

    log_debug(f"Polygon sweep created with {twist_rotations} rotations")
    return new_body.name

# --- Pattern & Copy Functions ---
def copy_body_symmetric(source_body_name: str, new_body_name: str, plane: str = 'xy', **kwargs):
    source_body = find_entity_by_name(source_body_name)
    if not source_body: raise ValueError(f"Body '{source_body_name}' not found.")
    root = _app.activeProduct.rootComponent
    mirror_features = root.features.mirrorFeatures
    mirror_input = mirror_features.createInput(adsk.core.ObjectCollection.createWithArray([source_body]), get_construction_plane(root, plane))
    mirror_input.patternComputeOption = adsk.fusion.PatternComputeOptions.IdenticalPatternCompute
    new_body = mirror_features.add(mirror_input).bodies.item(0)
    if new_body_name:
        new_body.name = get_unique_body_name(root, new_body_name)
    return new_body.name

def create_circular_pattern(source_body_name: str, axis: str = 'z', quantity: int = 4, angle: float = 360.0, new_body_base_name: str = None, **kwargs):
    source_body = find_entity_by_name(source_body_name)
    if not source_body: raise ValueError(f"Body '{source_body_name}' not found.")
    root = _app.activeProduct.rootComponent
    axis_map = {'x': root.xConstructionAxis, 'y': root.yConstructionAxis, 'z': root.zConstructionAxis}
    rotation_axis = axis_map.get(axis.lower())
    if not rotation_axis: raise ValueError(f"Invalid axis: {axis}")
    circular_patterns = root.features.circularPatternFeatures
    pattern_input = circular_patterns.createInput(adsk.core.ObjectCollection.createWithArray([source_body]), rotation_axis)
    pattern_input.quantity = adsk.core.ValueInput.createByReal(quantity)
    if angle == 360.0:
        pattern_input.isFull = True
    else:
        pattern_input.isFull = False
        pattern_input.totalAngle = adsk.core.ValueInput.createByString(f"{angle} deg")
    pattern_input.patternComputeOption = adsk.fusion.PatternComputeOptions.IdenticalPatternCompute

    pattern_feature = circular_patterns.add(pattern_input)
    if new_body_base_name:
        for i, body in enumerate(pattern_feature.bodies):
            body.name = get_unique_body_name(root, f"{new_body_base_name}_{i+1}")

    return f"Created circular pattern with {quantity} instances."

def create_rectangular_pattern(source_body_name: str, distance_type: str='spacing', quantity_one: int=2, distance_one: float=10.0, direction_one_axis: str='x', quantity_two: int=1, distance_two: float=10.0, direction_two_axis: str='y', new_body_base_name: str=None, **kwargs):
    source_body = find_entity_by_name(source_body_name)
    if not source_body: raise ValueError(f"Body '{source_body_name}' not found.")
    root = _app.activeProduct.rootComponent
    scale = get_fusion_unit_scale()
    axis_map = {'x': root.xConstructionAxis, 'y': root.yConstructionAxis, 'z': root.zConstructionAxis}
    dir_one = axis_map.get(direction_one_axis.lower())
    dir_two = axis_map.get(direction_two_axis.lower())
    rect_patterns = root.features.rectangularPatternFeatures
    dist_type_enum = adsk.fusion.PatternDistanceType.ExtentPatternDistanceType if distance_type.lower() == 'extent' else adsk.fusion.PatternDistanceType.SpacingPatternDistanceType
    pattern_input = rect_patterns.createInput(adsk.core.ObjectCollection.createWithArray([source_body]), dir_one, adsk.core.ValueInput.createByReal(quantity_one), adsk.core.ValueInput.createByReal(distance_one * scale), dist_type_enum)
    if quantity_two > 1 and dir_two:
        pattern_input.setDirectionTwo(dir_two, adsk.core.ValueInput.createByReal(quantity_two), adsk.core.ValueInput.createByReal(distance_two * scale))
    pattern_input.patternComputeOption = adsk.fusion.PatternComputeOptions.IdenticalPatternCompute

    pattern_feature = rect_patterns.add(pattern_input)
    if new_body_base_name:
        for i, body in enumerate(pattern_feature.bodies):
            body.name = get_unique_body_name(root, f"{new_body_base_name}_{i+1}")

    return f"Created rectangular pattern {quantity_one}x{quantity_two}."

# --- Modification Functions ---
def add_fillet(body_name: str, radius: float=1.0, edge_indices: list=None, **kwargs):
    """Add fillet to specific edges of a body (by 0-based edge index)."""
    target_body = find_entity_by_name(body_name)
    if not target_body:
        raise ValueError(f"Body '{body_name}' not found.")

    all_edges = target_body.edges
    edges_to_fillet = adsk.core.ObjectCollection.create()

    if edge_indices and isinstance(edge_indices, list) and len(edge_indices) > 0:
        log_debug(f"Applying fillet to edge indices: {edge_indices}")
        for index in edge_indices:
            try:
                idx = int(index)
                if 0 <= idx < all_edges.count:
                    edges_to_fillet.add(all_edges.item(idx))
                else:
                    log_debug(f"Warning: Invalid edge index {idx}, skipping.")
            except (ValueError, TypeError):
                log_debug(f"Warning: Non-numeric edge index '{index}', skipping.")
    else:
        log_debug("No edge indices specified, filleting all boundary edges.")
        for edge in all_edges:
            if len(edge.faces) == 2:
                edges_to_fillet.add(edge)

    if edges_to_fillet.count == 0:
        return "No edges found for fillet."

    root = _app.activeProduct.rootComponent
    fillets = root.features.filletFeatures
    fillet_input = fillets.createInput()
    fillet_input.addConstantRadiusEdgeSet(edges_to_fillet, adsk.core.ValueInput.createByReal(radius * get_fusion_unit_scale()), True)
    fillets.add(fillet_input)

    return f"Added {radius}mm fillet to {edges_to_fillet.count} edges."

def add_chamfer(body_name: str, distance: float=1.0, edge_indices: list=None, **kwargs):
    """Add chamfer to specific edges of a body (by 0-based edge index)."""
    target_body = find_entity_by_name(body_name)
    if not target_body:
        raise ValueError(f"Body '{body_name}' not found.")

    all_edges = target_body.edges
    edges_to_chamfer = adsk.core.ObjectCollection.create()

    if edge_indices and isinstance(edge_indices, list) and len(edge_indices) > 0:
        log_debug(f"Applying chamfer to edge indices: {edge_indices}")
        for index in edge_indices:
            try:
                idx = int(index)
                if 0 <= idx < all_edges.count:
                    edges_to_chamfer.add(all_edges.item(idx))
                else:
                    log_debug(f"Warning: Invalid edge index {idx}, skipping.")
            except (ValueError, TypeError):
                log_debug(f"Warning: Non-numeric edge index '{index}', skipping.")
    else:
        log_debug("No edge indices specified, chamfering all boundary edges.")
        for edge in all_edges:
            if len(edge.faces) == 2:
                edges_to_chamfer.add(edge)

    if edges_to_chamfer.count == 0:
        return "No edges found for chamfer."

    root = _app.activeProduct.rootComponent
    chamfers = root.features.chamferFeatures
    chamfer_input = chamfers.createInput(edges_to_chamfer, True)
    chamfer_input.setToEqualDistance(adsk.core.ValueInput.createByReal(distance * get_fusion_unit_scale()))
    chamfers.add(chamfer_input)

    return f"Added {distance}mm chamfer to {edges_to_chamfer.count} edges."

# --- Boolean / Combine Functions ---
def combine_selection(operation: str, new_body_name: str=None, **kwargs):
    op_enum = validate_boolean_operation(operation)
    selections = _ui.activeSelections
    if selections.count < 2: return "Select at least 2 bodies to combine."
    bodies = [sel.entity for sel in selections if sel.entity and sel.entity.objectType == adsk.fusion.BRepBody.classType()]
    if len(bodies) < 2: return "Less than 2 bodies found in selection."
    target_body = bodies[0]
    tool_bodies = adsk.core.ObjectCollection.createWithArray(bodies[1:])
    root = _app.activeProduct.rootComponent
    combine_features = root.features.combineFeatures
    combine_input = combine_features.createInput(target_body, tool_bodies)
    combine_input.operation = op_enum
    result_feature = combine_features.add(combine_input)
    if new_body_name and result_feature.bodies.count > 0:
        result_feature.bodies.item(0).name = get_unique_body_name(root, new_body_name)
        return result_feature.bodies.item(0).name
    return f"Combined selected bodies with '{operation}' operation."

def combine_selection_all(operation: str='join', new_body_name: str=None, **kwargs):
    return combine_selection(operation, new_body_name, **kwargs)

def combine_by_name(target_body: str, tool_body: str, operation: str, new_body_name: str=None, **kwargs):
    op_enum = validate_boolean_operation(operation)
    target = find_entity_by_name(target_body)
    tool = find_entity_by_name(tool_body)
    if not target or not tool: raise ValueError(f"Body '{target_body}' or '{tool_body}' not found.")
    root = _app.activeProduct.rootComponent
    combine_features = root.features.combineFeatures
    combine_input = combine_features.createInput(target, adsk.core.ObjectCollection.createWithArray([tool]))
    combine_input.operation = op_enum
    result_feature = combine_features.add(combine_input)
    if new_body_name and result_feature.bodies.count > 0:
        result_feature.bodies.item(0).name = get_unique_body_name(root, new_body_name)
        return result_feature.bodies.item(0).name
    return f"Combined bodies with '{operation}' operation."

# --- Selection & Visibility Functions ---
def select_bodies(body_name1: str, body_name2: str, **kwargs):
    _ui.activeSelections.clear()
    body1 = find_entity_by_name(body_name1)
    if body1: _ui.activeSelections.add(body1)
    body2 = find_entity_by_name(body_name2)
    if body2: _ui.activeSelections.add(body2)
    return f"Selected bodies '{body_name1}' and '{body_name2}'."

def set_body_visibility(body_name: str, is_visible: bool):
    target_body = find_entity_by_name(body_name)
    if target_body:
        target_body.isLightBulbOn = is_visible
        return f"Body '{body_name}' visibility set to {'on' if is_visible else 'off'}."
    else:
        raise ValueError(f"Body '{body_name}' not found.")

def hide_body(body_name: str, **kwargs): return set_body_visibility(body_name, False)
def show_body(body_name: str, **kwargs): return set_body_visibility(body_name, True)

def move_by_name(body_name: str, x_dist: float=0, y_dist: float=0, z_dist: float=0, **kwargs):
    target_entity = find_entity_by_name(body_name)
    if not target_entity: raise ValueError(f"Entity '{body_name}' not found.")
    scale = get_fusion_unit_scale()
    vector = adsk.core.Vector3D.create(x_dist * scale, y_dist * scale, z_dist * scale)
    transform = adsk.core.Matrix3D.create()
    transform.translation = vector
    root = _app.activeProduct.rootComponent
    move_features = root.features.moveFeatures
    move_input = move_features.createInput(adsk.core.ObjectCollection.createWithArray([target_entity]), transform)
    move_features.add(move_input)
    return f"Moved '{body_name}'."

def rotate_by_name(body_name: str, axis: str='z', angle: float=90.0, cx: float=0, cy: float=0, cz: float=0, **kwargs):
    target_entity = find_entity_by_name(body_name)
    if not target_entity: raise ValueError(f"Entity '{body_name}' not found.")
    scale = get_fusion_unit_scale()
    axis_map = {'x': adsk.core.Vector3D.create(1, 0, 0), 'y': adsk.core.Vector3D.create(0, 1, 0), 'z': adsk.core.Vector3D.create(0, 0, 1)}
    axis_vector = axis_map.get(axis.lower())
    center_point = adsk.core.Point3D.create(cx * scale, cy * scale, cz * scale)
    transform = adsk.core.Matrix3D.create()
    transform.setToRotation(math.radians(angle), axis_vector, center_point)
    root = _app.activeProduct.rootComponent
    move_features = root.features.moveFeatures
    move_input = move_features.createInput(adsk.core.ObjectCollection.createWithArray([target_entity]), transform)
    move_features.add(move_input)
    return f"Rotated '{body_name}'."

def select_body(body_name: str, **kwargs):
    target_body = find_entity_by_name(body_name)
    if target_body:
        _ui.activeSelections.clear()
        _ui.activeSelections.add(target_body)
        return f"Selected body '{body_name}'."
    else:
        raise ValueError(f"Body '{body_name}' not found.")

def select_all_bodies(**kwargs):
    root = _app.activeProduct.rootComponent
    if root.bRepBodies.count > 0:
        _ui.activeSelections.clear()
        for body in root.bRepBodies: _ui.activeSelections.add(body)
        return f"Selected all {root.bRepBodies.count} bodies."
    return "No bodies to select."

def delete_all_features(**kwargs):
    """Delete all features from the timeline."""
    try:
        timeline = _app.activeProduct.timeline
        initial_count = timeline.count

        if initial_count == 0:
            return "No features to delete."

        _ui.activeSelections.clear()
        valid_entities = []

        for item in timeline:
            if item.entity and item.entity.isValid:
                _ui.activeSelections.add(item.entity)
                valid_entities.append(item.entity)

        if _ui.activeSelections.count == 0:
            return "No deletable features found."

        _ui.activeSelections.clear()

        deleted_count = 0
        failed_count = 0

        for entity in reversed(valid_entities):
            try:
                if hasattr(entity, 'deleteMe') and entity.isValid:
                    entity.deleteMe()
                    deleted_count += 1
                else:
                    failed_count += 1
            except Exception:
                failed_count += 1
                continue

        if failed_count > 0:
            return f"Deleted {deleted_count} features. ({failed_count} could not be deleted)"
        else:
            return f"Deleted {deleted_count} features."

    except Exception as e:
        return f"Error during deletion: {str(e)}"

def debug_coordinate_info(show_details: bool = True, **kwargs):
    info_text = ""
    info_text += f"Fusion 360 MCP Add-in\n"
    info_text += f"Status: OK\nTimestamp: {time.ctime()}\n\n"
    prefs = _app.preferences.generalPreferences
    orientation_enum = prefs.defaultModelingOrientation
    if orientation_enum == adsk.core.DefaultModelingOrientations.YUpModelingOrientation:
        info_text += "  Setting: [WARNING] Y-axis is Up (Y-up).\n"
        info_text += "  - Top      : +Y direction (XZ Plane)\n"
        info_text += "  - Bottom   : -Y direction (XZ Plane)\n"
        info_text += "  - Front    : +Z direction (XY Plane)\n"
        info_text += "  - Back     : -Z direction (XY Plane)\n"
        info_text += "  - Right    : +X direction (YZ Plane)\n"
        info_text += "  - Left     : -X direction (YZ Plane)\n\n"
        info_text += "  RECOMMENDATION: This tool is optimized for a Z-up orientation.\n"
        info_text += "  For best results, please switch to 'Z-up' in Fusion 360's preferences.\n"
    else:
        info_text += "  Setting: Z-axis is Up (Z-up)\n"
        info_text += "  - Top      : +Z direction (XY Plane)\n"
        info_text += "  - Bottom   : -Z direction (XY Plane)\n"
        info_text += "  - Front    : -Y direction (XZ Plane)\n"
        info_text += "  - Back     : +Y direction (XZ Plane)\n"
        info_text += "  - Right    : +X direction (YZ Plane)\n"
        info_text += "  - Left     : -X direction (YZ Plane)\n\n"
        info_text += "  Please use this coordinate system for accurate positioning.\n"
    info_text += "  Max taper angle = arctan((base width - top width) / (2 x height))\n"
    info_text += "  Max fillet size = wall thickness / 2.\n"
    camera = _app.activeViewport.camera
    up_vector = camera.upVector
    info_text += f"\nViewport up vector: ({up_vector.x:.2f}, {up_vector.y:.2f}, {up_vector.z:.2f})\n"
    if show_details:
        info_text += "\n--- Details ---\nInput Unit: mm\nInternal Unit: cm\n"
    log_debug("Debug info generated.")
    return info_text

# --- Query Functions ---
def get_bounding_box(body_name: str, **kwargs):
    """Get bounding box info for a body."""
    body = find_entity_by_name(body_name)
    if not body:
        raise ValueError(f"Body '{body_name}' not found.")

    bbox = body.boundingBox
    scale = get_fusion_unit_scale()

    result = {
        "min": {
            "x": bbox.minPoint.x / scale,
            "y": bbox.minPoint.y / scale,
            "z": bbox.minPoint.z / scale
        },
        "max": {
            "x": bbox.maxPoint.x / scale,
            "y": bbox.maxPoint.y / scale,
            "z": bbox.maxPoint.z / scale
        },
        "size": {
            "width": (bbox.maxPoint.x - bbox.minPoint.x) / scale,
            "height": (bbox.maxPoint.y - bbox.minPoint.y) / scale,
            "depth": (bbox.maxPoint.z - bbox.minPoint.z) / scale
        },
        "center": {
            "x": (bbox.minPoint.x + bbox.maxPoint.x) / 2 / scale,
            "y": (bbox.minPoint.y + bbox.maxPoint.y) / 2 / scale,
            "z": (bbox.minPoint.z + bbox.maxPoint.z) / 2 / scale
        }
    }

    log_debug(f"Bounding box for '{body_name}': {result}")
    return result

def get_body_center(body_name: str, **kwargs):
    """Get center point info for a body."""
    body = find_entity_by_name(body_name)
    if not body:
        raise ValueError(f"Body '{body_name}' not found.")

    bbox = body.boundingBox
    mass_center = body.physicalProperties.centerOfMass
    scale = get_fusion_unit_scale()

    result = {
        "geometric_center": {
            "x": (bbox.minPoint.x + bbox.maxPoint.x) / 2 / scale,
            "y": (bbox.minPoint.y + bbox.maxPoint.y) / 2 / scale,
            "z": (bbox.minPoint.z + bbox.maxPoint.z) / 2 / scale
        },
        "center_of_mass": {
            "x": mass_center.x / scale,
            "y": mass_center.y / scale,
            "z": mass_center.z / scale
        }
    }

    log_debug(f"Centers for '{body_name}': {result}")
    return result

def get_body_dimensions(body_name: str, **kwargs):
    """Get detailed dimension info for a body."""
    body = find_entity_by_name(body_name)
    if not body:
        raise ValueError(f"Body '{body_name}' not found.")

    bbox = body.boundingBox
    scale = get_fusion_unit_scale()

    try:
        volume_cm3 = body.physicalProperties.volume
        area_cm2 = body.physicalProperties.area
        volume_mm3 = volume_cm3 * 1000
        area_mm2 = area_cm2 * 100
    except Exception:
        volume_mm3 = 0
        area_mm2 = 0

    result = {
        "length": (bbox.maxPoint.x - bbox.minPoint.x) / scale,
        "width": (bbox.maxPoint.y - bbox.minPoint.y) / scale,
        "height": (bbox.maxPoint.z - bbox.minPoint.z) / scale,
        "volume": volume_mm3,
        "surface_area": area_mm2
    }

    log_debug(f"Dimensions for '{body_name}': {result}")
    return result

def get_faces_info(body_name: str, **kwargs):
    """Get face info for a body. Face indices are 0-based (matching add_fillet/add_chamfer)."""
    body = find_entity_by_name(body_name)
    if not body:
        raise ValueError(f"Body '{body_name}' not found.")

    scale = get_fusion_unit_scale()
    faces_info = []

    for i, face in enumerate(body.faces):
        try:
            face_data = {
                "index": i,
                "area": face.area * 100,  # cm² to mm²
            }

            geom = face.geometry
            if geom.objectType == adsk.core.Plane.classType():
                face_data["type"] = "planar"
                face_data["normal"] = {
                    "x": geom.normal.x,
                    "y": geom.normal.y,
                    "z": geom.normal.z
                }
                face_data["center"] = {
                    "x": geom.origin.x / scale,
                    "y": geom.origin.y / scale,
                    "z": geom.origin.z / scale
                }
            elif geom.objectType == adsk.core.Cylinder.classType():
                face_data["type"] = "cylindrical"
                face_data["radius"] = geom.radius / scale
                face_data["axis"] = {
                    "x": geom.axis.x,
                    "y": geom.axis.y,
                    "z": geom.axis.z
                }
            elif geom.objectType == adsk.core.Sphere.classType():
                face_data["type"] = "spherical"
                face_data["radius"] = geom.radius / scale
                face_data["center"] = {
                    "x": geom.origin.x / scale,
                    "y": geom.origin.y / scale,
                    "z": geom.origin.z / scale
                }
            elif geom.objectType == adsk.core.Cone.classType():
                face_data["type"] = "conical"
                face_data["radius"] = geom.radius / scale
                face_data["half_angle"] = math.degrees(geom.halfAngle)
            else:
                face_data["type"] = "other"

            faces_info.append(face_data)

        except Exception as e:
            log_debug(f"Error processing face {i}: {e}")
            faces_info.append({
                "index": i,
                "type": "error",
                "error": str(e)
            })

    log_debug(f"Found {len(faces_info)} faces for '{body_name}'")
    return faces_info

def get_edges_info(body_name: str, **kwargs):
    """Get edge info for a body. Edge indices are 0-based (use these with add_fillet/add_chamfer)."""
    body = find_entity_by_name(body_name)
    if not body:
        raise ValueError(f"Body '{body_name}' not found.")

    scale = get_fusion_unit_scale()
    edges_info = []

    for i, edge in enumerate(body.edges):
        try:
            edge_data = {
                "index": i,
                "length": edge.length / scale
            }

            geom = edge.geometry

            if not geom:
                edge_data["type"] = "unknown_geometry"
                edges_info.append(edge_data)
                continue

            if geom.curveType == adsk.core.Curve3DTypes.Line3DCurveType:
                edge_data["type"] = "line"
                edge_data["start_point"] = {
                    "x": geom.startPoint.x / scale,
                    "y": geom.startPoint.y / scale,
                    "z": geom.startPoint.z / scale
                }
                edge_data["end_point"] = {
                    "x": geom.endPoint.x / scale,
                    "y": geom.endPoint.y / scale,
                    "z": geom.endPoint.z / scale
                }
                direction = geom.startPoint.vectorTo(geom.endPoint)
                direction.normalize()
                edge_data["direction"] = {
                    "x": direction.x,
                    "y": direction.y,
                    "z": direction.z
                }
            elif geom.curveType == adsk.core.Curve3DTypes.Circle3DCurveType:
                edge_data["type"] = "circle"
                edge_data["radius"] = geom.radius / scale
                edge_data["center"] = {
                    "x": geom.center.x / scale,
                    "y": geom.center.y / scale,
                    "z": geom.center.z / scale
                }
                edge_data["normal"] = {
                    "x": geom.normal.x,
                    "y": geom.normal.y,
                    "z": geom.normal.z
                }
            elif geom.curveType == adsk.core.Curve3DTypes.Arc3DCurveType:
                edge_data["type"] = "arc"
                edge_data["radius"] = geom.radius / scale
                edge_data["center"] = {
                    "x": geom.center.x / scale,
                    "y": geom.center.y / scale,
                    "z": geom.center.z / scale
                }
                edge_data["start_angle"] = math.degrees(geom.startAngle)
                edge_data["end_angle"] = math.degrees(geom.endAngle)
            else:
                edge_data["type"] = "spline"

            edges_info.append(edge_data)

        except Exception as e:
            log_debug(f"Error processing edge {i}: {e}")
            edges_info.append({
                "index": i,
                "type": "error",
                "error": str(e)
            })

    log_debug(f"Found {len(edges_info)} edges for '{body_name}'")
    return edges_info

def get_mass_properties(body_name: str, material_density: float = 1.0, **kwargs):
    """Get mass properties for a body. material_density in g/cm³."""
    body = find_entity_by_name(body_name)
    if not body:
        raise ValueError(f"Body '{body_name}' not found.")

    scale = get_fusion_unit_scale()
    props = body.physicalProperties

    volume_mm3 = props.volume * 1000
    mass_g = material_density * props.volume

    result = {
        "volume": volume_mm3,
        "mass": mass_g,
        "center_of_mass": {
            "x": props.centerOfMass.x / scale,
            "y": props.centerOfMass.y / scale,
            "z": props.centerOfMass.z / scale
        },
        "moments_of_inertia": {
            "Ixx": props.principalMomentsOfInertia.x,
            "Iyy": props.principalMomentsOfInertia.y,
            "Izz": props.principalMomentsOfInertia.z
        },
        "material_density": material_density
    }

    log_debug(f"Mass properties for '{body_name}': volume={volume_mm3:.2f}mm³, mass={mass_g:.2f}g")
    return result

def get_body_relationships(body_name: str, other_body_name: str, **kwargs):
    """Get spatial relationship between two bodies."""
    body1 = find_entity_by_name(body_name)
    body2 = find_entity_by_name(other_body_name)

    if not body1:
        raise ValueError(f"Body '{body_name}' not found.")
    if not body2:
        raise ValueError(f"Body '{other_body_name}' not found.")

    scale = get_fusion_unit_scale()

    center1 = body1.physicalProperties.centerOfMass
    center2 = body2.physicalProperties.centerOfMass
    distance = center1.distanceTo(center2) / scale

    bbox1 = body1.boundingBox
    bbox2 = body2.boundingBox

    interference = (
        bbox1.minPoint.x <= bbox2.maxPoint.x and bbox1.maxPoint.x >= bbox2.minPoint.x and
        bbox1.minPoint.y <= bbox2.maxPoint.y and bbox1.maxPoint.y >= bbox2.minPoint.y and
        bbox1.minPoint.z <= bbox2.maxPoint.z and bbox1.maxPoint.z >= bbox2.minPoint.z
    )

    if center1.z > bbox2.maxPoint.z:
        relative_position = "above"
    elif center1.z < bbox2.minPoint.z:
        relative_position = "below"
    elif center1.x > bbox2.maxPoint.x:
        relative_position = "right"
    elif center1.x < bbox2.minPoint.x:
        relative_position = "left"
    elif center1.y > bbox2.maxPoint.y:
        relative_position = "back"
    elif center1.y < bbox2.minPoint.y:
        relative_position = "front"
    else:
        relative_position = "overlapping"

    result = {
        "distance": distance,
        "interference": interference,
        "relative_position": relative_position,
        "clearance": distance if not interference else 0
    }

    log_debug(f"Relationship between '{body_name}' and '{other_body_name}': {result}")
    return result

def measure_distance(body_name1: str, body_name2: str, **kwargs):
    """Measure distance between two bodies."""
    body1 = find_entity_by_name(body_name1)
    body2 = find_entity_by_name(body_name2)

    if not body1:
        raise ValueError(f"Body '{body_name1}' not found.")
    if not body2:
        raise ValueError(f"Body '{body_name2}' not found.")

    scale = get_fusion_unit_scale()

    center1 = body1.physicalProperties.centerOfMass
    center2 = body2.physicalProperties.centerOfMass
    center_distance = center1.distanceTo(center2) / scale

    bbox1 = body1.boundingBox
    bbox2 = body2.boundingBox

    dx = max(0, max(bbox1.minPoint.x - bbox2.maxPoint.x, bbox2.minPoint.x - bbox1.maxPoint.x))
    dy = max(0, max(bbox1.minPoint.y - bbox2.maxPoint.y, bbox2.minPoint.y - bbox1.maxPoint.y))
    dz = max(0, max(bbox1.minPoint.z - bbox2.maxPoint.z, bbox2.minPoint.z - bbox1.maxPoint.z))

    bbox_distance = math.sqrt(dx*dx + dy*dy + dz*dz) / scale

    result = {
        "center_to_center": center_distance,
        "bounding_box_clearance": bbox_distance,
        "is_overlapping": bbox_distance == 0
    }

    log_debug(f"Distance between '{body_name1}' and '{body_name2}': {result}")
    return result

# =============================================
# LOT 1 — Core Geometry Operations
# =============================================

def shell_body(body_name: str, thickness: float = 2.0, face_indices: list = None, **kwargs):
    """Hollow out a body, leaving walls of specified thickness. Optionally remove specific faces."""
    body = find_entity_by_name(body_name)
    if not body:
        raise ValueError(f"Body '{body_name}' not found.")
    root = _app.activeProduct.rootComponent
    scale = get_fusion_unit_scale()
    shell_features = root.features.shellFeatures
    faces_to_remove = adsk.core.ObjectCollection.create()
    if face_indices and isinstance(face_indices, list):
        for idx in face_indices:
            idx = int(idx)
            if 0 <= idx < body.faces.count:
                faces_to_remove.add(body.faces.item(idx))
    shell_input = shell_features.createInput(faces_to_remove, False)
    shell_input.insideThickness = adsk.core.ValueInput.createByReal(thickness * scale)
    shell_features.add(shell_input)
    return f"Applied {thickness}mm shell to '{body_name}' (removed {faces_to_remove.count} faces)."

def create_hole(body_name: str, face_index: int = 0, x: float = 0, y: float = 0,
                diameter: float = 10, depth: float = 0, hole_type: str = 'simple', **kwargs):
    """Create a hole on a face using sketch circle + cut extrude. hole_type: simple, through_all."""
    body = find_entity_by_name(body_name)
    if not body:
        raise ValueError(f"Body '{body_name}' not found.")
    if face_index < 0 or face_index >= body.faces.count:
        raise ValueError(f"Face index {face_index} out of range (0-{body.faces.count - 1}).")
    root = _app.activeProduct.rootComponent
    scale = get_fusion_unit_scale()
    face = body.faces.item(face_index)
    # Create a sketch on the target face and draw a circle for the hole
    sketch = root.sketches.add(face)
    sketch.sketchCurves.sketchCircles.addByCenterRadius(
        adsk.core.Point3D.create(x * scale, y * scale, 0), (diameter / 2) * scale)
    prof = sketch.profiles.item(0)
    extrudes = root.features.extrudeFeatures
    ext_input = extrudes.createInput(prof, adsk.fusion.FeatureOperations.CutFeatureOperation)
    if hole_type == 'through_all' or depth == 0:
        ext_input.setAllExtent(adsk.fusion.ExtentDirections.NegativeExtentDirection)
    else:
        distance = adsk.core.ValueInput.createByReal(depth * scale)
        extent_def = adsk.fusion.DistanceExtentDefinition.create(distance)
        ext_input.setOneSideExtent(extent_def, adsk.fusion.ExtentDirections.NegativeExtentDirection)
    extrudes.add(ext_input)
    sketch.isVisible = False
    return f"Created {hole_type} hole (d={diameter}mm) on '{body_name}'."

def create_thread(body_name: str, face_index: int = 0, thread_type: str = 'ISO Metric profile',
                  size: str = 'M10', designation: str = 'M10x1.5', is_internal: bool = True,
                  full_length: bool = True, length: float = 0, **kwargs):
    """Add thread to a cylindrical face."""
    body = find_entity_by_name(body_name)
    if not body:
        raise ValueError(f"Body '{body_name}' not found.")
    root = _app.activeProduct.rootComponent
    scale = get_fusion_unit_scale()
    face = body.faces.item(int(face_index))
    thread_features = root.features.threadFeatures
    thread_data_query = thread_features.threadDataQuery
    thread_types = thread_data_query.allThreadTypes
    found_type = None
    for t in thread_types:
        if thread_type.lower() in t.lower():
            found_type = t
            break
    if not found_type:
        found_type = thread_types[0]
    all_sizes = thread_data_query.allSizes(found_type)
    found_size = size if size in all_sizes else (all_sizes[0] if all_sizes else size)
    all_designations = thread_data_query.allDesignations(found_type, found_size)
    found_designation = designation if designation in all_designations else (all_designations[0] if all_designations else designation)
    thread_info = thread_data_query.findThread(found_type, found_size, found_designation, is_internal)
    thread_input = thread_features.createInput(face, thread_info)
    thread_input.isFullLength = full_length
    if not full_length and length > 0:
        thread_input.threadLength = adsk.core.ValueInput.createByReal(length * scale)
    thread_features.add(thread_input)
    return f"Added {found_designation} thread to '{body_name}' face {face_index}."

def offset_face(body_name: str, face_indices: list, distance: float = 1.0, **kwargs):
    """Move faces inward/outward by a distance."""
    body = find_entity_by_name(body_name)
    if not body:
        raise ValueError(f"Body '{body_name}' not found.")
    root = _app.activeProduct.rootComponent
    scale = get_fusion_unit_scale()
    faces = adsk.core.ObjectCollection.create()
    for idx in face_indices:
        idx = int(idx)
        if 0 <= idx < body.faces.count:
            faces.add(body.faces.item(idx))
    if faces.count == 0:
        raise ValueError("No valid face indices provided.")
    offset_features = root.features.offsetFacesFeatures
    offset_input = offset_features.createInput(faces, adsk.core.ValueInput.createByReal(distance * scale), False)
    offset_features.add(offset_input)
    return f"Offset {faces.count} faces by {distance}mm on '{body_name}'."

def split_body(body_name: str, plane: str = 'xy', offset: float = 0, **kwargs):
    """Split a body with a construction plane."""
    body = find_entity_by_name(body_name)
    if not body:
        raise ValueError(f"Body '{body_name}' not found.")
    root = _app.activeProduct.rootComponent
    scale = get_fusion_unit_scale()
    split_plane = get_construction_plane(root, plane)
    if offset != 0:
        planes = root.constructionPlanes
        plane_input = planes.createInput()
        plane_input.setByOffset(split_plane, adsk.core.ValueInput.createByReal(offset * scale))
        split_plane = planes.add(plane_input)
    split_features = root.features.splitBodyFeatures
    split_input = split_features.createInput(body, split_plane, True)
    split_features.add(split_input)
    result_bodies = [b.name for b in root.bRepBodies]
    return f"Split '{body_name}'. Bodies: {result_bodies}"

def scale_body(body_name: str, scale_x: float = 1.0, scale_y: float = 1.0, scale_z: float = 1.0,
               cx: float = 0, cy: float = 0, cz: float = 0, **kwargs):
    """Scale a body uniformly or non-uniformly."""
    body = find_entity_by_name(body_name)
    if not body:
        raise ValueError(f"Body '{body_name}' not found.")
    root = _app.activeProduct.rootComponent
    s = get_fusion_unit_scale()
    scale_features = root.features.scaleFeatures
    bodies = adsk.core.ObjectCollection.create()
    bodies.add(body)
    point = adsk.core.Point3D.create(cx * s, cy * s, cz * s)
    scale_input = scale_features.createInput(bodies, point, adsk.core.ValueInput.createByReal(scale_x))
    if scale_x != scale_y or scale_y != scale_z:
        scale_input.scaleType = adsk.fusion.ScaleTypes.NonUniformScaleType
        scale_input.xScale = adsk.core.ValueInput.createByReal(scale_x)
        scale_input.yScale = adsk.core.ValueInput.createByReal(scale_y)
        scale_input.zScale = adsk.core.ValueInput.createByReal(scale_z)
    scale_features.add(scale_input)
    return f"Scaled '{body_name}' by ({scale_x}, {scale_y}, {scale_z})."

def copy_body(body_name: str, new_body_name: str = None, x_offset: float = 0, y_offset: float = 0, z_offset: float = 0, **kwargs):
    """Duplicate a body with optional offset."""
    body = find_entity_by_name(body_name)
    if not body:
        raise ValueError(f"Body '{body_name}' not found.")
    root = _app.activeProduct.rootComponent
    scale = get_fusion_unit_scale()
    # Copy body using move feature with copy option
    move_features = root.features.moveFeatures
    bodies = adsk.core.ObjectCollection.create()
    bodies.add(body)
    transform = adsk.core.Matrix3D.create()
    transform.translation = adsk.core.Vector3D.create(x_offset * scale, y_offset * scale, z_offset * scale)
    move_input = move_features.createInput(bodies, transform)
    move_input.isCopy = True
    result = move_features.add(move_input)
    new_body = result.bodies.item(0)
    if new_body_name:
        new_body.name = get_unique_body_name(root, new_body_name)
    return f"Copied '{body_name}' as '{new_body.name}'."

def draft_face(body_name: str, face_indices: list, draft_angle: float = 3.0, pull_direction_axis: str = 'z', **kwargs):
    """Add draft angle to faces for mold release."""
    body = find_entity_by_name(body_name)
    if not body:
        raise ValueError(f"Body '{body_name}' not found.")
    root = _app.activeProduct.rootComponent
    faces = adsk.core.ObjectCollection.create()
    for idx in face_indices:
        idx = int(idx)
        if 0 <= idx < body.faces.count:
            faces.add(body.faces.item(idx))
    if faces.count == 0:
        raise ValueError("No valid face indices provided.")
    # DraftFeatures.createInput requires a plane (not an axis) as pull direction
    plane_map = {'z': root.xYConstructionPlane, 'y': root.xZConstructionPlane, 'x': root.yZConstructionPlane}
    pull_plane = plane_map.get(pull_direction_axis.lower(), root.xYConstructionPlane)
    draft_features = root.features.draftFeatures
    draft_input = draft_features.createInput(faces, pull_plane,
        adsk.core.ValueInput.createByString(f"{draft_angle} deg"), False)
    draft_features.add(draft_input)
    return f"Added {draft_angle}° draft to {faces.count} faces on '{body_name}'."

# =============================================
# LOT 2 — Sketch System + Advanced Modeling
# =============================================

# Global sketch registry to find sketches by name
_sketch_registry = {}

def sketch_create(plane: str = 'xy', name: str = None, offset: float = 0, face_body_name: str = None, face_index: int = -1, **kwargs):
    """Create a new sketch on a plane or face. Returns the sketch name."""
    root = _app.activeProduct.rootComponent
    scale = get_fusion_unit_scale()
    if face_body_name and face_index >= 0:
        body = find_entity_by_name(face_body_name)
        if not body:
            raise ValueError(f"Body '{face_body_name}' not found.")
        if face_index >= body.faces.count:
            raise ValueError(f"Face index {face_index} out of range.")
        sketch_plane = body.faces.item(face_index)
    elif offset != 0:
        base_plane = get_construction_plane(root, plane)
        planes = root.constructionPlanes
        plane_input = planes.createInput()
        plane_input.setByOffset(base_plane, adsk.core.ValueInput.createByReal(offset * scale))
        sketch_plane = planes.add(plane_input)
    else:
        sketch_plane = get_construction_plane(root, plane)
    sketch = root.sketches.add(sketch_plane)
    if name:
        sketch.name = name
    _sketch_registry[sketch.name] = sketch
    return sketch.name

def _get_sketch(sketch_name: str):
    """Find a sketch by name."""
    if sketch_name in _sketch_registry:
        s = _sketch_registry[sketch_name]
        if s.isValid:
            return s
    root = _app.activeProduct.rootComponent
    for sketch in root.sketches:
        if sketch.name == sketch_name:
            _sketch_registry[sketch_name] = sketch
            return sketch
    raise ValueError(f"Sketch '{sketch_name}' not found.")

def sketch_add_line(sketch_name: str, x1: float = 0, y1: float = 0, x2: float = 50, y2: float = 0, **kwargs):
    """Add a line to a sketch."""
    sketch = _get_sketch(sketch_name)
    scale = get_fusion_unit_scale()
    sketch.sketchCurves.sketchLines.addByTwoPoints(
        adsk.core.Point3D.create(x1 * scale, y1 * scale, 0),
        adsk.core.Point3D.create(x2 * scale, y2 * scale, 0))
    return f"Added line ({x1},{y1})->({x2},{y2}) to '{sketch_name}'."

def sketch_add_circle(sketch_name: str, cx: float = 0, cy: float = 0, radius: float = 25, **kwargs):
    """Add a circle to a sketch."""
    sketch = _get_sketch(sketch_name)
    scale = get_fusion_unit_scale()
    sketch.sketchCurves.sketchCircles.addByCenterRadius(
        adsk.core.Point3D.create(cx * scale, cy * scale, 0), radius * scale)
    return f"Added circle (r={radius}mm) at ({cx},{cy}) to '{sketch_name}'."

def sketch_add_arc(sketch_name: str, x1: float = 0, y1: float = 0, x2: float = 25, y2: float = 25, x3: float = 50, y3: float = 0, **kwargs):
    """Add an arc through 3 points to a sketch."""
    sketch = _get_sketch(sketch_name)
    scale = get_fusion_unit_scale()
    sketch.sketchCurves.sketchArcs.addByThreePoints(
        adsk.core.Point3D.create(x1 * scale, y1 * scale, 0),
        adsk.core.Point3D.create(x2 * scale, y2 * scale, 0),
        adsk.core.Point3D.create(x3 * scale, y3 * scale, 0))
    return f"Added arc through 3 points to '{sketch_name}'."

def sketch_add_rectangle(sketch_name: str, x1: float = -25, y1: float = -15, x2: float = 25, y2: float = 15, **kwargs):
    """Add a rectangle to a sketch."""
    sketch = _get_sketch(sketch_name)
    scale = get_fusion_unit_scale()
    sketch.sketchCurves.sketchLines.addTwoPointRectangle(
        adsk.core.Point3D.create(x1 * scale, y1 * scale, 0),
        adsk.core.Point3D.create(x2 * scale, y2 * scale, 0))
    return f"Added rectangle to '{sketch_name}'."

def sketch_add_polygon(sketch_name: str, cx: float = 0, cy: float = 0, radius: float = 25, num_sides: int = 6, **kwargs):
    """Add a regular polygon to a sketch."""
    if num_sides < 3:
        raise ValueError("Polygon must have at least 3 sides.")
    sketch = _get_sketch(sketch_name)
    scale = get_fusion_unit_scale()
    r = radius * scale
    points = [adsk.core.Point3D.create(
        cx * scale + r * math.cos(i * 2 * math.pi / num_sides),
        cy * scale + r * math.sin(i * 2 * math.pi / num_sides), 0) for i in range(num_sides)]
    lines = sketch.sketchCurves.sketchLines
    for i in range(num_sides):
        lines.addByTwoPoints(points[i], points[(i + 1) % num_sides])
    return f"Added {num_sides}-sided polygon to '{sketch_name}'."

def sketch_add_spline(sketch_name: str, points: list = None, **kwargs):
    """Add a fitted spline through points. points: [[x1,y1],[x2,y2],...]"""
    if not points or len(points) < 2:
        raise ValueError("At least 2 points required for a spline.")
    sketch = _get_sketch(sketch_name)
    scale = get_fusion_unit_scale()
    point_collection = adsk.core.ObjectCollection.create()
    for pt in points:
        point_collection.add(adsk.core.Point3D.create(pt[0] * scale, pt[1] * scale, 0))
    sketch.sketchCurves.sketchFittedSplines.add(point_collection)
    return f"Added spline with {len(points)} points to '{sketch_name}'."

def sketch_add_text(sketch_name: str, text: str = "Hello", x: float = 0, y: float = 0,
                    height: float = 10, font_name: str = "Arial", **kwargs):
    """Add text to a sketch for embossing/debossing."""
    sketch = _get_sketch(sketch_name)
    scale = get_fusion_unit_scale()
    texts = sketch.sketchTexts
    text_input = texts.createInput2(text, height * scale)
    text_input.setAsMultiLine(
        adsk.core.Point3D.create(x * scale, y * scale, 0),
        adsk.core.Point3D.create((x + height * len(text) * 0.6) * scale, y * scale, 0),
        adsk.core.Point3D.create(x * scale, (y + height) * scale, 0),
        adsk.core.Point3D.create((x + height * len(text) * 0.6) * scale, (y + height) * scale, 0))
    text_input.fontName = font_name
    texts.add(text_input)
    return f"Added text '{text}' to '{sketch_name}'."

def sketch_extrude(sketch_name: str, profile_index: int = 0, height: float = 10,
                   direction: str = 'positive', operation: str = 'new', body_name: str = None,
                   symmetric: bool = False, **kwargs):
    """Extrude a profile from a named sketch. operation: new, join, cut, intersect. Use symmetric=true for equal extrusion on both sides."""
    sketch = _get_sketch(sketch_name)
    scale = get_fusion_unit_scale()
    if profile_index >= sketch.profiles.count:
        raise ValueError(f"Profile index {profile_index} out of range (0-{sketch.profiles.count - 1}).")
    profile = sketch.profiles.item(profile_index)
    root = _app.activeProduct.rootComponent
    op_map = {
        'new': adsk.fusion.FeatureOperations.NewBodyFeatureOperation,
        'join': adsk.fusion.FeatureOperations.JoinFeatureOperation,
        'cut': adsk.fusion.FeatureOperations.CutFeatureOperation,
        'intersect': adsk.fusion.FeatureOperations.IntersectFeatureOperation,
    }
    operation_enum = op_map.get(operation.lower(), adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
    extrudes = root.features.extrudeFeatures
    ext_input = extrudes.createInput(profile, operation_enum)
    distance = adsk.core.ValueInput.createByReal(height * scale)
    if symmetric:
        ext_input.setSymmetricExtent(distance, True)
    elif direction.lower() == 'positive':
        ext_input.setDistanceExtent(False, distance)
    else:
        extent_def = adsk.fusion.DistanceExtentDefinition.create(distance)
        ext_input.setOneSideExtent(extent_def, adsk.fusion.ExtentDirections.NegativeExtentDirection)
    new_body = extrudes.add(ext_input).bodies.item(0)
    sketch.isVisible = False
    if body_name and new_body:
        new_body.name = get_unique_body_name(root, body_name)
    return new_body.name if new_body else "Extrusion completed."

def create_revolve(sketch_name: str, profile_index: int = 0, axis: str = 'x',
                   angle: float = 360, body_name: str = None, **kwargs):
    """Revolve a sketch profile around an axis."""
    sketch = _get_sketch(sketch_name)
    if profile_index >= sketch.profiles.count:
        raise ValueError(f"Profile index {profile_index} out of range.")
    profile = sketch.profiles.item(profile_index)
    root = _app.activeProduct.rootComponent
    axis_map = {'x': root.xConstructionAxis, 'y': root.yConstructionAxis, 'z': root.zConstructionAxis}
    revolve_axis = axis_map.get(axis.lower(), root.xConstructionAxis)
    revolves = root.features.revolveFeatures
    revolve_input = revolves.createInput(profile, revolve_axis, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
    revolve_input.setAngleExtent(False, adsk.core.ValueInput.createByReal(math.radians(angle)))
    new_body = revolves.add(revolve_input).bodies.item(0)
    sketch.isVisible = False
    if body_name:
        new_body.name = get_unique_body_name(root, body_name)
    return new_body.name

def create_loft(sketch_names: list, body_name: str = None, is_closed: bool = False, **kwargs):
    """Create a loft between profiles from multiple sketches."""
    if not sketch_names or len(sketch_names) < 2:
        raise ValueError("At least 2 sketch names required for a loft.")
    root = _app.activeProduct.rootComponent
    loft_features = root.features.loftFeatures
    loft_input = loft_features.createInput(adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
    for sname in sketch_names:
        sketch = _get_sketch(sname)
        if sketch.profiles.count == 0:
            raise ValueError(f"Sketch '{sname}' has no profiles.")
        loft_input.loftSections.add(sketch.profiles.item(0))
    loft_input.isClosed = is_closed
    new_body = loft_features.add(loft_input).bodies.item(0)
    for sname in sketch_names:
        _get_sketch(sname).isVisible = False
    if body_name:
        new_body.name = get_unique_body_name(root, body_name)
    return new_body.name

def create_sweep(profile_sketch_name: str, path_sketch_name: str, profile_index: int = 0,
                 body_name: str = None, **kwargs):
    """Sweep a profile along a path defined in another sketch."""
    profile_sketch = _get_sketch(profile_sketch_name)
    path_sketch = _get_sketch(path_sketch_name)
    if profile_index >= profile_sketch.profiles.count:
        raise ValueError(f"Profile index {profile_index} out of range.")
    profile = profile_sketch.profiles.item(profile_index)
    root = _app.activeProduct.rootComponent
    path_curve = path_sketch.sketchCurves.item(0)
    path = adsk.fusion.Path.create(path_curve, adsk.fusion.ChainedCurveOptions.connectedChainedCurves)
    sweeps = root.features.sweepFeatures
    sweep_input = sweeps.createInput(profile, path, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
    new_body = sweeps.add(sweep_input).bodies.item(0)
    profile_sketch.isVisible = False
    path_sketch.isVisible = False
    if body_name:
        new_body.name = get_unique_body_name(root, body_name)
    return new_body.name

def create_construction_plane(plane: str = 'xy', offset: float = 10, name: str = None, **kwargs):
    """Create a construction plane offset from a base plane."""
    root = _app.activeProduct.rootComponent
    scale = get_fusion_unit_scale()
    base_plane = get_construction_plane(root, plane)
    planes = root.constructionPlanes
    plane_input = planes.createInput()
    plane_input.setByOffset(base_plane, adsk.core.ValueInput.createByReal(offset * scale))
    new_plane = planes.add(plane_input)
    if name:
        new_plane.name = name
    return f"Created construction plane '{new_plane.name}' at offset {offset}mm from {plane}."

# =============================================
# LOT 3 — Export, Materials, Capture, Utility
# =============================================

def export_stl(file_path: str, body_name: str = None, refinement: str = 'medium', **kwargs):
    """Export body or design as STL. refinement: low, medium, high."""
    root = _app.activeProduct.rootComponent
    export_mgr = _app.activeProduct.exportManager
    refinement_map = {
        'low': adsk.fusion.MeshRefinementSettings.MeshRefinementLow,
        'medium': adsk.fusion.MeshRefinementSettings.MeshRefinementMedium,
        'high': adsk.fusion.MeshRefinementSettings.MeshRefinementHigh,
    }
    stl_options = export_mgr.createSTLExportOptions(root)
    if body_name:
        body = find_entity_by_name(body_name)
        if not body:
            raise ValueError(f"Body '{body_name}' not found.")
        stl_options = export_mgr.createSTLExportOptions(body)
    stl_options.meshRefinement = refinement_map.get(refinement.lower(), refinement_map['medium'])
    stl_options.filename = file_path
    export_mgr.execute(stl_options)
    return f"Exported STL to '{file_path}'."

def export_step(file_path: str, **kwargs):
    """Export design as STEP file."""
    root = _app.activeProduct.rootComponent
    export_mgr = _app.activeProduct.exportManager
    step_options = export_mgr.createSTEPExportOptions(file_path, root)
    export_mgr.execute(step_options)
    return f"Exported STEP to '{file_path}'."

def export_f3d(file_path: str, **kwargs):
    """Export design as Fusion 360 archive (.f3d)."""
    export_mgr = _app.activeProduct.exportManager
    f3d_options = export_mgr.createFusionArchiveExportOptions(file_path)
    export_mgr.execute(f3d_options)
    return f"Exported F3D to '{file_path}'."

def set_material(body_name: str, material_name: str = 'Steel', library_name: str = 'Fusion 360 Material Library', **kwargs):
    """Assign a physical material to a body."""
    body = find_entity_by_name(body_name)
    if not body:
        raise ValueError(f"Body '{body_name}' not found.")
    material_libs = _app.materialLibraries
    target_lib = None
    for lib in material_libs:
        if library_name.lower() in lib.name.lower():
            target_lib = lib
            break
    if not target_lib:
        target_lib = material_libs.item(0)
    material = None
    for mat in target_lib.materials:
        if material_name.lower() in mat.name.lower():
            material = mat
            break
    if not material:
        available = [m.name for m in target_lib.materials][:20]
        raise ValueError(f"Material '{material_name}' not found. Available (first 20): {available}")
    body.material = material
    return f"Set material '{material.name}' on '{body_name}'."

def set_appearance(body_name: str, appearance_name: str = 'Steel - Satin', library_name: str = 'Fusion 360 Appearance Library', **kwargs):
    """Assign a visual appearance to a body."""
    body = find_entity_by_name(body_name)
    if not body:
        raise ValueError(f"Body '{body_name}' not found.")
    app_libs = _app.materialLibraries
    target_lib = None
    for lib in app_libs:
        if library_name.lower() in lib.name.lower():
            target_lib = lib
            break
    if not target_lib:
        target_lib = app_libs.item(0)
    appearance = None
    for app in target_lib.appearances:
        if appearance_name.lower() in app.name.lower():
            appearance = app
            break
    if not appearance:
        available = [a.name for a in target_lib.appearances][:20]
        raise ValueError(f"Appearance '{appearance_name}' not found. Available (first 20): {available}")
    body.appearance = appearance
    return f"Set appearance '{appearance.name}' on '{body_name}'."

def set_user_parameter(name: str, value: float = 0, units: str = 'mm', expression: str = None, **kwargs):
    """Create or update a user parameter for parametric design."""
    design = adsk.fusion.Design.cast(_app.activeProduct)
    params = design.userParameters
    existing = params.itemByName(name)
    if existing:
        if expression:
            existing.expression = expression
        else:
            existing.expression = f"{value} {units}"
        return f"Updated parameter '{name}' = {existing.expression}."
    else:
        expr = expression if expression else f"{value} {units}"
        params.add(name, adsk.core.ValueInput.createByString(expr), units, '')
        return f"Created parameter '{name}' = {expr}."

def get_user_parameter(name: str = None, **kwargs):
    """Get user parameter(s). If name is None, returns all parameters."""
    design = adsk.fusion.Design.cast(_app.activeProduct)
    params = design.userParameters
    if name:
        param = params.itemByName(name)
        if not param:
            raise ValueError(f"Parameter '{name}' not found.")
        return {"name": param.name, "value": param.value, "expression": param.expression, "unit": param.unit}
    else:
        result = []
        for p in params:
            result.append({"name": p.name, "value": p.value, "expression": p.expression, "unit": p.unit})
        return result

def capture_viewport(file_path: str, width: int = 1920, height: int = 1080, **kwargs):
    """Capture the current viewport as an image."""
    viewport = _app.activeViewport
    viewport.saveAsImageFile(file_path, width, height)
    return f"Viewport captured to '{file_path}' ({width}x{height})."

def list_bodies(**kwargs):
    """List all bodies in the active document with their properties."""
    root = _app.activeProduct.rootComponent
    scale = get_fusion_unit_scale()
    bodies_info = []
    for body in root.bRepBodies:
        bbox = body.boundingBox
        center = body.physicalProperties.centerOfMass
        bodies_info.append({
            "name": body.name,
            "is_visible": body.isLightBulbOn,
            "volume_mm3": body.physicalProperties.volume * 1000,
            "center_of_mass": {"x": center.x / scale, "y": center.y / scale, "z": center.z / scale},
            "size": {
                "width": (bbox.maxPoint.x - bbox.minPoint.x) / scale,
                "depth": (bbox.maxPoint.y - bbox.minPoint.y) / scale,
                "height": (bbox.maxPoint.z - bbox.minPoint.z) / scale,
            }
        })
    return bodies_info

# =============================================
# Existing Design Interaction Tools
# =============================================

def rename_body(body_name: str, new_name: str, **kwargs):
    """Rename an existing body."""
    body = find_entity_by_name(body_name)
    if not body:
        raise ValueError(f"Body '{body_name}' not found.")
    root = _app.activeProduct.rootComponent
    body.name = get_unique_body_name(root, new_name)
    return f"Renamed '{body_name}' to '{body.name}'."

def list_features(**kwargs):
    """List all features in the timeline with their types and names."""
    timeline = _app.activeProduct.timeline
    features_info = []
    for i in range(timeline.count):
        item = timeline.item(i)
        try:
            entity = item.entity
            feature_data = {
                "index": i,
                "name": entity.name if entity and hasattr(entity, 'name') else f"Feature_{i}",
                "type": entity.objectType.split('::')[-1] if entity else "Unknown",
                "is_suppressed": item.isSuppressed,
                "is_valid": entity.isValid if entity else False
            }
            features_info.append(feature_data)
        except Exception:
            features_info.append({"index": i, "name": f"Feature_{i}", "type": "Unknown", "is_suppressed": False, "is_valid": False})
    return features_info

def list_sketches(**kwargs):
    """List all sketches in the active document."""
    root = _app.activeProduct.rootComponent
    sketches_info = []
    for sketch in root.sketches:
        sketches_info.append({
            "name": sketch.name,
            "is_visible": sketch.isVisible,
            "profile_count": sketch.profiles.count,
            "curve_count": sketch.sketchCurves.count,
            "is_fully_constrained": sketch.isFullyConstrained if hasattr(sketch, 'isFullyConstrained') else None
        })
    return sketches_info

def list_components(**kwargs):
    """List all components and occurrences in the design."""
    root = _app.activeProduct.rootComponent
    scale = get_fusion_unit_scale()
    components_info = []
    # Root component
    components_info.append({
        "name": root.name,
        "is_root": True,
        "bodies_count": root.bRepBodies.count,
        "bodies": [b.name for b in root.bRepBodies],
        "occurrences_count": root.occurrences.count
    })
    # Child occurrences
    for occ in root.allOccurrences:
        comp = occ.component
        components_info.append({
            "name": occ.name,
            "component": comp.name,
            "is_root": False,
            "bodies_count": comp.bRepBodies.count,
            "bodies": [b.name for b in comp.bRepBodies],
            "is_visible": occ.isLightBulbOn
        })
    return components_info

def get_design_info(**kwargs):
    """Get overall design information — document name, units, body count, component count."""
    design = adsk.fusion.Design.cast(_app.activeProduct)
    root = design.rootComponent
    doc = _app.activeDocument
    units_mgr = design.unitsManager
    all_bodies = root.bRepBodies
    result = {
        "document_name": doc.name if doc else "Untitled",
        "design_type": "ParametricDesign" if design.designType == adsk.fusion.DesignTypes.ParametricDesignType else "DirectDesign",
        "default_units": units_mgr.defaultLengthUnits,
        "body_count": all_bodies.count,
        "body_names": [b.name for b in all_bodies],
        "component_count": root.allOccurrences.count + 1,
        "sketch_count": root.sketches.count,
        "feature_count": _app.activeProduct.timeline.count,
        "has_unsaved_changes": doc.isModified if doc else False
    }
    return result

def suppress_feature(feature_index: int, **kwargs):
    """Suppress a feature in the timeline (non-destructive disable)."""
    timeline = _app.activeProduct.timeline
    if feature_index < 0 or feature_index >= timeline.count:
        raise ValueError(f"Feature index {feature_index} out of range (0-{timeline.count - 1}).")
    item = timeline.item(feature_index)
    item.isSuppressed = True
    return f"Feature at index {feature_index} suppressed."

def unsuppress_feature(feature_index: int, **kwargs):
    """Unsuppress a feature in the timeline."""
    timeline = _app.activeProduct.timeline
    if feature_index < 0 or feature_index >= timeline.count:
        raise ValueError(f"Feature index {feature_index} out of range (0-{timeline.count - 1}).")
    item = timeline.item(feature_index)
    item.isSuppressed = False
    return f"Feature at index {feature_index} unsuppressed."

def delete_feature(feature_index: int, **kwargs):
    """Delete a specific feature from the timeline."""
    timeline = _app.activeProduct.timeline
    if feature_index < 0 or feature_index >= timeline.count:
        raise ValueError(f"Feature index {feature_index} out of range (0-{timeline.count - 1}).")
    item = timeline.item(feature_index)
    entity = item.entity
    if entity and entity.isValid and hasattr(entity, 'deleteMe'):
        entity.deleteMe()
        return f"Feature at index {feature_index} deleted."
    else:
        raise ValueError(f"Feature at index {feature_index} cannot be deleted.")

# =============================================
# Intuitive High-Level Tools
# =============================================
# These tools exist so Claude naturally picks the right one from natural language.
# "Make a tube" → create_tube (not "create two cylinders + boolean cut")
# "Extrude both sides" → sketch_extrude with symmetric=true
# "Countersink screw hole" → create_countersink_hole

def create_tube(outer_radius: float = 25, inner_radius: float = 20, height: float = 50,
                body_name: str = None, plane: str = 'xy', cx: float = 0, cy: float = 0, cz: float = 0,
                z_placement: str = 'center', x_placement: str = 'center', y_placement: str = 'center',
                direction: str = 'positive', **kwargs):
    """Create a hollow tube/pipe/cylinder. Much simpler than creating two cylinders and cutting."""
    if inner_radius >= outer_radius:
        raise ValueError(f"inner_radius ({inner_radius}) must be less than outer_radius ({outer_radius}).")
    scale = get_fusion_unit_scale()
    outer_cm, inner_cm, height_cm = outer_radius * scale, inner_radius * scale, height * scale
    cx_cm, cy_cm, cz_cm = cx * scale, cy * scale, cz * scale
    root = _app.activeProduct.rootComponent
    sketch = root.sketches.add(get_construction_plane(root, plane))
    # Draw two concentric circles — the area between them forms the tube wall
    sketch.sketchCurves.sketchCircles.addByCenterRadius(adsk.core.Point3D.create(0, 0, 0), outer_cm)
    sketch.sketchCurves.sketchCircles.addByCenterRadius(adsk.core.Point3D.create(0, 0, 0), inner_cm)
    # The annular profile (ring between circles) is typically profiles.item(1)
    prof = None
    for i in range(sketch.profiles.count):
        p = sketch.profiles.item(i)
        area = p.areaProperties().area
        # The ring profile has area = pi*(outer² - inner²), the inner circle has area = pi*inner²
        expected_ring_area = math.pi * (outer_cm**2 - inner_cm**2)
        if abs(area - expected_ring_area) / expected_ring_area < 0.1:
            prof = p
            break
    if not prof:
        # Fallback: pick the largest profile
        max_area = 0
        for i in range(sketch.profiles.count):
            p = sketch.profiles.item(i)
            a = p.areaProperties().area
            if a > max_area:
                max_area = a
                prof = p
    new_body = extrude_profile(root, prof, height_cm, direction)
    sketch.isVisible = False
    return _finalize_body(new_body, root, body_name, cx_cm, cy_cm, cz_cm, z_placement, x_placement, y_placement, direction)

def create_counterbore_hole(body_name: str, face_index: int = 0, x: float = 0, y: float = 0,
                            hole_diameter: float = 5, hole_depth: float = 0,
                            counterbore_diameter: float = 10, counterbore_depth: float = 3, **kwargs):
    """Create a counterbore hole (stepped hole for socket head cap screws). Combines a large shallow bore + deeper narrow hole."""
    body = find_entity_by_name(body_name)
    if not body:
        raise ValueError(f"Body '{body_name}' not found.")
    if face_index >= body.faces.count:
        raise ValueError(f"Face index {face_index} out of range.")
    root = _app.activeProduct.rootComponent
    scale = get_fusion_unit_scale()
    face = body.faces.item(face_index)
    # Step 1: Counterbore (large, shallow)
    sketch1 = root.sketches.add(face)
    sketch1.sketchCurves.sketchCircles.addByCenterRadius(
        adsk.core.Point3D.create(x * scale, y * scale, 0), (counterbore_diameter / 2) * scale)
    prof1 = sketch1.profiles.item(0)
    extrudes = root.features.extrudeFeatures
    ext1 = extrudes.createInput(prof1, adsk.fusion.FeatureOperations.CutFeatureOperation)
    ext1.setDistanceExtent(False, adsk.core.ValueInput.createByReal(counterbore_depth * scale))
    extrudes.add(ext1)
    sketch1.isVisible = False
    # Step 2: Through hole (narrow, deep)
    sketch2 = root.sketches.add(face)
    sketch2.sketchCurves.sketchCircles.addByCenterRadius(
        adsk.core.Point3D.create(x * scale, y * scale, 0), (hole_diameter / 2) * scale)
    prof2 = sketch2.profiles.item(0)
    ext2 = extrudes.createInput(prof2, adsk.fusion.FeatureOperations.CutFeatureOperation)
    if hole_depth == 0:
        ext2.setAllExtent(adsk.fusion.ExtentDirections.NegativeExtentDirection)
    else:
        ext2.setDistanceExtent(False, adsk.core.ValueInput.createByReal(hole_depth * scale))
    extrudes.add(ext2)
    sketch2.isVisible = False
    return f"Created counterbore hole (bore d={counterbore_diameter}mm, hole d={hole_diameter}mm) on '{body_name}'."

def create_countersink_hole(body_name: str, face_index: int = 0, x: float = 0, y: float = 0,
                            hole_diameter: float = 5, hole_depth: float = 0,
                            countersink_diameter: float = 10, countersink_angle: float = 90, **kwargs):
    """Create a countersink hole (tapered entry for flat head screws). Combines a conical taper + narrow hole."""
    body = find_entity_by_name(body_name)
    if not body:
        raise ValueError(f"Body '{body_name}' not found.")
    if face_index >= body.faces.count:
        raise ValueError(f"Face index {face_index} out of range.")
    root = _app.activeProduct.rootComponent
    scale = get_fusion_unit_scale()
    face = body.faces.item(face_index)
    # Step 1: Countersink cone
    half_angle_rad = math.radians(countersink_angle / 2)
    cone_depth = ((countersink_diameter - hole_diameter) / 2) / math.tan(half_angle_rad)
    sketch1 = root.sketches.add(face)
    sketch1.sketchCurves.sketchCircles.addByCenterRadius(
        adsk.core.Point3D.create(x * scale, y * scale, 0), (countersink_diameter / 2) * scale)
    prof1 = sketch1.profiles.item(0)
    extrudes = root.features.extrudeFeatures
    ext1 = extrudes.createInput(prof1, adsk.fusion.FeatureOperations.CutFeatureOperation)
    dist1 = adsk.core.ValueInput.createByReal(cone_depth * scale)
    ext1.setDistanceExtent(False, dist1)
    taper_val = adsk.core.ValueInput.createByString(f"{90 - countersink_angle / 2} deg")
    ext1.taperAngle = taper_val
    extrudes.add(ext1)
    sketch1.isVisible = False
    # Step 2: Through hole
    sketch2 = root.sketches.add(face)
    sketch2.sketchCurves.sketchCircles.addByCenterRadius(
        adsk.core.Point3D.create(x * scale, y * scale, 0), (hole_diameter / 2) * scale)
    prof2 = sketch2.profiles.item(0)
    ext2 = extrudes.createInput(prof2, adsk.fusion.FeatureOperations.CutFeatureOperation)
    if hole_depth == 0:
        ext2.setAllExtent(adsk.fusion.ExtentDirections.NegativeExtentDirection)
    else:
        ext2.setDistanceExtent(False, adsk.core.ValueInput.createByReal(hole_depth * scale))
    extrudes.add(ext2)
    sketch2.isVisible = False
    return f"Created countersink hole (sink d={countersink_diameter}mm at {countersink_angle}°, hole d={hole_diameter}mm) on '{body_name}'."

def sketch_mirror(sketch_name: str, mirror_axis: str = 'x', **kwargs):
    """Mirror all sketch geometry across an axis (x or y). Creates symmetric sketch profiles."""
    sketch = _get_sketch(sketch_name)
    scale = get_fusion_unit_scale()
    # Collect all existing curves
    curves_to_mirror = adsk.core.ObjectCollection.create()
    for curve in sketch.sketchCurves:
        curves_to_mirror.add(curve)
    if curves_to_mirror.count == 0:
        return "No sketch curves to mirror."
    # Create mirror line
    if mirror_axis.lower() == 'y':
        mirror_line = sketch.sketchCurves.sketchLines.addByTwoPoints(
            adsk.core.Point3D.create(0, -1000, 0), adsk.core.Point3D.create(0, 1000, 0))
    else:
        mirror_line = sketch.sketchCurves.sketchLines.addByTwoPoints(
            adsk.core.Point3D.create(-1000, 0, 0), adsk.core.Point3D.create(1000, 0, 0))
    mirror_line.isConstruction = True
    sketch.geometricConstraints.addSymmetry(curves_to_mirror.item(0), curves_to_mirror.item(0), mirror_line)
    return f"Mirrored {curves_to_mirror.count} curves across {mirror_axis}-axis in '{sketch_name}'."

def sketch_offset(sketch_name: str, offset_distance: float = 5, curve_index: int = 0,
                  direction_point_x: float = 0, direction_point_y: float = 0, **kwargs):
    """Offset sketch curves to create parallel geometry (e.g., for walls, channels)."""
    sketch = _get_sketch(sketch_name)
    scale = get_fusion_unit_scale()
    if curve_index >= sketch.sketchCurves.count:
        raise ValueError(f"Curve index {curve_index} out of range (0-{sketch.sketchCurves.count - 1}).")
    curves = adsk.core.ObjectCollection.create()
    curves.add(sketch.sketchCurves.item(curve_index))
    dir_point = adsk.core.Point3D.create(direction_point_x * scale, direction_point_y * scale, 0)
    sketch.offset(curves, dir_point, offset_distance * scale)
    return f"Offset curve {curve_index} by {offset_distance}mm in '{sketch_name}'."

def sketch_fillet(sketch_name: str, curve_index_1: int = 0, curve_index_2: int = 1, radius: float = 5, **kwargs):
    """Add a fillet (rounded corner) between two sketch curves at their intersection."""
    sketch = _get_sketch(sketch_name)
    scale = get_fusion_unit_scale()
    curves = sketch.sketchCurves
    if curve_index_1 >= curves.count or curve_index_2 >= curves.count:
        raise ValueError(f"Curve index out of range (0-{curves.count - 1}).")
    fillets = sketch.sketchCurves.sketchArcs
    fillets.addFillet(curves.item(curve_index_1), curves.item(curve_index_1).endSketchPoint.geometry,
                      curves.item(curve_index_2), curves.item(curve_index_2).startSketchPoint.geometry,
                      radius * scale)
    return f"Added {radius}mm sketch fillet between curves {curve_index_1} and {curve_index_2} in '{sketch_name}'."

def create_component(body_names: list = None, component_name: str = None, **kwargs):
    """Create a new component from existing bodies. Use this to organize designs into sub-assemblies."""
    root = _app.activeProduct.rootComponent
    # Create new occurrence
    new_occ = root.occurrences.addNewComponent(adsk.core.Matrix3D.create())
    new_comp = new_occ.component
    if component_name:
        new_comp.name = component_name
    if body_names:
        for bname in body_names:
            body = find_entity_by_name(bname)
            if body:
                body.moveToComponent(new_occ)
    return f"Created component '{new_comp.name}' with {len(body_names) if body_names else 0} bodies."

def extrude_to_object(sketch_name: str, target_body_name: str, profile_index: int = 0,
                      operation: str = 'new', body_name: str = None, **kwargs):
    """Extrude a sketch profile up to the surface of another body (to-object extent)."""
    sketch = _get_sketch(sketch_name)
    if profile_index >= sketch.profiles.count:
        raise ValueError(f"Profile index {profile_index} out of range.")
    profile = sketch.profiles.item(profile_index)
    target = find_entity_by_name(target_body_name)
    if not target:
        raise ValueError(f"Target body '{target_body_name}' not found.")
    root = _app.activeProduct.rootComponent
    op_map = {
        'new': adsk.fusion.FeatureOperations.NewBodyFeatureOperation,
        'join': adsk.fusion.FeatureOperations.JoinFeatureOperation,
        'cut': adsk.fusion.FeatureOperations.CutFeatureOperation,
        'intersect': adsk.fusion.FeatureOperations.IntersectFeatureOperation,
    }
    operation_enum = op_map.get(operation.lower(), adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
    extrudes = root.features.extrudeFeatures
    ext_input = extrudes.createInput(profile, operation_enum)
    ext_input.setToExtent(adsk.fusion.ToEntityExtentDefinition.create(target, False))
    new_body = extrudes.add(ext_input).bodies.item(0)
    sketch.isVisible = False
    if body_name and new_body:
        new_body.name = get_unique_body_name(root, body_name)
    return new_body.name if new_body else "Extrusion to object completed."

# =============================================
# Undo, Constraints, Dimensions, Code Execution
# =============================================

def undo(**kwargs):
    """Undo the last operation. Same as pressing Ctrl+Z in Fusion 360."""
    cmd_def = _ui.commandDefinitions.itemById('UndoCommand')
    if cmd_def:
        cmd_def.execute()
        return "Undo executed."
    else:
        raise RuntimeError("Undo command not available.")

def sketch_add_constraint(sketch_name: str, constraint_type: str,
                          entity_one: int = None, entity_two: int = None,
                          symmetry_line: int = None, **kwargs):
    """Add a geometric constraint between sketch curves.
    constraint_type: coincident, parallel, perpendicular, tangent, equal, fix,
                     horizontal, vertical, concentric, collinear, smooth, midpoint, symmetry.
    entity_one/entity_two: 0-based curve indices in the sketch.
    symmetry_line: curve index used as the axis for symmetry constraint."""
    sketch = _get_sketch(sketch_name)
    constraints = sketch.geometricConstraints
    curves = list(sketch.sketchCurves)
    if not curves:
        raise ValueError(f"Sketch '{sketch_name}' has no curves.")

    e1 = curves[entity_one] if entity_one is not None and entity_one < len(curves) else None
    e2 = curves[entity_two] if entity_two is not None and entity_two < len(curves) else None

    constraint_map = {
        "coincident": lambda: constraints.addCoincident(e1, e2),
        "parallel": lambda: constraints.addParallel(e1, e2),
        "perpendicular": lambda: constraints.addPerpendicular(e1, e2),
        "tangent": lambda: constraints.addTangent(e1, e2),
        "equal": lambda: constraints.addEqual(e1, e2),
        "fix": lambda: constraints.addFix(e1),
        "horizontal": lambda: constraints.addHorizontal(e1),
        "vertical": lambda: constraints.addVertical(e1),
        "concentric": lambda: constraints.addConcentric(e1, e2),
        "collinear": lambda: constraints.addCollinear(e1, e2),
        "smooth": lambda: constraints.addSmooth(e1, e2),
        "midpoint": lambda: constraints.addMidPoint(
            sketch.sketchPoints.item(entity_one) if entity_one is not None else None, e2),
        "symmetry": lambda: constraints.addSymmetry(
            e1, e2, curves[symmetry_line] if symmetry_line is not None and symmetry_line < len(curves) else None),
    }

    if constraint_type not in constraint_map:
        raise ValueError(f"Unknown constraint type: '{constraint_type}'. Valid: {', '.join(constraint_map.keys())}")

    constraint_map[constraint_type]()
    return f"Added '{constraint_type}' constraint in sketch '{sketch_name}'."

def sketch_add_dimension(sketch_name: str, dimension_type: str, value: float,
                         entity_one: int = None, entity_two: int = None, **kwargs):
    """Add a parametric dimension to sketch geometry.
    dimension_type: distance, angular, radial, diameter, horizontal, vertical.
    value: dimension value in mm (distance/radial/diameter) or degrees (angular).
    entity_one/entity_two: 0-based curve indices."""
    sketch = _get_sketch(sketch_name)
    scale = get_fusion_unit_scale()
    dims = sketch.sketchDimensions
    curves = list(sketch.sketchCurves)
    if not curves:
        raise ValueError(f"Sketch '{sketch_name}' has no curves.")

    e1 = curves[entity_one] if entity_one is not None and entity_one < len(curves) else None
    e2 = curves[entity_two] if entity_two is not None and entity_two < len(curves) else None
    text_pt = adsk.core.Point3D.create(1, 1, 0)  # Dimension label position

    if dimension_type == "distance":
        if e1 and e2:
            dim = dims.addDistanceDimension(
                e1.startSketchPoint, e2.startSketchPoint,
                adsk.fusion.DimensionOrientations.AlignedDimensionOrientation, text_pt)
        else:
            raise ValueError("distance dimension requires entity_one and entity_two.")
    elif dimension_type == "angular":
        if e1 and e2:
            dim = dims.addAngularDimension(e1, e2, text_pt)
        else:
            raise ValueError("angular dimension requires entity_one and entity_two.")
    elif dimension_type == "radial":
        if e1:
            dim = dims.addRadialDimension(e1, text_pt)
        else:
            raise ValueError("radial dimension requires entity_one.")
    elif dimension_type == "diameter":
        if e1:
            dim = dims.addDiameterDimension(e1, text_pt)
        else:
            raise ValueError("diameter dimension requires entity_one.")
    elif dimension_type == "horizontal":
        if e1 and e2:
            dim = dims.addDistanceDimension(
                e1.startSketchPoint, e2.startSketchPoint,
                adsk.fusion.DimensionOrientations.HorizontalDimensionOrientation, text_pt)
        else:
            raise ValueError("horizontal dimension requires entity_one and entity_two.")
    elif dimension_type == "vertical":
        if e1 and e2:
            dim = dims.addDistanceDimension(
                e1.startSketchPoint, e2.startSketchPoint,
                adsk.fusion.DimensionOrientations.VerticalDimensionOrientation, text_pt)
        else:
            raise ValueError("vertical dimension requires entity_one and entity_two.")
    else:
        raise ValueError(f"Unknown dimension type: '{dimension_type}'. Valid: distance, angular, radial, diameter, horizontal, vertical")

    # Set the dimension value (mm → cm for distance types, degrees → radians for angular)
    if dimension_type == "angular":
        dim.parameter.value = math.radians(value)
    else:
        dim.parameter.value = value * scale
    return f"Added {dimension_type} dimension ({value}) in sketch '{sketch_name}'."

def execute_code(code: str, **kwargs):
    """Execute arbitrary Python code inside Fusion 360. Use this as a last resort when no specific tool exists.
    The code has access to: adsk, app, ui, design, root, math, json.
    The last expression's value is returned as the result."""
    ns = {
        "adsk": adsk,
        "app": _app,
        "ui": _ui,
        "design": adsk.fusion.Design.cast(_app.activeProduct),
        "root": _app.activeProduct.rootComponent,
        "math": math,
        "json": json,
    }

    buf = io.StringIO()

    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        raise RuntimeError(f"SyntaxError: {exc}")

    last_expr_value = None
    if tree.body and isinstance(tree.body[-1], ast.Expr):
        last_node = tree.body.pop()
        if tree.body:
            with redirect_stdout(buf):
                exec(compile(ast.Module(body=tree.body, type_ignores=[]), "<mcp>", "exec"), ns)
        expr_code = compile(ast.Expression(body=last_node.value), "<mcp>", "eval")
        with redirect_stdout(buf):
            last_expr_value = eval(expr_code, ns)
    else:
        with redirect_stdout(buf):
            exec(compile(tree, "<mcp>", "exec"), ns)

    output = buf.getvalue()
    result = last_expr_value if last_expr_value is not None else output

    # Ensure result is JSON-serializable
    if result is not None:
        try:
            json.dumps(result)
        except (TypeError, ValueError):
            result = str(result)

    return {"executed": True, "result": result, "output": output}

# --- Command Dispatcher ---
_BASE_COMMAND_MAP = {
    # Shape creation
    'create_cube': create_cube, 'create_cylinder': create_cylinder, 'create_box': create_box,
    'create_sphere': create_sphere, 'create_hemisphere': create_hemisphere, 'create_cone': create_cone,
    'create_polygon_prism': create_polygon_prism, 'create_torus': create_torus, 'create_half_torus': create_half_torus,
    'create_pipe': create_pipe, 'create_polygon_sweep': create_polygon_sweep,
    # Patterns & copies
    'copy_body_symmetric': copy_body_symmetric, 'create_circular_pattern': create_circular_pattern,
    'create_rectangular_pattern': create_rectangular_pattern, 'copy_body': copy_body,
    # Modifications
    'add_fillet': add_fillet, 'add_chamfer': add_chamfer,
    'combine_selection': combine_selection, 'combine_selection_all': combine_selection_all,
    'combine_by_name': combine_by_name,
    # Lot 1 — Core geometry
    'shell_body': shell_body, 'create_hole': create_hole, 'create_thread': create_thread,
    'offset_face': offset_face, 'split_body': split_body, 'scale_body': scale_body,
    'draft_face': draft_face,
    # Selection & visibility
    'select_body': select_body, 'select_bodies': select_bodies, 'select_all_bodies': select_all_bodies,
    'hide_body': hide_body, 'show_body': show_body,
    'move_by_name': move_by_name, 'rotate_by_name': rotate_by_name,
    # Lot 2 — Sketch system
    'sketch_create': sketch_create, 'sketch_add_line': sketch_add_line, 'sketch_add_circle': sketch_add_circle,
    'sketch_add_arc': sketch_add_arc, 'sketch_add_rectangle': sketch_add_rectangle,
    'sketch_add_polygon': sketch_add_polygon, 'sketch_add_spline': sketch_add_spline,
    'sketch_add_text': sketch_add_text, 'sketch_extrude': sketch_extrude,
    'create_revolve': create_revolve, 'create_loft': create_loft, 'create_sweep': create_sweep,
    'create_construction_plane': create_construction_plane,
    # Lot 3 — Export, materials, capture
    'export_stl': export_stl, 'export_step': export_step, 'export_f3d': export_f3d,
    'set_material': set_material, 'set_appearance': set_appearance,
    'set_user_parameter': set_user_parameter, 'get_user_parameter': get_user_parameter,
    'capture_viewport': capture_viewport, 'list_bodies': list_bodies,
    # Existing design interaction
    'rename_body': rename_body, 'list_features': list_features, 'list_sketches': list_sketches,
    'list_components': list_components, 'get_design_info': get_design_info,
    'suppress_feature': suppress_feature, 'unsuppress_feature': unsuppress_feature,
    'delete_feature': delete_feature,
    # Intuitive high-level tools
    'create_tube': create_tube, 'create_counterbore_hole': create_counterbore_hole,
    'create_countersink_hole': create_countersink_hole, 'sketch_mirror': sketch_mirror,
    'sketch_offset': sketch_offset, 'sketch_fillet': sketch_fillet,
    'create_component': create_component, 'extrude_to_object': extrude_to_object,
    # Advanced sketch tools
    'sketch_add_constraint': sketch_add_constraint, 'sketch_add_dimension': sketch_add_dimension,
    # Escape hatch & undo
    'undo': undo, 'execute_code': execute_code,
    # Utility
    'delete_all_features': delete_all_features, 'debug_coordinate_info': debug_coordinate_info,
    'debug_body_placement': debug_body_placement,
    'get_bounding_box': get_bounding_box, 'get_body_center': get_body_center,
    'get_body_dimensions': get_body_dimensions, 'get_faces_info': get_faces_info,
    'get_edges_info': get_edges_info, 'get_mass_properties': get_mass_properties,
    'get_body_relationships': get_body_relationships, 'measure_distance': measure_distance,
}
# Auto-generate fusion: prefixed versions
COMMAND_MAP = {**_BASE_COMMAND_MAP, **{f'fusion:{k}': v for k, v in _BASE_COMMAND_MAP.items()}}

def dispatch_command(command_name, params):
    log_debug(f"Executing command: {command_name}")
    func = COMMAND_MAP.get(command_name)
    response_data = {}
    try:
        if func:
            result = func(**params)
            response_data['status'] = 'success'
            response_data['result'] = result if result is not None else 'OK'
        else:
            raise ValueError(f"Unsupported command: {command_name}")

    except Exception as e:
        log_debug(f"Error executing '{command_name}': {traceback.format_exc()}")
        response_data['status'] = 'error'
        response_data['message'] = f"Failed to execute '{command_name}': {str(e)}"
        response_data['traceback'] = traceback.format_exc()

    finally:
        try:
            with open(_response_file_path, 'w', encoding='utf-8') as f:
                json.dump(response_data, f, ensure_ascii=False, indent=4)
            log_debug(f"Wrote response for {command_name} to file.")
        except Exception as e:
            log_debug(f"Failed to write response file: {traceback.format_exc()}")

# --- Event Handler ---
class CommandReceivedEventHandler(adsk.core.CustomEventHandler):
    def notify(self, args):
        try:
            if os.path.exists(_response_file_path):
                with open(_response_file_path, 'w', encoding='utf-8') as f: f.truncate(0)
            data = json.loads(args.additionalInfo)
            command_name = data.get('command')
            params = data.get('parameters', {})
            if not _app.activeDocument: raise RuntimeError("No active design document.")

            if command_name == 'execute_macro':
                commands_list = params.get('commands', [])
                macro_results = []
                for cmd_item in commands_list:
                    cmd_name = cmd_item.get('tool_name')
                    cmd_args = cmd_item.get('arguments', {})
                    func = COMMAND_MAP.get(cmd_name)
                    if func:
                        try:
                            result = func(**cmd_args)
                            macro_results.append({'command': cmd_name, 'status': 'success', 'result': result if result is not None else 'OK'})
                        except Exception as e:
                            macro_results.append({'command': cmd_name, 'status': 'error', 'message': str(e)})
                    else:
                        macro_results.append({'command': cmd_name, 'status': 'error', 'message': f'Unknown command: {cmd_name}'})

                response = {'status': 'success', 'result': macro_results}
                with open(_response_file_path, 'w', encoding='utf-8') as f: json.dump(response, f, ensure_ascii=False, indent=4)
            else:
                dispatch_command(command_name, params)
        except Exception as e:
            error_response = {'status': 'error', 'message': 'Failed to process command event.', 'traceback': traceback.format_exc()}
            try:
                with open(_response_file_path, 'w', encoding='utf-8') as f: json.dump(error_response, f, ensure_ascii=False, indent=4)
            except Exception:
                pass
            log_debug(f'Command processing failed:\n{traceback.format_exc()}')

# --- UI Command Handlers ---
class StartServerCreatedHandler(adsk.core.CommandCreatedEventHandler):
    def __init__(self): super().__init__()
    def notify(self, args):
        command = args.command; onExecute = StartServerExecuteHandler(); command.execute.add(onExecute); _handlers.append(onExecute)

class StartServerExecuteHandler(adsk.core.CommandEventHandler):
    def __init__(self): super().__init__()
    def notify(self, args): start_server()

class StopServerCreatedHandler(adsk.core.CommandCreatedEventHandler):
    def __init__(self): super().__init__()
    def notify(self, args):
        command = args.command; onExecute = StopServerExecuteHandler(); command.execute.add(onExecute); _handlers.append(onExecute)

class StopServerExecuteHandler(adsk.core.CommandEventHandler):
    def __init__(self): super().__init__()
    def notify(self, args): stop_server()

# --- File Watcher & Server Control ---
def file_watcher(stop_event):
    last_modified = 0
    while not stop_event.is_set():
        try:
            if os.path.exists(_command_file_path):
                modified = os.path.getmtime(_command_file_path)
                if modified > last_modified:
                    last_modified = modified
                    with open(_command_file_path, 'r+', encoding='utf-8') as f:
                        content = f.read().strip()
                        if content:
                            # Validate JSON before firing event to avoid partial reads
                            try:
                                json.loads(content)
                            except json.JSONDecodeError:
                                log_debug("Partial JSON detected, retrying next poll.")
                                continue
                            _app.fireCustomEvent(_command_received_event_id, content)
                            f.seek(0)
                            f.truncate()
        except Exception as e:
            log_debug(f"File watcher error: {traceback.format_exc()}")
        time.sleep(0.5)

def start_server():
    global _is_running, _file_watcher_thread, _stop_flag, _command_received_event, _event_handler
    if _is_running: return
    try:
        with open(_command_file_path, 'w', encoding='utf-8') as f: f.truncate(0)
        with open(_response_file_path, 'w', encoding='utf-8') as f: f.truncate(0)
        _command_received_event = _app.registerCustomEvent(_command_received_event_id)
        _event_handler = CommandReceivedEventHandler()
        _command_received_event.add(_event_handler)
        _handlers.append(_event_handler)
        _stop_flag = threading.Event()
        _file_watcher_thread = threading.Thread(target=file_watcher, args=(_stop_flag,))
        _file_watcher_thread.start()
        _is_running = True
        if _start_cmd_control: _start_cmd_control.isEnabled = False
        if _stop_cmd_control: _stop_cmd_control.isEnabled = True
        if _ui: _ui.messageBox('MCP Server started.')
    except Exception as e:
        if _ui: _ui.messageBox(f'Failed to start server: {e}')

def stop_server():
    global _is_running, _file_watcher_thread, _stop_flag, _command_received_event, _event_handler
    if not _is_running: return
    _sketch_registry.clear()
    try:
        if _stop_flag: _stop_flag.set()
        if _file_watcher_thread: _file_watcher_thread.join(timeout=2)
        if _command_received_event and _event_handler in _handlers:
            _command_received_event.remove(_event_handler)
            _handlers.remove(_event_handler)
        if _command_received_event and _app.unregisterCustomEvent(_command_received_event_id):
            _command_received_event = None
        _is_running = False
        if _start_cmd_control: _start_cmd_control.isEnabled = True
        if _stop_cmd_control: _stop_cmd_control.isEnabled = False
        if _ui: _ui.messageBox('MCP Server stopped.')
    except Exception as e:
        if _ui: _ui.messageBox(f'Failed to stop server: {e}')

# --- Add-in Lifecycle ---
def run(context):
    global _app, _ui, _start_cmd_def, _stop_cmd_def, _mcp_panel, _start_cmd_control, _stop_cmd_control, _handlers
    _app = adsk.core.Application.get()
    _ui  = _app.userInterface
    _handlers = []
    try:
        ws = _ui.workspaces.itemById('FusionSolidEnvironment')
        if not ws:
            if _ui: _ui.messageBox('This add-in must be run in the Design workspace.', 'MCP Server Error')
            return
        panel_id = 'MCPServerPanel'
        _mcp_panel = ws.toolbarPanels.itemById(panel_id)
        if _mcp_panel: _mcp_panel.deleteMe()
        toolbar = ws.toolbarTabs.itemById('ToolsTab')
        if toolbar:
            _mcp_panel = toolbar.toolbarPanels.add(panel_id, 'MCP Server')
        else:
            _mcp_panel = ws.toolbarPanels.add(panel_id, 'MCP Server')
        res_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resources')
        start_icon = os.path.join(res_dir, 'start') if os.path.isdir(os.path.join(res_dir, 'start')) else ''
        stop_icon = os.path.join(res_dir, 'stop') if os.path.isdir(os.path.join(res_dir, 'stop')) else ''
        start_cmd_id = 'StartMCPServerCmd'
        _start_cmd_def = _ui.commandDefinitions.itemById(start_cmd_id)
        if not _start_cmd_def: _start_cmd_def = _ui.commandDefinitions.addButtonDefinition(start_cmd_id, 'START', 'Start MCP server connection.', start_icon)
        stop_cmd_id = 'StopMCPServerCmd'
        _stop_cmd_def = _ui.commandDefinitions.itemById(stop_cmd_id)
        if not _stop_cmd_def: _stop_cmd_def = _ui.commandDefinitions.addButtonDefinition(stop_cmd_id, 'STOP', 'Stop MCP server connection.', stop_icon)
        onStartCreated = StartServerCreatedHandler()
        _start_cmd_def.commandCreated.add(onStartCreated)
        _handlers.append(onStartCreated)
        onStopCreated = StopServerCreatedHandler()
        _stop_cmd_def.commandCreated.add(onStopCreated)
        _handlers.append(onStopCreated)
        _start_cmd_control = _mcp_panel.controls.addCommand(_start_cmd_def)
        _stop_cmd_control = _mcp_panel.controls.addCommand(_stop_cmd_def)
        _start_cmd_control.isEnabled = True
        _stop_cmd_control.isEnabled = False
        _is_running = False
    except Exception:
        if _ui: _ui.messageBox(f'Unexpected error loading add-in:\n{traceback.format_exc()}', 'MCP Server Error')

def stop(context):
    global _ui, _mcp_panel, _start_cmd_def, _stop_cmd_def
    try:
        if _is_running: stop_server()
        if _mcp_panel: _mcp_panel.deleteMe()
        if _start_cmd_def: _start_cmd_def.deleteMe()
        if _stop_cmd_def: _stop_cmd_def.deleteMe()
    except Exception:
        if _ui: _ui.messageBox(f'Unexpected error unloading add-in:\n{traceback.format_exc()}', 'MCP Server Error')
