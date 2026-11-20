"""Fusion add-in entry point and native command dialog."""

from dataclasses import dataclass
from html import escape
from math import isfinite
from pathlib import Path
import traceback

import adsk.core as core
import adsk.fusion as fusion

from . import catalog, fusion_model


COMMAND_ID = "InitialFusionFastenerWorkbench"
PANEL_ID = "SolidCreatePanel"
TITLE = "紧固件工坊 · Peter Shelby"
ICON_FOLDER = Path(__file__).resolve().parent / "resources" / "peter-shelby"
GRID = "在模型旁排开"
SEQUENCE = "按选孔顺序放置"
REPEAT = "每个孔重复整批"
MAX_BATCH = 500
MAX_QUANTITY = 200
PLACEMENTS = (GRID, SEQUENCE, REPEAT)
THREAD_MODES = (fusion_model.SIMPLIFIED, fusion_model.COSMETIC, fusion_model.MODELED)
_startup_handlers = []
_dialogs = set()


@dataclass(frozen=True)
class Row:
    part: catalog.Part
    quantity: int
    offset: float


def listen(event, handler_type, callback, owners):
    class Handler(handler_type):
        def notify(self, args):
            callback(args)

    handler = Handler()
    if not event.add(handler):
        raise RuntimeError("Fusion 事件注册失败。")
    owners.append(handler)


def dropdown(inputs, field, label, options=()):
    result = inputs.addDropDownCommandInput(field, label, core.DropDownStyles.TextListDropDownStyle)
    set_options(result, options)
    return result


def set_options(control, options, selected=None):
    control.listItems.clear()
    for index, option in enumerate(options):
        control.listItems.add(option, option == selected if selected is not None else index == 0)


def value(inputs, field, label, mm):
    return inputs.addValueInput(field, label, "mm", core.ValueInput.createByReal(mm / 10))


def panel_for(ui):
    workspace = ui.workspaces.itemById("FusionSolidEnvironment")
    return workspace.toolbarPanels.itemById(PANEL_ID) if workspace else None


def design_for(app):
    design = fusion.Design.cast(app.activeProduct)
    if not design:
        raise ValueError("请先打开 Fusion 设计文档。")
    intents = getattr(fusion, "DesignIntentTypes", None)
    if intents and design.designIntent != intents.HybridDesignIntentType:
        raise ValueError("请使用混合设计。可在文档设置中检查设计类型。")
    return design


