# Flip-dot P2000 display

Wall display in the living room showing Dutch P2000 fire-service dispatch messages,
built from second-hand Mobitec bus destination panels.

## Panel hardware

Mobitec flip-dot panel ("mobitec" on silkscreen; board number reads approximately
WA10067, uncertain; test stamp 981103, so late-1998 production).

- 28 columns x 16 rows = 448 dots, 10 mm pitch
- Board 19 x 28 cm; the dot field is ~16 x 28 cm, leaving a ~30 mm bare PCB strip
  along ONE long edge carrying the driver ICs
- Dots are magnetically latching: they hold state with zero power
- Designed for logic 5 V, coils 24 V, both arriving over the ribbon. Verified to work
  with logic at 3.3 V and coils at 20 V (see Status)

ICs (all confirmed from photos):
- 74HC4514 (Philips) - 4-to-16 decoder with input latches, 1-of-7 row/column select
- 74HC138 (Philips) - 3-to-8 decoder, selects which 4514 bank from the high address bits
- 74HC02 (National MM74HC02M) - NOR, polarity interlock preventing shoot-through
- TD62783A - 8ch high-voltage SOURCE driver (marking "783A"), TTL input threshold, VIN(ON) 2.0 V min
- TD62083AG - 8ch Darlington SINK driver (marking "083AG")
- BAV99 (SOT-23 "A7") dual diode, 4.7uF/16V tantalums, 22k and 0R resistors

There is NO microcontroller and NO RS-485 transceiver on the panel. It is a dumb
address-driven H-bridge matrix.

## Electrical (measured, not estimated)

- Coil DC resistance: **16 ohm** (measured)
- Coil inductance: ~4.6 mH (derived from current measurements, not measured directly)
- L/R time constant ~290 us, so a 200 us pulse reaches only ~1/3 of the DC asymptote
- Peak instantaneous current at end of a 200 us pulse: ~0.75 A
- Average during continuous full-panel sweeping: **0.25 A at 24 V** (measured, stable,
  observed repeatedly). This is a hard ceiling; normal use is far lower.
- Full-panel sweep: 448 dots in ~150 ms, i.e. ~335 us per dot
- Only ONE coil is ever energised at a time, so current does NOT scale with panel count
- The RL model (16 ohm, 290 us) predicts ~83 uC per 200 us pulse at 24 V, i.e. 0.25 A
  at one dot per 335 us, matching the measured sweep current. It ignores the voltage
  lost in the panel's drivers, though, and at 20 V with 260 us it overestimates the
  measured sweep current by about a quarter (below), so treat it as an upper bound.
- At **20 V** (the planned USB-C PD supply): peak 0.62 A at the end of a 200 us pulse,
  ~70 uC per flip, ~0.21 A for continuous sweeping (model). Measured on the S3 bench
  during a diagonal wipe: at most 0.04 A on the bench supply (its finest resolution),
  consistent with the model's ~0.02 A per 250 ms frame. A stuck 400 us pulse (the
  firmware ceiling) would peak at ~0.94 A.
- The firmware now pulses 260 us (see Status): at 20 V that peaks at ~0.74 A, the same
  as 200 us at 24 V, with ~110 uC per flip, so ~0.33 A for continuous sweeping (model).
  **Measured** on the 2 x 2 bench, alternating the whole display yellow/black at full
  speed (1792 dots per 0.62 s redraw): 0.24-0.25 A at 20.2 V, supply in CV (not
  limiting). The model overestimates by about a quarter here. Likely causes, not
  verified: the panel's source and sink drivers drop a few volts, so the coil sees
  less than the rail, and the real time between dots exceeds the 335 us minimum.

DANGER: 24 V across 16 ohm continuously is 36 W (25 W at 20 V) in a coil the size of a
shirt button.
A hung controller holding a strobe destroys that dot within seconds. Firmware MUST
enforce a hard pulse-width ceiling, and outputs must be inactive at reset/power-up.

## Ribbon pinout (26-way, 2x13 IDC)

Source: https://github.com/prefixFelix/mobitec-flipdot (docs/img/26pin.png)

