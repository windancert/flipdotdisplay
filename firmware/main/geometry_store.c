#include "geometry_store.h"

#include <string.h>

#include "esp_log.h"
#include "esp_system.h"
#include "flipdot.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "nvs.h"
#include "panel_hw.h"

#define NVS_NAMESPACE "flipdot"
#define NVS_KEY "geometry"

#define RESTART_DELAY_MS 500

static const char *TAG = "geometry";

// geometry_parse only knows the 8 COL-SEL lines exist; this board may wire fewer.
static bool fits_board(const geometry_t *g, const char **err)
{
    for (int i = 0; i < g->panels_x * g->panels_y; i++) {
        if (!panel_hw_has_sel(g->panels[i].sel)) {
            *err = "a panel uses a COL-SEL line this board has no GPIO for";
            return false;
        }
    }
    return true;
}

static bool read_stored(char *text, size_t size)
{
    nvs_handle_t nvs;
    if (nvs_open(NVS_NAMESPACE, NVS_READONLY, &nvs) != ESP_OK) {
        return false;
    }
    esp_err_t err = nvs_get_str(nvs, NVS_KEY, text, &size);
    nvs_close(nvs);
    return err == ESP_OK;
}

static esp_err_t write_stored(const char *text)
{
    nvs_handle_t nvs;
    esp_err_t err = nvs_open(NVS_NAMESPACE, NVS_READWRITE, &nvs);
    if (err != ESP_OK) {
        return err;
    }
    err = nvs_set_str(nvs, NVS_KEY, text);
    if (err == ESP_OK) {
        err = nvs_commit(nvs);
    }
    nvs_close(nvs);
    return err;
}

void geometry_load(void)
{
    char text[GEOMETRY_TEXT_MAX];
    geometry_t g;
    const char *err = "nothing stored";
    if (!read_stored(text, sizeof(text)) || !geometry_parse(text, &g, &err) || !fits_board(&g, &err)) {
        ESP_LOGW(TAG, "using the default geometry: %s", err);
        bool ok = geometry_parse(GEOMETRY_DEFAULT, &g, &err) && fits_board(&g, &err);
        configASSERT(ok);
    }
    flipdot_set_geometry(&g);

    geometry_format(&g, text, sizeof(text));
    ESP_LOGI(TAG, "%s: %u x %u dots, %u-byte frames", text, g.width, g.height, g.frame_bytes);
}

static esp_err_t handle_get(httpd_req_t *req)
{
    char text[GEOMETRY_TEXT_MAX + 1];
    geometry_format(flipdot_geometry(), text, GEOMETRY_TEXT_MAX);
    strcat(text, "\n");
    return httpd_resp_sendstr(req, text);
}

static esp_err_t handle_set(httpd_req_t *req)
{
    char text[GEOMETRY_TEXT_MAX];
    if (req->content_len == 0 || req->content_len >= sizeof(text)) {
        return httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "geometry missing or too long");
    }
    size_t received = 0;
    while (received < req->content_len) {
        int len = httpd_req_recv(req, text + received, req->content_len - received);
        if (len <= 0) {
            return ESP_FAIL;  // the server closes the connection
        }
        received += len;
    }
    text[received] = '\0';

    geometry_t g;
    const char *err;
    if (!geometry_parse(text, &g, &err) || !fits_board(&g, &err)) {
        return httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, err);
    }

    char canonical[GEOMETRY_TEXT_MAX];
    char current[GEOMETRY_TEXT_MAX];
    geometry_format(&g, canonical, sizeof(canonical));
    geometry_format(flipdot_geometry(), current, sizeof(current));
    if (strcmp(canonical, current) == 0) {
        return httpd_resp_sendstr(req, "unchanged\n");
    }

    // Flash writes can delay the interrupt that ends a pulse.
    flipdot_pause();
    esp_err_t store_err = write_stored(canonical);
    if (store_err != ESP_OK) {
        flipdot_resume();
        ESP_LOGE(TAG, "storing failed: %s", esp_err_to_name(store_err));
        return httpd_resp_send_err(req, HTTPD_500_INTERNAL_SERVER_ERROR, esp_err_to_name(store_err));
    }

    // Buffer sizes and the blackout at boot both follow the geometry, so the
    // simplest correct way to apply a new one is to start over.
    ESP_LOGI(TAG, "stored %s, restarting", canonical);
    httpd_resp_sendstr(req, "stored, restarting\n");
    vTaskDelay(pdMS_TO_TICKS(RESTART_DELAY_MS));
    esp_restart();
    return ESP_OK;
}

void geometry_register(httpd_handle_t server)
{
    const httpd_uri_t get = {.uri = "/geometry", .method = HTTP_GET, .handler = handle_get};
    const httpd_uri_t set = {.uri = "/geometry", .method = HTTP_POST, .handler = handle_set};
    ESP_ERROR_CHECK(httpd_register_uri_handler(server, &get));
    ESP_ERROR_CHECK(httpd_register_uri_handler(server, &set));
}