class Dialog:
    def __init__(self, command, app, design):
        self.app = app
        self.design = design
        self.handlers = []
        self.rows = []
        self.family_keys = []
        self.sizes = ()
        self.busy = False
        command.setDialogInitialSize(398, 685)
        command.okButtonText = "生成"
        inputs = command.commandInputs
        self.group = dropdown(inputs, "category", "类别", catalog.GROUPS)
        self.family = dropdown(inputs, "family", "类型")
        self.size = dropdown(inputs, "metric", "M 规格")
        self.length_preset = dropdown(inputs, "length_preset", "常用长度")
        self.dimensions = {
            "diameter": value(inputs, "diameter", "直径 D", 4),
            "inner": value(inputs, "inner", "内孔直径", 3.2),
            "outer": value(inputs, "outer", "外径 / 对边 S", 6),
            "length": value(inputs, "length", "长度 L", 12),
            "thread_length": value(inputs, "thread_length", "螺纹段长度", 7),
        }
        self.quantity = inputs.addIntegerSpinnerCommandInput("quantity", "数量", 1, MAX_QUANTITY, 1, 1)
        self.threads = dropdown(inputs, "threads", "螺纹表现", THREAD_MODES)
        self.details = inputs.addTextBoxCommandInput("details", "", "", 2, True)

        placement = inputs.addGroupCommandInput("placement", "装配放置")
        placement.isExpanded = True
        place_inputs = placement.children
        self.placement = dropdown(place_inputs, "placement_mode", "放置方式", PLACEMENTS)
        self.holes = place_inputs.addSelectionInput("holes", "圆孔边", "依次选择各孔口的完整圆边")
        self.holes.addSelectionFilter("CircularEdges")
        self.holes.setSelectionLimits(0, MAX_BATCH)
        self.flip = place_inputs.addBoolValueInput("flip", "反转轴向", True, "", False)
        self.offset = value(place_inputs, "offset", "沿轴偏移", 0)
        self.status = inputs.addTextBoxCommandInput("status", "", "", 2, True)

        batch = inputs.addGroupCommandInput("batch", "批次清单")
        batch.isExpanded = False
        batch_inputs = batch.children
        self.enqueue = batch_inputs.addBoolValueInput("enqueue", "加入当前规格", False, "", False)
        self.pop = batch_inputs.addBoolValueInput("pop", "移除最后一条", False, "", False)
        self.clear = batch_inputs.addBoolValueInput("clear", "清空清单", False, "", False)
        for button in (self.enqueue, self.pop, self.clear):
            button.isFullWidth = True
        self.summary = batch_inputs.addTextBoxCommandInput("summary", "", "", 4, True)

        self.load_families()
        self.refresh()
        listen(command.inputChanged, core.InputChangedEventHandler, self.change, self.handlers)
        listen(command.validateInputs, core.ValidateInputsEventHandler, self.validate, self.handlers)
        listen(command.preSelect, core.SelectionEventHandler, self.preselect, self.handlers)
        listen(command.execute, core.CommandEventHandler, self.execute, self.handlers)
        listen(command.destroy, core.CommandEventHandler, self.destroy, self.handlers)

    @property
    def kind(self):
        return self.family_keys[self.family.selectedItem.index]

    @property
    def metric_size(self):
        return self.sizes[self.size.selectedItem.index] if self.sizes else 0

    @property
    def placement_mode(self):
        return self.placement.selectedItem.name

    def load_families(self):
        group = self.group.selectedItem.name
        self.family_keys = [key for key, family in catalog.FAMILIES.items() if family.group == group]
        set_options(self.family, [catalog.FAMILIES[key].label for key in self.family_keys])
        self.load_sizes()

    def load_sizes(self):
        family = catalog.FAMILIES[self.kind]
        self.sizes = family.sizes
        preferred = 5 if self.kind == "shoulder" else 3
        set_options(self.size, [catalog.metric(size) for size in self.sizes],
                    catalog.metric(preferred) if preferred in self.sizes else None)
        self.size.isVisible = bool(self.sizes)
        self.load_dimensions()

    def load_dimensions(self, keep_length=False):
        kind = self.kind
        family = catalog.FAMILIES[kind]
        defaults = catalog.defaults(kind, self.metric_size)
        for key, field in self.dimensions.items():
            field.isVisible = key in defaults
            if key in defaults and (key != "length" or not keep_length):
                field.value = defaults[key] / 10
        if "length" in defaults:
            choices = catalog.LENGTHS
            if family.head == "countersunk":
                head_height = catalog.build_part(kind, self.metric_size, defaults).head[1]
                choices = tuple(length for length in choices if length > head_height + 0.1)
            self.length_choices = choices
            set_options(self.length_preset, ["自定义", *(f"{length} mm" for length in choices)])
            self.sync_length_preset()
        self.length_preset.isVisible = "length" in defaults

    def sync_length_preset(self):
        mm = self.dimensions["length"].value * 10
        index = next((i + 1 for i, length in enumerate(self.length_choices)
                      if abs(length - mm) < 1e-6), 0)
        self.length_preset.listItems.item(index).isSelected = True

    def current_row(self):
        values = {}
        for key in catalog.defaults(self.kind, self.metric_size):
            field = self.dimensions[key]
            if not field.isValidExpression:
                raise ValueError(f"请检查「{field.name}」的数值。")
            values[key] = field.value * 10
        offset = 0.0
        if self.placement_mode != GRID:
            if not self.offset.isValidExpression:
                raise ValueError("请检查沿轴偏移的数值。")
            offset = self.offset.value * 10
            if not isfinite(offset) or abs(offset) > 1500:
                raise ValueError("沿轴偏移须在 ±1500 mm 内。")
        part = catalog.build_part(self.kind, self.metric_size, values)
        return Row(part, self.quantity.value, offset)

    def refresh(self, message=None):
        family = catalog.FAMILIES[self.kind]
        details = escape(family.reference)
        size = self.metric_size
        if self.kind == "shoulder":
            shaft, threaded, *_ = catalog.SHOULDER[size]
            details += f"<br>D、L 为光杆尺寸。{catalog.metric(size)} 预设 Ø{shaft:g}，牙长 {threaded:g} mm"
        elif family.head == "countersunk":
            details += "<br>L 为含头总长"
        elif family.head or self.kind == "clevis_pin":
            details += "<br>L 为头下长度"
        elif self.kind == "taper_pin":
            details += "<br>D 为小端直径"
        elif self.kind == "rivet":
            details += "<br>D 为铆体直径，L 为头下长度"
        elif family.group in (catalog.NUTS, catalog.WASHERS):
            first, *_ = catalog.TABLES[self.kind][size]
            if family.group == catalog.WASHERS:
                inner, outer, height = catalog.TABLES[self.kind][size]
                details += f"<br>内 Ø{inner:g} / 外 Ø{outer:g} / 厚 {height:g} mm"
            else:
                details += f"<br>对边 {first:g} mm"
        elif family.group == catalog.SPACERS:
            outside = "六角对边 S" if self.kind.startswith("hex") else "圆柱外径"
            inside = f"内螺纹 {catalog.designation(size)}" if size else "通孔直径"
            details += f"<br>{outside} · {inside}"
            if self.kind == "hex_male":
                details += " · 螺纹段长度指公牙"
        self.details.formattedText = details
        at_holes = self.placement_mode != GRID
        for item in (self.holes, self.offset, self.flip):
            if item.isVisible != at_holes:
                item.isVisible = at_holes
        for button in (self.pop, self.clear):
            button.isEnabled = bool(self.rows)
        if self.rows:
            lines = []
            for index, row in enumerate(self.rows, 1):
                suffix = f" · 偏移 {row.offset:g} mm" if row.offset else ""
                lines.append(f"{index}. {escape(row.part.name)} · {row.quantity} 件{suffix}")
            self.summary.formattedText = "<br>".join(lines)
        else:
            self.summary.formattedText = "清单为空时，「生成」使用上面的规格。"

        if message is None:
            try:
                rows, _ = self.plan()
                count = sum(row.quantity for row in rows)
                source = "清单" if self.rows else "当前规格"
                message = f"将按{source}生成 {count} 件。"
            except ValueError as error:
                message = str(error)
        self.status.formattedText = escape(message)

    def plan(self):
        rows = self.rows or [self.current_row()]
        counts = [row.quantity for row in rows]
        if sum(counts) > MAX_BATCH:
            raise ValueError(f"一次最多生成 {MAX_BATCH} 件。")
        placement = self.placement_mode
        if placement == GRID:
            return rows, None
        count = self.holes.selectionCount
        return rows, catalog.mounting_order(counts, count, placement == REPEAT)

    def change(self, args):
        if self.busy:
            return
        self.busy = True
        field = args.input.id
        message = None
        try:
            if field == "category":
                self.load_families()
            elif field == "family":
                self.load_sizes()
            elif field == "metric":
                self.load_dimensions(keep_length=True)
            elif field == "length_preset":
                index = self.length_preset.selectedItem.index
                if index:
                    self.dimensions["length"].value = self.length_choices[index - 1] / 10
            elif field == "length":
                self.sync_length_preset()
            elif field == "enqueue" and self.enqueue.value:
                self.enqueue.value = False
                row = self.current_row()
                if sum(item.quantity for item in self.rows) + row.quantity > MAX_BATCH:
                    raise ValueError(f"一次最多生成 {MAX_BATCH} 件。")
                self.rows.append(row)
            elif field == "pop" and self.pop.value:
                self.pop.value = False
                if self.rows:
                    self.rows.pop()
            elif field == "clear" and self.clear.value:
                self.clear.value = False
                self.rows.clear()
        except ValueError as error:
            message = str(error)
        except Exception:
            self.app.log(traceback.format_exc())
            message = "无法更新紧固件输入，请重新打开命令。"
        finally:
            try:
                self.refresh(message)
                if field == "placement_mode" and self.holes.isVisible:
                    self.holes.hasFocus = True
            finally:
                self.busy = False

    def preselect(self, args):
        edge = fusion.BRepEdge.cast(args.selection.entity)
        args.isSelectable = bool(edge and core.Circle3D.cast(edge.geometry))

    def validate(self, args):
        try:
            self.plan()
            args.areInputsValid = True
        except ValueError:
            args.areInputsValid = False

    def execute(self, args):
        try:
            rows, placements = self.plan()
            frames = []
            if placements is not None:
                frames = [fusion_model.hole_frame(self.holes.selection(i).entity)
                          for i in range(self.holes.selectionCount)]
            count = fusion_model.generate(self.design, rows, placements, frames,
                                          self.threads.selectedItem.name, self.flip.value)
        except Exception as error:
            self.app.log(traceback.format_exc())
            args.executeFailed = True
            args.executeFailedMessage = str(error)
            return
        self.app.log(f"{TITLE}已生成 {count} 件。")
        if placements is None:
            self.app.activeViewport.fit()

    def destroy(self, _args):
        _dialogs.discard(self)
        self.handlers.clear()


