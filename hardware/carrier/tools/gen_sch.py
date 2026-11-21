"""Generate the carrier board schematic and its project symbol library.

Every pin gets a short wire stub ending in a net label or power symbol, so the
schematic reads as a netlist. Run with any Python 3:  python gen_sch.py
"""
import copy
import os
import uuid

import design
from sexpr import QStr, dump, find, find_all, parse, q

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.dirname(HERE)
KICAD_SYM = "C:/Program Files/KiCad/10.0/share/kicad/symbols"
PROJECT = "flipdot_carrier"
SCH_VERSION = "20250114"

_ns = uuid.UUID("5d0c8a52-61b6-4a33-9a39-9f3b0e0b2f10")


def uid(*key):
    """Stable UUIDs, so regenerating does not churn the files."""
    return QStr(str(uuid.uuid5(_ns, "/".join(str(k) for k in key))))


ROOT = uid("root")
_libs = {}


def lib(name):
    if name not in _libs:
        with open(f"{KICAD_SYM}/{name}.kicad_sym", encoding="utf8") as f:
            tree = parse(f.read())
        _libs[name] = {s[1]: s for s in find_all(tree, "symbol")}
    return _libs[name]


def flatten(libname, name):
    syms = lib(libname)
    node = copy.deepcopy(syms[name])
    ext = find(node, "extends")
    if not ext:
        return node
    parent = flatten(libname, ext[1])
    props = find_all(node, "property")
    out = [x for x in parent if not (isinstance(x, list) and x[0] == "property")]
    out[1] = QStr(name)
    for x in out:
        if isinstance(x, list) and x[0] == "symbol":
            x[1] = QStr(x[1].replace(parent[1], name, 1))
    # properties go right after the flags, before the drawing units
    idx = next(i for i, x in enumerate(out) if isinstance(x, list) and x[0] == "symbol")
    return out[:idx] + props + out[idx:]


def font(hide=False, justify=None):
    e = ["effects", ["font", ["size", 1.27, 1.27]]]
    if justify:
        e.append(["justify"] + justify)
    if hide:
        e.append(["hide", "yes"])
    return e


def prop(name, value, x, y, hide=False, n=0):
    return ["property", q(name), q(value), ["at", x, y, 0], font(hide)]


def pico_symbol():
    pins = []
    for n in range(1, 41):
        name = design.PICO_PIN_NAMES.get(n, "~")
        if n <= 20:
            at = ["at", -17.78, round(24.13 - (n - 1) * 2.54, 2), 0]
        else:
            at = ["at", 17.78, round(24.13 - (40 - n) * 2.54, 2), 180]
        pins.append(["pin", "passive", "line", at, ["length", 5.08],
                     ["name", q(name), font()], ["number", q(str(n)), font()]])
    return ["symbol", q("ESP32-S3-Pico"),
            ["pin_names", ["offset", 1.016]],
            ["exclude_from_sim", "no"], ["in_bom", "yes"], ["on_board", "yes"],
            ["property", q("Reference"), q("U"), ["at", 0, 29.21, 0], font()],
            ["property", q("Value"), q("ESP32-S3-Pico"), ["at", 0, -29.21, 0], font()],
            ["property", q("Footprint"), q("Module:RaspberryPi_Pico_Common_THT"),
             ["at", 0, -31.75, 0], font(True)],
            ["property", q("Datasheet"), q("https://www.waveshare.com/wiki/ESP32-S3-Pico"),
             ["at", 0, -34.29, 0], font(True)],
            ["property", q("Description"),
             q("Waveshare ESP32-S3-Pico, Raspberry Pi Pico header numbering, top view, USB at the top"),
             ["at", 0, -36.83, 0], font(True)],
            ["symbol", q("ESP32-S3-Pico_0_1"),
             ["rectangle", ["start", -12.7, 26.67], ["end", 12.7, -26.67],
              ["stroke", ["width", 0.254], ["type", "default"]], ["fill", ["type", "background"]]],
             ["text", q("USB"), ["at", 0, 24.13, 0], font()]],
            ["symbol", q("ESP32-S3-Pico_1_1")] + pins]


def plus20_symbol():
    node = flatten("power", "+24V")
    node[1] = QStr("+20V")
    for p in find_all(node, "property"):
        if p[1] == "Value":
            p[2] = QStr("+20V")
        if p[1] == "Description":
            p[2] = QStr('Power symbol creates a global label with name "+20V"')
    for x in node:
        if isinstance(x, list) and x[0] == "symbol":
            x[1] = QStr(x[1].replace("+24V", "+20V", 1))
            for p in find_all(x, "pin"):
                nm = find(p, "name")
                if nm and nm[1] == "+24V":
                    nm[1] = QStr("+20V")
    return node


