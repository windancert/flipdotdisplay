#include <string.h>

#include "flipdot.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "geometry_store.h"
#include "net.h"
#include "nvs_flash.h"
#include "ota.h"
#include "sdkconfig.h"
#include "status_led.h"

#if CONFIG_FLIPDOT_BOOT_TEST
// Lights a 7x7 block in the top-left corner of each panel position in turn, left
// to right, top row first. Each block should appear at the top-left of the panel
// you expect; if not, the stored geometry is wrong.
static void boot_test(void)
{
    const geometry_t *geo = flipdot_geometry();
    static uint8_t frame[GEOMETRY_MAX_FRAME_BYTES];
    for (int py = 0; py < geo->panels_y; py++) {
        for (int px = 0; px < geo->panels_x; px++) {
            memset(frame, 0, sizeof(frame));
            for (int y = 0; y < 7 && y < geo->panel_rows; y++) {
                for (int x = 0; x < 7 && x < geo->panel_cols; x++) {
                    int dx = px * geo->panel_cols + x;
                    int dy = py * geo->panel_rows + y;
                    frame[dy * geo->stride + dx / 8] |= 0x80 >> (dx % 8);
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

static void nvs_start(void)
{
    esp_err_t err = nvs_flash_init();
    if (err == ESP_ERR_NVS_NO_FREE_PAGES || err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        err = nvs_flash_init();
    }
    ESP_ERROR_CHECK(err);
}

void app_main(void)
{
    ota_start();
    status_led_start();
    nvs_start();
    geometry_load();
    flipdot_start();
#if CONFIG_FLIPDOT_BOOT_TEST
    boot_test();
#endif
    net_start();
}
