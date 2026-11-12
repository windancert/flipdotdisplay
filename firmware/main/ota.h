// Firmware updates over WiFi, with automatic rollback of a build that can't get online.
#pragma once

#include "esp_http_server.h"

// Call first thing at boot. If this is a new update, starts the rollback timer.
void ota_start(void);

// Call once the network is up. Accepts the running update and stops the timer.
void ota_mark_good(void);

// Adds POST /update and GET /version to the server.
void ota_register(httpd_handle_t server);
