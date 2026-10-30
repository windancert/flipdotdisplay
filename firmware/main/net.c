#include "net.h"

#include <string.h>

#include "esp_check.h"
#include "esp_event.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_wifi.h"
#include "flipdot.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "lwip/sockets.h"
#include "nvs_flash.h"
#include "status_led.h"

static const char *TAG = "net";

static void on_wifi_event(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    if (base == WIFI_EVENT && (id == WIFI_EVENT_STA_START || id == WIFI_EVENT_STA_DISCONNECTED)) {
        if (id == WIFI_EVENT_STA_DISCONNECTED) {
            const wifi_event_sta_disconnected_t *event = data;
            ESP_LOGW(TAG, "WiFi connect failed or lost, reason %d", event->reason);
        }
        status_led_set(STATUS_CONNECTING);
        esp_wifi_connect();
    } else if (base == IP_EVENT && id == IP_EVENT_STA_GOT_IP) {
        status_led_set(STATUS_ONLINE);
        const ip_event_got_ip_t *event = data;
        ESP_LOGI(TAG, "listening on " IPSTR ":%d", IP2STR(&event->ip_info.ip),
                 CONFIG_FLIPDOT_UDP_PORT);
    }
}

static void wifi_start(void)
{
    esp_err_t err = nvs_flash_init();
    if (err == ESP_ERR_NVS_NO_FREE_PAGES || err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        err = nvs_flash_init();
    }
    ESP_ERROR_CHECK(err);

    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_sta();

    const wifi_init_config_t init_cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&init_cfg));
    ESP_ERROR_CHECK(esp_event_handler_register(WIFI_EVENT, ESP_EVENT_ANY_ID, on_wifi_event, NULL));
    ESP_ERROR_CHECK(esp_event_handler_register(IP_EVENT, IP_EVENT_STA_GOT_IP, on_wifi_event, NULL));

    wifi_config_t wifi_cfg = {};
    strlcpy((char *)wifi_cfg.sta.ssid, CONFIG_FLIPDOT_WIFI_SSID, sizeof(wifi_cfg.sta.ssid));
    strlcpy((char *)wifi_cfg.sta.password, CONFIG_FLIPDOT_WIFI_PASSWORD, sizeof(wifi_cfg.sta.password));
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &wifi_cfg));
    ESP_ERROR_CHECK(esp_wifi_start());
}

static void udp_task(void *arg)
{
    int sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_IP);
    configASSERT(sock >= 0);

    const struct sockaddr_in addr = {
        .sin_family = AF_INET,
        .sin_port = htons(CONFIG_FLIPDOT_UDP_PORT),
        .sin_addr.s_addr = htonl(INADDR_ANY),
    };
    int err = bind(sock, (const struct sockaddr *)&addr, sizeof(addr));
    configASSERT(err == 0);

    // One byte extra, so an oversized datagram shows up as the wrong length
    // instead of being silently truncated to a valid one.
    static uint8_t buf[FRAME_BYTES + 1];
    for (;;) {
        int len = recv(sock, buf, sizeof(buf), 0);
        if (len == FRAME_BYTES) {
            flipdot_show(buf);
            status_led_flash();
        } else {
            ESP_LOGW(TAG, "dropped datagram of %d bytes, expected %d", len, FRAME_BYTES);
        }
    }
}

void net_start(void)
{
    if (strlen(CONFIG_FLIPDOT_WIFI_SSID) == 0) {
        ESP_LOGW(TAG, "no WiFi SSID configured, running without network");
        status_led_set(STATUS_NO_NETWORK);
        return;
    }
    wifi_start();
    BaseType_t ok = xTaskCreate(udp_task, "udp", 4096, NULL, 4, NULL);
    configASSERT(ok == pdPASS);
}
