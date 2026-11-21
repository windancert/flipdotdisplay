#!/usr/bin/env python3
"""Show the latest P2000 alarm for the fire station on the flip-dot display.

Listens to the MQTT topic with messages already filtered for the station (the
broker retains the last one, so it shows right after starting), keeps only those
for the capcode that means trucks are rolling, and shows the type of emergency
and the location. Priority, region codes, unit capcodes and parentheticals are
dropped. Text that doesn't fit on one screen alternates between pages.

Needs paho-mqtt 2 (pip install paho-mqtt) and mqtt_config.py, copied from
mqtt_config.example.py.

    python3 p2000_display.py                      # run
    python3 p2000_display.py --all                # every message nationwide
    python3 p2000_display.py --preview "P 1 ..."  # print how a message would look
"""
import argparse
import json
import re
import socket
import threading
import time
import unicodedata

from display import DISPLAY_IP, UDP_PORT, display_size, stride

# Kazernealarm Eindhoven-Centrum: the trucks actually roll. Other capcodes on the
# same message (the station's Lichtkrant, volunteer drivers) don't count.
STATION_CAPCODE = 1106973

# Every message the receiver decodes, nationwide, for --all.
ALL_TOPIC = "p2000/melding"

PAGE_S = 4  # how long each page shows when the text needs more than one

