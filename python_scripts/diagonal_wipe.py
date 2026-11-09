#!/usr/bin/env python3
"""Wipe the display corner to corner along the diagonal, every 5 seconds.

Each wipe runs from the top-left to the bottom-right corner, alternating
between yellow and black, so the display fills and then clears.
"""
import socket
import time

DISPLAY_IP = "192.168.42.199"
UDP_PORT = 7777

COLS, ROWS = 28, 32          # two 28x16 panels stacked, one per ribbon
STRIDE = (COLS + 7) // 8
FRAME_BYTES = STRIDE * ROWS

PERIOD_S = 5                 # a new wipe starts this often
FRAME_S = 0.25               # the firmware adopts at most 4 frames a second
WIPE_S = 3                   # time for one wipe, within PERIOD_S


def diagonal_frame(reach, yellow):
    """Dots with x + y <= reach take the wipe colour, the rest the opposite."""
    frame = bytearray(FRAME_BYTES)
    for y in range(ROWS):
        for x in range(COLS):
            if (x + y <= reach) == yellow:
                frame[y * STRIDE + x // 8] |= 0x80 >> (x % 8)   # MSB = leftmost dot
    return bytes(frame)


def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    steps = round(WIPE_S / FRAME_S)
    last_diagonal = COLS + ROWS - 2
    yellow = True

    sock.sendto(bytes(FRAME_BYTES), (DISPLAY_IP, UDP_PORT))   # start from black
    try:
        while True:
            start = time.monotonic()
            for step in range(1, steps + 1):
                reach = round(last_diagonal * step / steps)
                sock.sendto(diagonal_frame(reach, yellow), (DISPLAY_IP, UDP_PORT))
                time.sleep(FRAME_S)
            print(f"{time.strftime('%H:%M:%S')}  wiped {'yellow' if yellow else 'black'}")
            yellow = not yellow
            time.sleep(max(0, PERIOD_S - (time.monotonic() - start)))
    except KeyboardInterrupt:
        pass
    finally:
        sock.sendto(bytes(FRAME_BYTES), (DISPLAY_IP, UDP_PORT))   # leave it dark
        sock.close()


if __name__ == "__main__":
    main()
