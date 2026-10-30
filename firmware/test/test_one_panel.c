// Host test for a geometry with padded rows:
//   cc -std=c11 -Wall -Wextra -Itest/one_panel -Imain test/test_one_panel.c main/flipdot_map.c -o test/test_one_panel && test/test_one_panel
#include <assert.h>
#include <stdio.h>
#include <string.h>

#include "flipdot_map.h"

int main(void)
{
    assert(DISPLAY_STRIDE == 4);
    assert(FRAME_BYTES == 64);

    uint8_t frame[FRAME_BYTES];
    memset(frame, 0xFF, sizeof(frame));
    flipdot_clear_padding(frame);
    for (int y = 0; y < DISPLAY_H; y++) {
        // The 28 real dots survive, the 4 padding bits don't.
        assert(frame[y * 4] == 0xFF && frame[y * 4 + 1] == 0xFF && frame[y * 4 + 2] == 0xFF);
        assert(frame[y * 4 + 3] == 0xF0);
    }

    dot_location_t last = flipdot_locate(DISPLAY_W - 1, DISPLAY_H - 1);
    assert(last.sel == 0 && last.col == 27 && last.row == 15);

    puts("ok");
    return 0;
}
