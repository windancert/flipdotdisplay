// Pure addressing logic: display coordinates -> 74HCT595 bit patterns.
// No ESP-IDF dependencies, so test/test_map.c can run it on the host.
#pragma once

#include <stdbool.h>
#include <stdint.h>

#define PANEL_COLS 28
#define PANEL_ROWS 16
#define DISPLAY_PANELS_X 4
#define DISPLAY_PANELS_Y 2
#define DISPLAY_W (PANEL_COLS * DISPLAY_PANELS_X)
#define DISPLAY_H (PANEL_ROWS * DISPLAY_PANELS_Y)

// 1 bit per dot, row-major, MSB is the leftmost dot. 1 = yellow, 0 = black.
#define DISPLAY_STRIDE (DISPLAY_W / 8)
#define FRAME_BYTES (DISPLAY_STRIDE * DISPLAY_H)

typedef enum { DOT_BLACK = 0, DOT_YELLOW = 1 } dot_colour_t;

// Bytes in the order they go out on SPI. The first byte travels furthest down
// the chain and ends up in U3. Within a byte, bit 0 lands on QA, bit 7 on QH.
typedef struct {
    uint8_t u3;  // ROW-HIGH, ROW-LOW, COL-SEL0-5: outputs gated by the strobe OE
    uint8_t u2;  // COL0-4, COL-SEL6-7
    uint8_t u1;  // ROW0-4, COL-H/L
} shift_frame_t;

// Which physical panel and which of its dots sit at a display coordinate.
typedef struct {
    uint8_t sel;  // COL-SEL line, 0-7
    uint8_t col;  // 0-27
    uint8_t row;  // 0-15
} dot_location_t;

// One-of-7 address: the low 3 bits are never 0 here, because 0 selects nothing.
uint8_t flipdot_addr(uint8_t n);

dot_location_t flipdot_locate(uint16_t x, uint16_t y);

// The bits to latch for one dot. The strobe bit is included, but stays invisible
// to the panel until the U3 output enable is pulsed.
shift_frame_t flipdot_dot_frame(dot_location_t loc, dot_colour_t colour);

// Everything deselected, strobes off.
shift_frame_t flipdot_idle_frame(void);
