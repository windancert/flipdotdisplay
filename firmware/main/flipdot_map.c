#include "flipdot_map.h"

// U1
#define U1_COL_HL (1u << 5)
// U2
#define U2_SEL6 (1u << 5)
// U3
#define U3_ROW_HIGH (1u << 0)
#define U3_ROW_LOW (1u << 1)
#define U3_SEL0 (1u << 2)

static geometry_t s_geo;

void flipdot_set_geometry(const geometry_t *g)
{
    s_geo = *g;
}

const geometry_t *flipdot_geometry(void)
{
    return &s_geo;
}

uint8_t flipdot_addr(uint8_t n)
{
    return (uint8_t)(((n / 7) << 3) | ((n % 7) + 1));
}

dot_location_t flipdot_locate(uint16_t x, uint16_t y)
{
    const panel_t *panel = &s_geo.panels[(y / s_geo.panel_rows) * s_geo.panels_x + x / s_geo.panel_cols];
    uint8_t col = x % s_geo.panel_cols;
    uint8_t row = y % s_geo.panel_rows;
    if (panel->rotated) {
        col = s_geo.panel_cols - 1 - col;
        row = s_geo.panel_rows - 1 - row;
    }
    return (dot_location_t){.sel = panel->sel, .col = col, .row = row};
}

void flipdot_clear_padding(uint8_t *frame)
{
    if (s_geo.width % 8 == 0) {
        return;
    }
    const uint8_t mask = (uint8_t)(0xFF << (8 - s_geo.width % 8));
    for (int y = 0; y < s_geo.height; y++) {
        frame[y * s_geo.stride + s_geo.stride - 1] &= mask;
    }
}

shift_frame_t flipdot_dot_frame(dot_location_t loc, dot_colour_t colour)
{
    shift_frame_t f = flipdot_idle_frame();
    f.u1 = flipdot_addr(loc.row);
    f.u2 = flipdot_addr(loc.col);

    // Colour is the direction of the current through the coil.
    if (colour == DOT_YELLOW) {
        f.u3 |= U3_ROW_HIGH;
    } else {
        f.u1 |= U1_COL_HL;
        f.u3 |= U3_ROW_LOW;
    }

    if (loc.sel < 6) {
        f.u3 |= (uint8_t)(U3_SEL0 << loc.sel);
    } else {
        f.u2 |= (uint8_t)(U2_SEL6 << (loc.sel - 6));
    }
    return f;
}

shift_frame_t flipdot_idle_frame(void)
{
    return (shift_frame_t){.u3 = 0, .u2 = 0, .u1 = 0};
}
