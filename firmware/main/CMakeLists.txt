if(NOT EXISTS "${CMAKE_CURRENT_LIST_DIR}/../local_config.h")
    message(FATAL_ERROR "Copy firmware/local_config.example.h to firmware/local_config.h and fill it in")
endif()

idf_component_register(
    SRCS "main.c" "flipdot.c" "flipdot_map.c" "panel_hw.c" "net.c" "status_led.c" "ota.c"
    INCLUDE_DIRS "." ".."
    REQUIRES app_update esp_app_format esp_http_server esp_driver_gpio esp_driver_rmt esp_driver_spi esp_event esp_netif
             esp_timer esp_wifi lwip nvs_flash
)
