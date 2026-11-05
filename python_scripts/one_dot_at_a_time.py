"""Walk through every dot, flipping one each half-second."""
import socket
import time

DISPLAY_IP = "192.168.42.172"
UDP_PORT = 7777

COLS, ROWS = 56, 16          # two 28x16 panels side by side
STRIDE = (COLS + 7) // 8
FRAME_BYTES = STRIDE * ROWS
INTERVAL_S = 0.5


def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    frame = bytearray(FRAME_BYTES)

    # Start from a known-blank display.
    sock.sendto(bytes(frame), (DISPLAY_IP, UDP_PORT))
    time.sleep(INTERVAL_S)

    try:
        while True:                                  # each pass fills, the next clears
            for y in range(ROWS):
                for x in range(COLS):
                    idx = y * STRIDE + x // 8
                    bit = 0x80 >> (x % 8)            # MSB = leftmost dot
                    frame[idx] ^= bit                # flip this one dot
                    sock.sendto(bytes(frame), (DISPLAY_IP, UDP_PORT))
                    state = "yellow" if frame[idx] & bit else "black"
                    print(f"{time.strftime('%H:%M:%S')}  ({x:2d},{y:2d}) -> {state}")
                    time.sleep(INTERVAL_S)
    except KeyboardInterrupt:
        pass
    finally:
        sock.sendto(bytes(FRAME_BYTES), (DISPLAY_IP, UDP_PORT))   # clear on exit
        sock.close()


if __name__ == "__main__":
    main()