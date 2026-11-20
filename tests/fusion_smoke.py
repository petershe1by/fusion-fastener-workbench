"""Run inside Fusion's Python console. Creates an unsaved test design and writes a local report."""

from importlib import reload
from pathlib import Path
import sys
import traceback

import adsk.core as core
import adsk.fusion as fusion


project = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project))
from FusionFastenerWorkbench import FusionFastenerWorkbench as addin, catalog, fusion_model as model

addin.stop(None)
reload(catalog)
reload(model)
reload(addin)


def part(kind, size=0):
    return catalog.build_part(kind, size, catalog.defaults(kind, size))


def check(actual, expected):
    if abs(actual - expected) > 1e-5:
        raise AssertionError(f"Expected {expected}, got {actual}")


def create_fixture(app, builder):
    app.documents.add(core.DocumentTypes.FusionDesignDocumentType)
    design = fusion.Design.cast(app.activeProduct)
    if design.designIntent != fusion.DesignIntentTypes.HybridDesignIntentType:
        design.designIntent = fusion.DesignIntentTypes.HybridDesignIntentType
    fixture = design.rootComponent.occurrences.addNewComponent(core.Matrix3D.create())
    plate = builder.box(-5, 0, 40, 18)
    for x in (-10, 10):
        hole = builder.manager.createCylinderOrCone(model.point(x, 0, -6), 0.165,
                                                   model.point(x, 0, 1), 0.165)
        builder.cut(plate, hole)
    model.populate(design, fixture.component, part("dowel"), [("测试板", plate)], [], model.SIMPLIFIED)
    fixture.component.name = "双孔测试件"
    return design, fixture


def run():
    app = core.Application.get()
    report = []
    try:
        builder = model.SolidBuilder()
        for kind, family in catalog.FAMILIES.items():
            checked = 0
            for size in family.sizes or (0,):
                try:
                    item = part(kind, size)
                    solids, _ = builder.build(item)
                    assert all(body.volume > 0 for _, body in solids)
                    checked += 1
                except Exception as error:
                    report.append(f"FAIL geometry {kind} {size}: {error}")
            report.append(f"geometry {kind}: {checked}/{len(family.sizes or (0,))}")

        for kind, size, expected in (("cap", 3, 15), ("flat", 3, 12), ("shoulder", 5, 24),
                                      ("round_spacer", 0, 15), ("dowel", 0, 12)):
            solids, _ = builder.build(part(kind, size))
            b = solids[0][1].boundingBox
            check((b.maxPoint.z - b.minPoint.z) * 10, expected)
        report.append("PASS axial dimensions")

        design, fixture = create_fixture(app, builder)
        root = design.rootComponent
        plate = fixture.bRepBodies.item(0)
        frames = []
        for edge in plate.edges:
            circle = core.Circle3D.cast(edge.geometry)
            if circle and abs(circle.center.z) < 1e-6:
                frames.append(model.hole_frame(edge))
        frames.sort(key=lambda frame: frame[0].x)
        assert len(frames) == 2
        for index, (center, direction) in enumerate(frames):
            check(center.x, -1 + index * 2)
            check(direction.z, 1)
        bolt_row = addin.Row(part("cap", 3), 2, 0.5)
        washer_row = addin.Row(part("plain_washer", 3), 2, 0.0)
        before = root.occurrences.count
        count = model.generate(design, [bolt_row, washer_row], [[0, 1], [0, 1]], frames, model.SIMPLIFIED, False)
        assert count == 4
        first = root.occurrences.item(before)
        second = root.occurrences.item(before + 1)
        assert first.component.id == second.component.id
        check(first.transform2.translation.x, -1)
        check(second.transform2.translation.x, 1)
        check(first.transform2.translation.z, 0.05)
        report.append("PASS repeated hole stack, component instance reuse, transform")

        for mode in (model.COSMETIC, model.MODELED):
            for kind, size in (("cap", 3), ("flat", 5), ("hex_partial", 6), ("shoulder", 5),
                               ("nut", 3), ("nylon", 4), ("acorn", 5), ("hex_male", 3)):
                try:
                    row = addin.Row(part(kind, size), 1, 0)
                    model.generate(design, [row], None, [], mode, False)
                    occ = root.occurrences.item(root.occurrences.count - 1)
                    assert occ.component.features.threadFeatures.count == (2 if kind == "hex_male" else 1)
                    report.append(f"PASS {mode} {kind}")
                except Exception as error:
                    report.append(f"FAIL {mode} {kind}: {error}")
        app.activeViewport.fit()
        addin.run(None)
        report.append(f"Command registered: {bool(app.userInterface.commandDefinitions.itemById(addin.COMMAND_ID))}")
    except Exception:
        report.append(traceback.format_exc())
    finally:
        (project / "tests" / "fusion-smoke-result.txt").write_text("\n".join(report), encoding="utf-8")
        app.log("紧固件验证结束。")


if globals().get("ui_check"):
    app = core.Application.get()
    create_fixture(app, model.SolidBuilder())
    camera = app.activeViewport.camera
    camera.viewOrientation = core.ViewOrientations.TopViewOrientation
    camera.isFitView = True
    app.activeViewport.camera = camera
    addin.run(None)
    app.userInterface.commandDefinitions.itemById(addin.COMMAND_ID).execute()
else:
    run()
