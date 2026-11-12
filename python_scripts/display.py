"""Where the display is and how big it is, shared by the scripts in this folder."""
import urllib.request

DISPLAY_IP = "192.168.42.199"
UDP_PORT = 7777


def display_size():
    """Dots across and down, from the geometry the display reports, e.g. "28x16 1x2 4 0r"."""
    with urllib.request.urlopen(f"http://{DISPLAY_IP}/geometry", timeout=5) as reply:
        panel, panels = reply.read().decode().split()[:2]
    panel_cols, panel_rows = map(int, panel.split("x"))
    across, down = map(int, panels.split("x"))
    return panel_cols * across, panel_rows * down


def stride(cols):
    """Bytes per frame row: 1 bit per dot, padded to whole bytes."""
    return (cols + 7) // 8
