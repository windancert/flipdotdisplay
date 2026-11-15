# Copy to mqtt_config.py and fill in. mqtt_config.py is gitignored, so the login
# stays out of the repository.

MQTT_HOST = "192.168.42.223"
MQTT_PORT = 1883
MQTT_USER = ""
MQTT_PASSWORD = ""

# Messages already filtered for the fire station, as JSON with "message" and
# "capcodes". The broker retains the last one, so it arrives right after connecting.
MQTT_TOPIC = "p2000/kazerne"
