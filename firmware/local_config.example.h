// Copy to local_config.h and fill in. The display geometry is not set here: it lives
// in NVS and is set over HTTP, see README.md. local_config.h is gitignored, so the WiFi
// password stays out of the repository.
#pragma once

// Leave the SSID empty to run without networking (useful during bring-up).
#define WIFI_SSID ""
#define WIFI_PASSWORD ""
