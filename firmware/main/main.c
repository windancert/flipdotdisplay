#include <string.h>

#include "flipdot.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "net.h"
#include "sdkconfig.h"
#include "status_led.h"

#if CONFIG_FLIPDOT_BOOT_TEST
// Lights a 7x7 block in the top-left corner of each panel position in turn, left
// to right, top row first. Each block should appear at the top-left of the panel
// you expect; if not, the layout table in local_config.h is wrong.
static void boot_test(void)
{
    static uint8_t frame[FRAME_BYTES];
    for (int py = 0; py < DISPLAY_PANELS_Y; py++) {
        for (int px = 0; px < DISPLAY_PANELS_X; px++) {
            memset(frame, 0, sizeof(frame));
            for (int y = 0; y < 7; y++) {
                for (int x = 0; x < 7; x++) {
                    int dx = px * PANEL_COLS + x;
                    int dy = py * PANEL_ROWS + y;
                    frame[dy * DISPLAY_STRIDE + dx / 8] |= 0x80 >> (dx % 8);
                }
            }
            flipdot_show(frame);
            vTaskDelay(pdMS_TO_TICKS(2000));
        }
    }
    memset(frame, 0, sizeof(frame));
    flipdot_show(frame);
}
#endif

void app_main(void)
{
    status_led_start();
    flipdot_start();
#if CONFIG_FLIPDOT_BOOT_TEST
    boot_test();
#endif
    net_start();
}
