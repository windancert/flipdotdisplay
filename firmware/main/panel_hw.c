#include "panel_hw.h"

#include "driver/gpio.h"
#include "driver/rmt_tx.h"
#include "driver/spi_master.h"
#include "esp_check.h"
#include "esp_log.h"
#include "esp_rom_sys.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "sdkconfig.h"

#if !CONFIG_IDF_TARGET_ESP32C6
// This pin map is for the C6; on the S3, GPIO19 and GPIO20 are USB.
#error "The shift-register driver only has a C6 pin map; use CONFIG_FLIPDOT_DIRECT_DRIVE"
#endif

// None of these are strapping pins, and all are broken out on both the
// ESP32-C6-DevKitC-1 and the XIAO ESP32-C6.
#define PIN_SER GPIO_NUM_18
#define PIN_SRCLK GPIO_NUM_19
#define PIN_RCLK GPIO_NUM_20
#define PIN_STROBE GPIO_NUM_21  // high = U3 outputs enabled, through the inverter

#define SPI_CLOCK_HZ (4 * 1000 * 1000)
#define RMT_RESOLUTION_HZ (1000 * 1000)
#define RMT_DONE_TIMEOUT_MS 50

// Measured 0.25 A ceiling applies at this dot rate, so never go faster.
#define MIN_PULSE_PERIOD_US 335

static const char *TAG = "panel_hw";

static spi_device_handle_t s_spi;
static rmt_channel_handle_t s_rmt;
static rmt_encoder_handle_t s_encoder;
static int64_t s_last_pulse_us;

static void shift_and_latch(shift_frame_t frame)
{
    const uint8_t bytes[] = {frame.u3, frame.u2, frame.u1};
    spi_transaction_t t = {.length = sizeof(bytes) * 8, .tx_buffer = bytes};
    ESP_ERROR_CHECK(spi_device_polling_transmit(s_spi, &t));

    gpio_set_level(PIN_RCLK, 1);
    gpio_set_level(PIN_RCLK, 0);
}

void panel_hw_init(void)
{
    // The RMT idles low, which holds the strobe inactive from here on. Before
    // this, the inverter's gate pull-down does the same.
    const rmt_tx_channel_config_t rmt_cfg = {
        .gpio_num = PIN_STROBE,
        .clk_src = RMT_CLK_SRC_DEFAULT,
        .resolution_hz = RMT_RESOLUTION_HZ,
        .mem_block_symbols = SOC_RMT_MEM_WORDS_PER_CHANNEL,
        .trans_queue_depth = 1,
    };
    ESP_ERROR_CHECK(rmt_new_tx_channel(&rmt_cfg, &s_rmt));
    const rmt_copy_encoder_config_t encoder_cfg = {};
    ESP_ERROR_CHECK(rmt_new_copy_encoder(&encoder_cfg, &s_encoder));
    ESP_ERROR_CHECK(rmt_enable(s_rmt));

    const gpio_config_t rclk_cfg = {
        .pin_bit_mask = 1ULL << PIN_RCLK,
        .mode = GPIO_MODE_OUTPUT,
    };
    ESP_ERROR_CHECK(gpio_config(&rclk_cfg));
    gpio_set_level(PIN_RCLK, 0);

    const spi_bus_config_t bus_cfg = {
        .mosi_io_num = PIN_SER,
        .miso_io_num = -1,
        .sclk_io_num = PIN_SRCLK,
        .quadwp_io_num = -1,
        .quadhd_io_num = -1,
        .max_transfer_sz = sizeof(shift_frame_t),
    };
    ESP_ERROR_CHECK(spi_bus_initialize(SPI2_HOST, &bus_cfg, SPI_DMA_DISABLED));
    const spi_device_interface_config_t dev_cfg = {
        .clock_speed_hz = SPI_CLOCK_HZ,
        .mode = 0,
        .spics_io_num = -1,
        .queue_size = 1,
    };
    ESP_ERROR_CHECK(spi_bus_add_device(SPI2_HOST, &dev_cfg, &s_spi));

    shift_and_latch(flipdot_idle_frame());
}

bool panel_hw_has_sel(uint8_t sel)
{
    return sel < 8;
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

    // The latch only reaches the panel's address lines: the strobe bits stay
    // behind U3's disabled outputs, so the address is settled before any current
    // flows, and a crash at this point leaves the coil off.
    shift_and_latch(frame);

    // The RMT ends the pulse by itself. From here on a hung CPU cannot hold the
    // coil on, and neither WiFi interrupts nor the scheduler can stretch it.
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

    shift_and_latch(flipdot_idle_frame());
}