| Pin | Signal | Pin | Signal |
|-----|--------|-----|--------|
| 1   | GND    | 2   | GND |
| 3   | 5V     | 4   | (5V, optional) |
| 5   | ROW0   | 6   | ROW2 |
| 7   | ROW1   | 8   | ROW3 |
| 9   | ROW4   | 10  | ROW-HIGH |
| 11  | ROW-LOW| 12  | n/c |
| 13  | COL0   | 14  | COL1 |
| 15  | COL2   | 16  | COL3 |
| 17  | COL4   | 18  | COL-H/L |
| 19  | COL-SEL0 | 20 | COL-SEL1 |
| 21  | COL-SEL2 | 22 | COL-SEL3 |
| 23  | COL-SEL4 | 24 | COL-SEL5 (n/c in the source, see below) |
| 25  | n/c    | 26  | 24 V |

NOTE: pins 6 and 7 are crossed (6 = ROW2, 7 = ROW1). Everything else runs in order.

Each panel has two of these headers, an input (towards the controller) and an output
(towards the next panel); see "Panel select" below for how to tell them apart. The
source pinout lists pin 24 as n/c, but on the input header it carries a sixth select
position through to the output.

Orientation fingerprint: pins 1+2 are the only adjacent pair both common with the
ground plane. Pins 12, 24 and 25 are the only pads with no track at all, and they sit
asymmetrically (12 and 24 in the even row, 25 in the odd row), which identifies both
the low-numbered end and which row is odd. This cannot hold on the INPUT header, where
pin 24 is tracked to output pin 23; it is expected to hold on the output header only.

## Addressing scheme

Five address bits each for row and column, split 2 + 3:
- low 3 bits select 1-of-7 within a bank; `0b000` selects NOTHING (safe idle)
- high 2 bits select which bank of 7

```c
uint8_t addr(uint8_t n) { return ((n / 7) << 3) | ((n % 7) + 1); }
```

Rows 0-15 (3 banks, 5 positions unused), columns 0-27 (4 banks exactly).

Colour is current direction through the coil:
- yellow: COL-H/L low, pulse ROW-HIGH
- black:  COL-H/L high, pulse ROW-LOW

### Panel select

COL-SEL selects which panel on a shared chain responds, one-hot: one line per panel,
one line high at a time. Every panel listens only to pin 19 of its INPUT header, and
the panel passes the remaining select lines to its OUTPUT header shifted down by one
(measured, 0 ohm):

