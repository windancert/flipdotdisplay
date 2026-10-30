# Flip-dot firmware (ESP32-C6, ESP-IDF)

Built against ESP-IDF 6.1. Not tried on older versions. Runs on a bare DevKitC-1, but
has not yet driven a panel.

```sh
cp local_config.example.h local_config.h   # display geometry and WiFi credentials
idf.py set-target esp32c6
idf.py menuconfig          # optional, "Flip-dot display": UDP port, boot test
idf.py build flash monitor
```

`local_config.h` is gitignored, so it needs creating on each new checkout.

Host test of the addressing logic, no toolchain needed:

```sh
cc -std=c11 -Wall -Wextra -Itest -Imain test/test_map.c main/flipdot_map.c -o test/test_map && test/test_map
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
top, MSB leftmost, 1 = yellow. For the 112 x 32 display that is 14 bytes per row, 448
bytes in total. The port is unauthenticated, so anything on
the LAN can write to the display.

```python
import socket
frame = bytearray(448)
frame[0] = 0x80  # top-left dot
socket.socket(socket.AF_INET, socket.SOCK_DGRAM).sendto(frame, ("<display-ip>", 7777))
```

## Status LED

The onboard RGB LED (GPIO8, as on the ESP32-C6-DevKitC-1) shows:

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
2. Connect one panel on COL-SEL4 (bottom-left position) and enable the boot test.
3. Do the COL-SEL buzz test from `CLAUDE.md`, then fix the `DISPLAY_LAYOUT` table in
   `local_config.h` if the headers shift the select lines.
