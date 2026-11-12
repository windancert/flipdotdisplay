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
  at one dot per 335 us, matching the measured sweep current. It is trustworthy.
- At **20 V** (the planned USB-C PD supply): peak 0.62 A at the end of a 200 us pulse,
  ~70 uC per flip, ~0.21 A for continuous sweeping (model). Measured on the S3 bench
  during a diagonal wipe: at most 0.04 A on the bench supply (its finest resolution),
  consistent with the model's ~0.02 A per 250 ms frame. A stuck 400 us pulse (the
  firmware ceiling) would peak at ~0.94 A.

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
| 23  | COL-SEL4 | 24 | n/c |
| 25  | n/c    | 26  | 24 V |

NOTE: pins 6 and 7 are crossed (6 = ROW2, 7 = ROW1). Everything else runs in order.

Orientation fingerprint: pins 1+2 are the only adjacent pair both common with the
ground plane. Pins 12, 24 and 25 are the only pads with no track at all, and they sit
asymmetrically (12 and 24 in the even row, 25 in the odd row), which identifies both
the low-numbered end and which row is odd.

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

COL-SEL0..4 select which panel on a shared chain responds. One-hot, so **max 5 panels
per ribbon chain**.

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

## ESP32-C6 direct-drive bench setup (working, two panels)

ESP32-C6 driving two daisy-chained panels side by side (56 x 16) straight from its
GPIOs, no shift registers. Built with `CONFIG_FLIPDOT_DIRECT_DRIVE=y`; the pin map
lives in `firmware/main/panel_hw_direct.c`.

| C6 | Signal | Ribbon |
|----|--------|--------|
| GPIO18-22 | ROW0-4 | 5, 6, 7, 8, 9 (straight; firmware undoes the 6/7 crossing) |
| GPIO4, 5, 6, 7, 0 | COL0-4 | 13-17 |
| GPIO23 | COL-H/L | 18 |
| GPIO1 | COL-SEL0 (left panel) | 19 |
| GPIO2 | COL-SEL1 (right panel) | 20 |
| GPIO10 | ROW-HIGH | 10 |
| GPIO11 | ROW-LOW | 11 |
| 3V3 | panel logic supply | 3 |
| GND | GND | 1, 2 |

Plus 10k pull-downs to ground on ribbon 10, 11, 19 and 20, and 24 V on pin 26.

The C6 has only two RMT TX channels and the status LED owns one, so both polarity
strobes share a single RMT channel that is re-pointed through the GPIO matrix per
pulse. A second strobe channel does not exist and panics at boot.

## ESP32-S3 two-row direct drive (working, one panel per row)

Waveshare ESP32-S3-Pico (ESP32-S3R2, 16 MB flash, 2 MB PSRAM) driving two rows of
panels, each row on its own ribbon. Address, polarity and strobe lines are wired in
parallel to both ribbons; only COL-SEL is per ribbon (0-3 on ribbon A / top row,
4-7 on ribbon B / bottom row). The pin map reserves all 21 signals, enough for the
full 4 x 2 target without rewiring. Full table in `firmware/README.md`, code in
`firmware/main/panel_hw_direct.c`. Status LED is a WS2812 on GPIO21, RGB order.

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
- ROW-HIGH and ROW-LOW work as two separate polarity strobes (C6 direct drive pulses
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
  bottom and rotated, so the geometry is `28x16 1x2 4 0r`.
- Coils at 20 V with 200 us pulses flip reliably in both directions (S3 two-row bench,
  bench supply at 20 V). A few dots stay put in both colours (about 2 on one panel,
  4 on the other, one cluster of 3), probably mechanical; untested whether 24 V or a
  longer pulse frees them.

NOT YET VERIFIED - do not assume:
- WHY the second panel answers on COL-SEL1: the 26-way headers may shift the COL-SEL
  lines by one position as the ribbon chains, or the panel may be strapped to SEL1.
  Chaining works either way, but it matters for panels 3-5. TEST: buzz COL-SEL0
  (pin 19) on one header against pins 19-23 on the other.

## Target build

4 panels wide x 2 tall = 8 panels, 112 x 32 dots, ~112 x 38 cm.

- Top row mounted rotated 180 degrees, so the bare-PCB strips move to the outer edges
  and the two dot fields meet. Firmware must mirror BOTH axes for that row:
  `col = 27 - col; row = 15 - row`
- Two ribbon chains of 4 (the 5-panel bus limit). Address and polarity lines are
  common to both chains; only the 8 COL-SEL lines are unique.
- Controller: Waveshare ESP32-S3-Pico in direct drive, no shift registers (current
  plan). Its pin map already covers all 21 signals; see `firmware/README.md`.
  The earlier plan, an ESP32 + 3x 74HCT595 with OE through a BSS138 inverter, is still
  in the firmware for the C6 only. Its reason for HCT parts (level shifting to 5 V) no
  longer applies, since the panel logic is verified at 3.3 V.
- WiFi, not Ethernet (no drop at the location). The panels are ~3500 steel discs plus
  ground planes, so use a module with an external antenna mounted clear of the array,
  or put the ESP32 in the frame's bottom rail. Observed on the S3 bench: with the
  ribbons wired up near the Pico's ceramic antenna, pings went from 0% loss / 35 ms
  to 20% loss / 138 ms. Keep wiring away from the antenna end of the board.
- Power: **USB-C PD at 20 V** (decided; not yet built). Needs a PD trigger chip
  requesting 20 V; at most ~0.62 A peak and ~0.21 A continuous, so any 20 V profile
  suffices. Design rules:
  - NEVER put 20 V on the Pico's USB-C or VSYS, which take 3.7-6 V. The 20 V goes to
    the coil rail (ribbon pin 26) and to a buck converter rated well above 20 V
    (~28 V or more) that feeds the Pico's VSYS with 5 V.
  - USB-PD limits sink capacitance before the 20 V contract is made, so put the bulk
    capacitance (470 uF) behind a load switch, typically a P-MOSFET, enabled by the
    trigger chip's power-good output.
  - Chargers without a 20 V profile (many phone chargers stop at 9 or 12 V) leave the
    rail too low to flip reliably. Plan: the PD trigger's power-good output switches
    the coil rail in hardware AND goes to GPIO40, so firmware can refuse to pulse and
    show it on the status LED (not implemented yet). An ADC divider is not an option:
    the S3's ADC pins are GPIO1-20, all used by the pin map, and GPIO40 has no ADC.
  - Draft schematic (rev 0): https://claude.ai/artifact/8Sb9KLrSTWjDoLQiBUVHx7
  - Keep the series Schottky plus 220-470 uF ahead of the buck input, so coil pulses
    cannot brown out the ESP32.
- Coil supply chains through the ribbons (fine at 0.62 A peak on 28 AWG).
- Star ground: coil return and logic return join at one point near the power input.

## Message formatting

Source is a P2000 receiver (RTL-SDR + own Python script) on a Raspberry Pi.

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
