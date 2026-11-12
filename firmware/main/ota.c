#include "ota.h"

#include <stdbool.h>
#include <stdio.h>

#include "esp_app_desc.h"
#include "esp_check.h"
#include "esp_http_server.h"
#include "esp_log.h"
#include "esp_ota_ops.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "flipdot.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "status_led.h"

// How long an update gets to reach the network before it is rolled back.
#define ROLLBACK_TIMEOUT_US (120 * 1000 * 1000)

// Each timeout is the HTTP server's 5 s receive wait.
#define MAX_RECV_TIMEOUTS 3

#define RESTART_DELAY_MS 500

static const char *TAG = "ota";

static esp_timer_handle_t s_rollback_timer;

static void on_rollback_timeout(void *arg)
{
    ESP_LOGE(TAG, "update did not reach the network, rolling back");
    esp_ota_mark_app_invalid_rollback_and_reboot();
}

void ota_start(void)
{
    esp_ota_img_states_t state;
    esp_err_t err = esp_ota_get_state_partition(esp_ota_get_running_partition(), &state);
    if (err != ESP_OK || state != ESP_OTA_IMG_PENDING_VERIFY) {
        return;
    }
    const esp_timer_create_args_t args = {.callback = on_rollback_timeout, .name = "ota_rollback"};
    ESP_ERROR_CHECK(esp_timer_create(&args, &s_rollback_timer));
    ESP_ERROR_CHECK(esp_timer_start_once(s_rollback_timer, ROLLBACK_TIMEOUT_US));
}

void ota_mark_good(void)
{
    if (s_rollback_timer == NULL) {
        return;
    }
    esp_timer_stop(s_rollback_timer);
    esp_timer_delete(s_rollback_timer);
    s_rollback_timer = NULL;
    ESP_ERROR_CHECK(esp_ota_mark_app_valid_cancel_rollback());
    ESP_LOGI(TAG, "update accepted");
}

// Streams the request body into the partition. On failure the partition is left
// unbootable and the running firmware stays selected.
static esp_err_t receive_image(httpd_req_t *req, const esp_partition_t *partition)
{
    esp_ota_handle_t ota;
    ESP_RETURN_ON_ERROR(esp_ota_begin(partition, OTA_WITH_SEQUENTIAL_WRITES, &ota), TAG, "begin failed");

    static char buf[4096];
    size_t remaining = req->content_len;
    int timeouts = 0;
    esp_err_t err = ESP_OK;
    while (remaining > 0 && err == ESP_OK) {
        int len = httpd_req_recv(req, buf, remaining < sizeof(buf) ? remaining : sizeof(buf));
        if (len == HTTPD_SOCK_ERR_TIMEOUT && ++timeouts < MAX_RECV_TIMEOUTS) {
            continue;
        }
        if (len <= 0) {
            err = ESP_ERR_INVALID_RESPONSE;
            break;
        }
        err = esp_ota_write(ota, buf, len);
        remaining -= len;
    }

    if (err != ESP_OK) {
        esp_ota_abort(ota);
        return err;
    }
    // Checks the image's integrity, and that it is built for this chip.
    ESP_RETURN_ON_ERROR(esp_ota_end(ota), TAG, "invalid image");
    return esp_ota_set_boot_partition(partition);
}

static esp_err_t handle_update(httpd_req_t *req)
{
    const esp_partition_t *partition = esp_ota_get_next_update_partition(NULL);
    if (partition == NULL || req->content_len == 0 || req->content_len > partition->size) {
        return httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "image missing or too large");
    }

    ESP_LOGI(TAG, "receiving %u bytes into %s", (unsigned)req->content_len, partition->label);
    status_led_set(STATUS_UPDATING);
    flipdot_pause();

    esp_err_t err = receive_image(req, partition);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "update failed: %s", esp_err_to_name(err));
        flipdot_resume();
        status_led_set(STATUS_ONLINE);
        return httpd_resp_send_err(req, HTTPD_500_INTERNAL_SERVER_ERROR, esp_err_to_name(err));
    }

    httpd_resp_sendstr(req, "update stored, restarting\n");
    vTaskDelay(pdMS_TO_TICKS(RESTART_DELAY_MS));
    esp_restart();
    return ESP_OK;
}

static esp_err_t handle_version(httpd_req_t *req)
{
    const esp_app_desc_t *app = esp_app_get_description();
    char body[128];
    snprintf(body, sizeof(body), "built %s %s, running from %s\n", app->date, app->time,
             esp_ota_get_running_partition()->label);
    return httpd_resp_sendstr(req, body);
}

void ota_register(httpd_handle_t server)
{
    const httpd_uri_t update = {.uri = "/update", .method = HTTP_POST, .handler = handle_update};
    const httpd_uri_t version = {.uri = "/version", .method = HTTP_GET, .handler = handle_version};
    ESP_ERROR_CHECK(httpd_register_uri_handler(server, &update));
    ESP_ERROR_CHECK(httpd_register_uri_handler(server, &version));
}