PROJECT_SYMBOLS = {"ESP32-S3-Pico": pico_symbol(), "+20V": plus20_symbol()}


def get_symbol(lib_id):
    libname, name = lib_id.split(":")
    if libname == "flipdot":
        return copy.deepcopy(PROJECT_SYMBOLS[name])
    return flatten(libname, name)


def pins_of(sym):
    out = []
    for sub in find_all(sym, "symbol"):
        unit = sub[1].rsplit("_", 2)[-2]
        if unit not in ("0", "1"):
            continue
        for p in find_all(sub, "pin"):
            at = find(p, "at")
            out.append((str(find(p, "number")[1]), float(at[1]), float(at[2]), int(float(at[3]))))
    return out


class Sheet:
    def __init__(self):
        self.lib_symbols = {}
        self.items = []
        self.pwr_n = 0

    def use(self, lib_id):
        if lib_id not in self.lib_symbols:
            sym = get_symbol(lib_id)
            sym[1] = QStr(lib_id)
            self.lib_symbols[lib_id] = sym
        return self.lib_symbols[lib_id]

    def place(self, lib_id, ref, value, x, y, footprint=None, extra=None, rot=0):
        sym = self.use(lib_id)
        node = ["symbol", ["lib_id", q(lib_id)], ["at", x, y, rot], ["unit", 1],
                ["exclude_from_sim", "no"],
                ["in_bom", find(sym, "in_bom")[1] if find(sym, "in_bom") else "yes"],
                ["on_board", "yes"], ["dnp", "no"], ["uuid", uid("sym", ref)]]
        for p in find_all(sym, "property"):
            name = str(p[1])
            at = find(p, "at")
            val = {"Reference": ref, "Value": value}.get(name, p[2])
            if name == "Footprint" and footprint:
                val = footprint
            eff = copy.deepcopy(find(p, "effects"))
            node.append(["property", q(name), q(val),
                         ["at", round(x + float(at[1]), 2), round(y - float(at[2]), 2), 0], eff])
        for k, v in (extra or {}).items():
            node.append(["property", q(k), q(v), ["at", x, y, 0], font(True)])
        for num, *_ in pins_of(sym):
            node.append(["pin", q(num), ["uuid", uid("pin", ref, num)]])
        node.append(["instances", ["project", q(PROJECT),
                                   ["path", q("/" + ROOT), ["reference", q(ref)], ["unit", 1]]]])
        self.items.append(node)
        return sym

    def wire(self, x1, y1, x2, y2):
        self.items.append(["wire", ["pts", ["xy", x1, y1], ["xy", x2, y2]],
                           ["stroke", ["width", 0], ["type", "default"]],
                           ["uuid", uid("wire", x1, y1, x2, y2)]])

    def label(self, net, x, y, ang):
        just = {0: ["left", "bottom"], 90: ["left", "bottom"],
                180: ["right", "bottom"], 270: ["right", "bottom"]}[ang]
        self.items.append(["label", q(net), ["at", x, y, ang],
                           ["effects", ["font", ["size", 1.27, 1.27]], ["justify"] + just],
                           ["uuid", uid("label", net, x, y)]])

    def power(self, net, x, y):
        self.pwr_n += 1
        lib_id = "flipdot:+20V" if net == "+20V" else f"power:{net}"
        self.place(lib_id, f"#PWR{self.pwr_n:02d}", net, x, y)

    def flag(self, x, y):
        self.pwr_n += 1
        self.place("power:PWR_FLAG", f"#FLG{self.pwr_n:02d}", "PWR_FLAG", x, y)

    def no_connect(self, x, y):
        self.items.append(["no_connect", ["at", x, y], ["uuid", uid("nc", x, y)]])

    def text(self, s, x, y, size=1.27):
        self.items.append(["text", q(s), ["exclude_from_sim", "no"], ["at", x, y, 0],
                           ["effects", ["font", ["size", size, size]], ["justify", "left", "bottom"]],
                           ["uuid", uid("text", s)]])

    def connect_pins(self, sym, x, y, nets):
        # outward direction for each lib pin angle (sheet coordinates, y down)
        out_dir = {0: (-1, 0), 180: (1, 0), 90: (0, 1), 270: (0, -1)}
        label_ang = {0: 180, 180: 0, 90: 270, 270: 90}
        for num, px, py, ang in pins_of(sym):
            sx, sy = round(x + px, 2), round(y - py, 2)
            net = nets.get(int(num)) if num.isdigit() else None
            if net is None:
                self.no_connect(sx, sy)
                continue
            dx, dy = out_dir[ang]
            ex, ey = round(sx + dx * 2.54, 2), round(sy + dy * 2.54, 2)
            self.wire(sx, sy, ex, ey)
            if net in design.POWER_NETS:
                self.power(net, ex, ey)
            else:
                self.label(net, ex, ey, label_ang[ang])

    def write(self, path):
        doc = ["kicad_sch", ["version", SCH_VERSION], ["generator", q("eeschema")],
               ["generator_version", q("10.0")], ["uuid", ROOT], ["paper", q("A3")],
               ["title_block", ["title", q("Flip-dot carrier board")], ["date", q("2026-11-21")],
                ["rev", q("A")],
                ["comment", 1, q("Waveshare ESP32-S3-Pico to two Mobitec ribbons, 20 V coil rail")]],
               ["lib_symbols"] + list(self.lib_symbols.values())]
        doc += self.items
        doc.append(["sheet_instances", ["path", q("/"), ["page", q("1")]]])
        doc.append(["embedded_fonts", "no"])
        with open(path, "w", encoding="utf8", newline="\n") as f:
            f.write(dump(doc) + "\n")


