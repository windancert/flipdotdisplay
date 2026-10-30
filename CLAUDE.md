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
- Logic 5 V, coils 24 V, both arriving over the ribbon

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

DANGER: 24 V across 16 ohm continuously is 36 W in a coil the size of a shirt button.
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

## Status

VERIFIED by experiment:
- Panel flips reliably in both directions
- Full-panel sweep works cleanly, dot by dot, no missed or doubled dots - which proves
  the row/column address decoding is correct
- The polarity model is correct (dots go both ways)
- At least one stuck dot near the left edge, ~6 rows down (probably mechanical)

NOT YET VERIFIED - do not assume:
- Whether ROW-HIGH and ROW-LOW are genuinely two separate polarity strobes, or are
  gated together as the reference firmware's single SET_PX implies
- Whether the two 26-way headers are straight-through pin-for-pin, or shift the
  COL-SEL lines by one position as the ribbon chains. This decides how a panel claims
  its select line, and therefore how chaining is wired. TEST: buzz COL-SEL0 (pin 19)
  on one header against pins 19-23 on the other.

## Target build

4 panels wide x 2 tall = 8 panels, 112 x 32 dots, ~112 x 38 cm.

- Top row mounted rotated 180 degrees, so the bare-PCB strips move to the outer edges
  and the two dot fields meet. Firmware must mirror BOTH axes for that row:
  `col = 27 - col; row = 15 - row`
- Two ribbon chains of 4 (the 5-panel bus limit). Address and polarity lines are
  common to both chains; only the 8 COL-SEL lines are unique.
- Controller: ESP32 + 3x **74HCT595** shift registers. HCT (not HC) because its TTL
  input thresholds accept the ESP32's 3.3 V while its outputs swing to 5 V for the
  panel's HC inputs. 21 signals needed, 24 outputs available.
  Tie the 595 OE pin high through a pull-up so outputs are disabled at reset.
- WiFi, not Ethernet (no drop at the location). The panels are ~3500 steel discs plus
  ground planes, so use a module with an external antenna mounted clear of the array,
  or put the ESP32 in the frame's bottom rail.
- Power: 24 V / 1 A external brick. 470 uF bulk at the controller. 24 V chains through
  the ribbons (fine at 0.75 A peak on 28 AWG). Buck 24 V -> 5 V (not linear), feeding
  the 595s and the ESP32's VIN pin. Put a series Schottky plus 220-470 uF between the
  24 V rail and the buck input so coil pulses cannot brown out the ESP32.
- Star ground: coil return and logic return join at one point near the 24 V input.

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
