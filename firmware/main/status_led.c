#include "status_led.h"

#include <stdbool.h>
#include <stdint.h>

#include "driver/gpio.h"
#include "driver/rmt_tx.h"
#include "esp_check.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

// ESP32-C6-DevKitC-1. GPIO8 is a strapping pin, which only matters during reset.
#define PIN_LED GPIO_NUM_8

// 0.1 us per RMT tick, for the WS2812 bit timings below.
#define RMT_RESOLUTION_HZ (10 * 1000 * 1000)
#define RMT_DONE_TIMEOUT_MS 50

#define TICK_MS 100
#define BLINK_TICKS 5

// The LED is bright and shares the supply, so keep it dim.
#define LEVEL 16

typedef struct {
    uint8_t g, r, b;  // the order the LED expects
} colour_t;

static const colour_t OFF = {0, 0, 0};
static const colour_t BLUE = {0, 0, LEVEL};
static const colour_t YELLOW = {LEVEL, LEVEL, 0};
static const colour_t GREEN = {LEVEL, 0, 0};
static const colour_t PURPLE = {0, LEVEL, LEVEL};
static const colour_t WHITE = {LEVEL, LEVEL, LEVEL};

static rmt_channel_handle_t s_rmt;
static rmt_encoder_handle_t s_encoder;
static volatile status_t s_status = STATUS_BOOTING;
static volatile bool s_flash;

// Errors are ignored: a status light is not worth taking the display down for.
static void write_colour(colour_t colour)
{
    const rmt_transmit_config_t tx_cfg = {.loop_count = 0};
    if (rmt_transmit(s_rmt, s_encoder, &colour, sizeof(colour), &tx_cfg) == ESP_OK) {
        rmt_tx_wait_all_done(s_rmt, RMT_DONE_TIMEOUT_MS);
    }
}

static colour_t colour_for(status_t status, uint32_t tick)
{
    switch (status) {
    case STATUS_BOOTING:
        return BLUE;
    case STATUS_CONNECTING:
        return (tick / BLINK_TICKS) % 2 ? OFF : YELLOW;
    case STATUS_ONLINE:
        return GREEN;
    case STATUS_NO_NETWORK:
        return PURPLE;
    case STATUS_UPDATING:
        return (tick / BLINK_TICKS) % 2 ? OFF : BLUE;
    }
    return OFF;
}

static void led_task(void *arg)
{
    for (uint32_t tick = 0;; tick++) {
        if (s_flash) {
            s_flash = false;
            write_colour(WHITE);
        } else {
            write_colour(colour_for(s_status, tick));
        }
        vTaskDelay(pdMS_TO_TICKS(TICK_MS));
    }
}

void status_led_start(void)
{
    const rmt_tx_channel_config_t rmt_cfg = {
        .gpio_num = PIN_LED,
        .clk_src = RMT_CLK_SRC_DEFAULT,
        .resolution_hz = RMT_RESOLUTION_HZ,
        .mem_block_symbols = SOC_RMT_MEM_WORDS_PER_CHANNEL,
        .trans_queue_depth = 1,
    };
    ESP_ERROR_CHECK(rmt_new_tx_channel(&rmt_cfg, &s_rmt));
    const rmt_bytes_encoder_config_t encoder_cfg = {
        .bit0 = {.level0 = 1, .duration0 = 3, .level1 = 0, .duration1 = 9},
        .bit1 = {.level0 = 1, .duration0 = 9, .level1 = 0, .duration1 = 3},
        .flags.msb_first = 1,
    };
    ESP_ERROR_CHECK(rmt_new_bytes_encoder(&encoder_cfg, &s_encoder));
    ESP_ERROR_CHECK(rmt_enable(s_rmt));

    BaseType_t ok = xTaskCreate(led_task, "status_led", 2048, NULL, 1, NULL);
    configASSERT(ok == pdPASS);
}

void status_led_set(status_t status)
{
    s_status = status;
}

void status_led_flash(void)
{
    s_flash = true;
}
