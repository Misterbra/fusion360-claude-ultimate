# fusion_mcp_server.py - Version FINALE HYBRIDE qui marche !
import adsk.core, adsk.fusion, traceback
import threading
import time
import os
import math

# --- Variables globales ---
_app = None
_ui = None
_command_file_path = None
_file_watcher_thread = None 
_stop_flag = None 
_command_received_event_id = 'FusionMCPCommandReceived'
_command_received_event = None
_event_handler = None 

# --- Fonctions utilitaires ---
def get_construction_plane(root: adsk.fusion.Component, plane_str: str):
    """Retourne le plan de construction approprié"""
    if plane_str and plane_str.lower() == 'yz':
        return root.yZConstructionPlane
    elif plane_str and plane_str.lower() == 'xz':
        return root.xZConstructionPlane
    else: # xy ou défaut
        return root.xYConstructionPlane

# --- Phase 1: Fonctions de création de base ---

def create_cube(size: float, body_name: str = None, plane_str: str = 'xy', cx: float = 0, cy: float = 0, cz: float = 0):
    """Crée un cube avec les paramètres spécifiés"""
    try:
        root = _app.activeProduct.rootComponent
        plane = get_construction_plane(root, plane_str)
        sketch = root.sketches.add(plane)
        
        transform = sketch.transform
        transform.invert()
        
        p1_model = adsk.core.Point3D.create(cx - size / 2, cy - size / 2, cz)
        p2_model = adsk.core.Point3D.create(cx + size / 2, cy + size / 2, cz)
        
        p1_model.transformBy(transform)
        p2_model.transformBy(transform)
        
        sketch.sketchCurves.sketchLines.addTwoPointRectangle(p1_model, p2_model)
        
        prof = sketch.profiles.item(0)
        extrudes = root.features.extrudeFeatures
        extInput = extrudes.createInput(prof, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
        distance = adsk.core.ValueInput.createByReal(size)
        extInput.setDistanceExtent(False, distance)
        
        extrude_feature = extrudes.add(extInput)
        new_body = extrude_feature.bodies.item(0)
        
        if body_name:
            new_body.name = body_name
        
        if _ui: _ui.messageBox(f"Cube '{new_body.name}' créé avec une taille de {size*10}mm")
        
    except:
        if _ui: _ui.messageBox(f"Échec de la création du cube:\n{traceback.format_exc()}")

def create_cylinder(radius: float, height: float, body_name: str = None, plane_str: str = 'xy', cx: float = 0, cy: float = 0, cz: float = 0):
    """Crée un cylindre avec les paramètres spécifiés"""
    try:
        root = _app.activeProduct.rootComponent
        plane = get_construction_plane(root, plane_str)
        sketch = root.sketches.add(plane)
        
        transform = sketch.transform
        transform.invert()
        
        center_point_model = adsk.core.Point3D.create(cx, cy, cz)
        center_point_model.transformBy(transform)
        
        sketch.sketchCurves.sketchCircles.addByCenterRadius(center_point_model, radius)
        
        prof = sketch.profiles.item(0)
        extrudes = root.features.extrudeFeatures
        extInput = extrudes.createInput(prof, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
        distance = adsk.core.ValueInput.createByReal(height)
        extInput.setDistanceExtent(False, distance)
        extrude_feature = extrudes.add(extInput)
        
        new_body = extrude_feature.bodies.item(0)
        
        if body_name:
            new_body.name = body_name
        
        if _ui: _ui.messageBox(f"Cylindre '{new_body.name}' créé (R:{radius*10}mm, H:{height*10}mm)")
        
    except:
        if _ui: _ui.messageBox(f"Échec de la création du cylindre:\n{traceback.format_exc()}")

def create_box(width: float, depth: float, height: float, body_name: str = None, plane_str: str = 'xy', cx: float = 0, cy: float = 0, cz: float = 0):
    """Crée une boîte rectangulaire"""
    try:
        root = _app.activeProduct.rootComponent
        plane = get_construction_plane(root, plane_str)
        sketch = root.sketches.add(plane)
        
        transform = sketch.transform
        transform.invert()
        
        p1_model = adsk.core.Point3D.create(cx - width / 2, cy - depth / 2, cz)
        p2_model = adsk.core.Point3D.create(cx + width / 2, cy + depth / 2, cz)
        
        p1_model.transformBy(transform)
        p2_model.transformBy(transform)
        
        sketch.sketchCurves.sketchLines.addTwoPointRectangle(p1_model, p2_model)
        
        prof = sketch.profiles.item(0)
        extrudes = root.features.extrudeFeatures
        extInput = extrudes.createInput(prof, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
        distance = adsk.core.ValueInput.createByReal(height)
        extInput.setDistanceExtent(False, distance)
        
        extrude_feature = extrudes.add(extInput)
        new_body = extrude_feature.bodies.item(0)
        
        if body_name:
            new_body.name = body_name
        
        if _ui: _ui.messageBox(f"Boîte '{new_body.name}' créée: {width*10}×{depth*10}×{height*10}mm")
        
    except:
        if _ui: _ui.messageBox(f"Échec de la création de la boîte:\n{traceback.format_exc()}")

def create_sphere(radius: float, body_name: str = None, plane_str: str = 'xy', cx: float = 0, cy: float = 0, cz: float = 0):
    """Crée une sphère"""
    try:
        root = _app.activeProduct.rootComponent
        
        tempSketch = root.sketches.add(root.xZConstructionPlane)
        centerPt = adsk.core.Point3D.create(0, 0, 0)
        
        arc = tempSketch.sketchCurves.sketchArcs.addByCenterStartEnd(
            centerPt,
            adsk.core.Point3D.create(0, radius, 0),
            adsk.core.Point3D.create(0, -radius, 0)
        )
        tempSketch.sketchCurves.sketchLines.addByTwoPoints(arc.startSketchPoint, arc.endSketchPoint)
        
        prof = tempSketch.profiles.item(0)
        
        revolves = root.features.revolveFeatures
        revolveInput = revolves.createInput(prof, root.yConstructionAxis, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
        angle = adsk.core.ValueInput.createByReal(math.pi * 2)
        revolveInput.setAngleExtent(False, angle)
        
        revolveFeature = revolves.add(revolveInput)
        new_body = revolveFeature.bodies.item(0)
        
        tempSketch.isVisible = False
        
        if cx != 0 or cy != 0 or cz != 0:
            bodiesToMove = adsk.core.ObjectCollection.create()
            bodiesToMove.add(new_body)
            vector = adsk.core.Vector3D.create(cx, cy, cz)
            transform = adsk.core.Matrix3D.create()
            transform.translation = vector
            
            moveFeats = root.features.moveFeatures
            moveInput = moveFeats.createInput(bodiesToMove, transform)
            moveFeats.add(moveInput)
        
        if body_name:
            new_body.name = body_name
        
        if _ui: _ui.messageBox(f"Sphère '{new_body.name}' créée: R{radius*10}mm")
        
    except:
        if _ui: _ui.messageBox(f"Échec de la création de la sphère:\n{traceback.format_exc()}")

def create_cone(radius: float, height: float, body_name: str = None, plane_str: str = 'xy', cx: float = 0, cy: float = 0, cz: float = 0):
    """Crée un cône"""
    try:
        root = _app.activeProduct.rootComponent
        plane = get_construction_plane(root, plane_str)
        sketch = root.sketches.add(plane)
        
        transform = sketch.transform
        transform.invert()

        p1_model = adsk.core.Point3D.create(cx, cy, cz)
        p2_model = adsk.core.Point3D.create(cx, cy, cz + height)
        p3_model = adsk.core.Point3D.create(cx + radius, cy, cz)
        
        p1_model.transformBy(transform)
        p2_model.transformBy(transform)
        p3_model.transformBy(transform)

        lines = sketch.sketchCurves.sketchLines
        line1 = lines.addByTwoPoints(p1_model, p2_model)
        lines.addByTwoPoints(p2_model, p3_model)
        lines.addByTwoPoints(p3_model, p1_model)

        prof = sketch.profiles.item(0)
        revolves = root.features.revolveFeatures
        revolve_input = revolves.createInput(prof, line1, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
        angle = adsk.core.ValueInput.createByReal(math.pi * 2)
        revolve_input.setAngleExtent(False, angle)

        revolve_feature = revolves.add(revolve_input)
        new_body = revolve_feature.bodies.item(0)

        if body_name:
            new_body.name = body_name

        if _ui: _ui.messageBox(f"Cône '{new_body.name}' créé (R:{radius*10}mm, H:{height*10}mm)")
    except:
        if _ui: _ui.messageBox(f"Échec de la création du cône:\n{traceback.format_exc()}")

def create_sq_pyramid(side_length: float, height: float, body_name: str = None, plane_str: str = 'xy', cx: float = 0, cy: float = 0, cz: float = 0):
    """Crée une pyramide carrée"""
    try:
        root = _app.activeProduct.rootComponent
        plane = get_construction_plane(root, plane_str)
        
        sketch_base = root.sketches.add(plane)
        s = side_length
        
        transform = sketch_base.transform
        transform.invert()
        
        p1_base_model = adsk.core.Point3D.create(cx - s/2, cy - s/2, cz)
        p2_base_model = adsk.core.Point3D.create(cx + s/2, cy + s/2, cz)
        p1_base_model.transformBy(transform)
        p2_base_model.transformBy(transform)
        sketch_base.sketchCurves.sketchLines.addTwoPointRectangle(p1_base_model, p2_base_model)
        prof_base = sketch_base.profiles.item(0)

        planes = root.constructionPlanes
        plane_input = planes.createInput()
        plane_input.setByOffset(plane, adsk.core.ValueInput.createByReal(height))
        plane_top = planes.add(plane_input)
        sketch_top = root.sketches.add(plane_top)

        top_point_model = adsk.core.Point3D.create(cx, cy, cz)
        top_point_model.transformBy(transform)
        top_point = sketch_top.sketchPoints.add(top_point_model)

        lofts = root.features.loftFeatures
        loft_input = lofts.createInput(adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
        loft_input.loftSections.add(prof_base)
        loft_input.loftSections.add(top_point)
        
        loft_feature = lofts.add(loft_input)
        new_body = loft_feature.bodies.item(0)

        if body_name:
            new_body.name = body_name

        if _ui: _ui.messageBox(f"Pyramide carrée '{new_body.name}' créée (base:{s*10}mm, hauteur:{height*10}mm)")
    except:
        if _ui: _ui.messageBox(f"Échec de la création de la pyramide carrée:\n{traceback.format_exc()}")

def create_tri_pyramid(side_length: float, height: float, body_name: str = None, plane_str: str = 'xy', cx: float = 0, cy: float = 0, cz: float = 0):
    """Crée une pyramide triangulaire"""
    try:
        root = _app.activeProduct.rootComponent
        plane = get_construction_plane(root, plane_str)
        
        sketch_base = root.sketches.add(plane)
        
        transform = sketch_base.transform
        transform.invert()
        
        s = side_length
        h_tri = s * math.sqrt(3) / 2
        
        p1_model = adsk.core.Point3D.create(cx - s/2, cy - h_tri/3, cz)
        p2_model = adsk.core.Point3D.create(cx + s/2, cy - h_tri/3, cz)
        p3_model = adsk.core.Point3D.create(cx, cy + h_tri*2/3, cz)
        
        p1_model.transformBy(transform)
        p2_model.transformBy(transform)
        p3_model.transformBy(transform)

        lines = sketch_base.sketchCurves.sketchLines
        lines.addByTwoPoints(p1_model, p2_model)
        lines.addByTwoPoints(p2_model, p3_model)
        lines.addByTwoPoints(p3_model, p1_model)
        prof_base = sketch_base.profiles.item(0)

        planes = root.constructionPlanes
        plane_input = planes.createInput()
        plane_input.setByOffset(plane, adsk.core.ValueInput.createByReal(height))
        plane_top = planes.add(plane_input)
        sketch_top = root.sketches.add(plane_top)
        
        top_point_model = adsk.core.Point3D.create(cx, cy, cz)
        top_point_model.transformBy(transform)
        top_point = sketch_top.sketchPoints.add(top_point_model)

        lofts = root.features.loftFeatures
        loft_input = lofts.createInput(adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
        loft_input.loftSections.add(prof_base)
        loft_input.loftSections.add(top_point)
        
        loft_feature = lofts.add(loft_input)
        new_body = loft_feature.bodies.item(0)

        if body_name:
            new_body.name = body_name

        if _ui: _ui.messageBox(f"Pyramide triangulaire '{new_body.name}' créée (base:{s*10}mm, hauteur:{height*10}mm)")
    except:
        if _ui: _ui.messageBox(f"Échec de la création de la pyramide triangulaire:\n{traceback.format_exc()}")

# --- Phase 2: Fonctions de manipulation ---

def move_selection(x_dist: float, y_dist: float, z_dist: float):
    """Déplace les objets sélectionnés"""
    try:
        selections = _ui.activeSelections
        if selections.count == 0:
            _ui.messageBox("Aucun objet sélectionné pour déplacement.")
            return

        bodies_to_move = adsk.core.ObjectCollection.create()
        for selection in selections:
            if selection.entity.objectType == adsk.fusion.BRepBody.classType():
                bodies_to_move.add(selection.entity)
        
        if bodies_to_move.count == 0:
            _ui.messageBox("Aucun corps sélectionné pour déplacement.")
            return

        vector = adsk.core.Vector3D.create(x_dist, y_dist, z_dist)
        transform = adsk.core.Matrix3D.create()
        transform.translation = vector

        root = _app.activeProduct.rootComponent
        move_features = root.features.moveFeatures
        
        move_input = move_features.createInput(bodies_to_move, transform)
        move_features.add(move_input)

        if _ui: _ui.messageBox(f"{bodies_to_move.count} objet(s) déplacé(s) de ({x_dist*10}, {y_dist*10}, {z_dist*10}) mm")

    except:
        if _ui: _ui.messageBox(f"Échec du déplacement:\n{traceback.format_exc()}")

def combine_selection(operation: str):
    """Combine deux objets sélectionnés"""
    try:
        selections = _ui.activeSelections
        if selections.count != 2:
            _ui.messageBox("Sélectionnez exactement 2 objets pour la combinaison.")
            return

        body1 = selections.item(0).entity
        body2 = selections.item(1).entity
        if not (body1.objectType == adsk.fusion.BRepBody.classType() and body2.objectType == adsk.fusion.BRepBody.classType()):
            _ui.messageBox("Les deux éléments sélectionnés doivent être des corps.")
            return

        target_body = body1
        tool_body = body2
        
        tool_bodies_collection = adsk.core.ObjectCollection.create()
        tool_bodies_collection.add(tool_body)

        root = _app.activeProduct.rootComponent
        combine_features = root.features.combineFeatures
        combine_input = combine_features.createInput(target_body, tool_bodies_collection)

        op_map = {
            'join': adsk.fusion.FeatureOperations.JoinFeatureOperation,
            'cut': adsk.fusion.FeatureOperations.CutFeatureOperation,
            'intersect': adsk.fusion.FeatureOperations.IntersectFeatureOperation
        }
        
        op_str = operation.lower()
        if op_str not in op_map:
            _ui.messageBox(f"Opération invalide: '{operation}'. Utilisez: join, cut, ou intersect")
            return
            
        combine_input.operation = op_map[op_str]
        
        combine_features.add(combine_input)
        if _ui: _ui.messageBox(f"Combinaison '{op_str}' effectuée entre '{target_body.name}' et '{tool_body.name}'")

    except:
        if _ui: _ui.messageBox(f"Échec de la combinaison:\n{traceback.format_exc()}")

def combine_by_name(target_body_name: str, tool_body_name: str, operation: str):
    """Combine deux objets par leur nom"""
    try:
        root = _app.activeProduct.rootComponent
        
        target_body = None
        tool_body = None
        for body in root.bRepBodies:
            if body.name == target_body_name:
                target_body = body
            elif body.name == tool_body_name:
                tool_body = body
        
        if not target_body:
            _ui.messageBox(f"Objet cible '{target_body_name}' introuvable.")
            return
        if not tool_body:
            _ui.messageBox(f"Objet outil '{tool_body_name}' introuvable.")
            return

        tool_bodies_collection = adsk.core.ObjectCollection.create()
        tool_bodies_collection.add(tool_body)

        combine_features = root.features.combineFeatures
        combine_input = combine_features.createInput(target_body, tool_bodies_collection)

        op_map = {
            'join': adsk.fusion.FeatureOperations.JoinFeatureOperation,
            'cut': adsk.fusion.FeatureOperations.CutFeatureOperation,
            'intersect': adsk.fusion.FeatureOperations.IntersectFeatureOperation
        }
        
        op_str = operation.lower()
        if op_str not in op_map:
            _ui.messageBox(f"Opération invalide: '{op_str}'. Utilisez: join, cut, ou intersect")
            return
            
        combine_input.operation = op_map[op_str]
        
        combine_features.add(combine_input)
        if _ui: _ui.messageBox(f"Combinaison '{op_str}' effectuée: '{target_body_name}' avec '{tool_body_name}'")

    except:
        if _ui: _ui.messageBox(f"Échec de la combinaison par nom:\n{traceback.format_exc()}")

def rotate_selection(axis_str: str, angle_degrees: float, cx: float, cy: float, cz: float):
    """Fait tourner l'objet sélectionné"""
    try:
        selections = _ui.activeSelections
        if selections.count != 1:
            _ui.messageBox("Sélectionnez exactement 1 objet pour la rotation.")
            return
        
        target_body = selections.item(0).entity
        if target_body.objectType != adsk.fusion.BRepBody.classType():
            _ui.messageBox("L'élément sélectionné doit être un corps.")
            return
        
        bodies_to_move = adsk.core.ObjectCollection.create()
        bodies_to_move.add(target_body)
        
        axis_str = axis_str.lower()
        if axis_str == 'x':
            axis_vector = adsk.core.Vector3D.create(1, 0, 0)
        elif axis_str == 'y':
            axis_vector = adsk.core.Vector3D.create(0, 1, 0)
        elif axis_str == 'z':
            axis_vector = adsk.core.Vector3D.create(0, 0, 1)
        else:
            _ui.messageBox(f"Axe invalide: '{axis_str}'. Utilisez: x, y, ou z")
            return
        
        center_point = adsk.core.Point3D.create(cx, cy, cz)
        
        angle_rad = math.radians(angle_degrees)
        
        transform = adsk.core.Matrix3D.create()
        transform.setToRotation(angle_rad, axis_vector, center_point)
        
        root = _app.activeProduct.rootComponent
        move_features = root.features.moveFeatures
        move_input = move_features.createInput(bodies_to_move, transform)
        move_features.add(move_input)
        
        if _ui: _ui.messageBox(f"Objet '{target_body.name}' tourné de {angle_degrees}° autour de l'axe {axis_str.upper()}")
        
    except:
        if _ui: _ui.messageBox(f"Échec de la rotation:\n{traceback.format_exc()}")

# --- Phase 3: Fonctions de sélection ---

def select_body(body_name: str):
    """Sélectionne un objet par son nom"""
    try:
        root = _app.activeProduct.rootComponent
        target_body = None
        for body in root.bRepBodies:
            if body.name == body_name:
                target_body = body
                break
        
        if not target_body:
            _ui.messageBox(f"Objet '{body_name}' introuvable.")
            return

        _ui.activeSelections.clear()
        _ui.activeSelections.add(target_body)
        if _ui: _ui.messageBox(f"Objet '{body_name}' sélectionné.")
    except:
        if _ui: _ui.messageBox(f"Échec de la sélection:\n{traceback.format_exc()}")

def select_bodies(body_name1: str, body_name2: str):
    """Sélectionne deux objets par leur nom"""
    try:
        root = _app.activeProduct.rootComponent
        body1 = None
        body2 = None
        for body in root.bRepBodies:
            if body.name == body_name1:
                body1 = body
            elif body.name == body_name2:
                body2 = body

        if not body1:
            _ui.messageBox(f"Objet '{body_name1}' introuvable.")
            return
        if not body2:
            _ui.messageBox(f"Objet '{body_name2}' introuvable.")
            return

        _ui.activeSelections.clear()
        _ui.activeSelections.add(body1)
        _ui.activeSelections.add(body2)

        if _ui: _ui.messageBox(f"Objets '{body_name1}' et '{body_name2}' sélectionnés.")
    except:
        if _ui: _ui.messageBox(f"Échec de la sélection multiple:\n{traceback.format_exc()}")

def select_edges(body_name: str, edge_type: str):
    """Sélectionne les arêtes d'un objet"""
    try:
        root = _app.activeProduct.rootComponent
        target_body = None
        for body in root.bRepBodies:
            if body.name == body_name:
                target_body = body
                break
        
        if not target_body:
            _ui.messageBox(f"Objet '{body_name}' introuvable.")
            return

        _ui.activeSelections.clear()

        selected_count = 0
        for edge in target_body.edges:
            if edge_type == 'all':
                _ui.activeSelections.add(edge)
                selected_count += 1
            elif edge_type == 'circular' and edge.geometry.curveType == adsk.core.Curve3DTypes.Circle3DCurveType:
                _ui.activeSelections.add(edge)
                selected_count += 1
        
        if selected_count > 0:
            if _ui: _ui.messageBox(f"{selected_count} arête(s) de type '{edge_type}' sélectionnée(s) sur '{body_name}'")
        else:
            if _ui: _ui.messageBox(f"Aucune arête de type '{edge_type}' trouvée sur '{body_name}'")

    except:
        if _ui: _ui.messageBox(f"Échec de la sélection d'arêtes:\n{traceback.format_exc()}")

def add_fillet(radius: float):
    """Ajoute un congé aux arêtes sélectionnées"""
    try:
        selections = _ui.activeSelections
        if selections.count == 0:
            _ui.messageBox("Sélectionnez des arêtes pour appliquer le congé.")
            return

        edges_to_fillet = adsk.core.ObjectCollection.create()
        for i in range(selections.count):
            selection = selections.item(i)
            entity = selection.entity
            if entity.objectType == adsk.fusion.BRepEdge.classType():
                edges_to_fillet.add(entity)

        if edges_to_fillet.count == 0:
            _ui.messageBox("Aucune arête sélectionnée.")
            return

        root = _app.activeProduct.rootComponent
        fillets = root.features.filletFeatures
        fillet_input = fillets.createInput()
        
        fillet_radius = adsk.core.ValueInput.createByReal(radius)
        fillet_input.addConstantRadiusEdgeSet(edges_to_fillet, fillet_radius, True)
        
        fillets.add(fillet_input)
        if _ui: _ui.messageBox(f"Congé de R{radius*10}mm appliqué à {edges_to_fillet.count} arête(s)")
    except:
        if _ui: _ui.messageBox(f"Échec de l'application du congé:\n{traceback.format_exc()}")

def undo():
    """Annule la dernière opération"""
    try:
        cmd_def = _ui.commandDefinitions.itemById('UndoCommand')
        if cmd_def:
            cmd_def.execute()
            if _ui: _ui.messageBox("Opération annulée")
        else:
            _ui.messageBox("Commande d'annulation introuvable")
    except:
        if _ui: _ui.messageBox(f"Échec de l'annulation:\n{traceback.format_exc()}")

def redo():
    """Refait la dernière opération annulée"""
    try:
        cmd_def = _ui.commandDefinitions.itemById('RedoCommand')
        if cmd_def:
            cmd_def.execute()
            if _ui: _ui.messageBox("Opération refaite")
        else:
            _ui.messageBox("Commande de rétablissement introuvable")
    except:
        if _ui: _ui.messageBox(f"Échec du rétablissement:\n{traceback.format_exc()}")

# --- Gestionnaire d'événements HYBRIDE ---
class CommandReceivedEventHandler(adsk.core.CustomEventHandler):
    """Gestionnaire hybride avec toutes les commandes qui marchent"""
    def __init__(self):
        super().__init__()
    
    def notify(self, args):
        try:
            command = args.additionalInfo.strip()
            if not command:
                return
            
            # Log sécurisé sans palette
            print(f"🔧 Commande reçue: {command}")

            parts = command.split()
            command_name = parts[0].lower()
            
            # Phase 1: Création de base
            if command_name == 'create_cube':
                size = float(parts[1]) / 10.0 if len(parts) > 1 else 1.0
                body_name = parts[2] if len(parts) > 2 and parts[2].lower() not in ['xy','yz','xz','none','null'] else None
                plane_str = parts[3] if len(parts) > 3 else 'xy'
                cx = float(parts[4]) / 10.0 if len(parts) > 4 else 0
                cy = float(parts[5]) / 10.0 if len(parts) > 5 else 0
                cz = float(parts[6]) / 10.0 if len(parts) > 6 else 0
                create_cube(size, body_name, plane_str, cx, cy, cz)
                
            elif command_name == 'create_cylinder':
                radius = float(parts[1]) / 10.0 if len(parts) > 1 else 0.5
                height = float(parts[2]) / 10.0 if len(parts) > 2 else 1.0
                body_name = parts[3] if len(parts) > 3 and parts[3].lower() not in ['xy','yz','xz','none','null'] else None
                plane_str = parts[4] if len(parts) > 4 else 'xy'
                cx = float(parts[5]) / 10.0 if len(parts) > 5 else 0
                cy = float(parts[6]) / 10.0 if len(parts) > 6 else 0
                cz = float(parts[7]) / 10.0 if len(parts) > 7 else 0
                create_cylinder(radius, height, body_name, plane_str, cx, cy, cz)
                
            elif command_name == 'create_box':
                width = float(parts[1]) / 10.0 if len(parts) > 1 else 1.0
                depth = float(parts[2]) / 10.0 if len(parts) > 2 else 1.0
                height = float(parts[3]) / 10.0 if len(parts) > 3 else 1.0
                body_name = parts[4] if len(parts) > 4 and parts[4].lower() not in ['xy','yz','xz','none','null'] else None
                plane_str = parts[5] if len(parts) > 5 else 'xy'
                cx = float(parts[6]) / 10.0 if len(parts) > 6 else 0
                cy = float(parts[7]) / 10.0 if len(parts) > 7 else 0
                cz = float(parts[8]) / 10.0 if len(parts) > 8 else 0
                create_box(width, depth, height, body_name, plane_str, cx, cy, cz)
                
            elif command_name == 'create_sphere':
                radius = float(parts[1]) / 10.0 if len(parts) > 1 else 0.5
                body_name = parts[2] if len(parts) > 2 and parts[2].lower() not in ['xy','yz','xz','none','null'] else None
                plane_str = parts[3] if len(parts) > 3 else 'xy'
                cx = float(parts[4]) / 10.0 if len(parts) > 4 else 0
                cy = float(parts[5]) / 10.0 if len(parts) > 5 else 0
                cz = float(parts[6]) / 10.0 if len(parts) > 6 else 0
                create_sphere(radius, body_name, plane_str, cx, cy, cz)
                
            elif command_name == 'create_cone':
                radius = float(parts[1]) / 10.0 if len(parts) > 1 else 0.5
                height = float(parts[2]) / 10.0 if len(parts) > 2 else 1.0
                body_name = parts[3] if len(parts) > 3 and parts[3].lower() not in ['xy','yz','xz','none','null'] else None
                plane_str = parts[4] if len(parts) > 4 else 'xy'
                cx = float(parts[5]) / 10.0 if len(parts) > 5 else 0
                cy = float(parts[6]) / 10.0 if len(parts) > 6 else 0
                cz = float(parts[7]) / 10.0 if len(parts) > 7 else 0
                create_cone(radius, height, body_name, plane_str, cx, cy, cz)
                
            elif command_name == 'create_sq_pyramid':
                side = float(parts[1]) / 10.0 if len(parts) > 1 else 1.0
                height = float(parts[2]) / 10.0 if len(parts) > 2 else 1.0
                body_name = parts[3] if len(parts) > 3 and parts[3].lower() not in ['xy','yz','xz','none','null'] else None
                plane_str = parts[4] if len(parts) > 4 else 'xy'
                cx = float(parts[5]) / 10.0 if len(parts) > 5 else 0
                cy = float(parts[6]) / 10.0 if len(parts) > 6 else 0
                cz = float(parts[7]) / 10.0 if len(parts) > 7 else 0
                create_sq_pyramid(side, height, body_name, plane_str, cx, cy, cz)
                
            elif command_name == 'create_tri_pyramid':
                side = float(parts[1]) / 10.0 if len(parts) > 1 else 1.0
                height = float(parts[2]) / 10.0 if len(parts) > 2 else 1.0
                body_name = parts[3] if len(parts) > 3 and parts[3].lower() not in ['xy','yz','xz','none','null'] else None
                plane_str = parts[4] if len(parts) > 4 else 'xy'
                cx = float(parts[5]) / 10.0 if len(parts) > 5 else 0
                cy = float(parts[6]) / 10.0 if len(parts) > 6 else 0
                cz = float(parts[7]) / 10.0 if len(parts) > 7 else 0
                create_tri_pyramid(side, height, body_name, plane_str, cx, cy, cz)
                
            # Phase 2: Manipulation
            elif command_name == 'move_selection':
                x = float(parts[1]) / 10.0 if len(parts) > 1 else 0
                y = float(parts[2]) / 10.0 if len(parts) > 2 else 0
                z = float(parts[3]) / 10.0 if len(parts) > 3 else 0
                move_selection(x, y, z)
                
            elif command_name == 'combine_selection':
                operation = parts[1] if len(parts) > 1 else 'join'
                combine_selection(operation)
                
            elif command_name == 'combine_by_name':
                target_body_name = parts[1] if len(parts) > 1 else ''
                tool_body_name = parts[2] if len(parts) > 2 else ''
                operation = parts[3] if len(parts) > 3 else 'join'
                combine_by_name(target_body_name, tool_body_name, operation)
                
            elif command_name == 'rotate_selection':
                axis = parts[1] if len(parts) > 1 else 'z'
                angle = float(parts[2]) if len(parts) > 2 else 90
                cx = float(parts[3]) / 10.0 if len(parts) > 3 else 0
                cy = float(parts[4]) / 10.0 if len(parts) > 4 else 0
                cz = float(parts[5]) / 10.0 if len(parts) > 5 else 0
                rotate_selection(axis, angle, cx, cy, cz)
                
            # Phase 3: Sélection et édition
            elif command_name == 'select_body':
                body_name = parts[1] if len(parts) > 1 else ''
                select_body(body_name)
                
            elif command_name == 'select_bodies':
                body_name1 = parts[1] if len(parts) > 1 else ''
                body_name2 = parts[2] if len(parts) > 2 else ''
                select_bodies(body_name1, body_name2)
                
            elif command_name == 'select_edges':
                body_name = parts[1] if len(parts) > 1 else ''
                edge_type = parts[2] if len(parts) > 2 else 'all'
                select_edges(body_name, edge_type)
                
            elif command_name == 'add_fillet':
                radius = float(parts[1]) / 10.0 if len(parts) > 1 else 0.5
                add_fillet(radius)
                
            elif command_name == 'undo':
                undo()
                
            elif command_name == 'redo':
                redo()

            else:
                if _ui: _ui.messageBox(f"Commande inconnue: '{command_name}'\nCommandes disponibles: create_cube, create_cylinder, create_box, create_sphere, create_cone, create_sq_pyramid, create_tri_pyramid, move_selection, combine_selection, combine_by_name, rotate_selection, select_body, select_bodies, select_edges, add_fillet, undo, redo")

        except Exception as e:
            print(f"❌ Erreur traitement commande: {str(e)}")
            if _ui: _ui.messageBox(f"Erreur lors du traitement de la commande:\n{str(e)}\n\nCommande: {command}")

# --- Surveillance de fichier ---
def file_watcher(stop_flag):
    """Surveille le fichier de commandes en continu"""
    last_modified = 0
    while not stop_flag.is_set():
        try:
            if os.path.exists(_command_file_path):
                modified = os.path.getmtime(_command_file_path)
                if modified > last_modified:
                    last_modified = modified
                    with open(_command_file_path, 'r+', encoding='utf-8') as f:
                        command = f.read().strip()
                        if command:
                            _app.fireCustomEvent(_command_received_event_id, command)
                            f.seek(0)
                            f.truncate()
        except:
            pass 
        time.sleep(0.5)

# --- Cycle de vie de l'add-in ---
def run(context):
    """Démarrage de l'add-in HYBRIDE qui marche !"""
    global _app, _ui, _command_file_path, _file_watcher_thread, _stop_flag, _command_received_event, _event_handler
    
    print("🚀 Démarrage add-in HYBRIDE...")
    
    _app = adsk.core.Application.get()
    _ui = _app.userInterface
    
    try:
        print("✅ Application et UI récupérés")
        
        _command_file_path = os.path.join(os.path.expanduser('~'), 'Documents', 'fusion_command.txt')
        print(f"✅ Chemin fichier: {_command_file_path}")
        
        _command_received_event = _app.registerCustomEvent(_command_received_event_id)
        print("✅ Event enregistré")
        
        _event_handler = CommandReceivedEventHandler()
        _command_received_event.add(_event_handler)
        print("✅ Handler ajouté")
        
        _stop_flag = threading.Event()
        _file_watcher_thread = threading.Thread(target=file_watcher, args=(_stop_flag,))
        _file_watcher_thread.daemon = True
        _file_watcher_thread.start()
        print("✅ Thread de surveillance démarré")

        if _ui: 
            _ui.messageBox("🎉 FUSION 360 MCP SERVER HYBRIDE DÉMARRÉ !\n✅ Toutes les commandes disponibles\n🚀 Prêt pour Claude Desktop !")
        
        print("🎉 Add-in HYBRIDE démarré avec succès !")
        
    except Exception as e:
        print(f"❌ ERREUR démarrage: {str(e)}")
        print(f"❌ TRACEBACK: {traceback.format_exc()}")
        if _ui: _ui.messageBox(f"Erreur au démarrage de l'add-in:\n{traceback.format_exc()}")

def stop(context):
    """Arrêt de l'add-in HYBRIDE"""
    global _stop_flag, _command_received_event, _event_handler
    
    try:
        print("🛑 Arrêt add-in HYBRIDE...")
        
        if _stop_flag:
            _stop_flag.set()
        
        if _command_received_event and _event_handler:
            _command_received_event.remove(_event_handler)
        
        print("✅ Add-in HYBRIDE arrêté proprement")
        
        if _ui: 
            _ui.messageBox("🛑 Fusion 360 MCP Server HYBRIDE arrêté.")
            
    except Exception as e:
        print(f"❌ Erreur arrêt: {str(e)}")
        if _ui: 
            _ui.messageBox(f"Erreur arrêt add-in: {str(e)}")