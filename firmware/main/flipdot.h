// Display driver: keeps the panels in step with the latest frame, flipping only
// the dots that differ.
#pragma once

#include <stdint.h>

#include "flipdot_map.h"

// Blacks out the whole display (blocking, about 1.2 s) and starts the driver task.
void flipdot_start(void);

// Queues a FRAME_BYTES frame. A newer frame replaces one that is still waiting.
void flipdot_show(const uint8_t *frame);

// Stops flipping dots, returning once no pulse is in progress. Needed around flash
// writes, which can delay the interrupt that reports the end of a pulse.
void flipdot_pause(void);
void flipdot_resume(void);
