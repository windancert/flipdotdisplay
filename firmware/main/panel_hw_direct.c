// Direct-drive variant of panel_hw: panels wired straight to the GPIOs, with no
// 74HCT595 shift registers. Selected by CONFIG_FLIPDOT_DIRECT_DRIVE.
//
// It implements the same interface as panel_hw.c and consumes the same
// shift_frame_t, whose bits already match the panel's input lines one-for-one, so
// flipdot.c and flipdot_map.c are untouched. Only the emission changes: the bits
// are fanned out to GPIOs and the active polarity strobe is pulsed by the RMT.
//
// Address, polarity and strobe lines are shared by every panel. With more than one
// ribbon, each shared GPIO goes to the same pin on every ribbon; only the COL-SEL
// lines are per panel. COL-SEL0-3 are pins 19-22 of ribbon A (top row), COL-SEL4-7
// pins 19-22 of ribbon B (bottom row). Ribbon pins in brackets below.
//
// ROW0-4 are wired straight to ribbon pins 5-9; the panel's 6<->7 row crossing is
// undone in firmware (ROW_BIT). COL-SEL and strobe lines need external 10k
// pull-downs, since they float until panel_hw_init runs.
//
// Both polarity strobes share ONE RMT channel: its output is re-pointed to ROW-HIGH
// or ROW-LOW through the GPIO matrix per pulse, and the idle polarity pin is driven
// low as a plain GPIO, so only one strobe is ever live. The C6 needs this, as it has
// only two RMT TX channels and the status LED owns one.

#include "panel_hw.h"

#include "driver/gpio.h"
#include "driver/rmt_tx.h"
#include "esp_check.h"
#include "esp_log.h"
#include "esp_rom_gpio.h"
#include "esp_rom_sys.h"
#include "esp_timer.h"
#include "flipdot_map.h"
#include "freertos/FreeRTOS.h"
#include "sdkconfig.h"
#include "soc/gpio_sig_map.h"  // SIG_GPIO_OUT_IDX
#include "soc/gpio_struct.h"   // read back the RMT output signal from the matrix

#if CONFIG_IDF_TARGET_ESP32C6
// ESP32-C6-DevKitC-1, one ribbon, two panels side by side (COL-SEL0/1).
// GPIO4 and GPIO5 (COL0, COL1) are strapping pins, but they only drive address
// lines, and nothing flows while the strobes are held low by their pull-downs.
static const gpio_num_t ROW_PINS[5] = {GPIO_NUM_18, GPIO_NUM_19, GPIO_NUM_20, GPIO_NUM_21, GPIO_NUM_22};
static const gpio_num_t COL_PINS[5] = {GPIO_NUM_4, GPIO_NUM_5, GPIO_NUM_6, GPIO_NUM_7, GPIO_NUM_0};
#define PIN_COL_HL GPIO_NUM_23    // [18]
#define PIN_ROW_HIGH GPIO_NUM_10  // [10]
#define PIN_ROW_LOW GPIO_NUM_11   // [11]
static const gpio_num_t SEL_PINS[8] = {
    GPIO_NUM_1, GPIO_NUM_2,  // [19, 20] left and right panel
    GPIO_NUM_NC, GPIO_NUM_NC, GPIO_NUM_NC, GPIO_NUM_NC, GPIO_NUM_NC, GPIO_NUM_NC,
};
#elif CONFIG_IDF_TARGET_ESP32S3
// Waveshare ESP32-S3-Pico, two ribbons, room for all eight panels. Header pins only,
// avoiding GPIO33-37, which Waveshare lists for PSRAM. Each group is an unbroken run
// down the header, apart from GND and RUN pins; Pico header pins in parentheses.
// Left header, top to bottom: ROW0-4, COL0-4, COL-H/L, in the ribbon's own order.
static const gpio_num_t ROW_PINS[5] = {GPIO_NUM_10, GPIO_NUM_9, GPIO_NUM_8, GPIO_NUM_7, GPIO_NUM_6};  // (35-29)
static const gpio_num_t COL_PINS[5] = {GPIO_NUM_5, GPIO_NUM_4, GPIO_NUM_2, GPIO_NUM_1, GPIO_NUM_41};  // (27-22)
#define PIN_COL_HL GPIO_NUM_42  // [18] (21)
// Right header: COL-SEL0-7 at the top, the strobes at the bottom.
static const gpio_num_t SEL_PINS[8] = {
    GPIO_NUM_11, GPIO_NUM_12, GPIO_NUM_13, GPIO_NUM_14,  // ribbon A [19-22] (1-5)
    GPIO_NUM_15, GPIO_NUM_16, GPIO_NUM_17, GPIO_NUM_18,  // ribbon B [19-22] (6-10)
};
#define PIN_ROW_HIGH GPIO_NUM_38  // [10] (17)
#define PIN_ROW_LOW GPIO_NUM_39   // [11] (19)
#else
#error "No direct-drive pin map for this target"
#endif

