#!/usr/bin/env python3
"""Show the time on the flip-dot display: large HH:MM with smaller seconds beside it.

The 5 x 7 digits are scaled up by whole numbers, as large as fit: on the
112 x 32 display the hours and minutes are 3x (15 x 21 dots) and the seconds
2x, sitting on the same baseline. The frame is resent every few seconds to cover
a lost datagram or a display that restarted; the display only flips the dots
that change. Ctrl-C leaves the display dark.

    python3 clock.py           # steady colon
    python3 clock.py --blink   # colon on for even seconds, off for odd
"""
import argparse
import socket
import time

from display import DISPLAY_IP, UDP_PORT, display_size, stride

# A plain zero: the slashed one of the text font looks odd this large.
DIGITS = {
    "0": [".###.", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."],
    "1": ["..#..", ".##..", "..#..", "..#..", "..#..", "..#..", ".###."],
    "2": [".###.", "#...#", "....#", "...#.", "..#..", ".#...", "#####"],
    "3": ["#####", "...#.", "..#..", "...#.", "....#", "#...#", ".###."],
    "4": ["...#.", "..##.", ".#.#.", "#..#.", "#####", "...#.", "...#."],
    "5": ["#####", "#....", "####.", "....#", "....#", "#...#", ".###."],
    "6": ["..##.", ".#...", "#....", "####.", "#...#", "#...#", ".###."],
    "7": ["#####", "....#", "...#.", "..#..", ".#...", ".#...", ".#..."],
    "8": [".###.", "#...#", "#...#", ".###.", "#...#", "#...#", ".###."],
    "9": [".###.", "#...#", "#...#", ".####", "....#", "...#.", ".##.."],
    ":": [".", ".", "#", ".", "#", ".", "."],
}
HEIGHT_UNITS = 7

# Layout in units of its scale: two digits with 1 between them.
PAIR_UNITS = 5 + 1 + 5
# HH:MM: a pair, 2 + colon + 2, a pair.
HHMM_UNITS = PAIR_UNITS + 2 + 1 + 2 + PAIR_UNITS   # 27
SECONDS_GAP = 4  # dots between the minutes and the seconds

RESEND_S = 5


def layout(cols, rows):
    """The (big, small) scales: the largest pair that fits, preferring big hours."""
    for big in range(rows // HEIGHT_UNITS, 0, -1):
        for small in range(big - 1, 0, -1):
            if HHMM_UNITS * big + SECONDS_GAP + PAIR_UNITS * small <= cols:
                return big, small
    return None


def clock_frame(cols, rows, hhmmss, colon):
    row_bytes = stride(cols)
    frame = bytearray(row_bytes * rows)

    def glyph(char, left, top, scale):
        for uy, bits in enumerate(DIGITS[char]):
            for ux, bit in enumerate(bits):
                if bit != "#":
                    continue
                for y in range(scale):
                    for x in range(scale):
                        px, py = left + ux * scale + x, top + uy * scale + y
                        if 0 <= px < cols and 0 <= py < rows:
                            frame[py * row_bytes + px // 8] |= 0x80 >> (px % 8)

    big, small = layout(cols, rows)
    width = HHMM_UNITS * big + SECONDS_GAP + PAIR_UNITS * small
    left = (cols - width) // 2
    top = (rows - HEIGHT_UNITS * big) // 2
    for char, ux in zip(hhmmss[:4], (0, 6, 16, 22)):
        glyph(char, left + ux * big, top, big)
    if colon:
        glyph(":", left + 13 * big, top, big)
    # The seconds share the baseline of the big digits.
    s_left = left + HHMM_UNITS * big + SECONDS_GAP
    s_top = top + (HEIGHT_UNITS * big - HEIGHT_UNITS * small)
    for char, ux in zip(hhmmss[4:], (0, 6)):
        glyph(char, s_left + ux * small, s_top, small)
    return bytes(frame)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--blink", action="store_true",
                        help="blink the colon every second")
    args = parser.parse_args()

    cols, rows = display_size()
    if layout(cols, rows) is None:
        raise SystemExit(f"a {cols} x {rows} display is too small for the clock")
    print(f"display is {cols} x {rows} dots, digit scales {layout(cols, rows)}")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    last, last_sent = None, 0.0
    try:
        while True:
            now = time.localtime()
            colon = not args.blink or now.tm_sec % 2 == 0
            frame = clock_frame(cols, rows, time.strftime("%H%M%S", now), colon)
            if frame != last or time.monotonic() - last_sent >= RESEND_S:
                sock.sendto(frame, (DISPLAY_IP, UDP_PORT))
                last, last_sent = frame, time.monotonic()
            # Wake just after the next whole second.
            time.sleep(1.02 - time.time() % 1)
    except KeyboardInterrupt:
        pass
    finally:
        sock.sendto(bytes(stride(cols) * rows), (DISPLAY_IP, UDP_PORT))  # leave it dark
        sock.close()


if __name__ == "__main__":
    main()
