# Flipdot S3 driver, rev A

A two-layer board that replaces the breadboard: it holds the Waveshare ESP32-S3-Pico in
sockets, the two ribbon headers, the 10k pull-downs and the 20 V / 5 V power stage. The
circuit is the bench wiring from `firmware/README.md` plus the module power plan in
`CLAUDE.md`, so the firmware does not change. Everything is through-hole and can be
soldered by hand. Board size 111 x 85 mm, four M3 holes.

Layout: ribbon B (COL-SEL4-7) on the left edge and ribbon A (COL-SEL0-3) on the right,
matching where each chain starts on the display: the top row's chain starts at its left
end, and the bottom row is rotated, so its chain starts at the right end. The Pico sits
upright in the middle, USB towards the top edge, antenna at the bottom edge pointing away
from the panels. The pull-downs are between the left header and the Pico, the power stage
below the shared lines on the right, with the 20 V screw terminal on the bottom edge.

Status: designed and checked by KiCad (ERC and DRC clean, the board matches the
schematic), **not yet ordered or built**.

## Files

| File | What |
|------|------|
| `flipdot_carrier.kicad_pro` | open this in KiCad 10 |
| `flipdot_carrier.kicad_sch` | schematic |
| `flipdot_carrier.kicad_pcb` | board, placed and routed |
| `flipdot_carrier_schematic.pdf`, `flipdot_carrier_layout.pdf` | for viewing without KiCad |
| `flipdot_carrier_gerbers.zip` | the file a board maker needs |
| `flipdot.kicad_sym` | project symbols: the ESP32-S3-Pico and a +20V power symbol |
| `tools/` | the generator that makes all of the above (see the end) |

## Parts

| Ref | Qty | Part | Notes |
|-----|-----|------|-------|
| U1 | 1 | Waveshare ESP32-S3-Pico | plugs in, not soldered |
| - | 2 | 1x20 female header, 2.54 mm | the Pico's socket |
| - | 2 | 1x20 male pin header, 2.54 mm | soldered to the Pico, if it has none |
| J1, J2 | 2 | 2x13 shrouded box header, 2.54 mm, straight | ribbon A (COL-SEL0-3), ribbon B (COL-SEL4-7) |
| J3 | 1 | 2-pole screw terminal, 5.08 mm pitch | 20 V in, from the PD trigger module |
| U2 | 1 | Recom R-78E5.0-1.0 | 5 V buck, SIP-3 |
| D1 | 1 | SA24A, DO-15 | unidirectional TVS, through-hole version of the SMBJ24A |
| D2, D3 | 2 | 1N5819, DO-41 | Schottky; replace the SS34 and SS14 of the module plan |
| C1 | 1 | 470 uF, 35 V or higher, radial, 12.5 mm max diameter, 5 mm lead spacing | coil rail bulk |
| C2 | 1 | 4.7 uF, 50 V, radial, 5 mm diameter, 2 mm lead spacing | buck input |
| C3 | 1 | 100 uF, 16 V, radial, 6.3 mm diameter, 2.5 mm lead spacing | buck output (keep under 220 uF) |
| C4, C5 | 2 | 100 nF ceramic, 5 mm lead spacing | 3.3 V decoupling at each ribbon header |
| R1-R10 | 10 | 10k, 1/4 W | pull-downs: R1-R8 on COL-SEL0-7, R9 ROW-HIGH, R10 ROW-LOW |
| TP1-TP12 | 12 | Keystone 5000-series miniature test point (5000 red, 5001 black, 5003 orange, 5004 yellow) | suggested: red 20V, black GND, orange 5V/VSYS/3V3, yellow signals |
| - | 1 | Joy-IT COM-ZY12PDN-ST (Reichelt DEBO USB-PD 1) | off the board, two wires to J3 |

## Before ordering

1. **Pico row spacing.** Confirmed: the Waveshare board's pin rows measure 17.8 mm
   apart, matching the Raspberry Pi Pico footprint (17.78 mm), pin 1 next to USB.
