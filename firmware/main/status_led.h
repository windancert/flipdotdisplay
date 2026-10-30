// Shows the firmware's state on the onboard addressable RGB LED.
#pragma once

typedef enum {
    STATUS_BOOTING,     // solid blue: blacking out the display
    STATUS_CONNECTING,  // blinking yellow: looking for WiFi
    STATUS_ONLINE,      // solid green: has an IP address, listening for frames
    STATUS_NO_NETWORK,  // solid purple: no SSID configured
} status_t;

void status_led_start(void);
void status_led_set(status_t status);

// Briefly shows white, then returns to the current status.
void status_led_flash(void);
