"""Metric dimensions and input validation. All lengths in this module are millimeters."""

from dataclasses import dataclass
from math import isfinite, sqrt


PITCH = {
    2: 0.4, 2.5: 0.45, 3: 0.5, 4: 0.7, 5: 0.8, 6: 1,
    8: 1.25, 10: 1.5, 12: 1.75, 16: 2, 20: 2.5,
}
SMALL = (2, 2.5, 3, 4, 5, 6, 8, 10, 12, 16)
MEDIUM = (3, 4, 5, 6, 8, 10, 12, 16)
HEX = (3, 4, 5, 6, 8, 10, 12, 16, 20)
WASHER = (2, 2.5, 3, 4, 5, 6, 8, 10, 12, 16, 20)

# Screw head diameter (or across flats for an external hex), height, key size.
CAP = dict(zip(SMALL, (
    (3.8, 2, 1.5), (4.5, 2.5, 2), (5.5, 3, 2.5), (7, 4, 3), (8.5, 5, 4),
    (10, 6, 5), (13, 8, 6), (16, 10, 8), (18, 12, 10), (24, 16, 14),
)))
LOW = dict(zip(MEDIUM, (
    (5.5, 2, 2), (7, 2.8, 2.5), (8.5, 3.5, 3), (10, 4, 4),
    (13, 5, 5), (16, 6.5, 7), (18, 7.5, 8), (24, 10, 12),
)))
BUTTON = dict(zip(MEDIUM, (
    (5.7, 1.65, 2), (7.6, 2.2, 2.5), (9.5, 2.75, 3), (10.5, 3.3, 4),
    (14, 4.4, 5), (17.5, 5.5, 6), (21, 6.6, 8), (28, 8.8, 10),
)))
FLAT = dict(zip(SMALL, (
    (4, 1.2, 1.3), (5, 1.5, 1.5), (6.72, 1.86, 2), (8.96, 2.48, 2.5),
    (11.2, 3.1, 3), (13.44, 3.72, 4), (17.92, 4.96, 5),
    (22.4, 6.2, 6), (26.88, 7.44, 8), (33.6, 8.8, 10),
)))
PAN = {
    2: (4, 1.6, 2), 2.5: (5, 2.1, 2.4), 3: (5.6, 2.4, 3),
    4: (8, 3.1, 4), 5: (9.5, 3.7, 4.8), 6: (12, 4.6, 6),
    8: (16, 6, 8), 10: (20, 7.5, 10),
}
HEX_HEAD = dict(zip(HEX, (
    (5.5, 2, 0), (7, 2.8, 0), (8, 3.5, 0), (10, 4, 0), (13, 5.3, 0),
    (16, 6.4, 0), (18, 7.5, 0), (24, 10, 0), (30, 12.5, 0),
)))
SET_KEY = dict(zip(SMALL, (0.9, 1.3, 1.5, 2, 2.5, 3, 4, 5, 6, 8)))

# Shaft diameter, threaded length, head diameter, head height, hex key.
SHOULDER = {
    3: (4, 7, 7, 3, 2), 4: (5, 8, 9, 4, 2.5), 5: (6, 9.5, 10, 4.5, 3),
    6: (8, 11, 13, 5.5, 4), 8: (10, 13, 16, 7, 5), 10: (12, 16, 18, 9, 6),
    12: (16, 18, 24, 11, 8), 16: (20, 22, 30, 14, 10), 20: (24, 27, 36, 16, 12),
}
# Across flats, overall height. Nylon-lock series uses the legacy DIN wrench widths.
NUT = dict(zip(WASHER, (
    (4, 1.6), (5, 2), (5.5, 2.4), (7, 3.2), (8, 4.7), (10, 5.2),
    (13, 6.8), (16, 8.4), (18, 10.8), (24, 14.8), (30, 18),
)))
NYLON = {
    3: (5.5, 4), 4: (7, 5), 5: (8, 5), 6: (10, 6),
    8: (13, 8), 10: (17, 10), 12: (19, 12), 16: (24, 16), 20: (30, 20),
}
THIN = {
    3: (5.5, 1.8), 4: (7, 2.2), 5: (8, 2.7), 6: (10, 3.2),
    8: (13, 4), 10: (16, 5), 12: (18, 6), 16: (24, 8), 20: (30, 10),
}
FLANGE_NUT = {
    5: (8, 5, 11.8), 6: (10, 6, 14.2), 8: (13, 8, 17.9),
    10: (15, 10, 21.8), 12: (18, 12, 26), 16: (24, 16, 34.5),
}
ACORN = {
    4: (7, 8), 5: (8, 10), 6: (10, 12), 8: (13, 15),
    10: (17, 18), 12: (19, 22), 16: (24, 28), 20: (30, 34),
}

