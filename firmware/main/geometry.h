// Display geometry: panel size, how the panels are arranged and which COL-SEL line
// each one answers on. Pure parsing and formatting, no ESP-IDF dependencies, so the
// host tests can run it.
//
// Text form, as stored in NVS and exchanged over HTTP:
//
//     28x16 1x2 4 0r
//
// Dots per panel (columns x rows), panels across x down, then one entry per panel,
// seen from the front, top row first and left to right: its COL-SEL line, with an r
// if the panel is mounted rotated 180 degrees. Entries are separated by whitespace.
#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

// The 5-bit address reaches 28 dots either way, and there are 8 COL-SEL lines.
#define GEOMETRY_MAX_PANEL_DOTS 28
#define GEOMETRY_MAX_PANELS 8

// The largest frame any valid geometry needs: 8 panels of 28 x 28 stacked in one
// column, 4 bytes per row x 224 rows.
#define GEOMETRY_MAX_FRAME_BYTES 896

// Longer than the longest canonical text (34 characters), leaving room for
// extra whitespace in what clients send.
#define GEOMETRY_TEXT_MAX 128

// Used when nothing valid is stored: one upright panel on COL-SEL0.
#define GEOMETRY_DEFAULT "28x16 1x1 0"

typedef struct {
    uint8_t sel;
    bool rotated;  // mounted 180 degrees, so both axes are mirrored
} panel_t;

typedef struct {
    uint8_t panel_cols, panel_rows;
    uint8_t panels_x, panels_y;
    panel_t panels[GEOMETRY_MAX_PANELS];  // row-major, [0] is the top-left panel

    // Derived by geometry_parse.
    uint16_t width, height;  // in dots
    uint16_t stride;         // bytes per frame row, padded to whole bytes
    uint16_t frame_bytes;
} geometry_t;

// Fills *g from text. On failure returns false and points *err at a message.
bool geometry_parse(const char *text, geometry_t *g, const char **err);

// Writes the canonical text form, which geometry_parse reads back unchanged.
void geometry_format(const geometry_t *g, char *buf, size_t size);