| Input pin | Output pin |
|-----------|------------|
| 19 | - (this panel's own select, does not continue) |
| 20 | 19 |
| 21 | 20 |
| 22 | 21 |
| 23 | 22 |
| 24 | 23 |

So all panels are identical and a panel's position in the chain sets its address: the
first panel answers on the controller's COL-SEL0, the next on COL-SEL1, and so on. The
input pins 19-24 give **6 select positions per ribbon chain** (the source pinout's
limit of 5 comes from listing pin 24 as n/c). Unlike the row and column lines, which
carry a binary address decoded on every panel, one line per panel needs no address
setting on the panels.

Telling input from output (unpowered, continuity meter): the header whose pin 19 has
no connection to any pin of the other header is the INPUT; the OUTPUT header's pin 19
beeps through to the input's pin 20.

## Reference firmware

A known-good AVR sketch for this panel family exists and matches the pinout exactly:
ROW0-4 on PB0-4, COL0-4 on PC0-4, COL-H/L on PC5, SET_PX on PD2, module select
one-hot on PD3-PD7. It packs 7 pixels per byte, does differential updates against an
`old_buffer`, and yields early when serial data arrives. DELAY is 80 us at 48 V,
200 us at 24 V, doubled for yellow.

Buffer width must stay a multiple of 7 (the packing) and ideally of 28 (panel width).

## Current bench setup (working)

Arduino Uno driving one panel directly - Uno GPIO is 5 V so no level shifting needed.

| Uno | Signal | Ribbon |
|-----|--------|--------|
| D8  | ROW0 | 5 |
| D9  | ROW1 | 7 |
| D10 | ROW2 | 6 |
| D11 | ROW3 | 8 |
| D12 | ROW4 | 9 |
| D2  | ROW-HIGH | 10 |
| D4  | ROW-LOW | 11 |
| A0-A4 | COL0-COL4 | 13-17 |
| A5  | COL-H/L | 18 |
| D3  | COL-SEL0 | 19 |
| D13 | (onboard LED, mirrors dot state) | - |
| GND | GND | 1, 2 |
| 5V  | 5V | 3 |

Plus 10k pull-downs to ground on ribbon 10, 11 and 19, because Uno pins are
high-impedance through the bootloader delay and on every upload reset.

## Earlier ESP32-C6 bench (retired)

An ESP32-C6-DevKitC-1 drove two panels side by side in direct drive before the S3
took over. Support for the C6, and for the 74HCT595 shift-register driver that only
existed for it, has been removed from the firmware; both are in the git history.

## ESP32-S3 two-row direct drive (working, full 4 x 2)

Waveshare ESP32-S3-Pico (ESP32-S3R2, 16 MB flash, 2 MB PSRAM) driving two rows of
four panels, each row on its own ribbon. Address, polarity and strobe lines are wired
in parallel to both ribbons; only COL-SEL is per ribbon (0-3 on ribbon A, 4-7 on
ribbon B). On the bench ribbon B feeds the top row (upright) and ribbon A the bottom
row (rotated), the reverse of the README's wiring table. The pin map covers all 21
signals of the 4 x 2 build. Full table in `firmware/README.md`, code in
`firmware/main/panel_hw.c`. Status LED is a WS2812 on GPIO21, RGB order. The S3 is the
only supported controller.

Both polarity strobes share a single RMT channel that is re-pointed through the GPIO
matrix per pulse, and the idle one is held low as a plain GPIO, so only one strobe is
ever live.

The display geometry (panel size, arrangement, COL-SEL line and rotation per panel)
lives in NVS and is set with `POST /geometry`; see `firmware/README.md`. Only the WiFi
credentials remain in the gitignored `firmware/local_config.h`.

## Status

VERIFIED by experiment:
- Panel flips reliably in both directions
- Full-panel sweep works cleanly, dot by dot, no missed or doubled dots - which proves
  the row/column address decoding is correct
- The polarity model is correct (dots go both ways)
- At least one stuck dot near the left edge, ~6 rows down (probably mechanical)
- ROW-HIGH and ROW-LOW work as two separate polarity strobes (direct drive pulses
  only one per dot, and dots go both ways)
- The panel logic runs at 3.3 V on pin 3, driven directly from 3.3 V GPIOs
- Two daisy-chained panels are addressed independently: driving COL-SEL1 (pin 20)
  at the controller selects the second panel only, orientation and addressing correct
- ESP32-S3-Pico drives two rows, one panel per ribbon, each answering on its own
  ribbon's pin 19 (COL-SEL0 and COL-SEL4), with address and strobe lines shared by
  both ribbons. Every row flips. Bring-up faults were wiring: ribbon pins 7 and 8
  crossed (only rows 1 and 15 dead, other rows misplaced), and a bad connection on
  the second ribbon. On this bench the arrangement is the reverse of the README:
  ribbon B (COL-SEL4) panel on top and upright, ribbon A (COL-SEL0) panel at the
  bottom and rotated, so the geometry was `28x16 1x2 4 0r`.
- S3 bench at 2 x 2 (56 x 32), a chained second panel on each ribbon. On both ribbons
  the second panel answers on the next COL-SEL line (5 after 4, 1 after 0). Seen from
  the front: top row upright, COL-SEL4 left, 5 right; bottom row rotated, COL-SEL1
  left, 0 right, so the chain on the rotated row runs right to left. Geometry
  `28x16 2x2 4 5 1r 0r`, confirmed with a numbered pattern per panel.
- Coils at 20 V with 200 us pulses flip reliably in both directions (S3 two-row bench,
  bench supply at 20 V). A few dots stay put in both colours (about 2 on one panel,
  4 on the other, one cluster of 3). With 260 us pulses at 20 V those dots flip too
  (2 x 2 bench, diagonal wipe), so the firmware uses 260 us for both colours.
- At 260 us, yellow flips still fail now and then: switching the whole display
  between yellow and black five times, no dot ever stayed yellow, but a few stayed
  black, and which ones varied from round to round. So yellow drive is marginal, not
  mechanical. Untested fix: a longer yellow pulse only (~320 us, ~0.82 A peak at 20 V).
- The panel shifts the COL-SEL lines by one position from input to output header
  (input 20-24 -> output 19-23, input 19 stays on the panel), measured with a
  continuity meter on one panel. This is why a chained panel answers on the next
  COL-SEL line. Table and input/output rule under "Panel select".
- Full 4 x 2 (112 x 32) on the S3 bench, four panels chained per ribbon, every panel
  answering on its chain position as the shift predicts. Seen from the front: top row
  upright, COL-SEL 4 5 6 7 left to right; bottom row rotated, its chain running right
  to left, COL-SEL 3 2 1 0 left to right. Geometry `28x16 4x2 4 5 6 7 3r 2r 1r 0r`,
  confirmed with a numbered pattern per panel and a full diagonal wipe.

NOT YET VERIFIED - do not assume:
- That output pin 24 has no connection (expected: it would come from input pin 25,
  which is unused), and so that the orientation fingerprint holds on the output header.
- That a sixth panel on a chain answers on pin 24. Nothing drives pin 24 yet; the
  firmware's pin map wires pins 19-22 only.
- That every panel shifts the same way with a meter; only one panel was measured. The
  4 x 2 bench shows it electrically for the first three panels on each ribbon (the
  fourth passes nothing on).

## Target build

4 panels wide x 2 tall = 8 panels, 112 x 32 dots, ~112 x 38 cm.

- Top row mounted rotated 180 degrees, so the bare-PCB strips move to the outer edges
  and the two dot fields meet. Firmware must mirror BOTH axes for that row:
  `col = 27 - col; row = 15 - row`
- Two ribbon chains of 4 (the bus has 6 select positions). Address and polarity lines are
  common to both chains; only the 8 COL-SEL lines are unique.
- Controller: Waveshare ESP32-S3-Pico in direct drive, no shift registers. Its pin
  map already covers all 21 signals; see `firmware/README.md`. An earlier plan used
  3x 74HCT595 for level shifting to 5 V, which the verified 3.3 V panel logic makes
  unnecessary.
- WiFi, not Ethernet (no drop at the location). The panels are ~3500 steel discs plus
  ground planes, so use a module with an external antenna mounted clear of the array,
  or put the ESP32 in the frame's bottom rail. Observed on the S3 bench: with the
  ribbons wired up near the Pico's ceramic antenna, pings went from 0% loss / 35 ms
  to 20% loss / 138 ms. Keep wiring away from the antenna end of the board.
- Power: **USB-C PD at 20 V** (decided; not yet built). At most ~0.62 A peak and
  ~0.21 A continuous, so any 20 V profile suffices. Current plan is built from modules
  (schematic and full wiring sheet: https://claude.ai/artifact/J4humSQehcH98LzdNP86HB):
  - PD trigger: **Joy-IT COM-ZY12PDN-ST** (Reichelt DEBO USB-PD 1). USB-C in, screw
    terminals out, voltage set with its button (LED dark blue = 20 V). It has NO
    power-good or status pin.
  - Buck: **Recom R-78E5.0-1.0**, 5 V into the Pico's VSYS through a Schottky (SS14),
    so the Pico's own USB-C can stay plugged in for flashing. Input 7-28 V: on a 5 V
    only charger the Pico does not boot. Output capacitance must stay under 220 uF
    (100 uF planned).
  - NEVER put 20 V on the Pico's USB-C or VSYS, which take 3.7-6 V.
  - The module's 20 V goes straight to the coil rail (ribbon pin 26) with 470 uF bulk,
    a unidirectional TVS (SMBJ24A) across it, and a series Schottky (SS34) plus
    4.7 uF into the buck. A coil pulse dips the 470 uF by only ~0.3 V, so the buck
    needs no large reservoir of its own. The TVS clamps near 39 V, above the R-78E's
    28 V limit: accepted risk, or use a buck rated to 40 V.
  - No coil-rail switch, on one condition not yet tested: with ~490 uF across the
    module's output, the charger in use must still settle on 20 V every time it is
    plugged in (USB-PD limits sink capacitance before the 20 V contract). If it does
    not, fall back to the earlier revision of the same page (version 2): a P-MOSFET
    switch turned on by a ~17 V zener detector, which also reports RAIL_OK to GPIO40.
  - Without a rail check, a charger below 20 V or a module left on another voltage only
    makes dots fail to flip (lower voltage is safe for the coils). Firmware should
    therefore redraw every dot now and then, e.g. on each new P2000 message, so missed
    flips get repaired (not implemented yet).
  - An ADC divider is not an option for rail sensing: the S3's ADC pins are GPIO1-20,
    all used by the pin map, and GPIO40 has no ADC.
  - The older discrete design (CH224K with power-good to GPIO40, AP63205 buck, which
    also runs a 5 V charger) is rev 0: https://claude.ai/artifact/8Sb9KLrSTWjDoLQiBUVHx7
- Carrier PCB "Flipdot S3 driver", rev A: `hardware/carrier/` (KiCad 10). A through-hole board holding the
  Pico in sockets, both ribbon headers, the 10 pull-downs and the module power stage
  (through-hole substitutes: SA24A for the SMBJ24A, 1N5819 for the SS34 and SS14). The
  PD trigger stays off the board, wired to a screw terminal. Schematic and board are
  generated by `hardware/carrier/tools/build.py` (own autorouter); ERC and DRC clean.
  Ribbon B on the left edge, ribbon A on the right (where each chain starts), the Pico
  upright between them with its antenna at the bottom edge. The Pico's antenna is on the
  short edge opposite USB, between the GPIO39/40 and GPIO41/42 pins (user-confirmed).
  Pico row spacing measured at 17.8 mm, matching the Pico footprint (17.78 mm).
  Not yet ordered; see its README for the remaining checks.
- Coil supply chains through the ribbons (fine at 0.62 A peak on 28 AWG).
- Star ground: coil return and logic return join at one point near the power input.

## Message formatting

Source is a P2000 receiver (RTL-SDR + own Python script) on a Raspberry Pi. It
publishes to the MQTT broker at 192.168.42.223:1883 (login required), all at QoS 0:

| Topic | Payload | Retained |
|-------|---------|----------|
| `p2000/melding` | every decoded message, nationwide (seen: Zandvoort, Rotterdam, Schagerbrug) | yes, the last one |
| `p2000/kazerne` | only messages for the station (capcode 1106973) | yes, the last one |
| `p2000/event` | the same messages as `p2000/melding`, published at the same moment | no |
| `p2000/status` | the plain text `online` | yes |

Messages are JSON `{"message", "capcodes", "timestamp", "received"}` with zero-padded
capcodes (`"001420070"`), `timestamp` in Unix seconds and `received` in ISO 8601 with
the local offset. Use `p2000/event` to react only to new messages: unlike
`p2000/melding`, subscribing to it does not replay an old one. `p2000/status` is
probably the receiver's MQTT last will, turning `offline` when it drops off the broker;
only `online` has been seen, so that is unverified.

`python_scripts/p2000_display.py` shows the latest station alarm from `p2000/kazerne`;
with `--all` it shows every message from `p2000/melding` instead, each on a single
page packed as full as it goes. Its login lives in the gitignored
`python_scripts/mqtt_config.py`.

Filter on capcode **1106973** (Kazernealarm Eindhoven-Centrum) - that is the one that
corresponds to trucks actually rolling. 1106998 is the station's own Lichtkrant feed
and fires for messages the station does not respond to; 1106926 is volunteer drivers.

Strip before display: the `BOB-xx` inzetvoorstel code, the trailing 6-digit unit
capcodes, and parentheticals. Suppress a trailing `EINDHOVEN` (most messages are local,
so leaving it in only for out-of-town calls makes those visually obvious).

Layout at 18 chars/line (6 px per char) x 4 lines (8 px pitch) fits every message in a
24-message sample with word wrapping. Longest single token observed: `ROOSENDAALSTRAAT`
(16 chars). Longest incident type: `ASSISTENTIE AMBULANCE` (21). Longest location:
`HEUVEL EINDHOVEN HEUVEL GALERIE` (31).

Keep the panel dark when idle; light it only when an incident arrives.

## References

- https://github.com/prefixFelix/mobitec-flipdot - replacement controller, 26-pin pinout
- https://github.com/bjarnekvae/pymobitec-flipdot - drives complete Mobitec displays via
  the ORIGINAL controller over RS-485; does not apply to a bare panel
- https://github.com/ChalmersRobotics/mqtt-flipdot-driver - same caveat
