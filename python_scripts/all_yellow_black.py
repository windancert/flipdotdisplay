#!/usr/bin/env python3
"""Cycle the flip-dot display between all-yellow and all-black."""
import socket
import time

DISPLAY_IP = "192.168.42.172"
UDP_PORT = 7777

# One 28x16 panel: each row padded to whole bytes -> 4 bytes/row * 16 rows = 64.
COLS, ROWS = 56, 16          # two 28x16 panels side by side
STRIDE = (COLS + 7) // 8
FRAME_BYTES = STRIDE * ROWS

INTERVAL_S = 5
DURATION_S = 60          # set to None to run until Ctrl-C

ALL_YELLOW = bytes([0xFF]) * FRAME_BYTES   # 1 = yellow; padding bits are ignored
ALL_BLACK = bytes(FRAME_BYTES)             # all zero


def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    frames = (("yellow", ALL_YELLOW), ("black", ALL_BLACK))
    start = time.monotonic()
    i = 0
    try:
        while DURATION_S is None or time.monotonic() - start < DURATION_S:
            name, frame = frames[i % 2]
            sock.sendto(frame, (DISPLAY_IP, UDP_PORT))
            print(f"{time.strftime('%H:%M:%S')}  {name}")
            i += 1
            time.sleep(INTERVAL_S)
    except KeyboardInterrupt:
        pass
    finally:
        sock.sendto(ALL_BLACK, (DISPLAY_IP, UDP_PORT))   # leave it dark
        sock.close()


if __name__ == "__main__":
    main()