// Pure addressing logic: display coordinates -> panel input line patterns.
// No ESP-IDF dependencies, so test/test_map.c can run it on the host.
#pragma once

#include <stdbool.h>
#include <stdint.h>

#include "geometry.h"

// Frames are 1 bit per dot, row-major, MSB is the leftmost dot. 1 = yellow,
// 0 = black. Rows are padded to whole bytes; the geometry gives the sizes.

typedef enum { DOT_BLACK = 0, DOT_YELLOW = 1 } dot_colour_t;

// The state of every panel input line for one pulse. The grouping into three
// bytes is that of the shift-register chain of an earlier design.
typedef struct {
    uint8_t u3;  // bits 0-7: ROW-HIGH, ROW-LOW, COL-SEL0-5
    uint8_t u2;  // bits 0-6: COL0-4, COL-SEL6-7
    uint8_t u1;  // bits 0-5: ROW0-4, COL-H/L
} shift_frame_t;

// Which physical panel and which of its dots sit at a display coordinate.
typedef struct {
    uint8_t sel;  // COL-SEL line, 0-7
    uint8_t col;  // 0-27
    uint8_t row;  // 0-15
} dot_location_t;

// Sets the geometry every other call works with. Call before the driver starts;
// g must have come from geometry_parse.
void flipdot_set_geometry(const geometry_t *g);
const geometry_t *flipdot_geometry(void);

// One-of-7 address: the low 3 bits are never 0 here, because 0 selects nothing.
uint8_t flipdot_addr(uint8_t n);

dot_location_t flipdot_locate(uint16_t x, uint16_t y);

// Clears the padding bits at the end of each row, which address no dot.
void flipdot_clear_padding(uint8_t *frame);

// The lines for one dot, including the polarity strobe that panel_hw_pulse times.
shift_frame_t flipdot_dot_frame(dot_location_t loc, dot_colour_t colour);

// Everything deselected, strobes off.
shift_frame_t flipdot_idle_frame(void);