# Inner diameter, outer diameter, thickness.
PLAIN = dict(zip(WASHER, (
    (2.2, 5, 0.3), (2.7, 6, 0.5), (3.2, 7, 0.5), (4.3, 9, 0.8),
    (5.3, 10, 1), (6.4, 12, 1.6), (8.4, 16, 1.6), (10.5, 20, 2),
    (13, 24, 2.5), (17, 30, 3), (21, 37, 3),
)))
WIDE = dict(zip(HEX, (
    (3.2, 9, 0.8), (4.3, 12, 1), (5.3, 15, 1.2), (6.4, 18, 1.6),
    (8.4, 24, 2), (10.5, 30, 2.5), (13, 37, 3), (17, 50, 3), (21, 60, 4),
)))
SPRING = dict(zip(HEX, (
    (3.1, 6.2, 0.8), (4.1, 7.6, 0.9), (5.1, 9.2, 1.2), (6.1, 11.8, 1.6),
    (8.1, 14.8, 2), (10.2, 18.1, 2.2), (12.2, 21.1, 2.5),
    (16.2, 27.4, 3.5), (20.2, 33.6, 4.5),
)))

SCREWS = "螺丝 / 螺栓"
NUTS = "螺母"
SPACERS = "铝柱 / 隔套"
PINS = "销"
WASHERS = "垫圈"
OTHERS = "牙条 / 铆钉"
LENGTHS = (3, 4, 5, 6, 8, 10, 12, 14, 16, 18, 20, 25, 30, 35, 40, 45, 50, 60, 70, 80, 100, 120, 150, 200)


@dataclass(frozen=True)
class Family:
    group: str
    label: str
    reference: str
    sizes: tuple = ()
    head: str = ""
    drive: str = ""