def run(_context):
    app = core.Application.get()
    ui = app.userInterface
    try:
        panel = panel_for(ui)
        if not panel:
            raise RuntimeError("找不到 Fusion 实体创建面板。")
        if ui.commandDefinitions.itemById(COMMAND_ID):
            return
        command = ui.commandDefinitions.addButtonDefinition(
            COMMAND_ID, TITLE, "按规格和数量生成标准紧固件，支持混合批次与多孔对齐。",
            str(ICON_FOLDER),
        )

        def created(args):
            try:
                dialog = Dialog(args.command, app, design_for(app))
                _dialogs.add(dialog)
            except ValueError as error:
                ui.messageBox(str(error), TITLE)
            except Exception:
                app.log(traceback.format_exc())
                ui.messageBox("紧固件面板未能打开，详情见 Fusion 文本命令。", TITLE)

        listen(command.commandCreated, core.CommandCreatedEventHandler, created, _startup_handlers)
        panel.controls.addCommand(command)
    except Exception:
        app.log(traceback.format_exc())
        ui.messageBox("紧固件工坊加载失败，详情见 Fusion 文本命令。", TITLE)


def stop(_context):
    app = core.Application.get()
    ui = app.userInterface
    panel = panel_for(ui)
    control = panel.controls.itemById(COMMAND_ID) if panel else None
    if control:
        control.deleteMe()
    definition = ui.commandDefinitions.itemById(COMMAND_ID)
    if definition:
        definition.deleteMe()
    _startup_handlers.clear()
    _dialogs.clear()
