"""The carrier board's parts and connections, shared by gen_sch.py and gen_pcb.py.

Board coordinates are millimetres from the board's top-left corner, y down,
seen from the component side.
"""
import sys

# Ribbon pins 5-18 are the same on both ribbons. Ribbon pins 6 and 7 are crossed on
# the panel (6 = ROW2, 7 = ROW1); the GPIOs run straight and the firmware undoes it.
SHARED = {
    5: "ROW0", 6: "ROW2", 7: "ROW1", 8: "ROW3", 9: "ROW4",
    10: "ROW_HIGH", 11: "ROW_LOW",
    13: "COL0", 14: "COL1", 15: "COL2", 16: "COL3", 17: "COL4", 18: "COL_HL",
}


def ribbon(sels):
    # The coils get their 20 V through the current-sense resistor R11.
    m = {1: "GND", 2: "GND", 3: "+3V3", 26: "COIL_20V"}
    m.update(SHARED)
    for i, s in enumerate(sels):
        m[19 + i] = s
    return m


# Waveshare ESP32-S3-Pico header pins (Raspberry Pi Pico numbering), from
# firmware/README.md and firmware/main/panel_hw.c. The S3 Pico's other GND pins
# (8, 13, 18, 23, 28, 33) are joined on the S3 Pico itself and left unconnected here;
# pin 18 sits next to the antenna, which wants as little copper around it as possible.
PICO = {
    1: "SEL0", 2: "SEL1", 3: "GND", 4: "SEL2", 5: "SEL3", 6: "SEL4", 7: "SEL5",
    9: "SEL6", 10: "SEL7", 17: "ROW_HIGH", 19: "ROW_LOW",
    21: "COL_HL", 22: "COL4", 24: "COL3", 25: "COL2", 26: "COL1", 27: "COL0",
    29: "ROW4", 31: "ROW3", 32: "ROW1", 34: "ROW2", 35: "ROW0",
    36: "+3V3", 38: "GND", 39: "VSYS",
}

PICO_PIN_NAMES = {
    1: "GPIO11", 2: "GPIO12", 3: "GND", 4: "GPIO13", 5: "GPIO14", 6: "GPIO15",
    7: "GPIO16", 8: "GND", 9: "GPIO17", 10: "GPIO18", 13: "GND", 17: "GPIO38",
    18: "GND", 19: "GPIO39", 20: "GPIO40", 21: "GPIO42", 22: "GPIO41", 23: "GND", 24: "GPIO1",
    25: "GPIO2", 26: "GPIO4", 27: "GPIO5", 28: "GND", 29: "GPIO6", 30: "RUN",
    31: "GPIO7", 32: "GPIO8", 33: "GND", 34: "GPIO9", 35: "GPIO10", 36: "3V3",
    38: "GND", 39: "VSYS", 40: "VBUS",
}

POWER_NETS = {"GND", "+3V3", "+5V", "+20V"}  # drawn with power symbols

# KiCad 10's own libraries, at its default install path.
if sys.platform == "darwin":
    KICAD_SHARE = "/Applications/KiCad/KiCad.app/Contents/SharedSupport"
else:
    KICAD_SHARE = "C:/Program Files/KiCad/10.0/share/kicad"
FP = f"{KICAD_SHARE}/footprints"

