if(NOT EXISTS "${CMAKE_CURRENT_LIST_DIR}/../local_config.h")
    message(FATAL_ERROR "Copy firmware/local_config.example.h to firmware/local_config.h and fill it in")
endif()

set(srcs "main.c" "flipdot.c" "flipdot_map.c" "net.c" "status_led.c" "ota.c")
if(CONFIG_FLIPDOT_DIRECT_DRIVE)
    # Bench variant: drive one panel straight from the GPIOs, no shift registers.
    list(APPEND srcs "panel_hw_direct.c")
else()
    list(APPEND srcs "panel_hw.c")
endif()

idf_component_register(
    SRCS ${srcs}
    INCLUDE_DIRS "." ".."
    REQUIRES app_update esp_app_format esp_http_server esp_driver_gpio esp_driver_rmt esp_driver_spi esp_event esp_netif
             esp_timer esp_wifi lwip nvs_flash
)
