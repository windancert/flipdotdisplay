// Host test for the addressing logic:
//   cc -std=c11 -Wall -Wextra -Imain test/test_map.c main/flipdot_map.c main/geometry.c -o test/test_map && test/test_map
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>

#include "flipdot_map.h"

#define U1_COL_HL (1u << 5)
#define U3_ROW_HIGH (1u << 0)
#define U3_ROW_LOW (1u << 1)

// The target build: top row rotated on COL-SEL0-3, bottom row upright on 4-7.
#define TARGET "28x16 4x2 0r 1r 2r 3r 4 5 6 7"

static void use(const char *text)
{
    geometry_t g;
    const char *err = NULL;
    assert(geometry_parse(text, &g, &err));
    flipdot_set_geometry(&g);
}

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
    for (int n = 0; n < GEOMETRY_MAX_PANEL_DOTS; n++) {
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
    use(TARGET);
    const geometry_t *g = flipdot_geometry();
    static bool seen[8][28][16];
    for (int y = 0; y < g->height; y++) {
        for (int x = 0; x < g->width; x++) {
            dot_location_t l = flipdot_locate((uint16_t)x, (uint16_t)y);
            assert(l.sel < 8 && l.col < 28 && l.row < 16);
            assert(!seen[l.sel][l.col][l.row]);
            seen[l.sel][l.col][l.row] = true;
        }
    }
}

static void test_top_row_is_mirrored_on_both_axes(void)
{
    use(TARGET);
    dot_location_t top = flipdot_locate(0, 0);
    assert(top.sel == 0 && top.col == 27 && top.row == 15);
    dot_location_t top_end = flipdot_locate(111, 15);
    assert(top_end.sel == 3 && top_end.col == 0 && top_end.row == 0);
    dot_location_t bottom = flipdot_locate(0, 16);
    assert(bottom.sel == 4 && bottom.col == 0 && bottom.row == 0);
    dot_location_t bottom_end = flipdot_locate(111, 31);
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

static void test_parse_target(void)
{
    geometry_t g;
    const char *err;
    assert(geometry_parse(TARGET, &g, &err));
    assert(g.panel_cols == 28 && g.panel_rows == 16 && g.panels_x == 4 && g.panels_y == 2);
    assert(g.width == 112 && g.height == 32 && g.stride == 14 && g.frame_bytes == 448);
    assert(g.panels[0].sel == 0 && g.panels[0].rotated);
    assert(g.panels[7].sel == 7 && !g.panels[7].rotated);

    char text[GEOMETRY_TEXT_MAX];
    geometry_format(&g, text, sizeof(text));
    assert(strcmp(text, TARGET) == 0);
}

static void test_parse_is_lenient_about_whitespace_only(void)
{
    geometry_t g;
    const char *err;
    assert(geometry_parse("  28x16\n1x2\t4   0r\r\n", &g, &err));
    char text[GEOMETRY_TEXT_MAX];
    geometry_format(&g, text, sizeof(text));
    assert(strcmp(text, "28x16 1x2 4 0r") == 0);
    assert(strcmp(GEOMETRY_DEFAULT, "28x16 1x1 0") == 0);
    assert(geometry_parse(GEOMETRY_DEFAULT, &g, &err));
}

static void test_parse_rejects(void)
{
    static const char *const bad[] = {
        "",
        "28x16",
        "28x16 1x1",                   // no panel entry
        "28x16 1x2 0",                 // too few panels
        "28x16 1x1 0 1",               // too many
        "29x16 1x1 0",                 // past the 5-bit address
        "28x0 1x1 0",
        "28x16 3x3 0 1 2 3 4 5 6 7 0", // 9 panels
        "28x16 0x1",
        "28x16 1x1 8",                 // no COL-SEL8
        "28x16 1x2 1 1r",              // shared COL-SEL line
        "28x16 1x1 0x",
        "28x16 1x1 0rr",
        "28x16 1x1 -0",
        "28x16 1x1 +0",
        "28 x16 1x1 0",
        "28x16x1 1x1 0",
        "28x16 1x1 999999999999",
    };
    for (size_t i = 0; i < sizeof(bad) / sizeof(bad[0]); i++) {
        geometry_t g;
        const char *err = NULL;
        assert(!geometry_parse(bad[i], &g, &err));
        assert(err && *err);
    }
}

static void test_max_frame_bytes_is_the_true_maximum(void)
{
    int max = 0;
    for (int across = 1; across <= 8; across++) {
        for (int down = 1; across * down <= 8; down++) {
            int bytes = (28 * across + 7) / 8 * 28 * down;
            max = bytes > max ? bytes : max;
        }
    }
    assert(max == GEOMETRY_MAX_FRAME_BYTES);

    geometry_t g;
    const char *err;
    assert(geometry_parse("28x28 1x8 0 1 2 3 4 5 6 7", &g, &err));
    assert(g.frame_bytes == GEOMETRY_MAX_FRAME_BYTES);
}

static void test_one_panel_has_padded_rows(void)
{
    use("28x16 1x1 0");
    const geometry_t *g = flipdot_geometry();
    assert(g->stride == 4 && g->frame_bytes == 64);

    uint8_t frame[64];
    memset(frame, 0xFF, sizeof(frame));
    flipdot_clear_padding(frame);
    for (int y = 0; y < 16; y++) {
        // The 28 real dots survive, the 4 padding bits don't.
        assert(frame[y * 4] == 0xFF && frame[y * 4 + 1] == 0xFF && frame[y * 4 + 2] == 0xFF);
        assert(frame[y * 4 + 3] == 0xF0);
    }

    dot_location_t last = flipdot_locate(27, 15);
    assert(last.sel == 0 && last.col == 27 && last.row == 15);
}

static void test_bench_layout(void)
{
    // The S3 bench: ribbon B's panel upright on top, ribbon A's rotated below.
    use("28x16 1x2 4 0r");
    dot_location_t top = flipdot_locate(0, 0);
    assert(top.sel == 4 && top.col == 0 && top.row == 0);
    dot_location_t bottom = flipdot_locate(0, 16);
    assert(bottom.sel == 0 && bottom.col == 27 && bottom.row == 15);
}

int main(void)
{
    test_parse_target();
    test_parse_is_lenient_about_whitespace_only();
    test_parse_rejects();
    test_max_frame_bytes_is_the_true_maximum();
    test_one_panel_has_padded_rows();
    test_bench_layout();
    test_addresses_are_unique_and_never_idle();
    test_every_dot_maps_to_one_physical_dot();
    test_top_row_is_mirrored_on_both_axes();
    test_frame_bits();
    test_idle_frame_selects_nothing();
    puts("ok");
    return 0;
}
