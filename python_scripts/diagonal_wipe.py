#!/usr/bin/env python3
"""Wipe the display corner to corner along the diagonal, one diagonal per frame.

Each wipe runs from the top-left to the bottom-right corner, alternating
between yellow and black, so the display fills and then clears. At the
firmware's 4 frames a second a wipe of the 28 x 32 bench takes about 15 seconds.
The display size comes from the display's own geometry.
"""
import socket
import time

from display import DISPLAY_IP, UDP_PORT, display_size, stride

FRAME_S = 0.25               # the firmware adopts at most 4 frames a second
PAUSE_S = 2                  # hold between wipes


def diagonal_frame(cols, rows, reach, yellow):
    """Dots with x + y <= reach take the wipe colour, the rest the opposite."""
    row_bytes = stride(cols)
    frame = bytearray(row_bytes * rows)
    for y in range(rows):
        for x in range(cols):
            if (x + y <= reach) == yellow:
                frame[y * row_bytes + x // 8] |= 0x80 >> (x % 8)   # MSB = leftmost dot
    return bytes(frame)


def main():
    cols, rows = display_size()
    black = bytes(stride(cols) * rows)
    print(f"display is {cols} x {rows} dots")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    last_diagonal = cols + rows - 2
    yellow = True

    sock.sendto(black, (DISPLAY_IP, UDP_PORT))   # start from black
    try:
        while True:
            for reach in range(last_diagonal + 1):
                sock.sendto(diagonal_frame(cols, rows, reach, yellow), (DISPLAY_IP, UDP_PORT))
                time.sleep(FRAME_S)
            print(f"{time.strftime('%H:%M:%S')}  wiped {'yellow' if yellow else 'black'}")
            yellow = not yellow
            time.sleep(PAUSE_S)
    except KeyboardInterrupt:
        pass
    finally:
        sock.sendto(black, (DISPLAY_IP, UDP_PORT))   # leave it dark
        sock.close()


if __name__ == "__main__":
    main()
