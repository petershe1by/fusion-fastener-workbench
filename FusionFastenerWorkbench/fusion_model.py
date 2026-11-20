"""Create local Fusion solids and place instances in the root assembly."""

import json
from dataclasses import dataclass
from math import cos, pi, sin

import adsk.core as core
import adsk.fusion as fusion

from . import catalog


SIMPLIFIED = "简化（批量装配）"
COSMETIC = "Fusion 外观螺纹"
MODELED = "Fusion 实体螺纹"
EPS = 0.02  # mm overlap for joining pieces and extending cutting tools


def point(x, y, z):
    return core.Point3D.create(x / 10, y / 10, z / 10)


def vector(x, y, z):
    return core.Vector3D.create(x, y, z)


@dataclass(frozen=True)
class Thread:
    size: float
    diameter: float
    lower: float
    upper: float
    internal: bool = False


class SolidBuilder:
    def __init__(self):
        self.manager = fusion.TemporaryBRepManager.get()

    def axial(self, lower, upper, diameter, top_diameter=None):
        if top_diameter is None:
            top_diameter = diameter
        body = self.manager.createCylinderOrCone(
            point(0, 0, lower), diameter / 20, point(0, 0, upper), top_diameter / 20,
        )
        if not body:
            raise RuntimeError("无法创建圆柱或圆锥。")
        return body

    def box(self, lower, upper, length, width, angle=0, x=0, y=0):
        box = core.OrientedBoundingBox3D.create(
            point(x, y, (lower + upper) / 2),
            vector(cos(angle), sin(angle), 0), vector(-sin(angle), cos(angle), 0),
            length / 10, width / 10, (upper - lower) / 10,
        )
        body = self.manager.createBox(box)
        if not body:
            raise RuntimeError("无法创建长方体。")
        return body

    def boolean(self, target, tool, operation):
        if not tool or not self.manager.booleanOperation(target, tool, operation):
            raise RuntimeError("紧固件实体布尔运算失败。")
        return target

    def join(self, target, tool):
        return self.boolean(target, tool, fusion.BooleanTypes.UnionBooleanType)

    def cut(self, target, tool):
        return self.boolean(target, tool, fusion.BooleanTypes.DifferenceBooleanType)

    def intersect(self, target, tool):
        return self.boolean(target, tool, fusion.BooleanTypes.IntersectionBooleanType)

    def hexagon(self, lower, upper, flats, chamfer=False):
        body = self.box(lower, upper, 2 * flats, flats)
        for angle in (pi / 3, 2 * pi / 3):
            self.intersect(body, self.box(lower - EPS, upper + EPS, 2 * flats, flats, angle))
        if chamfer:
            height = min((upper - lower) * 0.28, flats * 0.12)
            self._hex_chamfer(body, lower, upper, flats * 0.99, height)
        return body

    def _hex_chamfer(self, body, lower, upper, diameter, height):
        wide = diameter * 1.18
        tool = self.axial(lower - EPS, upper - height + EPS, wide)
        self.join(tool, self.axial(upper - height, upper + EPS, wide, diameter - EPS))
        self.intersect(body, tool)

    def dome(self, lower, upper, diameter):
        radius = diameter / 2
        height = upper - lower
        sphere_radius = (radius * radius + height * height) / (2 * height)
        sphere = self.manager.createSphere(point(0, 0, upper - sphere_radius), sphere_radius / 10)
        return self.intersect(
            self.axial(lower, upper + EPS, diameter + 2 * EPS), sphere,
        )

    def socket(self, body, style, key, top, depth):
        lower = top - depth
        if style == "hex":
            self.cut(body, self.hexagon(lower, top + EPS, key))
        elif style == "cross":
            for angle in (0, pi / 2):
                self.cut(body, self.box(lower, top + EPS, key, key * 0.24, angle))

    def screw(self, part):
        family = part.family
        size = part.size
        d = part.dimensions
        length = d["length"]
        if part.kind == "shoulder":
            threaded = d["thread_length"]
            body = self.axial(-length - threaded, -length + EPS, size)
            self.join(body, self.axial(-length, EPS, d["diameter"]))
            thread = Thread(size, size, -length - threaded, -length)
        elif family.head == "countersunk":
            _, height, _ = part.head
            body = self.axial(-length, -height + EPS, size)
            thread = Thread(size, size, -length, -height)
        elif part.kind == "hex_partial":
            threaded = catalog.bolt_thread_length(size, length)
            if threaded < length:
                # Separate the thread face from the cylindrical grip.
                crest = size - 0.07 * catalog.PITCH[size]
                body = self.axial(-length, -length + threaded + EPS, crest)
                self.join(body, self.axial(-length + threaded, EPS, size))
                thread = Thread(size, crest, -length, -length + threaded)
            else:
                body = self.axial(-length, EPS, size)
                thread = Thread(size, size, -length, 0)
        else:
            body = self.axial(-length, EPS if family.head else 0, size)
            thread = Thread(size, size, -length, 0)

        if family.head:
            width, height, key = part.head
            if family.head == "countersunk":
                head = self.axial(-height, 0, max(size, width - 2 * height), width)
                top = 0
            else:
                top = height
                if family.head == "dome":
                    head = self.dome(0, height, width)
                elif family.head == "hex":
                    head = self.hexagon(0, height, width, chamfer=True)
                else:
                    head = self.axial(0, height, width)
            self.join(body, head)
            self.socket(body, family.drive, key, top, height * 0.67)
        else:
            self.socket(body, family.drive, catalog.SET_KEY[size], 0, min(length * 0.48, size * 0.65))
            if part.kind == "set_cup":
                self.cut(body, self.axial(-length - EPS, -length + size * 0.19, size * 0.7, size * 0.16))
        return [("螺丝", body)], [thread]

    def nut(self, part):
        kind, size = part.kind, part.size
        flats, height, *extras = catalog.TABLES[kind][size]
        bore = catalog.tap_diameter(size)
        bodies = []
        if kind == "acorn":
            steel_top = height * 0.53
            body = self.hexagon(0, steel_top + EPS, flats, chamfer=False)
            self.join(body, self.dome(steel_top, height, flats))
            bore_top = steel_top + (height - steel_top) * 0.39
        elif kind == "nylon":
            steel_top = height * 0.77
            body = self.hexagon(0, steel_top, flats, chamfer=True)
            ring = self.axial(steel_top, height, flats * 0.94, flats * 0.85)
            self.cut(ring, self.axial(steel_top - EPS, height + EPS, bore))
            bodies.append(("尼龙防松圈", ring))
            bore_top = steel_top
        elif kind == "flange":
            body = self.hexagon(0, height, flats, chamfer=True)
            self.join(body, self.axial(0, height * 0.27, extras[0], flats * 0.93))
            bore_top = height
        else:
            body = self.hexagon(0, height, flats, chamfer=True)
            bore_top = height
        self.cut(body, self.axial(-EPS, bore_top + (0 if kind == "acorn" else EPS), bore))
        return [("螺母本体", body), *bodies], [Thread(size, bore, 0, bore_top, True)]

    def spacer(self, part):
        d = part.dimensions
        length = d["length"]
        outer = d["outer"]
        size = part.size
        bore = catalog.tap_diameter(size) if size else d["inner"]
        if part.kind.startswith("hex"):
            body = self.hexagon(0, length, outer)
        else:
            body = self.axial(0, length, outer)
        if part.kind == "hex_male":
            male = d["thread_length"]
            bore_bottom = length - min(length * 0.78, 2 * size)
            self.join(body, self.axial(-male, EPS, size))
            self.cut(body, self.axial(bore_bottom, length + EPS, bore))
            threads = [Thread(size, size, -male, 0), Thread(size, bore, bore_bottom, length, True)]
        else:
            self.cut(body, self.axial(-EPS, length + EPS, bore))
            threads = [Thread(size, bore, 0, length, True)] if size else []
        return [("铝柱", body)], threads

    def pin(self, part):
        d = part.dimensions
        diameter, length = d["diameter"], d["length"]
        if part.kind == "taper_pin":
            body = self.axial(-length, 0, diameter, diameter + length / 50)
        elif part.kind == "clevis_pin":
            body = self.axial(-length, EPS, diameter)
            self.join(body, self.axial(0, diameter * 0.27, diameter * 1.7))
            cross_hole_z = -length + diameter * 0.39
            tool = self.manager.createCylinderOrCone(
                point(-diameter, 0, cross_hole_z), diameter * 0.15 / 10,
                point(diameter, 0, cross_hole_z), diameter * 0.15 / 10,
            )
            self.cut(body, tool)
        else:
            chamfer = min(diameter * 0.12, length * 0.24)
            body = self.axial(-length + chamfer, -chamfer, diameter)
            self.join(body, self.axial(-length, -length + chamfer + EPS,
                                       diameter * 0.78, diameter))
            self.join(body, self.axial(-chamfer - EPS, 0, diameter, diameter * 0.78))
            if part.kind == "spring_pin":
                self.cut(body, self.axial(-length - EPS, EPS, diameter * 0.66))
                width = diameter * 0.16
                self.cut(body, self.box(-length - EPS, EPS, diameter, width, x=diameter / 2))
        return [("销", body)], []

    def washer(self, part):
        inner, outer, height = catalog.TABLES[part.kind][part.size]
        body = self.axial(0, height, outer)
        self.cut(body, self.axial(-EPS, height + EPS, inner))
        if part.kind == "spring_washer":
            self.cut(body, self.box(-EPS, height + EPS, outer, (outer - inner) * 0.2, x=outer / 2))
        return [("垫圈", body)], []

    def other(self, part):
        length = part.dimensions["length"]
        if part.kind == "rod":
            return [("牙条", self.axial(-length, 0, part.size))], [Thread(part.size, part.size, -length, 0)]
        diameter = part.dimensions["diameter"]
        height = diameter * 0.28
        shank = self.axial(-length, EPS, diameter)
        self.join(shank, self.axial(0, height, diameter * 2, diameter * 1.88))
        self.cut(shank, self.axial(-length - EPS, height + EPS, diameter * 0.48))
        mandrel = self.axial(-length, height + 3 * diameter, diameter * 0.43)
        self.join(mandrel, self.axial(-length - height, -length + EPS, diameter * 0.8))
        return [("铆体", shank), ("芯杆", mandrel)], []

    def build(self, part):
        builder = {
            catalog.SCREWS: self.screw,
            catalog.NUTS: self.nut,
            catalog.SPACERS: self.spacer,
            catalog.PINS: self.pin,
            catalog.WASHERS: self.washer,
            catalog.OTHERS: self.other,
        }[part.family.group]
        solids, threads = builder(part)
        for label, solid in solids:
            if not solid.isSolid or solid.lumps.count != 1:
                raise RuntimeError(f"{label}没有形成单一封闭实体。")
        return solids, threads


