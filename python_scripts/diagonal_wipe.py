#!/usr/bin/env python3
"""Wipe the display corner to corner along the diagonal, one diagonal per frame.

Each wipe runs from the top-left to the bottom-right corner, alternating
between yellow and black, so the display fills and then clears. At the
firmware's 4 frames a second a wipe takes about 15 seconds.
"""
import socket
import time

DISPLAY_IP = "192.168.42.199"
UDP_PORT = 7777

COLS, ROWS = 28, 32          # two 28x16 panels stacked, one per ribbon
STRIDE = (COLS + 7) // 8
FRAME_BYTES = STRIDE * ROWS

FRAME_S = 0.25               # the firmware adopts at most 4 frames a second
PAUSE_S = 2                  # hold between wipes


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
    last_diagonal = COLS + ROWS - 2
    yellow = True

    sock.sendto(bytes(FRAME_BYTES), (DISPLAY_IP, UDP_PORT))   # start from black
    try:
        while True:
            for reach in range(last_diagonal + 1):
                sock.sendto(diagonal_frame(reach, yellow), (DISPLAY_IP, UDP_PORT))
                time.sleep(FRAME_S)
            print(f"{time.strftime('%H:%M:%S')}  wiped {'yellow' if yellow else 'black'}")
            yellow = not yellow
            time.sleep(PAUSE_S)
    except KeyboardInterrupt:
        pass
    finally:
        sock.sendto(bytes(FRAME_BYTES), (DISPLAY_IP, UDP_PORT))   # leave it dark
        sock.close()


if __name__ == "__main__":
    main()
