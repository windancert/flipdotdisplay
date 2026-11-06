// Direct-drive bench variant of panel_hw: up to two panels wired straight to the C6's
// GPIOs, with no 74HCT595 shift registers. Selected by CONFIG_FLIPDOT_DIRECT_DRIVE.
//
// It implements the same interface as panel_hw.c and consumes the same
// shift_frame_t, whose bits already match the panel's input lines one-for-one, so
// flipdot.c and flipdot_map.c are untouched. Only the emission changes: the bits
// are fanned out to GPIOs and the active polarity strobe is pulsed by the RMT.
//
// Pin map, two 28x16 panels side by side (56x16), daisy-chained on one ribbon that
// shares every line except the per-panel COL-SEL. Each group is a contiguous run on
// the header so the wires bundle cleanly; the two strobe GPIOs share their ribbon pins.
// Ribbon pins (see CLAUDE.md / wiring diagram) in brackets.
//   ROW0-4   GPIO18-22  [ribbon 5,6,7,8,9]   straight 1:1; the panel's 6<->7 row
//                                            crossing is undone in firmware (ROW_BIT)
//   COL0-4   GPIO4,5,6,7,0  [ribbon 13-17]
//   COL-H/L  GPIO23     [ribbon 18]
//   COL-SEL0 GPIO1      [ribbon 19]   + external 10k pull-down  (left panel)
//   COL-SEL1 GPIO2      [ribbon 20]   + external 10k pull-down  (right panel)
//   ROW-HIGH GPIO10     [ribbon 10]   + external 10k pull-down, RMT-timed strobe
//   ROW-LOW  GPIO11     [ribbon 11]   + external 10k pull-down, RMT-timed strobe
//
// GPIO4 and GPIO5 (COL0, COL1) are strapping pins, but they only drive address
// lines, and nothing flows while the strobes are held low by their pull-downs. None
// of the pins are USB (12/13) or the UART console (16/17). Change the map here if
// your wiring differs.
//
// The C6 has only two RMT TX channels and the status LED already owns one, so the
// two polarity strobes share ONE RMT channel: its output is re-pointed to ROW-HIGH
// or ROW-LOW through the GPIO matrix per pulse. The idle polarity pin is driven low
// as a plain GPIO, so only one strobe is ever live.

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
#include "soc/gpio_sig_map.h"  // SIG_GPIO_OUT_IDX
#include "soc/gpio_struct.h"   // read back the RMT output signal from the matrix

_Static_assert(DISPLAY_PANELS_X * DISPLAY_PANELS_Y <= 2,
               "direct drive wires COL-SEL0 and COL-SEL1, so at most two panels");

// Address and static lines (plain outputs, idle low).
static const gpio_num_t ROW_PINS[5] = {GPIO_NUM_18, GPIO_NUM_19, GPIO_NUM_20, GPIO_NUM_21, GPIO_NUM_22};
static const gpio_num_t COL_PINS[5] = {GPIO_NUM_4, GPIO_NUM_5, GPIO_NUM_6, GPIO_NUM_7, GPIO_NUM_0};
#define PIN_COL_HL GPIO_NUM_23
#define PIN_SEL0 GPIO_NUM_1
#define PIN_SEL1 GPIO_NUM_2
// Polarity strobes (RMT-timed, idle low). One RMT channel drives whichever is active.
#define PIN_ROW_HIGH GPIO_NUM_10
#define PIN_ROW_LOW GPIO_NUM_11

// Bit positions within shift_frame_t, matching flipdot_dot_frame(). ROW0-4 are
// u1 bits 0-4, COL0-4 are u2 bits 0-4.
#define U1_COL_HL_BIT (1u << 5)
#define U3_ROW_HIGH_BIT (1u << 0)
#define U3_ROW_LOW_BIT (1u << 1)
#define U3_SEL0_BIT (1u << 2)
#define U3_SEL1_BIT (1u << 3)

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
    uint64_t mask = (1ULL << PIN_COL_HL) | (1ULL << PIN_SEL0) | (1ULL << PIN_SEL1) |
                    (1ULL << PIN_ROW_HIGH) | (1ULL << PIN_ROW_LOW);
    for (int i = 0; i < 5; i++) {
        mask |= (1ULL << ROW_PINS[i]) | (1ULL << COL_PINS[i]);
    }
    const gpio_config_t out_cfg = {.pin_bit_mask = mask, .mode = GPIO_MODE_OUTPUT};
    ESP_ERROR_CHECK(gpio_config(&out_cfg));
    for (int i = 0; i < 5; i++) {
        gpio_set_level(ROW_PINS[i], 0);
        gpio_set_level(COL_PINS[i], 0);
    }
    gpio_set_level(PIN_COL_HL, 0);
    gpio_set_level(PIN_SEL0, 0);
    gpio_set_level(PIN_SEL1, 0);
    gpio_set_level(PIN_ROW_HIGH, 0);
    gpio_set_level(PIN_ROW_LOW, 0);

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
    s_strobe_sig = GPIO.func_out_sel_cfg[PIN_ROW_HIGH].out_sel;
    s_rmt_pin = PIN_ROW_HIGH;

    const rmt_copy_encoder_config_t enc_cfg = {};
    ESP_ERROR_CHECK(rmt_new_copy_encoder(&enc_cfg, &s_encoder));
    ESP_ERROR_CHECK(rmt_enable(s_rmt));
}

// The panel swaps ribbon pins 6 and 7 (pin 6 = ROW2, pin 7 = ROW1). With a straight
// GPIO18->pin5 .. GPIO22->pin9 ribbon, undo that here: ROW_PINS[1] (GPIO19 -> pin 6)
// carries row address bit 2, ROW_PINS[2] (GPIO20 -> pin 7) carries bit 1.
static const uint8_t ROW_BIT[5] = {0, 2, 1, 3, 4};

static void set_lines(uint8_t u1, uint8_t u2, uint8_t u3)
{
    for (int i = 0; i < 5; i++) {
        gpio_set_level(ROW_PINS[i], (u1 >> ROW_BIT[i]) & 1);
        gpio_set_level(COL_PINS[i], (u2 >> i) & 1);
    }
    gpio_set_level(PIN_COL_HL, (u1 & U1_COL_HL_BIT) ? 1 : 0);
    gpio_set_level(PIN_SEL0, (u3 & U3_SEL0_BIT) ? 1 : 0);
    gpio_set_level(PIN_SEL1, (u3 & U3_SEL1_BIT) ? 1 : 0);
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
    set_lines(frame.u1, frame.u2, frame.u3);
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
    set_lines(0, 0, 0);
}