def thread_face(component, thread):
    candidates = []
    for body in component.bRepBodies:
        for face in body.faces:
            cylinder = core.Cylinder.cast(face.geometry)
            if not cylinder or abs(cylinder.radius * 20 - thread.diameter) > 0.03:
                continue
            bounds = face.boundingBox
            error = abs(bounds.minPoint.z * 10 - thread.lower) + abs(bounds.maxPoint.z * 10 - thread.upper)
            if error < 0.12:
                candidates.append((error, face))
    if not candidates:
        raise RuntimeError(f"找不到 {catalog.designation(thread.size)} 的螺纹圆柱面。")
    return min(candidates, key=lambda item: item[0])[1]


def add_threads(component, threads, mode):
    if not threads or mode == SIMPLIFIED:
        return
    query = fusion.ThreadDataQuery.create()
    features = component.features.threadFeatures
    for thread in threads:
        name = catalog.designation(thread.size)
        info = fusion.ThreadInfo.create(False, thread.internal, query.defaultMetricThreadType,
                                        name, "6H" if thread.internal else "6g", True)
        if not info:
            raise RuntimeError(f"Fusion 螺纹库中找不到 {name}。")
        setup = features.createInput(thread_face(component, thread), info)
        if not setup:
            raise RuntimeError(f"无法设定 {name} 螺纹。")
        setup.isModeled = mode == MODELED
        feature = features.add(setup)
        if not feature or feature.healthState == fusion.FeatureHealthStates.ErrorFeatureHealthState:
            message = feature.errorOrWarningMessage if feature else ""
            raise RuntimeError(f"{name} 螺纹生成失败。{message}")


