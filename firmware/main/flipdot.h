// Display driver: keeps the panels in step with the latest frame, flipping only
// the dots that differ.
#pragma once

#include <stdint.h>

#include "flipdot_map.h"

// Blacks out the whole display (blocking, about 1.2 s) and starts the driver task.
void flipdot_start(void);

// Queues a FRAME_BYTES frame. A newer frame replaces one that is still waiting.
void flipdot_show(const uint8_t *frame);