// Bit positions within shift_frame_t, matching flipdot_dot_frame(). ROW0-4 are
// u1 bits 0-4, COL0-4 are u2 bits 0-4, COL-SEL0-5 u3 bits 2-7, COL-SEL6-7 u2 bits 5-6.
#define U1_COL_HL_BIT (1u << 5)
#define U3_ROW_HIGH_BIT (1u << 0)
#define U3_ROW_LOW_BIT (1u << 1)

#define RMT_RESOLUTION_HZ (1000 * 1000)
#define RMT_DONE_TIMEOUT_MS 50

// Measured 0.25 A ceiling applies at this dot rate, so never go faster.
#define MIN_PULSE_PERIOD_US 335
// Address lines settle before the strobe; HC decoders need only tens of ns.
#define ADDR_SETTLE_US 2

static const char *TAG = "panel_hw_direct";

static rmt_channel_handle_t s_rmt;
static rmt_encoder_handle_t s_encoder;
static uint32_t s_strobe_sig;             // RMT TX output signal, read from the matrix
static gpio_num_t s_rmt_pin = PIN_ROW_HIGH;  // strobe pin the RMT currently drives
static int64_t s_last_pulse_us;

static bool sel_active(shift_frame_t frame, int sel)
{
    return sel < 6 ? (frame.u3 >> (2 + sel)) & 1 : (frame.u2 >> (5 + sel - 6)) & 1;
}

// A panel on an unwired COL-SEL line would simply never respond, so say so.
static void check_layout(void)
{
    for (int py = 0; py < DISPLAY_PANELS_Y; py++) {
        for (int px = 0; px < DISPLAY_PANELS_X; px++) {
            uint8_t sel = flipdot_locate(px * PANEL_COLS, py * PANEL_ROWS).sel;
            if (sel >= 8 || SEL_PINS[sel] == GPIO_NUM_NC) {
                ESP_LOGE(TAG, "panel at %d,%d uses COL-SEL%u, which has no GPIO here", px, py, sel);
            }
        }
    }
}

// Points the single RMT channel at one strobe pin, parking the other as a driven-
// low GPIO, so only the chosen polarity can be energised.
static void route_rmt_to(gpio_num_t pin)
{
    if (pin == s_rmt_pin) {
        return;
    }
    // Park the pin the RMT is leaving: back to plain GPIO, held low.
    esp_rom_gpio_connect_out_signal(s_rmt_pin, SIG_GPIO_OUT_IDX, false, false);
    gpio_set_direction(s_rmt_pin, GPIO_MODE_OUTPUT);
    gpio_set_level(s_rmt_pin, 0);
    // Route the RMT output to the new pin; this also enables its output path.
    esp_rom_gpio_connect_out_signal(pin, s_strobe_sig, false, false);
    s_rmt_pin = pin;
}

