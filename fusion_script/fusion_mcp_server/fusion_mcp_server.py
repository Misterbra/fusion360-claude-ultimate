# fusion_mcp_server.py - v 0.7.82 ベータ版 Beta version 2025.08.26
#  
# 

import adsk.core, adsk.fusion, traceback
import threading
import time
import os
import math
import json

# --- グローバル変数 ---
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

# --- 共通ヘルパー関数 ---
def log_debug(message):
    try:
        if _ui:
            text_palette = _ui.palettes.itemById('TextCommands')
            if text_palette:
                text_palette.writeText(f"[MCP-PY-STABLE] {message}")
    except:
        pass

def get_fusion_unit_scale():
    return 0.1 # mmからcmへの変換係数

def get_construction_plane(root: adsk.fusion.Component, plane_str: str):
    plane_map = {'yz': root.yZConstructionPlane, 'xz': root.xZConstructionPlane, 'xy': root.xYConstructionPlane}
    return plane_map.get(str(plane_str).lower(), root.xYConstructionPlane)

# ▼▼▼【新規追加】ボディ名の一意性を保証するヘルパー関数 ▼▼▼
def get_unique_body_name(root: adsk.fusion.Component, base_name: str) -> str:
    """
    指定されたベース名から一意のボディ名を生成します。
    同名が存在する場合、'_2', '_3' のようにサフィックスを追加します。
    """
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
# ▲▲▲【新規追加】ここまで ▲▲▲

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
    """
    【改善版】ボディを指定された基準で配置します。
    配置ロジックは押し出し方向(direction)に依存せず、常に形状の幾何的な上下左右に基づいて決定され、直感的で予測可能な挙動をします。
    """
    if not body:
        return

    bbox = body.boundingBox
    current_centroid = body.physicalProperties.centerOfMass
    scale = get_fusion_unit_scale()

    log_debug(f"Intuitive placement: z_placement={z_placement}, x_placement={x_placement}, y_placement={y_placement}")
    # Note: 'direction' パラメータは、配置ロジックの直感性を高めるために意図的に無視されます。

    # Z軸方向の配置計算 (改善版：押し出し方向に依存しない直感的なロジック)
    if z_placement == 'bottom':
        # 常にボディの底面 (min Z) が cz に揃うように移動
        target_centroid_z = cz_cm + (current_centroid.z - bbox.minPoint.z)
    elif z_placement == 'top':
        # 常にボディの上面 (max Z) が cz に揃うように移動
        target_centroid_z = cz_cm + (current_centroid.z - bbox.maxPoint.z)
    else:  # center
        # 常にボディの重心が cz に揃うように移動
        target_centroid_z = cz_cm

    # X軸方向の配置計算
    if x_placement == 'left':
        target_centroid_x = cx_cm + (current_centroid.x - bbox.minPoint.x)
    elif x_placement == 'right':
        target_centroid_x = cx_cm + (current_centroid.x - bbox.maxPoint.x)
    else:  # center
        target_centroid_x = cx_cm

    # Y軸方向の配置計算 (Fusion 360座標系: -YがFront, +YがBack)
    if y_placement == 'front':
        target_centroid_y = cy_cm + (current_centroid.y - bbox.minPoint.y)
    elif y_placement == 'back':
        target_centroid_y = cy_cm + (current_centroid.y - bbox.maxPoint.y)
    else:  # center
        target_centroid_y = cy_cm
    
    target_point = adsk.core.Point3D.create(target_centroid_x, target_centroid_y, target_centroid_z)
    move_body_to_absolute_position(body, target_point)

def find_entity_by_name(name: str):
    if not name: return None
    root = _app.activeProduct.rootComponent
    entity = next((b for b in root.bRepBodies if b.name == name), None)
    if entity: return entity
    return next((occ for occ in root.occurrences if occ.name.split(':', 1)[0] == name), None)

# --- デバッグ用関数 ---
def debug_body_placement(body_name: str, **kwargs):
    body = find_entity_by_name(body_name)
    if not body:
        return f"ボディ '{body_name}' が見つかりません。"
    
    bbox = body.boundingBox
    centroid = body.physicalProperties.centerOfMass
    scale = get_fusion_unit_scale()
    
    info = f"=== {body_name} の配置情報 ===\n"
    info += f"重心位置: ({centroid.x/scale:.2f}, {centroid.y/scale:.2f}, {centroid.z/scale:.2f}) mm\n"
    info += f"バウンディングボックス:\n"
    info += f"  最小点: ({bbox.minPoint.x/scale:.2f}, {bbox.minPoint.y/scale:.2f}, {bbox.minPoint.z/scale:.2f}) mm\n"
    info += f"  最大点: ({bbox.maxPoint.x/scale:.2f}, {bbox.maxPoint.y/scale:.2f}, {bbox.maxPoint.z/scale:.2f}) mm\n"
    info += f"サイズ:\n"
    info += f"  幅(X): {(bbox.maxPoint.x - bbox.minPoint.x)/scale:.2f} mm\n"
    info += f"  奥行(Y): {(bbox.maxPoint.y - bbox.minPoint.y)/scale:.2f} mm\n"
    info += f"  高さ(Z): {(bbox.maxPoint.z - bbox.minPoint.z)/scale:.2f} mm\n"
    info += f"配置基準:\n"
    info += f"  左端(X-): {bbox.minPoint.x/scale:.2f} mm\n"
    info += f"  右端(X+): {bbox.maxPoint.x/scale:.2f} mm\n"
    info += f"  後端(Y-): {bbox.minPoint.y/scale:.2f} mm\n"
    info += f"  前端(Y+): {bbox.maxPoint.y/scale:.2f} mm\n"
    info += f"  底面(Z-): {bbox.minPoint.z/scale:.2f} mm\n"
    info += f"  上面(Z+): {bbox.maxPoint.z/scale:.2f} mm\n"
    
    return info