def populate(design, component, part, solids, threads, mode):
    component.name = part.name
    component.partNumber = part.name
    data = {"family": part.kind, "reference": part.family.reference, "M": part.size,
            "dimensions_mm": part.dimensions, "thread_mode": mode,
            "threads": [vars(thread) for thread in threads]}
    component.attributes.add("FusionFastenerWorkbench", "spec", json.dumps(data, ensure_ascii=False))
    if design.designType == fusion.DesignTypes.ParametricDesignType:
        feature = component.features.baseFeatures.add()
        feature.name = "紧固件实体"
        if not feature.startEdit():
            raise RuntimeError("无法编辑紧固件基础特征。")
        try:
            for label, solid in solids:
                body = component.bRepBodies.add(solid, feature)
                if not body:
                    raise RuntimeError(f"无法写入实体 {label}。")
                body.name = label
        finally:
            finished = feature.finishEdit()
        if not finished:
            raise RuntimeError("无法完成紧固件基础特征。")
    else:
        for label, solid in solids:
            body = component.bRepBodies.add(solid)
            if not body:
                raise RuntimeError(f"无法写入实体 {label}。")
            body.name = label
    add_threads(component, threads, mode)


def hole_frame(entity):
    edge = fusion.BRepEdge.cast(entity)
    circle = core.Circle3D.cast(edge.geometry) if edge else None
    if not circle:
        raise ValueError("定位请选择完整圆边，圆弧不能作为孔位。")
    axis = circle.normal.copy()
    for face in edge.faces:
        if core.Plane.cast(face.geometry):
            success, normal = face.evaluator.getNormalAtPoint(face.pointOnFace)
            if success and axis.dotProduct(normal) < 0:
                axis.scaleBy(-1)
            break
    return circle.center, axis


