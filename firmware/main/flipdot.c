#include "flipdot.h"

#include <stdbool.h>
#include <string.h>

#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "panel_hw.h"

// 200 us is what the bench panel flips reliably with at 24 V. The reference
// firmware doubles yellow; try that if yellow flips turn out unreliable, but it
// raises the peak coil current from 0.75 A to about 1.1 A.
#define PULSE_BLACK_US 200
#define PULSE_YELLOW_US 200

// Differential updates mean a sender alternating two frames would hit the same
// coil at the full dot rate, for which the coil has no thermal margin. Limiting
// how often a frame can be adopted limits how often any single dot can flip.
#define MIN_FRAME_INTERVAL_US (250 * 1000)

static SemaphoreHandle_t s_lock;
static TaskHandle_t s_task;
static uint8_t s_pending[FRAME_BYTES];
static bool s_pending_dirty;

// Only touched by the driver task, after flipdot_start has finished with them.
static uint8_t s_target[FRAME_BYTES];
static uint8_t s_shown[FRAME_BYTES];
static int64_t s_last_adopt_us = -MIN_FRAME_INTERVAL_US;

static void flip_dot(uint16_t x, uint16_t y, dot_colour_t colour)
{
    panel_hw_pulse(flipdot_dot_frame(flipdot_locate(x, y), colour),
                   colour == DOT_YELLOW ? PULSE_YELLOW_US : PULSE_BLACK_US);
}

static void adopt_pending_frame(void)
{
    int64_t now = esp_timer_get_time();
    if (now - s_last_adopt_us < MIN_FRAME_INTERVAL_US) {
        return;
    }
    xSemaphoreTake(s_lock, portMAX_DELAY);
    if (s_pending_dirty) {
        memcpy(s_target, s_pending, FRAME_BYTES);
        s_pending_dirty = false;
        s_last_adopt_us = now;
    }
    xSemaphoreGive(s_lock);
}

// Flips the first dot that differs from the target. Returns false if none does.
static bool flip_next_dot(void)
{
    for (uint16_t i = 0; i < FRAME_BYTES; i++) {
        uint8_t diff = s_target[i] ^ s_shown[i];
        if (diff == 0) {
            continue;
        }
        uint8_t bit = 0;
        while (!(diff & (0x80 >> bit))) {
            bit++;
        }
        uint8_t mask = 0x80 >> bit;
        flip_dot((i % DISPLAY_STRIDE) * 8 + bit, i / DISPLAY_STRIDE,
                 (s_target[i] & mask) ? DOT_YELLOW : DOT_BLACK);
        s_shown[i] ^= mask;
        return true;
    }
    return false;
}

static void driver_task(void *arg)
{
    for (;;) {
        // Checked before every dot, so a new message interrupts a slow redraw.
        adopt_pending_frame();
        if (!flip_next_dot()) {
            ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(50));
        }
    }
}

void flipdot_start(void)
{
    s_lock = xSemaphoreCreateMutex();
    configASSERT(s_lock);

    panel_hw_init();

    // Dots latch, so the state left over from before this boot is unknown.
    for (uint16_t y = 0; y < DISPLAY_H; y++) {
        for (uint16_t x = 0; x < DISPLAY_W; x++) {
            flip_dot(x, y, DOT_BLACK);
        }
    }

    BaseType_t ok = xTaskCreate(driver_task, "flipdot", 4096, NULL, 5, &s_task);
    configASSERT(ok == pdPASS);
}

void flipdot_show(const uint8_t *frame)
{
    xSemaphoreTake(s_lock, portMAX_DELAY);
    memcpy(s_pending, frame, FRAME_BYTES);
    s_pending_dirty = true;
    xSemaphoreGive(s_lock);
    xTaskNotifyGive(s_task);
}
