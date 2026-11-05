// Low-level panel access: the 74HCT595 chain and the hardware-timed strobe.
#pragma once

#include <stdint.h>

#include "flipdot_map.h"

// 24 V across a 16 ohm coil is 36 W, so a held strobe destroys a dot in seconds.
#define PANEL_PULSE_MAX_US 400

// Sets all outputs safe. Must run before anything else touches the panel.
void panel_hw_init(void);

// Latches the frame, energises the selected coil for width_us (clamped to
// PANEL_PULSE_MAX_US) and returns the outputs to idle. Blocks for the duration.
void panel_hw_pulse(shift_frame_t frame, uint32_t width_us);
