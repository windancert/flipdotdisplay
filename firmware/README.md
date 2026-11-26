# Flip-dot firmware (Waveshare ESP32-S3-Pico, ESP-IDF)

Built against ESP-IDF 6.1. Not tried on older versions. Drives the panels straight from
the GPIOs of a Waveshare ESP32-S3-Pico, over two ribbons; no other board is supported.

```sh
cp local_config.example.h local_config.h   # WiFi credentials
idf.py set-target esp32s3
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

The GPIOs drive the ribbons directly, and the panel logic runs at 3.3 V from ribbon
pin 3. The pin map is in `main/panel_hw.c`.

Every shared line goes to the same pin on **both** ribbons. Ribbon A feeds the top
row (COL-SEL0-3), ribbon B the bottom row (COL-SEL4-7). The first panel on each
ribbon answers on that ribbon's pin 19.

Each group is an unbroken run down one header (apart from GND and RUN pins), and the
right header follows the ribbon's own order. Left and right are seen from above, USB at
the top: pins 1-20 run down the left side from pin 1 at the top, 21-40 up the right side.

| S3 Pico GPIO | S3 Pico header pin | Signal | Ribbon pin | Ribbons |
|---------|-----------------|--------|------------|---------|
| 10, 9, 8, 7, 6 | right 35, 34, 32, 31, 29 | ROW0-4 | 5, 6, 7, 8, 9 (straight; firmware undoes the 6/7 crossing) | both |
| 5, 4, 2, 1, 41 | right 27, 26, 25, 24, 22 | COL0-4 | 13-17 | both |
| 42 | right 21 | COL-H/L | 18 | both |
| 11, 12, 13, 14 | left 1, 2, 4, 5 | COL-SEL0-3 | 19-22 | A only |
| 15, 16, 17, 18 | left 6, 7, 9, 10 | COL-SEL4-7 | 19-22 | B only |
| 38 | left 17 | ROW-HIGH | 10 | both |
| 39 | left 19 | ROW-LOW | 11 | both |
| 3V3 | right 36 | logic supply | 3 | both |
| GND | any GND | GND | 1, 2 | both |

10k pull-downs to ground on ROW-HIGH, ROW-LOW and every COL-SEL line that is wired,
since they float until the firmware drives them. Coil supply on pin 26 of each ribbon.

GPIO33-37 are avoided because Waveshare lists them for PSRAM. The onboard WS2812 is
on GPIO21 and takes its colours red first.

## How a dot is flipped

1. Set the address, COL-H/L and COL-SEL lines while both strobes are low, so the
   address settles with no current flowing.
2. The RMT peripheral drives ROW-HIGH (yellow) or ROW-LOW (black) high for the pulse
   width and ends the pulse itself. One RMT channel serves both strobes: it is routed
   to the one needed through the GPIO matrix, and the other is held low.
3. Return every line to idle.

Because hardware ends the pulse, a crash or a WiFi interrupt cannot extend it. Pulses
are also clamped to 400 us, at least 335 us apart, and a new frame is adopted at most
4 times a second, so no single coil can be hammered by a bad sender.

## Sending frames

One UDP datagram per frame, port 7777 by default: 1 bit per dot, row by row from the
top, MSB leftmost, 1 = yellow, with each row padded to whole bytes. The 112 x 32 display
takes 14 bytes per row, 448 in total; a single 28 x 16 panel takes 4 per row, 64 in
total. The port is unauthenticated, so anything on the LAN can write to the display.

```python
import socket
frame = bytearray(448)
frame[0] = 0x80  # top-left dot
socket.socket(socket.AF_INET, socket.SOCK_DGRAM).sendto(frame, ("<display-ip>", 7777))
```

## Display geometry

The panel size, the arrangement of the panels and the COL-SEL line of each are kept in
NVS, so they survive restarts and firmware updates, and are set over HTTP:

```sh
curl http://<display-ip>/geometry                            # read it
curl --data "28x16 4x2 4 5 6 7 3r 2r 1r 0r" http://<display-ip>/geometry   # set it
```

The text is the size of one panel in dots (columns x rows), the number of panels
(across x down), then one entry per panel seen from the front, top row first and left
to right: its COL-SEL line, followed by `r` if the panel is mounted rotated 180
degrees. The example is the 4 x 2 bench: ribbon B's chain runs left to right along
the upright top row, ribbon A's right to left along the rotated bottom row, because
rotating a panel moves its input header to the other side.

A valid new geometry is stored and the board restarts to apply it, blacking out the
new display area. Anything invalid is refused with a 400 and a reason, and nothing
changes: a panel needs 1 to 28 dots each way, there are at most 8 panels, and every
panel needs its own COL-SEL line, 0 to 7.

Until a geometry is stored, or if the stored one is invalid, the
firmware uses one upright 28 x 16 panel on COL-SEL0. The frame size follows the
geometry, so senders must match it; the serial log prints both at boot. Like the
other endpoints, this one has no authentication.

## Status LED

The onboard RGB LED (GPIO21) shows:

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

1. Check ROW-HIGH and ROW-LOW (GPIO38 and 39) with a scope or LED **before connecting
   a panel**: low at all times except during a pulse.
2. Connect one panel on COL-SEL0 (the default geometry) and enable the boot test. The
   ribbon goes to the panel's input header; `CLAUDE.md` ("Panel select") has the
   continuity test that tells input from output.
3. Chain further panels from output to input. Each panel shifts the select lines down
   by one, so the n-th panel on a ribbon answers on that ribbon's n-th COL-SEL line
   (0-3 on ribbon A, 4-7 on ribbon B). Set the geometry over HTTP to match.
