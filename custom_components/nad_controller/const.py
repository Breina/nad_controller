"""Constants for the NAD multi-room audio controller integration."""
from datetime import timedelta

DOMAIN = "nad_controller"
MANUFACTURER = "NAD"

CONF_SERIAL_NUMBER = "serial_number"
CONF_MODEL = "model"

SCAN_INTERVAL = timedelta(seconds=10)
REFRESH_COOLDOWN = 0.5