2. **Antenna end.** Confirmed: the Pico's antenna is on the short edge opposite USB,
   between the pins for GPIO39/40 and GPIO41/42. That end sits at the board's bottom
   edge (marked ANTENNA END). From the GPIO38 pin down to the board edge, across the
   Pico's width plus a margin, there is no ground fill and no vias on either layer; the
   only copper is the four signal pins there and the tracks that reach them from the
   sides. The Pico's GND pin 18 is left unconnected for the same reason.
3. **Ribbon pin 1.** The triangle on the silkscreen next to each header marks pin 1.
   Pin 1 is GND, pin 26 is 20 V. With the ribbons crimped as on the bench (pin 1 to
   pin 1), the red stripe goes on the triangle side.

## Test points

Labelled loops for a meter probe or a scope clip:

| Where | Test points |
|-------|-------------|
| top edge, left of the USB plug | R-HI, R-LO (the two strobes), ROW4, COL4 (top address bits), SEL0, SEL4 (first panel on each ribbon) |
| top edge, right of the USB plug | 3V3, GND |
| power corner, bottom right | 20V, 5V, VSYS, GND |

The strobes are the ones to watch on a scope: each pulse should be about 260 us, never
more than the firmware's 400 us ceiling.

## Ordering

Planned maker: **Aisler** (Germany), 2-layer standard boards. Aisler reads KiCad files
directly: upload `flipdot_carrier.kicad_pcb` (or `flipdot_carrier_gerbers.zip`) and check
its preview of both sides. The tightest rules used are 0.2 mm clearance, 0.3 mm tracks
and 0.3 mm via holes, within every maker's standard process. Parts from Reichelt.

Order only after the 20 V charger test (see CLAUDE.md, Power): if the charger does not
settle on 20 V with ~490 uF on the module's output, the board needs a coil-rail switch.

## Assembly

Solder the lowest parts first so the board lies flat on the bench:

1. R1-R10 (either way round).
2. D1, D2, D3: the band is the cathode, the silkscreen marks it with a K.
3. C4, C5 (either way round).
4. The two 1x20 female headers for the Pico. Plug the Pico into them first so they line
   up, then solder.
5. J1, J2: the notch in the shroud goes on the side the silkscreen outline shows.
6. C1, C2, C3: the long leg is +, the stripe on the can is -, the silkscreen marks +.
7. U2: pin 1 (+Vin, marked on the module) in the leftmost hole, the body over its
   silkscreen outline.
8. J3: the wire openings face the bottom edge.

## First power-up

With the Pico **out** of its socket and no ribbons connected:

1. Set the PD trigger to 20 V (LED dark blue) and connect it to J3: + on the left,
   - on the right, as marked.
2. Measure against a GND test point:
   - 20V test point, J1 pin 26 and J2 pin 26: about 20 V.
   - 5V test point: about 5 V.
   - VSYS test point (also socket pin 39, right-hand row, second from the top):
     about 4.7 V (5 V minus the diode). **If this reads 20 V, stop.**
   - Every other socket pin: 0 V.
3. Unplug, insert the Pico (USB towards the top edge), power up again. The
   status LED should go blue, then yellow and green as on the bench. The 3V3 test
   point should now read about 3.3 V.
4. Unpower, then connect one ribbon between the board and a panel and check its
   orientation with a continuity meter, still unpowered: J3 - to the panel's ground
   plane (or its ribbon pin 1 or 2) must beep, J3 + to the panel's ground must not.
   A plug the wrong way round puts 20 V on the panel's ground pins. Repeat for the
   other ribbon, then power up.

## Regenerating

The schematic and board are generated by `tools/` and can be rebuilt with:

```sh
python tools/build.py
```

It needs KiCad 10 installed at its default path. It regenerates the schematic, runs ERC,
places and routes the board (about a minute and a half), runs DRC, and writes the
Gerbers and PDFs.

- `tools/design.py` holds the parts, their connections and their positions on the board.
- `tools/gen_sch.py` writes the schematic, `tools/gen_pcb.py` the board, using
  `tools/router.py`, a small autorouter.
- `tools/render.py out.png` draws the copper to a PNG for a quick look.

A rebuild overwrites the `.kicad_pcb`. To edit the board by hand in KiCad, do that from
then on and stop using `build.py` for the board; `python tools/build.py --no-pcb` still
rebuilds only the schematic.