void panel_hw_init(void)
{
    // All driven pins start as outputs held low. The external 10k pull-downs on the
    // strobe and select lines cover the window before this runs, while they float.
    uint64_t mask = (1ULL << PIN_COL_HL) | (1ULL << PIN_ROW_HIGH) | (1ULL << PIN_ROW_LOW);
    for (int i = 0; i < 5; i++) {
        mask |= (1ULL << ROW_PINS[i]) | (1ULL << COL_PINS[i]);
    }
    for (int i = 0; i < 8; i++) {
        if (SEL_PINS[i] != GPIO_NUM_NC) {
            mask |= 1ULL << SEL_PINS[i];
        }
    }
    const gpio_config_t out_cfg = {.pin_bit_mask = mask, .mode = GPIO_MODE_OUTPUT};
    ESP_ERROR_CHECK(gpio_config(&out_cfg));
    for (int pin = 0; pin < 64; pin++) {
        if (mask & (1ULL << pin)) {
            gpio_set_level(pin, 0);
        }
    }

    // One TX channel, initially bound to ROW-HIGH. Reading the signal it connected
    // back out of the matrix means the reroute never depends on the channel number.
    const rmt_tx_channel_config_t rmt_cfg = {
        .gpio_num = PIN_ROW_HIGH,
        .clk_src = RMT_CLK_SRC_DEFAULT,
        .resolution_hz = RMT_RESOLUTION_HZ,
        .mem_block_symbols = SOC_RMT_MEM_WORDS_PER_CHANNEL,
        .trans_queue_depth = 1,
    };
    ESP_ERROR_CHECK(rmt_new_tx_channel(&rmt_cfg, &s_rmt));
#if CONFIG_IDF_TARGET_ESP32S3
    s_strobe_sig = GPIO.func_out_sel_cfg[PIN_ROW_HIGH].func_sel;
#else
    s_strobe_sig = GPIO.func_out_sel_cfg[PIN_ROW_HIGH].out_sel;
#endif
    s_rmt_pin = PIN_ROW_HIGH;

    const rmt_copy_encoder_config_t enc_cfg = {};
    ESP_ERROR_CHECK(rmt_new_copy_encoder(&enc_cfg, &s_encoder));
    ESP_ERROR_CHECK(rmt_enable(s_rmt));

    check_layout();
}

// The panel swaps ribbon pins 6 and 7 (pin 6 = ROW2, pin 7 = ROW1). With ROW_PINS[i]
// wired straight to ribbon pin 5 + i, undo that here: ROW_PINS[1] (pin 6) carries
// row address bit 2, ROW_PINS[2] (pin 7) carries bit 1.
static const uint8_t ROW_BIT[5] = {0, 2, 1, 3, 4};

static void set_lines(shift_frame_t frame)
{
    for (int i = 0; i < 5; i++) {
        gpio_set_level(ROW_PINS[i], (frame.u1 >> ROW_BIT[i]) & 1);
        gpio_set_level(COL_PINS[i], (frame.u2 >> i) & 1);
    }
    gpio_set_level(PIN_COL_HL, (frame.u1 & U1_COL_HL_BIT) ? 1 : 0);
    for (int i = 0; i < 8; i++) {
        if (SEL_PINS[i] != GPIO_NUM_NC) {
            gpio_set_level(SEL_PINS[i], sel_active(frame, i));
        }
    }
}

static void strobe(uint32_t width_us)
{
    // The RMT ends the pulse itself, so a hung CPU, a WiFi interrupt or the
    // scheduler cannot stretch it.
    const rmt_symbol_word_t pulse = {
        .level0 = 1,
        .duration0 = width_us,
        .level1 = 0,
        .duration1 = 1,
    };
    const rmt_transmit_config_t tx_cfg = {.loop_count = 0, .flags.eot_level = 0};
    s_last_pulse_us = esp_timer_get_time();
    ESP_ERROR_CHECK(rmt_transmit(s_rmt, s_encoder, &pulse, sizeof(pulse), &tx_cfg));
    ESP_ERROR_CHECK(rmt_tx_wait_all_done(s_rmt, RMT_DONE_TIMEOUT_MS));
}

void panel_hw_pulse(shift_frame_t frame, uint32_t width_us)
{
    if (width_us > PANEL_PULSE_MAX_US) {
        ESP_LOGE(TAG, "pulse of %lu us clamped", (unsigned long)width_us);
        width_us = PANEL_PULSE_MAX_US;
    }

    int64_t wait_us = s_last_pulse_us + MIN_PULSE_PERIOD_US - esp_timer_get_time();
    if (wait_us > 0) {
        esp_rom_delay_us((uint32_t)wait_us);
    }

    // Address and select settle while both strobes are low, so no current flows
    // until the pulse, and a crash here leaves every coil off.
    set_lines(frame);
    esp_rom_delay_us(ADDR_SETTLE_US);

    // Exactly one polarity strobe fires per dot: ROW-HIGH for yellow, ROW-LOW for
    // black. The idle frame sets neither, so nothing is energised.
    if (frame.u3 & U3_ROW_HIGH_BIT) {
        route_rmt_to(PIN_ROW_HIGH);
        strobe(width_us);
    } else if (frame.u3 & U3_ROW_LOW_BIT) {
        route_rmt_to(PIN_ROW_LOW);
        strobe(width_us);
    }

    // Back to idle: deselect and clear the address.
    set_lines(flipdot_idle_frame());
}