def align(frame, flip, offset):
    center, axis = frame
    direction = axis.copy()
    direction.normalize()
    if flip:
        direction.scaleBy(-1)
    x_axis = vector(1, 0, 0) if abs(direction.x) < 0.9 else vector(0, 1, 0)
    y_axis = direction.crossProduct(x_axis)
    y_axis.normalize()
    x_axis = y_axis.crossProduct(direction)
    origin = center.copy()
    displacement = direction.copy()
    displacement.scaleBy(offset / 10)
    origin.translateBy(displacement)
    transform = core.Matrix3D.create()
    transform.setWithCoordinateSystem(origin, x_axis, y_axis, direction)
    return transform


def grid(root, rows):
    step = (max(row.part.width for row in rows) + 3) / 10
    bounds = root.boundingBox if root.bRepBodies.count or root.occurrences.count else None
    x = (bounds.maxPoint.x + step) if bounds else 0
    y = bounds.minPoint.y if bounds else 0
    z = bounds.minPoint.z if bounds else 0
    index = 0
    for row in rows:
        for _ in range(row.quantity):
            transform = core.Matrix3D.create()
            transform.translation = vector(x + (index % 8) * step, y + (index // 8) * step, z)
            index += 1
            yield row, transform


def generate(design, rows, placements, frames, mode, flip):
    root = design.rootComponent
    if placements is None:
        jobs = list(grid(root, rows))
    else:
        jobs = [(row, align(frames[index], flip, row.offset))
                for row, indexes in zip(rows, placements) for index in indexes]
    created = []
    definitions = {}
    builder = SolidBuilder()
    row = rows[0]
    try:
        for row, transform in jobs:
            part = row.part
            key = part.key
            component = definitions.get(key)
            if component:
                occurrence = root.occurrences.addExistingComponent(component, transform)
            else:
                solids, threads = builder.build(part)
                occurrence = root.occurrences.addNewComponent(transform)
            if not occurrence:
                raise RuntimeError("Fusion 未返回组件实例。")
            created.append(occurrence)
            if not component:
                definitions[key] = occurrence.component
                populate(design, occurrence.component, part, solids, threads, mode)
    except Exception as error:
        cleanup_errors = []
        for occurrence in reversed(created):
            try:
                if occurrence.isValid and not occurrence.deleteMe():
                    cleanup_errors.append(occurrence.name)
            except RuntimeError as cleanup:
                cleanup_errors.append(str(cleanup))
        suffix = " 部分组件清理失败，可在 Fusion 中撤销本次操作。" if cleanup_errors else ""
        raise RuntimeError(f"{row.part.name} 生成失败。{error}{suffix}") from error
    return len(created)
