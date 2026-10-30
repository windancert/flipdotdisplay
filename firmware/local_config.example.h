// Copy to local_config.h and fill in. local_config.h is gitignored, so the WiFi
// password stays out of the repository.
#pragma once

// Dots per panel. The 5-bit addressing allows at most 28 in either direction.
#define PANEL_COLS 28
#define PANEL_ROWS 16

// Panels in the array. The controller has 8 COL-SEL lines, so at most 8 in total,
// and the total width must be a multiple of 8.
#define DISPLAY_PANELS_X 4
#define DISPLAY_PANELS_Y 2

// {COL-SEL line, mounted rotated 180 degrees} for each panel seen from the front,
// top row first. Must match the panel counts above.
// If the ribbon headers turn out to shift the COL-SEL lines as they chain, the fix
// is to reorder the sel values here.
#define DISPLAY_LAYOUT                                \
    {                                                 \
        {{0, true}, {1, true}, {2, true}, {3, true}}, \
        {{4, false}, {5, false}, {6, false}, {7, false}}, \
    }

// Leave the SSID empty to run without networking (useful during bring-up).
#define WIFI_SSID ""
#define WIFI_PASSWORD ""