def write_project_lib(path):
    doc = ["kicad_symbol_lib", ["version", "20251024"], ["generator", q("kicad_symbol_editor")],
           ["generator_version", q("10.0")]]
    for name, sym in PROJECT_SYMBOLS.items():
        doc.append(copy.deepcopy(sym))
    with open(path, "w", encoding="utf8", newline="\n") as f:
        f.write(dump(doc) + "\n")


def main():
    sh = Sheet()
    for ref, lib_id, value, fp, nets, (x, y), _board, extra in design.PARTS:
        sym = sh.place(lib_id, ref, value, x, y, footprint=fp, extra=extra)
        sh.connect_pins(sym, x, y, nets or {})

    # PWR_FLAGs: these nets have power-input pins but no power-output pin to drive them.
    for i, net in enumerate(["GND", "+20V", "+3V3"]):
        x, y = 30.48 + i * 15.24, 86.36
        sh.flag(x, y)
        sh.power(net, x, y)
    x, y = 76.2, 86.36
    sh.flag(x, y)
    sh.label("VIN_BUCK", x, y, 0)

    sh.text("Power: 20 V from the USB-C PD trigger module (Joy-IT ZY12PDN, set to 20 V) into J3.\n"
            "+20V goes straight to the coils (ribbon pin 26). D2 and the R-78E make 5 V for the Pico;\n"
            "D3 lets the Pico's own USB-C stay plugged in for flashing. NEVER 20 V on VSYS.",
            25.4, 27.94)
    sh.text("ESP32-S3-Pico pins: Raspberry Pi Pico numbering, see firmware/README.md.\n"
            "GND pins 8, 13, 18, 23, 28 and 33 are joined on the Pico itself and left unconnected here.\n"
            "Pin 18 is next to the antenna, kept clear of copper.",
            63.5, 185.42)
    sh.text("Test points: Keystone 5000-series miniature loops.", 50.8, 266.7)
    sh.text("10k pull-downs: hold every COL-SEL line and both strobes low while the ESP32 boots.",
            50.8, 226.06)
    sh.text("Ribbon pins 6 and 7 are crossed on the panel (6 = ROW2, 7 = ROW1).\n"
            "Ribbon A feeds COL-SEL0-3, ribbon B COL-SEL4-7; everything else is shared.",
            198.12, 66.04)
    sh.write(os.path.join(OUT, PROJECT + ".kicad_sch"))
    write_project_lib(os.path.join(OUT, "flipdot.kicad_sym"))
    with open(os.path.join(OUT, "sym-lib-table"), "w", newline="\n") as f:
        f.write('(sym_lib_table\n\t(version 7)\n\t(lib (name "flipdot")(type "KiCad")'
                '(uri "${KIPRJMOD}/flipdot.kicad_sym")(options "")(descr "Flip-dot carrier symbols"))\n)\n')


if __name__ == "__main__":
    main()