FAMILIES = {
    "cap": Family(SCREWS, "内六角杯头", "ISO 4762", tuple(CAP), "cylinder", "hex"),
    "low": Family(SCREWS, "内六角平头（薄杯头）", "DIN 7984", tuple(LOW), "cylinder", "hex"),
    "button": Family(SCREWS, "内六角圆头", "ISO 7380-1", tuple(BUTTON), "dome", "hex"),
    "flat": Family(SCREWS, "内六角沉头", "ISO 10642", tuple(FLAT), "countersunk", "hex"),
    "pan": Family(SCREWS, "十字盘头", "ISO 7045 参考外形", tuple(PAN), "dome", "cross"),
    "cross_flat": Family(SCREWS, "十字沉头", "90° 常见外形", tuple(PAN), "countersunk", "cross"),
    "hex_full": Family(SCREWS, "外六角全牙", "ISO 4017", HEX, "hex"),
    "hex_partial": Family(SCREWS, "外六角半牙", "ISO 4014", HEX, "hex"),
    "set_flat": Family(SCREWS, "内六角紧定（平端）", "ISO 4026 参考外形", SMALL, "", "hex"),
    "set_cup": Family(SCREWS, "内六角紧定（凹端）", "ISO 4029 参考外形", SMALL, "", "hex"),
    "shoulder": Family(SCREWS, "塞打 / 轴肩螺丝", "ISO 7379 系列", tuple(SHOULDER), "cylinder", "hex"),
    "nut": Family(NUTS, "普通六角螺母", "ISO 4032", tuple(NUT)),
    "nylon": Family(NUTS, "尼龙防松螺母", "DIN 985", tuple(NYLON)),
    "thin": Family(NUTS, "薄六角螺母", "ISO 4035", tuple(THIN)),
    "flange": Family(NUTS, "法兰螺母（无齿）", "ISO 4161 参考外形", tuple(FLANGE_NUT)),
    "acorn": Family(NUTS, "盖形螺母", "DIN 1587 参考外形", tuple(ACORN)),
    "round_spacer": Family(SPACERS, "圆铝柱 · 通孔", "自定义"),
    "hex_spacer": Family(SPACERS, "六角铝柱 · 通孔", "自定义"),
    "round_female": Family(SPACERS, "圆铝柱 · 内牙", "自定义", SMALL),
    "hex_female": Family(SPACERS, "六角铝柱 · 内牙", "自定义", SMALL),
    "hex_male": Family(SPACERS, "六角铝柱 · 一公一母", "自定义", SMALL),
    "dowel": Family(PINS, "圆柱定位销", "ISO 8734 参考外形"),
    "spring_pin": Family(PINS, "开槽弹性圆柱销", "ISO 8752 参考外形"),
    "taper_pin": Family(PINS, "圆锥销", "ISO 2339 参考外形"),
    "clevis_pin": Family(PINS, "带头带孔销轴", "ISO 2341 参考外形"),
    "plain_washer": Family(WASHERS, "平垫圈", "ISO 7089", tuple(PLAIN)),
    "wide_washer": Family(WASHERS, "加大平垫圈", "ISO 7093-1", tuple(WIDE)),
    "spring_washer": Family(WASHERS, "开口弹垫（压平外形）", "DIN 127 B", tuple(SPRING)),
    "rod": Family(OTHERS, "全牙螺杆 / 牙条", "DIN 976-1 参考外形", tuple(PITCH)),
    "rivet": Family(OTHERS, "抽芯铆钉（安装前外形）", "圆头开口型参考外形"),
}
GROUPS = tuple(dict.fromkeys(family.group for family in FAMILIES.values()))

TABLES = {
    "cap": CAP, "low": LOW, "button": BUTTON, "flat": FLAT, "pan": PAN,
    "hex_full": HEX_HEAD, "hex_partial": HEX_HEAD,
    "nut": NUT, "nylon": NYLON, "thin": THIN, "flange": FLANGE_NUT, "acorn": ACORN,
    "plain_washer": PLAIN, "wide_washer": WIDE, "spring_washer": SPRING,
}


def number(value):
    return f"{value:g}"


def metric(size):
    return "M" + number(size)


def designation(size):
    return f"{metric(size)}x{number(PITCH[size])}"


def tap_diameter(size):
    return round(size - 1.08253 * PITCH[size], 4)


def defaults(kind, size):
    family = FAMILIES[kind]
    if family.sizes and size not in family.sizes:
        raise ValueError("螺纹或配套规格不在此系列内。")
    if kind == "shoulder":
        diameter, threaded, *_ = SHOULDER[size]
        return {"diameter": diameter, "length": max(10, diameter), "thread_length": threaded}
    if family.group == SCREWS or kind == "rod":
        length = max(6, round(size * 4))
        if kind == "hex_partial":
            length = max(25, round(size * 5))
        elif kind == "rod":
            length = 30
        return {"length": length}
    if family.group == SPACERS:
        stock = max(5, size * 1.65) if size else 6
        result = {"outer": round(stock, 1), "length": 15}
        if not size:
            result["inner"] = 3.2
        if kind == "hex_male":
            result["thread_length"] = max(4, size)
        return result
    if family.group == PINS or kind == "rivet":
        return {"diameter": 3.2 if kind == "rivet" else 4, "length": 12}
    return {}


