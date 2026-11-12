"""Walk through every dot, flipping one each half-second."""
import socket
import time

from display import DISPLAY_IP, UDP_PORT, display_size, stride

INTERVAL_S = 0.5


def main():
    cols, rows = display_size()
    row_bytes = stride(cols)
    print(f"display is {cols} x {rows} dots")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    frame = bytearray(row_bytes * rows)

    # Start from a known-blank display.
    sock.sendto(bytes(frame), (DISPLAY_IP, UDP_PORT))
    time.sleep(INTERVAL_S)

    try:
        while True:                                  # each pass fills, the next clears
            for y in range(rows):
                for x in range(cols):
                    idx = y * row_bytes + x // 8
                    bit = 0x80 >> (x % 8)            # MSB = leftmost dot
                    frame[idx] ^= bit                # flip this one dot
                    sock.sendto(bytes(frame), (DISPLAY_IP, UDP_PORT))
                    state = "yellow" if frame[idx] & bit else "black"
                    print(f"{time.strftime('%H:%M:%S')}  ({x:2d},{y:2d}) -> {state}")
                    time.sleep(INTERVAL_S)
    except KeyboardInterrupt:
        pass
    finally:
        sock.sendto(bytes(len(frame)), (DISPLAY_IP, UDP_PORT))   # clear on exit
        sock.close()


if __name__ == "__main__":
    main()