"""Rebuild the whole carrier board: schematic, ERC, netlist, board (placed and
routed), DRC, and the fabrication files.

  python tools/build.py           everything
  python tools/build.py --no-pcb  schematic and ERC only (the board takes ~1.5 min)

Needs KiCad 10 at its default install path. The generated board replaces
flipdot_carrier.kicad_pcb: hand edits to it are lost on the next full build.
"""
import os
import shutil
import subprocess
import sys
import zipfile

KICAD = "C:/Program Files/KiCad/10.0/bin"
CLI = f"{KICAD}/kicad-cli.exe"
KPY = f"{KICAD}/python.exe"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.dirname(HERE)
P = "flipdot_carrier"


def run(*args):
    print("+", " ".join(os.path.basename(a) if i == 0 else a for i, a in enumerate(args)), flush=True)
    r = subprocess.run(args, cwd=OUT, capture_output=True, text=True)
    out = (r.stdout + r.stderr).strip()
    if out:
        print("  " + out.replace("\n", "\n  "))
    if r.returncode:
        sys.exit(r.returncode)
    return out


def main():
    run(sys.executable, os.path.join(HERE, "gen_sch.py"))
    erc = run(CLI, "sch", "erc", "--exit-code-violations", "-o", "erc.rpt", P + ".kicad_sch")
    run(CLI, "sch", "export", "netlist", "-o", P + ".net", P + ".kicad_sch")
    run(CLI, "sch", "export", "pdf", "-o", P + "_schematic.pdf", P + ".kicad_sch")
    if "--no-pcb" in sys.argv:
        return
    run(KPY, os.path.join(HERE, "gen_pcb.py"))
    run(CLI, "pcb", "drc", "--schematic-parity", "--exit-code-violations", "-o", "drc.rpt", P + ".kicad_pcb")

    fab = os.path.join(OUT, "fab")
    shutil.rmtree(fab, ignore_errors=True)
    os.makedirs(fab)
    run(CLI, "pcb", "export", "gerbers", "-o", "fab/", "--layers",
        "F.Cu,B.Cu,F.Mask,B.Mask,F.Silkscreen,B.Silkscreen,Edge.Cuts", P + ".kicad_pcb")
    run(CLI, "pcb", "export", "drill", "-o", "fab/", "--format", "excellon",
        "--excellon-separate-th", P + ".kicad_pcb")
    with zipfile.ZipFile(os.path.join(OUT, P + "_gerbers.zip"), "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(os.listdir(fab)):
            z.write(os.path.join(fab, f), f)
    shutil.rmtree(fab)
    run(CLI, "pcb", "export", "pdf", "-o", P + "_layout.pdf", "--layers",
        "F.Cu,B.Cu,F.Silkscreen,Edge.Cuts", "--mode-single", P + ".kicad_pcb")
    print("done: erc.rpt, drc.rpt,", P + "_gerbers.zip,", P + "_schematic.pdf,", P + "_layout.pdf")


if __name__ == "__main__":
    main()