# --- コマンド実行関数 ---
def create_cube(size: float=50, body_name: str=None, plane: str='xy', cx: float=0, cy: float=0, cz: float=0, z_placement: str='center', x_placement: str='center', y_placement: str='center', taper_angle: float=0, taper_direction: str='inward', direction: str='positive', **kwargs):
    scale = get_fusion_unit_scale()
    size_cm = size * scale
    cx_cm, cy_cm, cz_cm = cx * scale, cy * scale, cz * scale
    root = _app.activeProduct.rootComponent
    sketch = root.sketches.add(get_construction_plane(root, plane))
    sketch.sketchCurves.sketchLines.addTwoPointRectangle(adsk.core.Point3D.create(-size_cm/2, -size_cm/2, 0), adsk.core.Point3D.create(size_cm/2, size_cm/2, 0))
    prof = sketch.profiles.item(0)
    extrudes = root.features.extrudeFeatures
    ext_input = extrudes.createInput(prof, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
    distance = adsk.core.ValueInput.createByReal(size_cm)
    if direction.lower() == 'positive':
        ext_input.setDistanceExtent(False, distance)
    else:
        extent_definition = adsk.fusion.DistanceExtentDefinition.create(distance)
        ext_input.setOneSideExtent(extent_definition, adsk.fusion.ExtentDirections.NegativeExtentDirection)
    if taper_angle != 0:
        final_taper = abs(taper_angle) * (-1 if taper_direction.lower() == 'inward' else 1)
        taper_angle_input = adsk.core.ValueInput.createByString(f"{final_taper} deg")
        ext_input.taperAngle = taper_angle_input
    extrude_feature = extrudes.add(ext_input)
    new_body = extrude_feature.bodies.item(0)
    sketch.isVisible = False
    
    # 【重要】Direction対応修正版の配置関数を使用
    move_body_with_placement(new_body, cx_cm, cy_cm, cz_cm, z_placement, x_placement, y_placement, direction)
    
    if body_name:
        new_body.name = get_unique_body_name(root, body_name) #【修正】一意な名前を生成
    return new_body.name

def create_cylinder(radius: float=25, height: float=50, body_name: str=None, plane: str='xy', cx: float=0, cy: float=0, cz: float=0, z_placement: str='center', x_placement: str='center', y_placement: str='center', taper_angle: float=0, taper_direction: str='inward', direction: str='positive', **kwargs):
    scale = get_fusion_unit_scale()
    radius_cm, height_cm = radius * scale, height * scale
    cx_cm, cy_cm, cz_cm = cx * scale, cy * scale, cz * scale
    root = _app.activeProduct.rootComponent
    sketch = root.sketches.add(get_construction_plane(root, plane))
    sketch.sketchCurves.sketchCircles.addByCenterRadius(adsk.core.Point3D.create(0, 0, 0), radius_cm)
    prof = sketch.profiles.item(0)
    extrudes = root.features.extrudeFeatures
    ext_input = extrudes.createInput(prof, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
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
    extrude_feature = extrudes.add(ext_input)
    new_body = extrude_feature.bodies.item(0)
    sketch.isVisible = False
    
    # 【重要】Direction対応修正版の配置関数を使用
    move_body_with_placement(new_body, cx_cm, cy_cm, cz_cm, z_placement, x_placement, y_placement, direction)
    
    if body_name:
        new_body.name = get_unique_body_name(root, body_name) #【修正】一意な名前を生成
    return new_body.name

def create_box(width: float=50, depth: float=30, height: float=20, body_name: str=None, plane: str='xy', cx: float=0, cy: float=0, cz: float=0, z_placement: str='center', x_placement: str='center', y_placement: str='center', taper_angle: float=0, taper_direction: str='inward', direction: str='positive', **kwargs):
    scale = get_fusion_unit_scale()
    width_cm, depth_cm, height_cm = width * scale, depth * scale, height * scale
    cx_cm, cy_cm, cz_cm = cx * scale, cy * scale, cz * scale
    root = _app.activeProduct.rootComponent
    sketch = root.sketches.add(get_construction_plane(root, plane))
    sketch.sketchCurves.sketchLines.addTwoPointRectangle(adsk.core.Point3D.create(-width_cm/2, -depth_cm/2, 0), adsk.core.Point3D.create(width_cm/2, depth_cm/2, 0))
    prof = sketch.profiles.item(0)
    extrudes = root.features.extrudeFeatures
    ext_input = extrudes.createInput(prof, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
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
    new_body = extrudes.add(ext_input).bodies.item(0)
    sketch.isVisible = False
    move_body_with_placement(new_body, cx_cm, cy_cm, cz_cm, z_placement, x_placement, y_placement, direction)
    
    if body_name:
        new_body.name = get_unique_body_name(root, body_name) #【修正】一意な名前を生成
    return new_body.name

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
    transform = adsk.core.Matrix3D.create()
    if plane.lower() == 'xz':
        transform.setToRotation(math.radians(90), adsk.core.Vector3D.create(1, 0, 0), adsk.core.Point3D.create(0,0,0))
    elif plane.lower() == 'yz':
        transform.setToRotation(math.radians(-90), adsk.core.Vector3D.create(0, 1, 0), adsk.core.Point3D.create(0,0,0))
    if plane.lower() != 'xy':
        move_features = root.features.moveFeatures
        move_input = move_features.createInput(adsk.core.ObjectCollection.createWithArray([new_body]), transform)
        move_features.add(move_input)
        adsk.doEvents()
    move_body_with_placement(new_body, cx_cm, cy_cm, cz_cm, z_placement, x_placement, y_placement, 'positive')  # hemisphereにはdirectionパラメータなし
    if body_name: new_body.name = get_unique_body_name(root, body_name)
    return new_body.name

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
    transform = adsk.core.Matrix3D.create()
    if plane.lower() == 'xz':
        transform.setToRotation(math.radians(-90), adsk.core.Vector3D.create(1, 0, 0), adsk.core.Point3D.create(0,0,0))
    elif plane.lower() == 'yz':
        transform.setToRotation(math.radians(90), adsk.core.Vector3D.create(0, 1, 0), adsk.core.Point3D.create(0,0,0))
    if plane.lower() != 'xy':
        move_features = root.features.moveFeatures
        move_input = move_features.createInput(adsk.core.ObjectCollection.createWithArray([new_body]), transform)
        move_features.add(move_input)
        adsk.doEvents()
    move_body_with_placement(new_body, cx_cm, cy_cm, cz_cm, z_placement, x_placement, y_placement, 'positive')  # coneにはdirectionパラメータなし
    if body_name: new_body.name = get_unique_body_name(root, body_name)
    return new_body.name
        
def create_polygon_prism(num_sides: int=6, radius: float=25, height: float=50, body_name: str=None, plane: str='xy', cx: float=0, cy: float=0, cz: float=0, z_placement: str='center', x_placement: str='center', y_placement: str='center', taper_angle: float=0, taper_direction: str='inward', direction: str='positive', **kwargs):
    if num_sides < 3: raise ValueError("多角形の辺の数は3以上でなければなりません。")
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
    extrudes = root.features.extrudeFeatures
    ext_input = extrudes.createInput(prof, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
    distance = adsk.core.ValueInput.createByReal(height_cm)
    
    # Direction処理
    if direction.lower() == 'positive':
        ext_input.setDistanceExtent(False, distance)  # 非対称、+Z方向
    else:
        # negativeの場合は、逆方向の押し出しを実現
        extent_definition = adsk.fusion.DistanceExtentDefinition.create(distance)
        ext_input.setOneSideExtent(extent_definition, adsk.fusion.ExtentDirections.NegativeExtentDirection)
    
    # テーパー角度の処理
    if taper_angle != 0:
        final_taper = abs(taper_angle) * (-1 if taper_direction.lower() == 'inward' else 1)
        taper_angle_input = adsk.core.ValueInput.createByString(f"{final_taper} deg")
        ext_input.taperAngle = taper_angle_input
    
    new_body = extrudes.add(ext_input).bodies.item(0)
    sketch.isVisible = False
    
    # 配置関数を使用
    move_body_with_placement(new_body, cx_cm, cy_cm, cz_cm, z_placement, x_placement, y_placement, direction)
    
    if body_name: new_body.name = get_unique_body_name(root, body_name)
    return new_body.name
        
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
    
    if plane.lower() == 'xz':
        transform = adsk.core.Matrix3D.create()
        transform.setToRotation(math.radians(90), 
                              adsk.core.Vector3D.create(1, 0, 0), 
                              adsk.core.Point3D.create(0, 0, 0))
        move_features = root.features.moveFeatures
        move_input = move_features.createInput(
            adsk.core.ObjectCollection.createWithArray([new_body]), transform)
        move_features.add(move_input)
        adsk.doEvents()
    elif plane.lower() == 'yz':
        transform = adsk.core.Matrix3D.create()
        transform.setToRotation(math.radians(90), 
                              adsk.core.Vector3D.create(0, 1, 0), 
                              adsk.core.Point3D.create(0, 0, 0))
        move_features = root.features.moveFeatures
        move_input = move_features.createInput(
            adsk.core.ObjectCollection.createWithArray([new_body]), transform)
        move_features.add(move_input)
        adsk.doEvents()
    
    move_body_with_placement(new_body, cx_cm, cy_cm, cz_cm, z_placement, x_placement, y_placement, 'positive')  # torusにはdirectionパラメータなし
    
    if body_name:
        new_body.name = get_unique_body_name(root, body_name) #【修正】一意な名前を生成
    return new_body.name

def create_half_torus(major_radius=30, minor_radius=10, cx=0, cy=0, cz=0, plane='xy', z_placement='center', x_placement='center', y_placement='center', body_name=None, orientation: str='back', plane_rotation_angle: float=0, opening_extrude_distance: float=0, **kwargs):
    scale = get_fusion_unit_scale()
    major_radius_cm, minor_radius_cm = major_radius * scale, minor_radius * scale
    cx_cm, cy_cm, cz_cm = cx * scale, cy * scale, cz * scale
    root = _app.activeProduct.rootComponent
    move_features = root.features.moveFeatures

    # --- 本体作成 ---
    sketch = root.sketches.add(root.xZConstructionPlane)
    sketch.sketchCurves.sketchCircles.addByCenterRadius(
        adsk.core.Point3D.create(major_radius_cm, 0, 0), minor_radius_cm)
    prof = sketch.profiles.item(0)
    revolves = root.features.revolveFeatures
    revolve_input = revolves.createInput(prof, root.zConstructionAxis, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
    revolve_input.setAngleExtent(False, adsk.core.ValueInput.createByReal(math.pi))
    new_body = revolves.add(revolve_input).bodies.item(0)
    sketch.isVisible = False

    # --- 回転処理 ---
    transform_matrix = adsk.core.Matrix3D.create()
    plane_normal = adsk.core.Vector3D.create(0, 0, 1)
    
    plane_lower = plane.lower()
    if plane_lower == 'xz':
        transform_matrix.setToRotation(math.pi / 2, adsk.core.Vector3D.create(1, 0, 0), adsk.core.Point3D.create(0,0,0))
        plane_normal = adsk.core.Vector3D.create(0, 1, 0)
    elif plane_lower == 'yz':
        transform_matrix.setToRotation(-math.pi / 2, adsk.core.Vector3D.create(0, 1, 0), adsk.core.Point3D.create(0,0,0))
        plane_normal = adsk.core.Vector3D.create(1, 0, 0)

    orientation_angle_deg = 0
    orientation_lower = orientation.lower()

    if plane_lower == 'xy':
        if orientation_lower == 'back': orientation_angle_deg = 180
        elif orientation_lower == 'left': orientation_angle_deg = 90
        elif orientation_lower == 'right': orientation_angle_deg = -90
    elif plane_lower == 'xz':
        if orientation_lower == 'back': orientation_angle_deg = 180
        elif orientation_lower == 'left': orientation_angle_deg = 90
        elif orientation_lower == 'right': orientation_angle_deg = -90
    elif plane_lower == 'yz':
        if orientation_lower == 'back': orientation_angle_deg = 180
        elif orientation_lower == 'left': orientation_angle_deg = 90
        elif orientation_lower == 'right': orientation_angle_deg = -90

    total_rotation_angle_rad = math.radians(orientation_angle_deg + plane_rotation_angle)

    if total_rotation_angle_rad != 0:
        orientation_matrix = adsk.core.Matrix3D.create()
        orientation_matrix.setToRotation(total_rotation_angle_rad, plane_normal, adsk.core.Point3D.create(0,0,0))
        transform_matrix.transformBy(orientation_matrix)

    if not transform_matrix.isEqualTo(adsk.core.Matrix3D.create()):
        move_input = move_features.createInput(adsk.core.ObjectCollection.createWithArray([new_body]), transform_matrix)
        move_features.add(move_input)
        adsk.doEvents()

    # --- 最終配置 ---
    move_body_with_placement(new_body, cx_cm, cy_cm, cz_cm, z_placement, x_placement, y_placement, 'positive')
    
    # --- 開口断面の押し出し処理 ---
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
        new_body.name = get_unique_body_name(root, body_name) #【修正】一意な名前を生成
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
    distance = adsk.core.ValueInput.createByReal(length)
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
        new_body.name = get_unique_body_name(root, body_name) #【修正】一意な名前を生成
    
    return new_body.name

def create_polygon_sweep(cx=0, cy=0, cz=0, path_radius=30, sweep_angle=360,
                        profile_sides=6, profile_radius=10, plane="xy",
                        x_placement="center", y_placement="center", z_placement="center",
                        twist_rotations=0, body_name=None, **kwargs):
    """
    多角形プロファイルを円形パスでスイープします。
    sweep_angleは360のみ指定可能です。
    twist_rotations（回転数）で0回転から10回転まで指定可能です。
    """
    # --- パラメータ検証と前処理 ---
    if sweep_angle != 360:
        raise ValueError(f"スイープ角度(sweep_angle)は360のみ指定可能です。指定された値: {sweep_angle}")

    # 回転数の検証と角度への変換
    if twist_rotations not in [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10]:
        raise ValueError(f"回転数(twist_rotations)は0から10まで指定可能です。指定された値: {twist_rotations}")
    
    twist_angle = twist_rotations * 360
    log_debug(f"回転数 {twist_rotations} を角度 {twist_angle}度 に変換しました")

    if path_radius <= profile_radius:
        raise ValueError(f"パスの半径(path_radius: {path_radius})は、プロファイルの半径(profile_radius: {profile_radius})より大きくする必要があります。スイープ形状が自己交差してしまいます。")

    root = _app.activeProduct.rootComponent
    scale = get_fusion_unit_scale()

    # 入力値をmmからcmに変換
    path_radius_cm = path_radius * scale
    profile_radius_cm = profile_radius * scale
    cx_cm, cy_cm, cz_cm = cx * scale, cy * scale, cz * scale

    log_debug(f"Creating polygon sweep: path_radius={path_radius}mm, profile_radius={profile_radius}mm, twist_rotations={twist_rotations}回転 (twist_angle={twist_angle}度)")

    # --- ジオメトリ作成 ---
    
    # 1. パススケッチを作成 (XZ平面上)
    path_sketch = root.sketches.add(root.xZConstructionPlane)
    center_point = adsk.core.Point3D.create(0, 0, 0)

    # 360度の場合は完全な円を作成
    path_curve = path_sketch.sketchCurves.sketchCircles.addByCenterRadius(center_point, path_radius_cm)

    # 2. XY平面上にプロファイルスケッチを作成 (パスの始点に垂直)
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
    except:
        raise RuntimeError("多角形の閉じたプロファイルの作成に失敗しました。")

    # 3. スイープを実行
    path_obj = adsk.fusion.Path.create(path_curve, adsk.fusion.ChainedCurveOptions.connectedChainedCurves)
    sweeps = root.features.sweepFeatures
    sweep_input = sweeps.createInput(profile, path_obj, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
    
    # --- ねじり角度の設定 ---
    if twist_angle != 0:
        log_debug(f"Setting twist angle: {twist_angle} degrees")
        # ねじり角度をラジアンに変換
        twist_angle_rad = math.radians(twist_angle)
        twist_angle_value = adsk.core.ValueInput.createByReal(twist_angle_rad)
        
        # スイープにねじりオプションを設定
        try:
            sweep_input.twistAngle = twist_angle_value
            log_debug("Twist angle set successfully")
        except Exception as e:
            log_debug(f"Warning: Failed to set twist angle: {e}")
            # ねじり角度の設定に失敗した場合でも、通常のスイープを続行
    
    new_body = sweeps.add(sweep_input).bodies.item(0)
    path_sketch.isVisible = False
    profile_sketch.isVisible = False

    # --- 変換と配置 ---
    
    # 4. ボディを目的の平面に回転
    transform = adsk.core.Matrix3D.create()
    plane_lower = plane.lower()

    if plane_lower == 'xy':
        # XZ平面からXY平面へ -> X軸を中心に-90度回転
        transform.setToRotation(-math.pi / 2, adsk.core.Vector3D.create(1, 0, 0), adsk.core.Point3D.create(0,0,0))
    elif plane_lower == 'yz':
        # XZ平面からYZ平面へ -> Z軸を中心に90度回転
        transform.setToRotation(math.pi / 2, adsk.core.Vector3D.create(0, 0, 1), adsk.core.Point3D.create(0,0,0))

    if plane_lower != 'xz':
        move_features = root.features.moveFeatures
        move_input = move_features.createInput(adsk.core.ObjectCollection.createWithArray([new_body]), transform)
        move_features.add(move_input)
        adsk.doEvents()

    # 5. ボディを最終位置に移動
    move_body_with_placement(new_body, cx_cm, cy_cm, cz_cm, z_placement, x_placement, y_placement, 'positive')

    if body_name:
        new_body.name = get_unique_body_name(root, body_name) #【修正】一意な名前を生成
    
    log_debug(f"Polygon sweep created successfully with {twist_rotations} rotations (twist_angle: {twist_angle} degrees)")
    return new_body.name

def copy_body_symmetric(source_body_name: str, new_body_name: str, plane: str = 'xy', **kwargs):
    source_body = find_entity_by_name(source_body_name)
    if not source_body: raise ValueError(f"ボディ '{source_body_name}' が見つかりません。")
    root = _app.activeProduct.rootComponent
    mirror_features = root.features.mirrorFeatures
    mirror_input = mirror_features.createInput(adsk.core.ObjectCollection.createWithArray([source_body]), get_construction_plane(root, plane))
    mirror_input.pattern_type = 0 # 0 = Body Pattern
    new_body = mirror_features.add(mirror_input).bodies.item(0)
    if new_body_name:
        new_body.name = get_unique_body_name(root, new_body_name) #【修正】一意な名前を生成
    return new_body.name

def create_circular_pattern(source_body_name: str, axis: str = 'z', quantity: int = 4, angle: float = 360.0, new_body_base_name: str = None, **kwargs):
    source_body = find_entity_by_name(source_body_name)
    if not source_body: raise ValueError(f"ボディ '{source_body_name}' が見つかりません。")
    root = _app.activeProduct.rootComponent
    axis_map = {'x': root.xConstructionAxis, 'y': root.yConstructionAxis, 'z': root.zConstructionAxis}
    rotation_axis = axis_map.get(axis.lower())
    if not rotation_axis: raise ValueError(f"無効な軸: {axis}")
    circular_patterns = root.features.circularPatternFeatures
    pattern_input = circular_patterns.createInput(adsk.core.ObjectCollection.createWithArray([source_body]), rotation_axis)
    pattern_input.quantity = adsk.core.ValueInput.createByReal(quantity)
    if angle == 360.0:
        pattern_input.isFull = True
    else:
        pattern_input.isFull = False
        pattern_input.totalAngle = adsk.core.ValueInput.createByString(f"{angle} deg")
    pattern_input.pattern_type = 0 # 0 = Body Pattern

    #【修正】堅牢なロジックに変更
    pattern_feature = circular_patterns.add(pattern_input)
    if new_body_base_name:
        # パターン機能から直接新しいボディを取得（高速・確実）
        newly_created_bodies = pattern_feature.bodies
        for i, body in enumerate(newly_created_bodies):
            # 新しいボディそれぞれに一意な名前を生成して付与
            unique_name = get_unique_body_name(root, f"{new_body_base_name}_{i+1}")
            body.name = unique_name
            
    return f"{quantity}個の円形状パターンを作成しました。"

def create_rectangular_pattern(source_body_name: str, distance_type: str='spacing', quantity_one: int=2, distance_one: float=10.0, direction_one_axis: str='x', quantity_two: int=1, distance_two: float=10.0, direction_two_axis: str='y', new_body_base_name: str=None, **kwargs):
    source_body = find_entity_by_name(source_body_name)
    if not source_body: raise ValueError(f"ボディ '{source_body_name}' が見つかりません。")
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
    pattern_input.pattern_type = 0 # 0 = Body Pattern
    
    #【修正】堅牢なロジックに変更
    pattern_feature = rect_patterns.add(pattern_input)
    if new_body_base_name:
        # パターン機能から直接新しいボディを取得（高速・確実）
        newly_created_bodies = pattern_feature.bodies
        for i, body in enumerate(newly_created_bodies):
            # 新しいボディそれぞれに一意な名前を生成して付与
            unique_name = get_unique_body_name(root, f"{new_body_base_name}_{i+1}")
            body.name = unique_name
            
    return f"{quantity_one}x{quantity_two}の矩形状パターンを作成しました。"
        
def add_fillet(body_name: str, radius: float=1.0, edge_indices: list=None, **kwargs):
    """
    指定されたボディの特定のエッジにフィレットを追加します。
    UIの選択状態に依存せず、引数で直接指定する堅牢な実装です。
    """
    target_body = find_entity_by_name(body_name)
    if not target_body:
        raise ValueError(f"ボディ '{body_name}' が見つかりません。")

    all_edges = target_body.edges
    edges_to_fillet = adsk.core.ObjectCollection.create()

    if edge_indices and isinstance(edge_indices, list) and len(edge_indices) > 0:
        # 特定のエッジインデックスが指定された場合
        log_debug(f"Applying fillet to specified edge indices: {edge_indices}")
        for index in edge_indices:
            try:
                # 入力が数値であることを確認
                idx = int(index)
                if 0 <= idx < all_edges.count:
                    edges_to_fillet.add(all_edges.item(idx))
                else:
                    log_debug(f"警告: 無効なエッジインデックス {idx} は無視されます。")
            except (ValueError, TypeError):
                log_debug(f"警告: 数値でないエッジインデックス '{index}' は無視されます。")
    else:
        # インデックスが指定されない場合は全ての外周エッジを対象にする
        log_debug("エッジが指定されなかったため、全ての外周エッジを対象にします。")
        for edge in all_edges:
            # 2つの面に接しているエッジを外周エッジとみなす
            if len(edge.faces) == 2:
                edges_to_fillet.add(edge)
    
    if edges_to_fillet.count == 0:
        return "フィレット対象のエッジが見つかりません。"

    root = _app.activeProduct.rootComponent
    fillets = root.features.filletFeatures
    fillet_input = fillets.createInput()
    fillet_input.addConstantRadiusEdgeSet(edges_to_fillet, adsk.core.ValueInput.createByReal(radius * get_fusion_unit_scale()), True)
    fillets.add(fillet_input)
    
    return f"{edges_to_fillet.count}個のエッジに半径{radius}mmのフィレットを追加しました。"

def add_chamfer(body_name: str, distance: float=1.0, edge_indices: list=None, **kwargs):
    """
    指定されたボディの特定のエッジに面取りを追加します。
    UIの選択状態に依存せず、引数で直接指定する堅牢な実装です。
    """
    target_body = find_entity_by_name(body_name)
    if not target_body:
        raise ValueError(f"ボディ '{body_name}' が見つかりません。")

    all_edges = target_body.edges
    edges_to_chamfer = adsk.core.ObjectCollection.create()

    if edge_indices and isinstance(edge_indices, list) and len(edge_indices) > 0:
        # 特定のエッジインデックスが指定された場合
        log_debug(f"Applying chamfer to specified edge indices: {edge_indices}")
        for index in edge_indices:
            try:
                # 入力が数値であることを確認
                idx = int(index)
                if 0 <= idx < all_edges.count:
                    edges_to_chamfer.add(all_edges.item(idx))
                else:
                    log_debug(f"警告: 無効なエッジインデックス {idx} は無視されます。")
            except (ValueError, TypeError):
                log_debug(f"警告: 数値でないエッジインデックス '{index}' は無視されます。")
    else:
        # インデックスが指定されない場合は全ての外周エッジを対象にする
        log_debug("エッジが指定されなかったため、全ての外周エッジを対象にします。")
        for edge in all_edges:
            # 2つの面に接しているエッジを外周エッジとみなす
            if len(edge.faces) == 2:
                edges_to_chamfer.add(edge)

    if edges_to_chamfer.count == 0:
        return "面取り対象のエッジが見つかりません。"

    root = _app.activeProduct.rootComponent
    chamfers = root.features.chamferFeatures
    chamfer_input = chamfers.createInput(edges_to_chamfer, True)
    chamfer_input.setToEqualDistance(adsk.core.ValueInput.createByReal(distance * get_fusion_unit_scale()))
    chamfers.add(chamfer_input)

    return f"{edges_to_chamfer.count}個のエッジに{distance}mmの面取りを追加しました。"
    
def combine_selection(operation: str, new_body_name: str=None, **kwargs):
    selections = _ui.activeSelections
    if selections.count < 2: return "結合するには少なくとも2つのボディを選択してください。"
    bodies = [sel.entity for sel in selections if sel.entity.objectType == adsk.fusion.BRepBody.classType()]
    if len(bodies) < 2: return "選択内にボディが2つ以上見つかりません。"
    target_body = bodies[0]
    tool_bodies = adsk.core.ObjectCollection.createWithArray(bodies[1:])
    root = _app.activeProduct.rootComponent
    combine_features = root.features.combineFeatures
    combine_input = combine_features.createInput(target_body, tool_bodies)
    op_map = {'join': adsk.fusion.FeatureOperations.JoinFeatureOperation, 'cut': adsk.fusion.FeatureOperations.CutFeatureOperation, 'intersect': adsk.fusion.FeatureOperations.IntersectFeatureOperation}
    combine_input.operation = op_map.get(operation.lower())
    result_feature = combine_features.add(combine_input)
    if new_body_name and result_feature.bodies.count > 0:
        result_feature.bodies.item(0).name = get_unique_body_name(root, new_body_name)
        return result_feature.bodies.item(0).name
    return f"選択したボディを{operation}操作で結合しました。"

def combine_selection_all(operation: str='join', new_body_name: str=None, **kwargs):
    return combine_selection(operation, new_body_name, **kwargs)

def select_bodies(body_name1: str, body_name2: str, **kwargs):
    _ui.activeSelections.clear()
    body1 = find_entity_by_name(body_name1)
    if body1: _ui.activeSelections.add(body1)
    body2 = find_entity_by_name(body_name2)
    if body2: _ui.activeSelections.add(body2)
    return f"ボディ '{body_name1}' と '{body_name2}' を選択しました。"
        
def combine_by_name(target_body: str, tool_body: str, operation: str, new_body_name: str=None, **kwargs):
    target = find_entity_by_name(target_body)
    tool = find_entity_by_name(tool_body)
    if not target or not tool: raise ValueError(f"ボディ '{target_body}' または '{tool_body}' が見つかりません。")
    root = _app.activeProduct.rootComponent
    combine_features = root.features.combineFeatures
    combine_input = combine_features.createInput(target, adsk.core.ObjectCollection.createWithArray([tool]))
    op_map = {'join': adsk.fusion.FeatureOperations.JoinFeatureOperation, 'cut': adsk.fusion.FeatureOperations.CutFeatureOperation, 'intersect': adsk.fusion.FeatureOperations.IntersectFeatureOperation}
    combine_input.operation = op_map.get(operation.lower())
    result_feature = combine_features.add(combine_input)
    if new_body_name and result_feature.bodies.count > 0:
        result_feature.bodies.item(0).name = get_unique_body_name(root, new_body_name)
        return result_feature.bodies.item(0).name
    return f"ボディを{operation}操作で結合しました。"

def set_body_visibility(body_name: str, is_visible: bool):
    target_body = find_entity_by_name(body_name)
    if target_body:
        target_body.isLightBulbOn = is_visible
        return f"ボディ '{body_name}' の表示を{'On' if is_visible else 'Off'}にしました。"
    else:
        raise ValueError(f"ボディ '{body_name}' が見つかりません。")

def hide_body(body_name: str, **kwargs): return set_body_visibility(body_name, False)
def show_body(body_name: str, **kwargs): return set_body_visibility(body_name, True)

def move_by_name(body_name: str, x_dist: float=0, y_dist: float=0, z_dist: float=0, **kwargs):
    target_entity = find_entity_by_name(body_name)
    if not target_entity: raise ValueError(f"エンティティ '{body_name}' が見つかりません。")
    scale = get_fusion_unit_scale()
    vector = adsk.core.Vector3D.create(x_dist * scale, y_dist * scale, z_dist * scale)
    transform = adsk.core.Matrix3D.create()
    transform.translation = vector
    root = _app.activeProduct.rootComponent
    move_features = root.features.moveFeatures
    move_input = move_features.createInput(adsk.core.ObjectCollection.createWithArray([target_entity]), transform)
    move_features.add(move_input)
    return f"'{body_name}' を移動しました。"

def rotate_by_name(body_name: str, axis: str='z', angle: float=90.0, cx: float=0, cy: float=0, cz: float=0, **kwargs):
    target_entity = find_entity_by_name(body_name)
    if not target_entity: raise ValueError(f"エンティティ '{body_name}' が見つかりません。")
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
    return f"'{body_name}' を回転しました。"

def select_body(body_name: str, **kwargs):
    target_body = find_entity_by_name(body_name)
    if target_body:
        _ui.activeSelections.clear()
        _ui.activeSelections.add(target_body)
        return f"ボディ '{body_name}' を選択しました。"
    else:
        raise ValueError(f"ボディ '{body_name}' が見つかりません。")

def select_all_bodies(**kwargs):
    root = _app.activeProduct.rootComponent
    if root.bRepBodies.count > 0:
        _ui.activeSelections.clear()
        for body in root.bRepBodies: _ui.activeSelections.add(body)
        return f"{root.bRepBodies.count}個のボディをすべて選択しました。"
    return "選択するボディがありません。"

def delete_all_features(**kwargs):
    """
    タイムライン上のすべてのフィーチャーを効率的に削除します。
    """
    try:
        timeline = _app.activeProduct.timeline
        initial_count = timeline.count
        
        if initial_count == 0:
            return "削除するフィーチャーがありません。"
        
        # 選択をクリアして収集
        _ui.activeSelections.clear()
        valid_entities = []
        
        for item in timeline:
            if item.entity and item.entity.isValid:
                _ui.activeSelections.add(item.entity)
                valid_entities.append(item.entity)
        
        selection_count = _ui.activeSelections.count
        
        if selection_count == 0:
            return "削除可能なフィーチャが見つかりませんでした。"
        
        # 選択をクリアしてから削除実行
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
        
        # 結果メッセージ
        if failed_count > 0:
            return f"{deleted_count}個のフィーチャを削除しました。（{failed_count}個は削除できませんでした）"
        else:
            return f"{deleted_count}個のフィーチャを削除しました。"
            
    except Exception as e:
        return f"削除処理中にエラーが発生しました: {str(e)}"
        
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
        info_text += "  Maximum taper angle = arctan((base width - top width) / (2 x height))\n"
        info_text += "  The maximum size of the fillet is wall thickness/2.\n"
        info_text += "  Reviewing 3D CAD modeling considerations.\n"
    else:
            info_text += "  Setting: Z-axis is Up (Z-up)\n"
            info_text += "  - Top      : +Z direction (XY Plane)\n"
            info_text += "  - Bottom   : -Z direction (XY Plane)\n"
            info_text += "  - Front    : -Y direction (XZ Plane)\n"
            info_text += "  - Back     : +Y direction (XZ Plane)\n"
            info_text += "  - Right    : +X direction (YZ Plane)\n"
            info_text += "  - Left     : -X direction (YZ Plane)\n\n"
            info_text += "  Please use this coordinate system for accurate positioning.\n"
            info_text += "  Taper angle calculation formula : Maximum taper angle = arctan((base width - top width) / (2 x height))\n"
            info_text += "  The maximum size of the fillet is wall thickness/2.\n"
            info_text += "  Reviewing 3D CAD modeling considerations.\n"
    camera = _app.activeViewport.camera
    up_vector = camera.upVector
    info_text += f"\n現在のビューポートの上方向ベクトル: ({up_vector.x:.2f}, {up_vector.y:.2f}, {up_vector.z:.2f})\n"
    if show_details:
         info_text += "\n--- 詳細情報 ---\nInput Unit: mm\nInternal Unit: cm\n"
         info_text += "修正内容: direction パラメータの処理を完全修正（Direction対応配置関数適用）\n"
    log_debug("Debug info generated (Direction Complete Fixed version).")
    return info_text       
# ボディ情報取得機能の追加コード
# 既存のfusion_mcp_server.pyに追加する関数群

def get_bounding_box(body_name: str, **kwargs):
    """
    指定したボディのバウンディングボックス情報を取得
    """
    body = find_entity_by_name(body_name)
    if not body:
        raise ValueError(f"ボディ '{body_name}' が見つかりません。")
    
    bbox = body.boundingBox
    scale = get_fusion_unit_scale()
    
    # mmに変換して返す
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
    """
    指定したボディの中心点情報を取得
    """
    body = find_entity_by_name(body_name)
    if not body:
        raise ValueError(f"ボディ '{body_name}' が見つかりません。")
    
    bbox = body.boundingBox
    mass_center = body.physicalProperties.centerOfMass
    scale = get_fusion_unit_scale()
    
    result = {
        "geometric_center": {
            "x": (bbox.minPoint.x + bbox.maxPoint.x) / 2 / scale,
            "y": (bbox.minPoint.y + bbox.maxPoint.y) / 2 / scale,
            "z": (bbox.minPoint.z + bbox.maxPoint.z) / 2 / scale
        },
        "mass_center": {
            "x": mass_center.x / scale,
            "y": mass_center.y / scale,
            "z": mass_center.z / scale
        },
        "bounding_center": {
            "x": (bbox.minPoint.x + bbox.maxPoint.x) / 2 / scale,
            "y": (bbox.minPoint.y + bbox.maxPoint.y) / 2 / scale,
            "z": (bbox.minPoint.z + bbox.maxPoint.z) / 2 / scale
        }
    }
    
    log_debug(f"Centers for '{body_name}': {result}")
    return result

def get_body_dimensions(body_name: str, **kwargs):
    """
    指定したボディの詳細寸法情報を取得
    """
    body = find_entity_by_name(body_name)
    if not body:
        raise ValueError(f"ボディ '{body_name}' が見つかりません。")
    
    bbox = body.boundingBox
    scale = get_fusion_unit_scale()
    
    # 物理プロパティから体積と表面積を取得
    try:
        volume_cm3 = body.physicalProperties.volume
        area_cm2 = body.physicalProperties.area
        volume_mm3 = volume_cm3 * 1000  # cm³ to mm³
        area_mm2 = area_cm2 * 100       # cm² to mm²
    except:
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
    """
    指定したボディの面情報を取得
    """
    body = find_entity_by_name(body_name)
    if not body:
        raise ValueError(f"ボディ '{body_name}' が見つかりません。")
    
    scale = get_fusion_unit_scale()
    faces_info = []
    
    for i, face in enumerate(body.faces):
        try:
            face_data = {
                "id": f"face_{i+1}",
                "area": face.area * 100,  # cm² to mm²
            }
            
            # 面のタイプを判定
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
                "id": f"face_{i+1}",
                "type": "error",
                "error": str(e)
            })
    
    log_debug(f"Found {len(faces_info)} faces for '{body_name}'")
    return faces_info

def get_edges_info(body_name: str, **kwargs):
    """
    指定したボディのエッジ情報を取得
    """
    body = find_entity_by_name(body_name)
    if not body:
        raise ValueError(f"ボディ '{body_name}' が見つかりません。")
    
    scale = get_fusion_unit_scale()
    edges_info = []
    
    for i, edge in enumerate(body.edges):
        try:
            edge_data = {
                "id": f"edge_{i+1}",
                "length": edge.length / scale
            }
            
            # エッジのタイプを判定
            geom = edge.geometry
            
            if not geom:
                edge_data["type"] = "unknown_geometry"
                edges_info.append(edge_data)
                continue # 次のエッジの処理に進む
            
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
                "id": f"edge_{i+1}",
                "type": "error",
                "error": str(e)
            })
    
    log_debug(f"Found {len(edges_info)} edges for '{body_name}'")
    return edges_info

def get_mass_properties(body_name: str, material_density: float = 1.0, **kwargs):
    """
    指定したボディの質量特性を取得
    material_density: 材料密度 (g/cm³)
    """
    body = find_entity_by_name(body_name)
    if not body:
        raise ValueError(f"ボディ '{body_name}' が見つかりません。")
    
    scale = get_fusion_unit_scale()
    props = body.physicalProperties
    
    # 体積をcm³からmm³に変換
    volume_mm3 = props.volume * 1000
    
    # 質量を計算 (密度 g/cm³ × 体積 cm³ = 質量 g)
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
    """
    2つのボディ間の位置関係を取得
    """
    body1 = find_entity_by_name(body_name)
    body2 = find_entity_by_name(other_body_name)
    
    if not body1:
        raise ValueError(f"ボディ '{body_name}' が見つかりません。")
    if not body2:
        raise ValueError(f"ボディ '{other_body_name}' が見つかりません。")
    
    scale = get_fusion_unit_scale()
    
    # 重心間の距離を計算
    center1 = body1.physicalProperties.centerOfMass
    center2 = body2.physicalProperties.centerOfMass
    distance = center1.distanceTo(center2) / scale
    
    # バウンディングボックス情報
    bbox1 = body1.boundingBox
    bbox2 = body2.boundingBox
    
    # 簡易的な干渉チェック（バウンディングボックスベース）
    interference = (
        bbox1.minPoint.x <= bbox2.maxPoint.x and bbox1.maxPoint.x >= bbox2.minPoint.x and
        bbox1.minPoint.y <= bbox2.maxPoint.y and bbox1.maxPoint.y >= bbox2.minPoint.y and
        bbox1.minPoint.z <= bbox2.maxPoint.z and bbox1.maxPoint.z >= bbox2.minPoint.z
    )
    
    # 相対位置の判定
    relative_position = "unknown"
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
    """
    2つのボディ間の最短距離を測定
    """
    body1 = find_entity_by_name(body_name1)
    body2 = find_entity_by_name(body_name2)
    
    if not body1:
        raise ValueError(f"ボディ '{body_name1}' が見つかりません。")
    if not body2:
        raise ValueError(f"ボディ '{body_name2}' が見つかりません。")
    
    scale = get_fusion_unit_scale()
    
    # 重心間距離を計算
    center1 = body1.physicalProperties.centerOfMass
    center2 = body2.physicalProperties.centerOfMass
    center_distance = center1.distanceTo(center2) / scale
    
    # バウンディングボックス間の最短距離を計算
    bbox1 = body1.boundingBox
    bbox2 = body2.boundingBox
    
    # 各軸での最短距離を計算
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

# --- ディスパッチャー ---
COMMAND_MAP = {
    'create_cube': create_cube, 'create_cylinder': create_cylinder, 'create_box': create_box,
    'create_sphere': create_sphere, 'create_hemisphere': create_hemisphere, 'create_cone': create_cone,
    'create_polygon_prism': create_polygon_prism, 'create_torus': create_torus, 'create_half_torus': create_half_torus,
    'create_pipe': create_pipe, 'copy_body_symmetric': copy_body_symmetric, 'create_circular_pattern': create_circular_pattern,
    'create_rectangular_pattern': create_rectangular_pattern, 'add_fillet': add_fillet, 'add_chamfer': add_chamfer,
    'combine_selection': combine_selection, 'select_bodies': select_bodies,
    'combine_by_name': combine_by_name, 'combine_selection_all': combine_selection_all, 'hide_body': hide_body,
    'show_body': show_body, 'move_by_name': move_by_name, 'rotate_by_name': rotate_by_name,
    'select_body': select_body, 'select_all_bodies': select_all_bodies,'delete_all_features': delete_all_features,
    'debug_coordinate_info': debug_coordinate_info,
    'debug_body_placement': debug_body_placement,
    'create_polygon_sweep': create_polygon_sweep,
    'get_bounding_box': get_bounding_box,
    'get_body_center': get_body_center,
    'get_body_dimensions': get_body_dimensions,
    'get_faces_info': get_faces_info,
    'get_edges_info': get_edges_info,
    'get_mass_properties': get_mass_properties,
    'get_body_relationships': get_body_relationships,
    'measure_distance': measure_distance,
    # Fusion:プレフィックス付きバージョン
    'fusion:create_cube': create_cube, 'fusion:create_cylinder': create_cylinder, 'fusion:create_box': create_box,
    'fusion:create_sphere': create_sphere, 'fusion:create_hemisphere': create_hemisphere, 'fusion:create_cone': create_cone,
    'fusion:create_polygon_prism': create_polygon_prism, 'fusion:create_torus': create_torus, 'fusion:create_half_torus': create_half_torus,
    'fusion:create_pipe': create_pipe, 'fusion:copy_body_symmetric': copy_body_symmetric, 'fusion:create_circular_pattern': create_circular_pattern,
    'fusion:create_rectangular_pattern': create_rectangular_pattern, 'fusion:add_fillet': add_fillet, 'fusion:add_chamfer': add_chamfer,
    'fusion:combine_selection': combine_selection, 'fusion:select_bodies': select_bodies,
    'fusion:combine_by_name': combine_by_name, 'fusion:combine_selection_all': combine_selection_all, 'fusion:hide_body': hide_body,
    'fusion:show_body': show_body, 'fusion:move_by_name': move_by_name, 'fusion:rotate_by_name': rotate_by_name,
    'fusion:select_body': select_body, 'fusion:select_all_bodies': select_all_bodies, 'fusion:delete_all_features': delete_all_features, 
    'fusion:debug_coordinate_info': debug_coordinate_info,
    'fusion:debug_body_placement': debug_body_placement,
    'fusion:create_polygon_sweep': create_polygon_sweep,
    'fusion:get_bounding_box': get_bounding_box,
    'fusion:get_body_center': get_body_center,
    'fusion:get_body_dimensions': get_body_dimensions,
    'fusion:get_faces_info': get_faces_info,
    'fusion:get_edges_info': get_edges_info,
    'fusion:get_mass_properties': get_mass_properties,
    'fusion:get_body_relationships': get_body_relationships,
    'fusion:measure_distance': measure_distance,
}

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

# --- イベントハンドラ ---
class CommandReceivedEventHandler(adsk.core.CustomEventHandler):
    def notify(self, args):
        try:
            if os.path.exists(_response_file_path):
                with open(_response_file_path, 'w', encoding='utf-8') as f: f.truncate(0)
            data = json.loads(args.additionalInfo)
            command_name = data.get('command')
            params = data.get('parameters', {})
            if not _app.activeDocument: raise RuntimeError("アクティブなデザイン ドキュメントがありません。")

            if command_name == 'execute_macro':
                for cmd_item in params.get('commands', []):
                    dispatch_command(cmd_item.get('tool_name'), cmd_item.get('arguments', {}))
                
                response = {'status': 'success', 'result': f"Macro with {len(params.get('commands',[]))} steps executed."}
                with open(_response_file_path, 'w', encoding='utf-8') as f: json.dump(response, f, ensure_ascii=False, indent=4)
            else:
                dispatch_command(command_name, params)
        except Exception as e:
            error_response = {'status': 'error', 'message': 'Failed to process command event.', 'traceback': traceback.format_exc()}
            try:
                 with open(_response_file_path, 'w', encoding='utf-8') as f: json.dump(error_response, f, ensure_ascii=False, indent=4)
            except: pass
            log_debug(f'コマンド処理に失敗:\n{traceback.format_exc()}')

# --- UIコマンドハンドラ ---
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

# --- ファイル監視とサーバー制御 ---
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
        if _ui: _ui.messageBox('MCPサーバー連携を開始しました。')
    except Exception as e:
        if _ui: _ui.messageBox(f'サーバーの開始に失敗: {e}')

def stop_server():
    global _is_running, _file_watcher_thread, _stop_flag, _command_received_event, _event_handler
    if not _is_running: return
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
        if _ui: _ui.messageBox('MCPサーバー連携を停止しました。')
    except Exception as e:
        if _ui: _ui.messageBox(f'サーバーの停止に失敗: {e}')

# --- アドインのメインライフサイクル ---
def run(context):
    global _app, _ui, _start_cmd_def, _stop_cmd_def, _mcp_panel, _start_cmd_control, _stop_cmd_control, _handlers
    _app = adsk.core.Application.get()
    _ui  = _app.userInterface
    _handlers = []
    try:
        ws = _ui.workspaces.itemById('FusionSolidEnvironment')
        if not ws:
            if _ui: _ui.messageBox('このアドインは「デザイン」ワークスペースで実行する必要があります。', 'MCPサーバー連携 エラー')
            return
        panel_id = 'MCPServerPanel'
        _mcp_panel = ws.toolbarPanels.itemById(panel_id)
        if _mcp_panel: _mcp_panel.deleteMe()
        _mcp_panel = ws.toolbarPanels.add(panel_id, 'MCPサーバー連携', 'ScriptsManagerPanel', False)
        start_cmd_id = 'StartMCPServerCmd'
        _start_cmd_def = _ui.commandDefinitions.itemById(start_cmd_id)
        if not _start_cmd_def: _start_cmd_def = _ui.commandDefinitions.addButtonDefinition(start_cmd_id, 'START', 'MCPサーバー連携を開始します。')
        stop_cmd_id = 'StopMCPServerCmd'
        _stop_cmd_def = _ui.commandDefinitions.itemById(stop_cmd_id)
        if not _stop_cmd_def: _stop_cmd_def = _ui.commandDefinitions.addButtonDefinition(stop_cmd_id, 'STOP', 'MCPサーバー連携を停止します。')
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
    except:
        if _ui: _ui.messageBox(f'アドインのロード中に予期せぬエラーが発生しました (run):\n{traceback.format_exc()}', 'MCPサーバー連携 エラー')

def stop(context):
    global _ui, _mcp_panel, _start_cmd_def, _stop_cmd_def
    try:
        if _is_running: stop_server()
        if _mcp_panel: _mcp_panel.deleteMe()
        if _start_cmd_def: _start_cmd_def.deleteMe()
        if _stop_cmd_def: _stop_cmd_def.deleteMe()
    except:
        if _ui: _ui.messageBox(f'アドインのアンロード中に予期せぬエラーが発生しました (stop):\n{traceback.format_exc()}', 'MCPサーバー連携 エラー')
        