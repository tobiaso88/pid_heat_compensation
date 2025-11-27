import logging

_LOGGER = logging.getLogger(__name__)

# Core constants
DOMAIN = "pid_heat_compensation"
PLATFORMS = ["climate", "sensor"]
HA_DATA_KEY = "pid_compensation_data"
ATTR_COMPENSATED_TEMP = "compensated_outdoor_temperature" # <-- NY KONSTANT

# Configuration keys for the PID controller
CONF_INDOOR_SENSOR = "indoor_temp_entity"
CONF_OUTDOOR_SENSOR = "outdoor_temp_entity"
CONF_KP_ENTITY = "kp_entity"
CONF_KI_ENTITY = "ki_entity"
CONF_KD_ENTITY = "kd_entity"

# Default values
DEFAULT_NAME = "PID Heat Compensation"
MAX_TEMP_DIFFERENCE = 10.0