@dataclass(frozen=True)
class Part:
    kind: str
    size: float
    dimensions: dict

    @property
    def family(self):
        return FAMILIES[self.kind]

    @property
    def key(self):
        return self.kind, self.size, tuple(sorted(self.dimensions.items()))

    @property
    def name(self):
        d = self.dimensions
        if self.kind == "shoulder":
            size = f"Ø{number(d['diameter'])}×{number(d['length'])} {metric(self.size)}×{number(d['thread_length'])}"
        elif self.family.group == SPACERS:
            outer = ("S" if self.kind.startswith("hex") else "Ø") + number(d["outer"])
            inner = metric(self.size) if self.size else "Ø" + number(d["inner"])
            size = f"{outer}/{inner}×{number(d['length'])}"
            if self.kind == "hex_male":
                size += f" + {number(d['thread_length'])}"
        elif self.size:
            size = metric(self.size)
            if "length" in d:
                size += "×" + number(d["length"])
        else:
            size = f"Ø{number(d['diameter'])}×{number(d['length'])}"
        return f"{self.family.label} {size}"

    @property
    def head(self):
        if self.kind == "shoulder":
            _, _, diameter, height, key = SHOULDER[self.size]
            return max(diameter, self.dimensions["diameter"] + 0.5), height, key
        if self.kind == "cross_flat":
            return self.size * 2, self.size / 2, PAN[self.size][2]
        return TABLES[self.kind][self.size]

    @property
    def width(self):
        if self.family.group == SCREWS and self.family.head:
            return self.head[0] * (2 / sqrt(3) if self.family.head == "hex" else 1)
        if self.family.group == NUTS:
            dims = TABLES[self.kind][self.size]
            return max(dims[0] * 2 / sqrt(3), dims[2] if len(dims) > 2 else 0)
        if self.family.group == SPACERS:
            return self.dimensions["outer"] * (2 / sqrt(3) if self.kind.startswith("hex") else 1)
        if self.family.group == WASHERS:
            return TABLES[self.kind][self.size][1]
        if self.size:
            return self.size
        diameter = self.dimensions["diameter"]
        if self.kind == "taper_pin":
            return diameter + self.dimensions["length"] / 50
        return diameter * (2 if self.kind in ("clevis_pin", "rivet") else 1)


def bolt_thread_length(size, length):
    return min(length, 2 * size + (6 if length <= 125 else 12 if length <= 200 else 25))


def build_part(kind, size, dimensions):
    expected = defaults(kind, size)
    if set(dimensions) != set(expected):
        raise ValueError("当前类型的尺寸字段不完整。")
    if any(not isfinite(value) or not 0.1 <= value <= 1500 for value in dimensions.values()):
        raise ValueError("尺寸须为 0.1–1500 mm。")
    part = Part(kind, size, {key: round(value, 6) for key, value in dimensions.items()})
    d = part.dimensions
    if kind == "shoulder" and d["diameter"] <= size:
        raise ValueError("塞打光杆直径必须大于螺纹公称直径。")
    if part.family.group == SPACERS:
        if d["outer"] <= d.get("inner", size) + 0.2:
            raise ValueError("铝柱外径或对边须比内孔或螺纹公称直径至少大 0.2 mm。")
    if part.family.head == "countersunk" and d["length"] <= part.head[1] + 0.1:
        raise ValueError("沉头螺丝的总长须大于头高 0.1 mm 以上。")
    if kind.startswith("set_") and d["length"] < size * 0.5:
        raise ValueError("紧定螺丝太短，无法容纳驱动槽。")
    if kind == "clevis_pin" and d["length"] < d["diameter"]:
        raise ValueError("销轴长度须至少等于直径，以容纳横孔。")
    if kind == "hex_male" and d["length"] < max(1, size / 2):
        raise ValueError("一公一母铝柱的柱体太短，无法容纳内牙盲孔。")
    return part


def mounting_order(counts, hole_count, repeat):
    if not hole_count:
        raise ValueError("请至少选择一个完整圆形孔边。")
    if repeat:
        if any(count != hole_count for count in counts):
            raise ValueError(f"逐孔重复时，每条规格的数量须等于选中的孔数（{hole_count}）。")
        return [range(hole_count) for _ in counts]
    if sum(counts) != hole_count:
        raise ValueError(f"顺序装配需要 {sum(counts)} 个孔边，已选 {hole_count} 个。")
    result = []
    first = 0
    for count in counts:
        result.append(range(first, first + count))
        first += count
    return result