# ref, symbol, value, footprint, {pin: net}, schematic (x, y), board (x, y, rot), extra fields
PARTS = [
    ("U1", "flipdot:ESP32-S3-Pico", "Waveshare ESP32-S3-Pico",
     "Module:RaspberryPi_Pico_Common_THT", PICO, (101.6, 139.7), (43.82, 31.75, 0),
     {"Note": "Plugged into 2x 1x20 female headers, not soldered"}),
    ("J1", "Connector_Generic:Conn_02x13_Odd_Even", "Ribbon A (COL-SEL0-3)",
     "Connector_IDC:IDC-Header_2x13_P2.54mm_Vertical", ribbon(["SEL0", "SEL1", "SEL2", "SEL3"]),
     (215.9, 101.6), (101.6, 13.97, 0), {}),
    ("J2", "Connector_Generic:Conn_02x13_Odd_Even", "Ribbon B (COL-SEL4-7)",
     "Connector_IDC:IDC-Header_2x13_P2.54mm_Vertical", ribbon(["SEL4", "SEL5", "SEL6", "SEL7"]),
     (215.9, 177.8), (5.08, 13.97, 0), {}),
    ("J3", "Connector:Screw_Terminal_01x02", "20V in (from PD trigger)",
     "TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1,5-2-5.08_1x02_P5.08mm_Horizontal",
     {1: "+20V", 2: "GND"}, (30.48, 50.8), (83.82, 79.375, 0), {}),
    ("D1", "Device:D_Zener", "P6KE30CA", "Diode_THT:D_DO-15_P10.16mm_Horizontal",
     {1: "+20V", 2: "GND"}, (55.88, 50.8), (68.58, 55.88, 0),
     {"Note": "Bidirectional TVS, 25.6 V standoff, either way round (Reichelt P6KE 30CA)"}),
    ("C1", "Device:C_Polarized", "470uF 35V", "Capacitor_THT:CP_Radial_D12.5mm_P5.00mm",
     {1: "+20V", 2: "GND"}, (78.74, 50.8), (69.85, 66.04, 0), {}),
    ("D2", "Device:D_Schottky", "1N5819", "Diode_THT:D_DO-41_SOD81_P10.16mm_Horizontal",
     {1: "VIN_BUCK", 2: "+20V"}, (101.6, 50.8), (83.82, 55.88, 0), {}),
    ("C2", "Device:C_Polarized", "4.7uF 50V", "Capacitor_THT:CP_Radial_D5.0mm_P2.00mm",
     {1: "VIN_BUCK", 2: "GND"}, (124.46, 50.8), (99.06, 55.88, 0), {}),
    ("U2", "Converter_DCDC:R-78E5.0-1.0", "R-78E5.0-1.0",
     "Converter_DCDC:Converter_DCDC_RECOM_R-78E-0.5_THT",
     {1: "VIN_BUCK", 2: "GND", 3: "+5V"}, (152.4, 50.8), (83.82, 66.04, 0), {}),
    ("C3", "Device:C_Polarized", "100uF 16V", "Capacitor_THT:CP_Radial_D6.3mm_P2.50mm",
     {1: "+5V", 2: "GND"}, (182.88, 50.8), (69.85, 78.74, 0), {}),
    ("D3", "Device:D_Schottky", "1N5819", "Diode_THT:D_DO-41_SOD81_P10.16mm_Horizontal",
     {1: "VSYS", 2: "+5V"}, (208.28, 50.8), (96.52, 78.74, 90), {}),
    # Current sense for the coils: 0.1 ohm behind C1, so it carries the coil pulses
    # themselves. Scope across the I+ and I- test points: 100 mV is 1 A.
    ("R11", "Device:R", "0.1R 10%", "Resistor_THT:R_Axial_DIN0614_L14.3mm_D5.7mm_P20.32mm_Horizontal",
     {1: "+20V", 2: "COIL_20V"}, (101.6, 76.2), (71.12, 49.0, 0),
     {"Note": "Vitrohm BW235, 0.1 ohm 10%, 2 W wirewound (Reichelt 2W DRAHT 0,1); "
              "a wire link if no current sense is wanted"}),
    ("C4", "Device:C", "100nF", "Capacitor_THT:C_Disc_D5.0mm_W2.5mm_P5.00mm",
     {1: "+3V3", 2: "GND"}, (276.86, 101.6), (15.24, 19.05, 90), {}),
    ("C5", "Device:C", "100nF", "Capacitor_THT:C_Disc_D5.0mm_W2.5mm_P5.00mm",
     {1: "+3V3", 2: "GND"}, (276.86, 177.8), (95.25, 19.05, 90), {}),
]

# Each pull-down level with its S3 Pico pin where there is room (3.81 mm apart).
PULLDOWN_Y = [31.75 + 3.81 * i for i in range(8)] + [72.39, 77.47]
PULLDOWNS = ["SEL0", "SEL1", "SEL2", "SEL3", "SEL4", "SEL5", "SEL6", "SEL7", "ROW_HIGH", "ROW_LOW"]
for i, net in enumerate(PULLDOWNS):
    PARTS.append((f"R{i + 1}", "Device:R", "10k",
                  "Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal",
                  {1: net, 2: "GND"}, (50.8 + i * 20.32, 238.76),
                  (38.1, PULLDOWN_Y[i], 180), {}))

# Test points (Keystone 5000-series miniature loops): net, silkscreen label, board x, y.
# Signals along the top edge left of the USB plug; 3.3 V and a GND right of it; 20 V,
# 5 V, VSYS and a second GND in the power corner.
TESTPOINTS = [
    ("ROW_HIGH", "R-HI", 17.78, 6.35), ("ROW_LOW", "R-LO", 22.86, 6.35),
    ("ROW4", "ROW4", 27.94, 6.35), ("COL4", "COL4", 33.02, 6.35),
    ("SEL0", "SEL0", 38.1, 6.35), ("SEL4", "SEL4", 43.18, 6.35),
    ("+3V3", "3V3", 63.5, 6.35), ("GND", "GND", 68.58, 6.35),
    ("+20V", "20V", 102.87, 62.23), ("+5V", "5V", 102.87, 66.04),
    ("VSYS", "VSYS", 102.87, 69.85), ("GND", "GND", 102.87, 73.66),
    ("+20V", "I+", 71.12, 43.94), ("COIL_20V", "I-", 88.9, 43.94),
]
for i, (net, label, x, y) in enumerate(TESTPOINTS):
    PARTS.append((f"TP{i + 1}", "Connector:TestPoint", label,
                  "TestPoint:TestPoint_Keystone_5000-5004_Miniature", {1: net},
                  (50.8 + i * 15.24, 276.86), (x, y, 0), {}))

BOARD_W, BOARD_H = 111.0, 85.0
# The S3 Pico's antenna is on the short edge opposite USB, between the GPIO39/40 and
# GPIO41/42 pins, at the board's bottom edge. From the GPIO38 pin to the board edge,
# across the S3 Pico plus a margin: no copper fill and no vias, and tracks only where
# they have to reach a pin.
ANTENNA_AREA = (40.0, 70.0, 66.5, 85.0)
HOLES = [(3.5, 3.5), (107.5, 3.5), (3.5, 81.5), (107.5, 81.5)]
for i in range(4):
    PARTS.append((f"H{i + 1}", "Mechanical:MountingHole", "M3",
                  "MountingHole:MountingHole_3.2mm_M3", {}, (330.2 + i * 12.7, 254.0),
                  HOLES[i] + (0,), {}))
