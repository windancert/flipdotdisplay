"""Place, route and save the carrier board.

Run with KiCad's own Python, after gen_sch.py and a netlist export:
  "C:/Program Files/KiCad/10.0/bin/python.exe" tools/gen_pcb.py
"""
import json
import os
import sys
import time

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import design  # noqa: E402
from router import B, F, Router  # noqa: E402
from sexpr import find, find_all, parse  # noqa: E402

OUT = os.path.dirname(HERE)
PROJECT = "flipdot_carrier"
OX, OY = 100.0, 50.0  # board origin on the KiCad page

POWER = {"GND": (0.8, 0.25, 1.0, 0.5), "+20V": (0.8, 0.25, 1.0, 0.5),
         "/COIL_20V": (0.8, 0.25, 1.0, 0.5),
         "/VIN_BUCK": (0.6, 0.25, 1.0, 0.5), "+5V": (0.6, 0.25, 1.0, 0.5),
         "/VSYS": (0.6, 0.25, 1.0, 0.5), "+3V3": (0.6, 0.25, 1.0, 0.5)}
SIGNAL = (0.3, 0.2, 0.6, 0.3)


def mm(v):
    return pcbnew.FromMM(v)


def pt(x, y):
    return pcbnew.VECTOR2I(mm(x + OX), mm(y + OY))


def read_netlist():
    with open(os.path.join(OUT, PROJECT + ".net"), encoding="utf8") as f:
        tree = parse(f.read())
    comps = {}
    for c in find_all(find(tree, "components"), "comp"):
        ref = str(find(c, "ref")[1])
        fields = {}
        for fl in find_all(find(c, "fields") or [], "field"):
            name = str(find(fl, "name")[1])
            if name not in ("Footprint", "ki_fp_filters") and len(fl) > 2 and str(fl[2]) not in ("", "~"):
                fields[name] = str(fl[2])
        for pr in find_all(c, "property"):
            name, val = str(find(pr, "name")[1]), find(pr, "value")
            if name == "ki_keywords" and val:
                fields[name] = str(val[1])
        comps[ref] = (str(find(c, "footprint")[1]), str(find(c, "value")[1]),
                      str(find(c, "tstamps")[1]), fields)
    nets = {}
    for n in find_all(find(tree, "nets"), "net"):
        name = str(find(n, "name")[1])
        nodes = [(str(find(x, "ref")[1]), str(find(x, "pin")[1])) for x in find_all(n, "node")]
        nets[name] = nodes
    return comps, nets


def add_text(board, s, x, y, size=1.2, layer=pcbnew.F_SilkS, angle=0, bold=False):
    t = pcbnew.PCB_TEXT(board)
    t.SetText(s)
    t.SetPosition(pt(x, y))
    t.SetLayer(layer)
    t.SetTextSize(pcbnew.VECTOR2I(mm(size), mm(size)))
    t.SetTextThickness(mm(size * (0.2 if bold else 0.15)))
    t.SetTextAngleDegrees(angle)
    if layer == pcbnew.B_SilkS:
        t.SetMirrored(True)
    board.Add(t)


def build():
    comps, nets = read_netlist()
    board = pcbnew.BOARD()
    ds = board.GetDesignSettings()
    ds.SetCopperLayerCount(2)

    netinfo = {}
    for name in sorted(nets):
        ni = pcbnew.NETINFO_ITEM(board, name)
        board.Add(ni)
        netinfo[name] = ni
    pin_net = {(r, p): n for n, nodes in nets.items() for (r, p) in nodes}

    fps = {}
    for ref, _sym, _val, _fp, _nets, _sch, (x, y, rot), _extra in design.PARTS:
        fpid, value, tstamp, fields = comps[ref]
        lib, name = fpid.split(":")
        fp = pcbnew.FootprintLoad(f"{design.FP}/{lib}.pretty", name)
        fp.SetFPID(pcbnew.LIB_ID(lib, name))
        fp.SetReference(ref)
        fp.SetValue(value)
        fp.SetPosition(pt(x, y))
        fp.SetOrientationDegrees(rot)
        fp.SetPath(pcbnew.KIID_PATH("/" + tstamp))
        for k, v in fields.items():
            fp.SetField(k, v)
            fp.GetField(k).SetVisible(False)
        if ref.startswith("R"):  # reference inside the resistor body, clear of its neighbours
            f = fp.Reference()
            f.SetTextSize(pcbnew.VECTOR2I(mm(0.8), mm(0.8)))
            f.SetTextThickness(mm(0.12))
            f.SetPosition(pt(x - 5.08, y))
            f.SetTextAngleDegrees(0)
        # Test point labels say which net, and a mounting hole needs no name: no TPn or Hn clutter
        if ref.startswith("TP") or ref.startswith("H"):
            fp.Reference().SetVisible(False)
            fp.Value().SetVisible(False)
        if ref == "J3":
            fp.Reference().SetPosition(pt(77.6, 77.5))
        board.Add(fp)
        for pad in fp.Pads():
            n = pin_net.get((ref, pad.GetNumber()))
            if n:
                pad.SetNet(netinfo[n])
        fps[ref] = fp

    edge = pcbnew.PCB_SHAPE(board)
    edge.SetShape(pcbnew.SHAPE_T_RECT)
    edge.SetStart(pt(0, 0))
    edge.SetEnd(pt(design.BOARD_W, design.BOARD_H))
    edge.SetLayer(pcbnew.Edge_Cuts)
    edge.SetWidth(mm(0.1))
    board.Add(edge)
    return board, fps, netinfo, nets


