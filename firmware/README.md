# Flip-dot firmware (ESP32-C6, ESP-IDF)

Built against ESP-IDF 6.1. Not tried on older versions. Runs on a bare DevKitC-1, but
has not yet driven a panel.

```sh
cp local_config.example.h local_config.h   # WiFi credentials
idf.py set-target esp32c6
idf.py menuconfig          # optional, "Flip-dot display": UDP port, boot test
idf.py build flash monitor
```

`local_config.h` is gitignored, so it needs creating on each new checkout. The display
geometry is not in it: see [Display geometry](#display-geometry).

Host test of the addressing logic, no toolchain needed:

```sh
cc -std=c11 -Wall -Wextra -Imain test/test_map.c main/flipdot_map.c main/geometry.c -o test/test_map && test/test_map
```

## Wiring

| C6 GPIO | Goes to |
|---------|---------|
| 18 | U1 SER (U1 QH' -> U2 SER, U2 QH' -> U3 SER) |
| 19 | SRCLK on all three |
| 20 | RCLK on all three |
| 21 | Strobe inverter gate (see below) |

| Register | QA | QB | QC | QD | QE | QF | QG | QH |
|----------|----|----|----|----|----|----|----|----|
| U1 | ROW0 | ROW1 | ROW2 | ROW3 | ROW4 | COL-H/L | - | - |
| U2 | COL0 | COL1 | COL2 | COL3 | COL4 | COL-SEL6 | COL-SEL7 | - |
| U3 | ROW-HIGH | ROW-LOW | COL-SEL0 | COL-SEL1 | COL-SEL2 | COL-SEL3 | COL-SEL4 | COL-SEL5 |

Mind the ribbon crossing: ROW2 is pin 6, ROW1 is pin 7. All 595s run from 5 V, with
SRCLR tied to 5 V. Chain A (top row) uses COL-SEL0-3, chain B (bottom) COL-SEL4-7.

### Output enables

- **U1, U2:** OE tied to ground. They only carry addresses and COL-SEL6/7, and no
  current can flow without a strobe, so random power-up contents are harmless.
- **U3:** OE driven by an inverter, so the strobes are off whenever the C6 is not
  actively enabling them:

```
              5 V
               |
              4.7k
               |
               +------- U3 OE
               |
             D |
GPIO21 ----- G  BSS138
         |   S |
        10k    |
         |     |
        GND   GND
```

Do not pull OE up to 5 V directly on a GPIO: C6 pins are not 5 V tolerant. A 3.3 V
pull-up would leave OE low while 5 V is up and 3.3 V is not. Use a logic-level FET;
a 2N7000's threshold is too close to 3.3 V.

- **Pull-downs:** 10k to ground on all 8 U3 outputs, since they float while OE is high.

## How a dot is flipped

1. Shift and latch the address, polarity and strobe bit. U1 and U2 change now; U3's
   outputs are still disabled, so the address settles with no current flowing.
2. The RMT peripheral drives GPIO21 high for the pulse width and ends the pulse itself.
3. Latch the all-zero idle frame.

Because hardware ends the pulse, a crash or a WiFi interrupt cannot extend it. Pulses
are also clamped to 400 us, at least 335 us apart, and a new frame is adopted at most
4 times a second, so no single coil can be hammered by a bad sender.

## Sending frames

One UDP datagram per frame, port 7777 by default: 1 bit per dot, row by row from the
top, MSB leftmost, 1 = yellow, with each row padded to whole bytes. The 112 x 32 display
takes 14 bytes per row, 448 in total; a single 28 x 16 panel takes 4 per row, 64 in total. The port is unauthenticated, so anything on
the LAN can write to the display.

```python
import socket
frame = bytearray(448)
frame[0] = 0x80  # top-left dot
socket.socket(socket.AF_INET, socket.SOCK_DGRAM).sendto(frame, ("<display-ip>", 7777))
```

## Direct drive (no shift registers)

With `CONFIG_FLIPDOT_DIRECT_DRIVE=y` (the default on the S3) the GPIOs drive the
ribbon directly. The panel logic runs at 3.3 V from ribbon pin 3. Pin maps are in
`main/panel_hw_direct.c`; the C6 bench map is in `CLAUDE.md`.

### Waveshare ESP32-S3-Pico, two ribbons

Every shared line goes to the same pin on **both** ribbons. Ribbon A feeds the top
row (COL-SEL0-3), ribbon B the bottom row (COL-SEL4-7). The first panel on each
ribbon answers on that ribbon's pin 19.

Each group is an unbroken run down one header (apart from GND and RUN pins), and the
left header follows the ribbon's own order.

| S3 GPIO | Pico header pin | Signal | Ribbon pin | Ribbons |
|---------|-----------------|--------|------------|---------|
| 10, 9, 8, 7, 6 | left 35, 34, 32, 31, 29 | ROW0-4 | 5, 6, 7, 8, 9 (straight; firmware undoes the 6/7 crossing) | both |
| 5, 4, 2, 1, 41 | left 27, 26, 25, 24, 22 | COL0-4 | 13-17 | both |
| 42 | left 21 | COL-H/L | 18 | both |
| 11, 12, 13, 14 | right 1, 2, 4, 5 | COL-SEL0-3 | 19-22 | A only |
| 15, 16, 17, 18 | right 6, 7, 9, 10 | COL-SEL4-7 | 19-22 | B only |
| 38 | right 17 | ROW-HIGH | 10 | both |
| 39 | right 19 | ROW-LOW | 11 | both |
| 3V3 | left 36 | logic supply | 3 | both |
| GND | any GND | GND | 1, 2 | both |

10k pull-downs to ground on ROW-HIGH, ROW-LOW and every COL-SEL line that is wired.
24 V on pin 26 of each ribbon.

GPIO33-37 are avoided because Waveshare lists them for PSRAM. The onboard WS2812 is
on GPIO21 and takes its colours red first.

For one panel per row, mounted as in the target build, the geometry is
`28x16 1x2 0r 4`.

## Display geometry

The panel size, the arrangement of the panels and the COL-SEL line of each are kept in
NVS, so they survive restarts and firmware updates, and are set over HTTP:

```sh
curl http://<display-ip>/geometry                            # read it
curl --data "28x16 4x2 0r 1r 2r 3r 4 5 6 7" http://<display-ip>/geometry   # set it
```

The text is the size of one panel in dots (columns x rows), the number of panels
(across x down), then one entry per panel seen from the front, top row first and left
to right: its COL-SEL line, followed by `r` if the panel is mounted rotated 180
degrees. The example is the 4 x 2 target build; `28x16 1x2 4 0r` is the S3 bench.

A valid new geometry is stored and the board restarts to apply it, blacking out the
new display area. Anything invalid is refused with a 400 and a reason, and nothing
changes: a panel needs 1 to 28 dots each way, there are at most 8 panels, and every
panel needs its own COL-SEL line that this board has a GPIO for (the C6 direct-drive
map has only COL-SEL0 and 1).

Until a geometry is stored, or if the stored one no longer fits the board, the
firmware uses one upright 28 x 16 panel on COL-SEL0. The frame size follows the
geometry, so senders must match it; the serial log prints both at boot. Like the
other endpoints, this one has no authentication.

## Status LED

The onboard RGB LED (GPIO8 on the ESP32-C6-DevKitC-1, GPIO21 on the ESP32-S3-Pico) shows:

| LED | Meaning |
|-----|---------|
| Solid blue | Booting, blacking out the display |
| Blinking yellow | Looking for WiFi |
| Solid green | Has an IP address, listening for frames |
| Solid purple | No SSID configured |
| Short white flash | Valid frame received |
| Blinking blue | Receiving a firmware update |

Blue should last about 1.5 s and only appear once. Blue repeating every couple of
seconds, with a brief flicker in between, means a reset loop, usually a brownout while
WiFi starts: check the serial log and the power supply.

## Updating over WiFi

The first flash after adding OTA must go over USB and erase the flash, because the
partition table changed (`idf.py erase-flash flash`). After that:

```sh
idf.py fullclean build     # always a clean build, see below
curl --data-binary @build/flipdot.bin http://<display-ip>/update
curl http://<display-ip>/version
```

The image goes into the slot that isn't running, and the board reboots into it. The
display blacks out and redraws on restart.

A new image must get an IP address within 2 minutes. If it doesn't, or if it crashes or
hangs first, the board returns to the previous firmware. Rollback can't catch a build
that gets online but misbehaves, so test changes to `panel_hw.c` over USB first. The
same goes for bootloader and partition table changes, which OTA doesn't update.

Clean builds matter because incremental PlatformIO builds have produced images that
flash fine but can't use WiFi, for reasons not yet understood.

The endpoint has no authentication: anything on the LAN can replace the firmware,
including the code that limits coil pulses.

## Bring-up

1. Check the strobe with a scope or LED on U3 QA **before connecting a panel**.
2. Connect one panel on COL-SEL0 (the default geometry) and enable the boot test.
3. Do the COL-SEL buzz test from `CLAUDE.md`, then set the geometry over HTTP, swapping
   the COL-SEL lines if the headers shift them.
