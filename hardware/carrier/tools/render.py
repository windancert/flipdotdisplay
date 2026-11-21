"""Draw the board's copper to a PNG for a quick look (KiCad Python, uses PIL).

  "C:/Program Files/KiCad/10.0/bin/python.exe" tools/render.py out.png [net ...]
Named nets are drawn bright, everything else dimmed.
"""
import os
import sys

import pcbnew
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
board = pcbnew.LoadBoard(os.path.join(os.path.dirname(HERE), "flipdot_carrier.kicad_pcb"))
S = 10  # px per mm
bb = board.GetBoardEdgesBoundingBox()
X0, Y0 = pcbnew.ToMM(bb.GetLeft()) - 2, pcbnew.ToMM(bb.GetTop()) - 2
W, H = pcbnew.ToMM(bb.GetWidth()) + 4, pcbnew.ToMM(bb.GetHeight()) + 4
img = Image.new("RGB", (int(W * S), int(H * S)), (20, 20, 24))
d = ImageDraw.Draw(img)
focus = set(sys.argv[2:])


def P(v):
    return ((pcbnew.ToMM(v.x) - X0) * S, (pcbnew.ToMM(v.y) - Y0) * S)


def col(base, net):
    if not focus or net in focus:
        return base
    return tuple(c // 4 for c in base)


d.rectangle([P(bb.GetOrigin()), P(bb.GetEnd())], outline=(200, 200, 0))
for z in board.Zones():
    if z.GetIsRuleArea():
        continue
for fp in board.GetFootprints():
    cy = fp.GetCourtyard(pcbnew.F_CrtYd).BBox()
    d.rectangle([P(cy.GetOrigin()), P(cy.GetEnd())], outline=(70, 70, 70))
for t in board.GetTracks():
    net = t.GetNetname()
    if t.GetClass() == "PCB_VIA":
        x, y = P(t.GetPosition())
        r = pcbnew.ToMM(t.GetWidth(pcbnew.F_Cu)) / 2 * S
        d.ellipse([x - r, y - r, x + r, y + r], fill=col((220, 220, 220), net))
        continue
    c = (220, 60, 60) if t.GetLayer() == pcbnew.F_Cu else (70, 120, 255)
    d.line([P(t.GetStart()), P(t.GetEnd())], fill=col(c, net), width=max(1, int(pcbnew.ToMM(t.GetWidth()) * S)))
for fp in board.GetFootprints():
    for pad in fp.Pads():
        bbp = pad.GetBoundingBox()
        c = (230, 180, 40) if pad.GetNetname() else (110, 110, 110)
        d.ellipse([P(bbp.GetOrigin()), P(bbp.GetEnd())], fill=col(c, pad.GetNetname()))
    x, y = P(fp.GetPosition())
    d.text((x + 3, y + 3), fp.GetReference(), fill=(255, 255, 255))
img.save(sys.argv[1])