def make_router(board, fps, nets):
    r = Router(design.BOARD_W, design.BOARD_H)
    r.default_rule = SIGNAL
    r.rules = dict(POWER)
    for fp in fps.values():
        for pad in fp.Pads():
            pos = pad.GetPosition()
            x, y = pcbnew.ToMM(pos.x) - OX, pcbnew.ToMM(pos.y) - OY
            net = pad.GetNetname() or None
            if pad.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH or not pad.GetNumber():
                r.add_pad(None, "circle", (x, y), hw=3.0, clr=0.0)  # M3 screw head
                continue
            clr = r.rule(net)[1] if net else 0.2
            if pad.GetShape(pcbnew.F_Cu) == pcbnew.PAD_SHAPE_CIRCLE:
                r.add_pad(net, "circle", (x, y), hw=pcbnew.ToMM(pad.GetSize(pcbnew.F_Cu).x) / 2, clr=clr)
            else:
                bb = pad.GetBoundingBox()
                x0, y0 = pcbnew.ToMM(bb.GetLeft()) - OX, pcbnew.ToMM(bb.GetTop()) - OY
                x1, y1 = pcbnew.ToMM(bb.GetRight()) - OX, pcbnew.ToMM(bb.GetBottom()) - OY
                r.add_pad(net, "rect", ((x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2, (y1 - y0) / 2), clr=clr)
        for z in fp.Zones():
            if not z.GetIsRuleArea() or not z.GetDoNotAllowTracks():
                continue
            ol = z.Outline()
            poly = [(pcbnew.ToMM(ol.CVertex(i).x) - OX, pcbnew.ToMM(ol.CVertex(i).y) - OY)
                    for i in range(ol.TotalVertices())]
            r.keepouts.append(poly)
    # The antenna end of the S3 Pico: route around it if at all possible.
    r.cost_zones.append(design.ANTENNA_AREA + (10.0,))
    r.via_keepouts.append(design.ANTENNA_AREA)
    return r


ORDER_FIRST = ["+20V", "/COIL_20V", "/VIN_BUCK", "+5V", "/VSYS", "+3V3", "/ROW_HIGH", "/ROW_LOW"]


def route_all(r, nets):
    names = [n for n in nets if n != "GND"]
    order = ORDER_FIRST + sorted(n for n in names if n not in ORDER_FIRST) + ["GND"]
    t0 = time.time()
    failed = r.route_all(order, log=lambda m: print(m, flush=True))
    print(f"routing took {time.time() - t0:.0f}s", flush=True)
    return failed, order


def emit(board, r, netinfo):
    layer = {F: pcbnew.F_Cu, B: pcbnew.B_Cu}
    for net, ni in netinfo.items():
        w, _clr, vd, vdrill = r.rule(net)
        for (L, x0, y0, x1, y1) in r.segments(net):
            t = pcbnew.PCB_TRACK(board)
            t.SetStart(pt(x0, y0))
            t.SetEnd(pt(x1, y1))
            t.SetWidth(mm(w))
            t.SetLayer(layer[L])
            t.SetNet(ni)
            board.Add(t)
        for (x, y) in r.via_points(net):
            v = pcbnew.PCB_VIA(board)
            v.SetPosition(pt(x, y))
            v.SetViaType(pcbnew.VIATYPE_THROUGH)
            v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
            try:
                v.SetWidth(mm(vd))
            except TypeError:
                v.SetWidth(pcbnew.F_Cu, mm(vd))
            v.SetDrill(mm(vdrill))
            v.SetNet(ni)
            board.Add(v)


def add_gnd_pour(board, netinfo):
    for lay in (pcbnew.B_Cu, pcbnew.F_Cu):
        z = pcbnew.ZONE(board)
        z.SetLayer(lay)
        z.SetNet(netinfo["GND"])
        z.SetLocalClearance(mm(0.3))
        z.SetMinThickness(mm(0.25))
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
        z.SetThermalReliefGap(mm(0.5))
        z.SetThermalReliefSpokeWidth(mm(0.6))
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
        z.SetAssignedPriority(0)
        ol = z.Outline()
        ol.NewOutline()
        for (x, y) in [(0, 0), (design.BOARD_W, 0), (design.BOARD_W, design.BOARD_H), (0, design.BOARD_H)]:
            ol.Append(mm(x + OX), mm(y + OY))
        board.Add(z)
    ka = pcbnew.ZONE(board)
    ka.SetIsRuleArea(True)
    ka.SetZoneName("Antenna keep-out")
    ls = pcbnew.LSET()
    ls.AddLayer(pcbnew.F_Cu)
    ls.AddLayer(pcbnew.B_Cu)
    ka.SetLayerSet(ls)
    ka.SetDoNotAllowZoneFills(True)
    ka.SetDoNotAllowVias(True)
    ka.SetDoNotAllowTracks(False)
    ka.SetDoNotAllowPads(False)
    ka.SetDoNotAllowFootprints(False)
    x0, y0, x1, y1 = design.ANTENNA_AREA
    ol = ka.Outline()
    ol.NewOutline()
    for (x, y) in [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]:
        ol.Append(mm(x + OX), mm(y + OY))
    board.Add(ka)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())


