#!/usr/bin/env python3
"""Cycle the flip-dot display between all-yellow and all-black."""
import socket
import time

from display import DISPLAY_IP, UDP_PORT, display_size, stride

INTERVAL_S = 5
DURATION_S = 60          # set to None to run until Ctrl-C


def main():
    cols, rows = display_size()
    frame_bytes = stride(cols) * rows
    print(f"display is {cols} x {rows} dots")
    all_yellow = bytes([0xFF]) * frame_bytes   # 1 = yellow; padding bits are ignored
    all_black = bytes(frame_bytes)             # all zero

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    frames = (("yellow", all_yellow), ("black", all_black))
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
        sock.sendto(all_black, (DISPLAY_IP, UDP_PORT))   # leave it dark
        sock.close()


if __name__ == "__main__":
    main()