# 5x7 letters and digits, "#" lit; the lowercase follows the HD44780 LCD font,
# which keeps descenders inside the 7 rows. Each character takes 6 columns including the
# gap, and each line 8 rows, so every 16-row panel holds exactly 2 lines and
# 56 x 32 dots hold 9 characters on 4 lines.
FONT = {
    "A": [".###.", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"],
    "B": ["####.", "#...#", "#...#", "####.", "#...#", "#...#", "####."],
    "C": [".###.", "#...#", "#....", "#....", "#....", "#...#", ".###."],
    "D": ["###..", "#..#.", "#...#", "#...#", "#...#", "#..#.", "###.."],
    "E": ["#####", "#....", "#....", "####.", "#....", "#....", "#####"],
    "F": ["#####", "#....", "#....", "####.", "#....", "#....", "#...."],
    "G": [".###.", "#...#", "#....", "#.###", "#...#", "#...#", ".####"],
    "H": ["#...#", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"],
    "I": [".###.", "..#..", "..#..", "..#..", "..#..", "..#..", ".###."],
    "J": ["..###", "...#.", "...#.", "...#.", "...#.", "#..#.", ".##.."],
    "K": ["#...#", "#..#.", "#.#..", "##...", "#.#..", "#..#.", "#...#"],
    "L": ["#....", "#....", "#....", "#....", "#....", "#....", "#####"],
    "M": ["#...#", "##.##", "#.#.#", "#.#.#", "#...#", "#...#", "#...#"],
    "N": ["#...#", "#...#", "##..#", "#.#.#", "#..##", "#...#", "#...#"],
    "O": [".###.", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."],
    "P": ["####.", "#...#", "#...#", "####.", "#....", "#....", "#...."],
    "Q": [".###.", "#...#", "#...#", "#...#", "#.#.#", "#..#.", ".##.#"],
    "R": ["####.", "#...#", "#...#", "####.", "#.#..", "#..#.", "#...#"],
    "S": [".####", "#....", "#....", ".###.", "....#", "....#", "####."],
    "T": ["#####", "..#..", "..#..", "..#..", "..#..", "..#..", "..#.."],
    "U": ["#...#", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."],
    "V": ["#...#", "#...#", "#...#", "#...#", "#...#", ".#.#.", "..#.."],
    "W": ["#...#", "#...#", "#...#", "#.#.#", "#.#.#", "#.#.#", ".#.#."],
    "X": ["#...#", "#...#", ".#.#.", "..#..", ".#.#.", "#...#", "#...#"],
    "Y": ["#...#", "#...#", ".#.#.", "..#..", "..#..", "..#..", "..#.."],
    "Z": ["#####", "....#", "...#.", "..#..", ".#...", "#....", "#####"],
    "a": [".....", ".....", ".###.", "....#", ".####", "#...#", ".####"],
    "b": ["#....", "#....", "#.##.", "##..#", "#...#", "#...#", "####."],
    "c": [".....", ".....", ".###.", "#....", "#....", "#...#", ".###."],
    "d": ["....#", "....#", ".##.#", "#..##", "#...#", "#...#", ".####"],
    "e": [".....", ".....", ".###.", "#...#", "#####", "#....", ".###."],
    "f": ["..##.", ".#..#", ".#...", "###..", ".#...", ".#...", ".#..."],
    "g": [".....", ".####", "#...#", "#...#", ".####", "....#", ".###."],
    "h": ["#....", "#....", "#.##.", "##..#", "#...#", "#...#", "#...#"],
    "i": ["..#..", ".....", ".##..", "..#..", "..#..", "..#..", ".###."],
    "j": ["...#.", ".....", "..##.", "...#.", "...#.", "#..#.", ".##.."],
    "k": ["#....", "#....", "#..#.", "#.#..", "##...", "#.#..", "#..#."],
    "l": [".##..", "..#..", "..#..", "..#..", "..#..", "..#..", ".###."],
    "m": [".....", ".....", "##.#.", "#.#.#", "#.#.#", "#...#", "#...#"],
    "n": [".....", ".....", "#.##.", "##..#", "#...#", "#...#", "#...#"],
    "o": [".....", ".....", ".###.", "#...#", "#...#", "#...#", ".###."],
    "p": [".....", ".....", "####.", "#...#", "####.", "#....", "#...."],
    "q": [".....", ".....", ".##.#", "#..##", ".####", "....#", "....#"],
    "r": [".....", ".....", "#.##.", "##..#", "#....", "#....", "#...."],
    "s": [".....", ".....", ".###.", "#....", ".###.", "....#", "####."],
    "t": [".#...", ".#...", "###..", ".#...", ".#...", ".#..#", "..##."],
    "u": [".....", ".....", "#...#", "#...#", "#...#", "#..##", ".##.#"],
    "v": [".....", ".....", "#...#", "#...#", "#...#", ".#.#.", "..#.."],
    "w": [".....", ".....", "#...#", "#...#", "#.#.#", "#.#.#", ".#.#."],
    "x": [".....", ".....", "#...#", ".#.#.", "..#..", ".#.#.", "#...#"],
    "y": [".....", ".....", "#...#", "#...#", ".####", "....#", ".###."],
    "z": [".....", ".....", "#####", "...#.", "..#..", ".#...", "#####"],
    "0": [".###.", "#...#", "#..##", "#.#.#", "##..#", "#...#", ".###."],
    "1": ["..#..", ".##..", "..#..", "..#..", "..#..", "..#..", ".###."],
    "2": [".###.", "#...#", "....#", "...#.", "..#..", ".#...", "#####"],
    "3": ["#####", "...#.", "..#..", "...#.", "....#", "#...#", ".###."],
    "4": ["...#.", "..##.", ".#.#.", "#..#.", "#####", "...#.", "...#."],
    "5": ["#####", "#....", "####.", "....#", "....#", "#...#", ".###."],
    "6": ["..##.", ".#...", "#....", "####.", "#...#", "#...#", ".###."],
    "7": ["#####", "....#", "...#.", "..#..", ".#...", ".#...", ".#..."],
    "8": [".###.", "#...#", "#...#", ".###.", "#...#", "#...#", ".###."],
    "9": [".###.", "#...#", "#...#", ".####", "....#", "...#.", ".##.."],
    "-": [".....", ".....", ".....", "#####", ".....", ".....", "....."],
    ".": [".....", ".....", ".....", ".....", ".....", ".##..", ".##.."],
    ",": [".....", ".....", ".....", ".....", ".##..", "..#..", ".#..."],
    ":": [".....", ".##..", ".##..", ".....", ".##..", ".##..", "....."],
    "/": [".....", "....#", "...#.", "..#..", ".#...", "#....", "....."],
    "'": [".##..", "..#..", ".#...", ".....", ".....", ".....", "....."],
    "&": [".##..", "#..#.", "#.#..", ".#...", "#.#.#", "#..#.", ".##.#"],
    "?": [".###.", "#...#", "....#", "...#.", "..#..", ".....", "..#.."],
    " ": [".....", ".....", ".....", ".....", ".....", ".....", "....."],
}
CHAR_W, LINE_H = 6, 8


def clean(message):
    """The type of emergency and the location, without codes and numbers.

    "P 2 BOB-03 Liftopsluiting Theresia Woonzorgcentrum Bredalaan Eindhoven 222332"
    becomes "Liftopsluiting Theresia Woonzorgcentrum Bredalaan".
    """
    text = re.sub(r"\([^)]*\)", " ", message)                      # parentheticals
    text = re.sub(r"^\s*(prio\s*\d|[PAB]\s?\d)\b", " ", text, flags=re.I)  # priority
    text = re.sub(r"\b[A-Z]{2,3}-\d{1,2}\b", " ", text)            # BOB-03 and the like
    text = re.sub(r"\brit:?\s*\d+", " ", text, flags=re.I)         # ambulance trip numbers
    text = re.sub(r"(\s+\d{5,})+\s*$", " ", text)                  # unit capcodes
    text = re.sub(r"\s+eindhoven\s*$", " ", text, flags=re.I)      # local is the default
    return " ".join(text.split())


def wrap(text, width):
    """Word-wraps to lines of at most width characters.

    A line may also break after a "/" within a word; words that still don't fit
    are hyphenated.
    """
    lines, line = [], ""
    for word in text.split():
        # Pieces of the word that may end a line, joined without a space.
        for k, piece in enumerate(re.split(r"(?<=/)(?=.)", word)):
            sep = "" if k else " "
            if line and len(line) + len(sep) + len(piece) <= width:
                line += sep + piece
                continue
            if line:
                lines.append(line)
            while len(piece) > width:
                lines.append(piece[:width - 1] + "-")
                piece = piece[width - 1:]
            line = piece
    if line:
        lines.append(line)
    return lines


def to_font(text):
    """The text without accents, with anything the font lacks shown as "?"."""
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return "".join(c if c in FONT else "?" for c in plain)


def render(lines, cols, rows):
    """One frame with the lines centred both ways.

    Lines sit in fixed 8-row slots, centred by whole slots, so none straddles the
    seam between two rows of panels.
    """
    row_bytes = stride(cols)
    frame = bytearray(row_bytes * rows)
    top = ((rows + 1) // LINE_H - len(lines)) // 2 * LINE_H
    for i, line in enumerate(lines):
        left = (cols - (len(line) * CHAR_W - 1)) // 2
        for j, char in enumerate(line):
            for y, bits in enumerate(FONT[char]):
                for x, bit in enumerate(bits):
                    if bit == "#":
                        px, py = left + j * CHAR_W + x, top + i * LINE_H + y
                        frame[py * row_bytes + px // 8] |= 0x80 >> (px % 8)
    return bytes(frame)


def pack(text, width):
    """Fills every line to the full width, hyphenating words wherever they break."""
    lines, line = [], ""
    for word in text.split():
        if line and len(line) + 1 + len(word) <= width:
            line += " " + word
            continue
        if line:
            # Start the word on this line if a useful part of it fits.
            room = width - len(line) - 1
            if room >= 3 and len(word) > room:
                lines.append(line + " " + word[:room - 1] + "-")
                word = word[room - 1:]
            else:
                lines.append(line)
        while len(word) > width:
            lines.append(word[:width - 1] + "-")
            word = word[width - 1:]
        line = word
    if line:
        lines.append(line)
    return lines


def frames_for(message, cols, rows, one_page=False):
    """The pages that show a message, each a ready frame.

    With one_page, as much of the message as fits on a single page, the rest cut off.
    """
    per_page = (rows + 1) // LINE_H
    text, width = to_font(clean(message)), (cols + 1) // CHAR_W
    lines = wrap(text, width)
    if one_page:
        if len(lines) > per_page:
            lines = pack(text, width)
        return [render(lines[:per_page], cols, rows)]
    # Spread the lines evenly, so 5 lines become 3 + 2 rather than 4 + 1.
    count = max(1, -(-len(lines) // per_page))
    per_page = -(-len(lines) // count) or 1
    pages = [lines[i:i + per_page] for i in range(0, len(lines), per_page)] or [[]]
    return [render(page, cols, rows) for page in pages]


def preview(frame, cols, rows):
    row_bytes = stride(cols)
    for y in range(rows):
        print("".join("#" if frame[y * row_bytes + x // 8] & (0x80 >> (x % 8)) else "."
                      for x in range(cols)))


def message_text(payload, station_only=True):
    """The message text, or None if unreadable or (station_only) not for the station."""
    try:
        alarm = json.loads(payload)
        capcodes = {int(c) for c in alarm.get("capcodes", [])}
        message = alarm["message"]
    except (ValueError, KeyError, TypeError):
        print(f"ignored unreadable message: {payload[:200]!r}")
        return None
    return message if not station_only or STATION_CAPCODE in capcodes else None


def run(show_all):
    import paho.mqtt.client as mqtt

    import mqtt_config

    topic = ALL_TOPIC if show_all else mqtt_config.MQTT_TOPIC
    cols, rows = display_size()
    print(f"display is {cols} x {rows} dots")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    lock = threading.Lock()
    pages = [bytes(stride(cols) * rows)]  # dark until the first alarm

    def on_connect(client, userdata, flags, reason, properties):
        print(f"MQTT {mqtt_config.MQTT_HOST}: {reason}")
        if not reason.is_failure:
            client.subscribe(topic)

    def on_message(client, userdata, msg):
        message = message_text(msg.payload, station_only=not show_all)
        if message is None:
            return
        # Messages for the whole country follow each other too fast for pages.
        new = frames_for(message, cols, rows, one_page=show_all)
        print(f"{time.strftime('%H:%M:%S')}  {message}\n          -> {clean(message)}")
        with lock:
            pages[:] = new

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.username_pw_set(mqtt_config.MQTT_USER, mqtt_config.MQTT_PASSWORD)
    client.on_connect, client.on_message = on_connect, on_message
    client.connect_async(mqtt_config.MQTT_HOST, mqtt_config.MQTT_PORT)
    client.loop_start()  # reconnects by itself

    # Resending the current page each round covers lost datagrams and a display
    # that restarted; the display only flips dots that differ.
    page = 0
    try:
        while True:
            with lock:
                page = page % len(pages)
                frame = pages[page]
            sock.sendto(frame, (DISPLAY_IP, UDP_PORT))
            page += 1
            time.sleep(PAGE_S)
    except KeyboardInterrupt:
        pass
    finally:
        client.loop_stop()
        sock.sendto(bytes(stride(cols) * rows), (DISPLAY_IP, UDP_PORT))  # leave it dark
        sock.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--preview", metavar="MESSAGE",
                        help="print the pages for a P2000 message and exit")
    parser.add_argument("--size", default="56x32", metavar="COLSxROWS",
                        help="display size for --preview (default 56x32)")
    parser.add_argument("--all", action="store_true",
                        help=f"show every P2000 message nationwide ({ALL_TOPIC}), not just the station's")
    args = parser.parse_args()
    if args.preview:
        cols, rows = map(int, args.size.split("x"))
        print(clean(args.preview))
        for frame in frames_for(args.preview, cols, rows):
            print()
            preview(frame, cols, rows)
        return
    run(args.all)


if __name__ == "__main__":
    main()
