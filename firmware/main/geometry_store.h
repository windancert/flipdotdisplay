// The display geometry kept in NVS, and the HTTP endpoints that change it.
#pragma once

#include "esp_http_server.h"

// Reads the stored geometry, or the default if none is stored or it doesn't fit
// this board, and hands it to flipdot_set_geometry. Needs NVS to be initialised.
void geometry_load(void);

// Adds GET /geometry, which returns the text form, and POST /geometry, which stores
// a new one and restarts the board to apply it.
void geometry_register(httpd_handle_t server);
