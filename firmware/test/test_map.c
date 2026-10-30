// Host test for the addressing logic:
//   cc -std=c11 -Wall -Wextra -Imain test/test_map.c main/flipdot_map.c -o test/test_map && test/test_map
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>

#include "flipdot_map.h"

#define U1_COL_HL (1u << 5)
#define U3_ROW_HIGH (1u << 0)
#define U3_ROW_LOW (1u << 1)

static int popcount(unsigned v)
{
    int n = 0;
    for (; v; v &= v - 1) {
        n++;
    }
    return n;
}

static void test_addresses_are_unique_and_never_idle(void)
{
    bool seen[32] = {false};
    for (int n = 0; n < PANEL_COLS; n++) {
        uint8_t a = flipdot_addr((uint8_t)n);
        assert(a < 32);
        assert((a & 7) != 0);
        assert(!seen[a]);
        seen[a] = true;
    }
    assert(flipdot_addr(0) == 0b00001);
    assert(flipdot_addr(6) == 0b00111);
    assert(flipdot_addr(7) == 0b01001);
    assert(flipdot_addr(27) == 0b11111);
}

static void test_every_dot_maps_to_one_physical_dot(void)
{
    static bool seen[8][PANEL_COLS][PANEL_ROWS];
    for (int y = 0; y < DISPLAY_H; y++) {
        for (int x = 0; x < DISPLAY_W; x++) {
            dot_location_t l = flipdot_locate((uint16_t)x, (uint16_t)y);
            assert(l.sel < 8 && l.col < PANEL_COLS && l.row < PANEL_ROWS);
            assert(!seen[l.sel][l.col][l.row]);
            seen[l.sel][l.col][l.row] = true;
        }
    }
}

static void test_top_row_is_mirrored_on_both_axes(void)
{
    dot_location_t top = flipdot_locate(0, 0);
    assert(top.sel == 0 && top.col == 27 && top.row == 15);
    dot_location_t top_end = flipdot_locate(DISPLAY_W - 1, 15);
    assert(top_end.sel == 3 && top_end.col == 0 && top_end.row == 0);
    dot_location_t bottom = flipdot_locate(0, 16);
    assert(bottom.sel == 4 && bottom.col == 0 && bottom.row == 0);
    dot_location_t bottom_end = flipdot_locate(DISPLAY_W - 1, DISPLAY_H - 1);
    assert(bottom_end.sel == 7 && bottom_end.col == 27 && bottom_end.row == 15);
}

static void test_frame_bits(void)
{
    for (int sel = 0; sel < 8; sel++) {
        dot_location_t l = {.sel = (uint8_t)sel, .col = 9, .row = 8};
        for (int c = 0; c < 2; c++) {
            shift_frame_t f = flipdot_dot_frame(l, c ? DOT_YELLOW : DOT_BLACK);

            // Row 8 is bank 1 position 1, column 9 is bank 1 position 2.
            assert((f.u1 & 0x1f) == 0b01010);
            assert((f.u2 & 0x1f) == 0b01011);

            // Exactly one strobe, in the direction the colour calls for.
            assert(popcount(f.u3 & (U3_ROW_HIGH | U3_ROW_LOW)) == 1);
            if (c) {
                assert((f.u3 & U3_ROW_HIGH) && !(f.u1 & U1_COL_HL));
            } else {
                assert((f.u3 & U3_ROW_LOW) && (f.u1 & U1_COL_HL));
            }

            // Exactly the one COL-SEL line, across its two registers.
            unsigned sels = (f.u3 >> 2) | ((unsigned)(f.u2 >> 5) << 6);
            assert(sels == (1u << sel));
        }
    }
}

static void test_idle_frame_selects_nothing(void)
{
    shift_frame_t f = flipdot_idle_frame();
    assert(f.u1 == 0 && f.u2 == 0 && f.u3 == 0);
}

int main(void)
{
    test_addresses_are_unique_and_never_idle();
    test_every_dot_maps_to_one_physical_dot();
    test_top_row_is_mirrored_on_both_axes();
    test_frame_bits();
    test_idle_frame_selects_nothing();
    puts("ok");
    return 0;
}
