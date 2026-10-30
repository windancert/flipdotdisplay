// Firmware updates over WiFi, with automatic rollback of a build that can't get online.
#pragma once

// Call first thing at boot. If this is a new update, starts the rollback timer.
void ota_start(void);

// Call once the network is up. Accepts the running update and stops the timer.
void ota_mark_good(void);

// Serves POST /update and GET /version. Needs the network stack to be initialised.
void ota_server_start(void);