def add_silk(board):
    add_text(board, "RIBBON B  COL-SEL 4-7", 13.5, 36.0, 1.0, angle=90)
    add_text(board, "RIBBON A  COL-SEL 0-3", 96.0, 36.0, 1.0, angle=90)
    add_text(board, "20V IN", 86.36, 69.6, 1.0)
    add_text(board, "+", 83.82, 71.6, 1.5, bold=True)
    add_text(board, "-", 88.9, 71.6, 1.5, bold=True)
    add_text(board, "USB", 52.71, 26.0, 1.0)
    add_text(board, "ANTENNA END", 52.71, 84.0, 0.8)
    for net, label, x, y in design.TESTPOINTS:
        if y < 10:
            add_text(board, label, x, y + 3.2, 0.8)
        else:
            add_text(board, label, x + 4.0, y, 0.8)
    add_text(board, "FLIPDOT S3 PICO DRIVER", 14.5, 62.0, 1.2, bold=True)
    add_text(board, "rev A  2026-11", 14.5, 64.4, 1.0)
    add_text(board, "20 V NEVER ON S3 PICO VSYS", 14.5, 66.4, 0.8)


def write_project():
    path = os.path.join(OUT, PROJECT + ".kicad_pro")
    try:
        with open(path) as f:
            pro = json.load(f)
    except (OSError, ValueError):
        pro = {}
    pro.setdefault("meta", {})["filename"] = PROJECT + ".kicad_pro"
    pro["meta"]["version"] = 3

    def cls(name, w, clr, vd, vdrill, prio):
        return {"name": name, "clearance": clr, "track_width": w, "via_diameter": vd,
                "via_drill": vdrill, "microvia_diameter": 0.3, "microvia_drill": 0.1,
                "diff_pair_width": 0.2, "diff_pair_gap": 0.25, "diff_pair_via_gap": 0.25,
                "bus_width": 12, "wire_width": 6, "line_style": 0,
                "pcb_color": "rgba(0, 0, 0, 0.000)", "schematic_color": "rgba(0, 0, 0, 0.000)",
                "priority": prio}
    pro["net_settings"] = {
        "classes": [cls("Default", *SIGNAL, 2147483647), cls("Power", 0.8, 0.25, 1.0, 0.5, 0)],
        "meta": {"version": 4},
        "net_colors": None,
        "netclass_assignments": None,
        "netclass_patterns": [{"netclass": "Power", "pattern": n} for n in POWER],
    }
    board = pro.setdefault("board", {})
    dset = board.setdefault("design_settings", {})
    dset["rules"] = {
        "min_clearance": 0.2, "min_copper_edge_clearance": 0.5, "min_track_width": 0.25,
        "min_via_diameter": 0.6, "min_via_annular_width": 0.13, "min_through_hole_diameter": 0.3,
        "min_hole_clearance": 0.25, "min_hole_to_hole": 0.25, "min_silk_clearance": 0.0,
        "min_text_height": 0.8, "min_text_thickness": 0.08,
        # every GND pad also has a routed track, so one spoke into the pour is enough
        "min_resolved_spokes": 1,
    }
    # KiCad 10 drops a footprint's ki_fp_filters field when it loads a board, so the
    # schematic parity check always reports it missing. Nothing else uses this check.
    dset.setdefault("rule_severities", {})["footprint_symbol_field_mismatch"] = "ignore"
    dset["track_widths"] = [0.0, 0.3, 0.6, 0.8]
    dset["via_dimensions"] = [{"diameter": 0.0, "drill": 0.0}, {"diameter": 0.6, "drill": 0.3},
                              {"diameter": 1.0, "drill": 0.5}]
    pro.setdefault("libraries", {"pinned_footprint_libs": [], "pinned_symbol_libs": []})
    with open(path, "w", newline="\n") as f:
        json.dump(pro, f, indent=2)


def main():
    board, fps, netinfo, nets = build()
    r = make_router(board, fps, nets)
    failed, order = route_all(r, nets)
    emit(board, r, netinfo)
    add_gnd_pour(board, netinfo)
    add_silk(board)
    tb = board.GetTitleBlock()
    tb.SetTitle("Flipdot S3 Pico driver")
    tb.SetRevision("A")
    tb.SetDate("2026-11-21")
    board.SetTitleBlock(tb)
    path = os.path.join(OUT, PROJECT + ".kicad_pcb")
    pcbnew.SaveBoard(path, board)
    write_project()
    print("route order:", order)
    print("unrouted:", failed)


if __name__ == "__main__":
    main()
