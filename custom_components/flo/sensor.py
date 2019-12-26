"""
Support for Flo water inflow monitoring and control devices

FUTURE:
- convert to async
- use track_point_in_utc_time() to trigger and update every 16 minutes
     (one minute after Flo's every 15 minute average rollup)
"""
import logging
import json
import voluptuous as vol

from homeassistant.const import TEMP_FAHRENHEIT, ATTR_TEMPERATURE
from homeassistant.components.sensor import PLATFORM_SCHEMA
import homeassistant.helpers.config_validation as cv

from pyflowater.const import FLO_V2_API_PREFIX, FLO_MODES, FLO_AWAY, FLO_HOME, FLO_SLEEP
from . import FloEntity, FLO_SERVICE, CONF_LOCATION_ID

LOG = logging.getLogger(__name__)

ATTR_TIME       = 'time'
ATTR_TOTAL_FLOW = 'total_flow'

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_LOCATION_ID): cv.string
})

# pylint: disable=unused-argument
# NOTE: there is a platform loaded for each LOCATION (not device, which there may be multiple devices)
def setup_platform(hass, config, add_sensors_callback, discovery_info=None):
    """Setup the Flo water inflow control sensor"""

    flo = hass[FLO_SERVICE]
    if not flo or not flo.service.is_connected():
        LOG.warning("No connection to Flo service, ignoring setup of platform sensor")
        return False

    location_id = config[CONF_LOCATION_ID]
    location = flo.location(location_id)
    if not location:
        LOG.warning(f"Flo location {location_id} not found, ignoring creation of Flo sensors")
        return False

    # iterate all devices and create a valve switch for each device
    sensors = []
    device_num = 0
    for device in location['devices']:
        device_id = device['id']
        device_num = device_num + 1
        
        sensors.append( FloRateSensor(hass, device_id) )
        sensors.append( FloTempSensor(hass, device_id) )
        sensors.append( FloPressureSensor(hass, device_id) )
        sensors.append( FloMonitoringMode(hass, device_id) )

    for sensor in sensors:
        sensor.update()

    add_sensors_callback(sensors)

# pylint: disable=too-many-instance-attributes
class FloRateSensor(FloEntity):
    """Water flow rate sensor for a Flo device"""

    def __init__(self, hass, device_id):
        super().__init__(hass)
        self._device_id = device_id
        self._name = 'Flo Water Flow Rate'
        self._state = 0.0

    @property
    def unit_of_measurement(self):
        """Gallons per minute (gpm)"""
        return 'gpm'

    @property
    def state(self):
        """Water flow rate"""
        return self._state

    @property
    def icon(self):
        return 'mdi:water-pump'

    def update(self):
        """Update sensor state"""
        json_response = self._flo_service.get_waterflow_measurement(self._device_id)

        # FIXME: add sanity checks on response

        self._state = float(json_response['average_flowrate'])
        self._attrs.update({
            ATTR_TOTAL_FLOW  : round(float(json_response['total_flow']),1),
            ATTR_TIME        : json_response['time']
        })
        LOG.info("Updated %s to %f %s : %s", self._name, self._state, self.unit_of_measurement, json_response)

class FloTempSensor(FloEntity):
    """Water temp sensor for a Flo device"""

    def __init__(self, hass, device_id):
        super().__init__(hass)
        self._device_id = device_id
        self._name = 'Flo Water Temperature'
        self._state = 0.0

    @property
    def unit_of_measurement(self):
        return TEMP_FAHRENHEIT # FIXME: use correct unit based on Flo device's config

    @property
    def state(self):
        """Water temperature"""
        return self._state

    @property
    def icon(self):
        return 'mdi:thermometer'

    def update(self):
        """Update sensor state"""
        # FIXME: cache results so that for each sensor don't update multiple times
        json_response = self._flo_service.get_waterflow_measurement(self._device_id)

        # FIXME: add sanity checks on response

        # FUTURE: round just to nearest degree?
        self._state = round(float(json_response['average_temperature']), 1)
        self._attrs.update({
            ATTR_TIME        : json_response['time']
        })
        LOG.info("Updated %s to %f %s : %s", self._name, self._state, self.unit_of_measurement, json_response)


class FloPressureSensor(FloEntity):
    """Water pressure sensor for a Flo device"""

    def __init__(self, hass, device_id):
        super().__init__(hass)
        self._device_id = device_id
        self._name = 'Flo Water Pressure'
        self._state = 0.0

    @property
    def unit_of_measurement(self):
        """Pounds per square inch (psi)"""
        return 'psi'

    @property
    def state(self):
        """Water pressure"""
        return self._state

    @property
    def icon(self):
        return 'mdi:gauge'

    def update(self):
        """Update sensor state"""
        # FIXME: cache results so that for each sensor don't update multiple times
        json_response = self._flo_service.get_waterflow_measurement(self._device_id)

        # FIXME: add sanity checks on response

        self._state = round(float(json_response['average_pressure']), 1)
        self._attrs.update({
            ATTR_TIME        : json_response['time']
        })
        LOG.info(f"Updated %s to %f %s : %s", self._name, self._state, self.unit_of_measurement, json_response)

# https://support.meetflo.com/hc/en-us/articles/115003927993-What-s-the-difference-between-Home-Away-and-Sleep-modes-
class FloMonitoringMode(FloEntity):
    """Sensor returning current monitoring mode for the Flo device"""

    def __init__(self, hass, device_id):
        super().__init__(hass)
        self._device_id = device_id
        self._name = 'Flo Monitoring Mode'
        self._mode = None

    @property
    def unit_of_measurement(self):
        """Monitoring mode"""
        return 'mode'

    @property
    def state(self):
        """Flo monitoring mode: home, away, sleep"""
        return self._mode

    @property
    def icon(self):
        return 'mdi:shield-search'

    def update(self):
        """Update sensor state"""
    
        # FIXME: cache results so that for each sensor don't update multiple times
        json_response = self._flo_service.get_request('/icdalarmnotificationdeliveryrules/scan')
        LOG.info("Flo alarm notification: " + json_response)

    def set_preset_mode(self, mode):
        if not mode in FLO_MODES:
            LOG.error("fInvalid preset mode {mode} (must be {FLO_MODES})")
            return

        self._mode = mode
        # FIXME: call service to update