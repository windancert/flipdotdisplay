// Fixed geometry for the host test, independent of anyone's real local_config.h.
#pragma once

#define PANEL_COLS 28
#define PANEL_ROWS 16
#define DISPLAY_PANELS_X 4
#define DISPLAY_PANELS_Y 2
#define DISPLAY_LAYOUT                                \
    {                                                 \
        {{0, true}, {1, true}, {2, true}, {3, true}}, \
        {{4, false}, {5, false}, {6, false}, {7, false}}, \
    }
