"""Behavior tests with real simple-pid and a minimal Home Assistant API double."""
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'custom_components/pid_heat_compensation'


class Entity:
    async def async_added_to_hass(self):
        pass

    def async_write_ha_state(self):
        self.writes = getattr(self, 'writes', 0) + 1

    def async_on_remove(self, listener):
        pass


class Restore:
    async def async_get_last_state(self):
        return getattr(self, 'last_state', None)


def load_modules():
    modules = {}
    def module(name, **attrs):
        value = ModuleType(name)
        value.__dict__.update(attrs)
        modules[name] = value
        return value
    module('homeassistant')
    module('homeassistant.core', HomeAssistant=object, State=object, callback=lambda f: f)
    module('homeassistant.components')
    module('homeassistant.components.climate', ClimateEntity=Entity,
           ClimateEntityFeature=SimpleNamespace(TARGET_TEMPERATURE=1),
           HVACMode=SimpleNamespace(HEAT='heat', OFF='off'))
    module('homeassistant.components.sensor', SensorEntity=Entity)
    module('homeassistant.components.number', NumberEntity=Entity,
           NumberMode=SimpleNamespace(BOX='box'))
    module('homeassistant.const', ATTR_TEMPERATURE='temperature',
           STATE_UNAVAILABLE='unavailable', STATE_UNKNOWN='unknown',
           UnitOfTemperature=SimpleNamespace(CELSIUS='°C'))
    module('homeassistant.config_entries', ConfigEntry=object)
    module('homeassistant.helpers')
    module('homeassistant.helpers.entity', EntityCategory=SimpleNamespace(CONFIG='config'))
    module('homeassistant.helpers.restore_state', RestoreEntity=Restore)
    module('homeassistant.helpers.entity_registry', async_get=lambda hass: hass.registry)
    events = module('homeassistant.helpers.event', async_track_state_change_event=Mock(),
                    async_call_later=Mock())
    package = module('pid_test_package')
    package.__path__ = [str(PACKAGE)]
    with patch.dict(sys.modules, modules):
        loaded = []
        for name in ('const', 'climate', 'number', 'sensor'):
            spec = importlib.util.spec_from_file_location(f'pid_test_package.{name}', PACKAGE / f'{name}.py')
            value = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = value
            spec.loader.exec_module(value)
            loaded.append(value)
    return (*loaded[1:], events)


climate, number, sensor, events = load_modules()


def state(value, **attrs):
    return SimpleNamespace(state=str(value), attributes=attrs)


class ControllerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.values = {
            'sensor.indoor': state(19), 'sensor.outdoor': state(-5),
            'number.test_weather_factor': state(1),
        }
        self.entry = SimpleNamespace(entry_id='test', title='Test', options={}, data={
            'name': 'Test', 'indoor_temp_entity': 'sensor.indoor',
            'outdoor_temp_entity': 'sensor.outdoor',
        })
        self.hass = SimpleNamespace(states=SimpleNamespace(get=self.values.get),
            registry=SimpleNamespace(async_get_entity_id=lambda *args: None))
        self.controller = climate.PIDClimateController(self.hass, self.entry)
        self.now = 0
        self.controller.pid.time_fn = lambda: self.now
        self.controller.pid.reset()
        self.controller.pid.setpoint = 20
        self.controller.pid.tunings = (-2, 0, 0)

    async def update(self, seconds=60):
        self.now += seconds
        # _get_float_state imports these constants locally.
        constants = SimpleNamespace(STATE_UNAVAILABLE='unavailable', STATE_UNKNOWN='unknown')
        with patch.dict(sys.modules, {'homeassistant.const': constants}):
            await self.controller._async_update_loop(None)

    async def mode(self, mode):
        constants = SimpleNamespace(STATE_UNAVAILABLE='unavailable', STATE_UNKNOWN='unknown')
        with patch.dict(sys.modules, {'homeassistant.const': constants}):
            await self.controller.async_set_hvac_mode(mode)

    async def test_cold_room_increases_heat(self):
        await self.update()
        self.assertEqual(self.controller._compensated_temp_value, -7)

    async def test_indoor_failure_uses_actual_outdoor_and_recovers(self):
        await self.update()
        self.values['sensor.indoor'] = state('unavailable')
        await self.update()
        self.assertEqual(self.controller._compensated_temp_value, -5)
        self.assertFalse(self.controller.pid.auto_mode)
        self.values['sensor.indoor'] = state(19)
        await self.update()
        self.assertEqual(self.controller._compensated_temp_value, -7)
        self.assertTrue(self.controller.pid.auto_mode)

    async def test_invalid_outdoor_clears_previous_output(self):
        for invalid in ('unavailable', 'unknown', 'nan', 'inf', '-inf', 'bad'):
            self.values['sensor.outdoor'] = state(-5)
            await self.update()
            self.values['sensor.outdoor'] = state(invalid)
            await self.update()
            self.assertIsNone(self.controller.extra_state_attributes['compensated_outdoor_temperature'])

    async def test_off_immediately_passes_outdoor_without_indoor(self):
        await self.update()
        await self.mode('off')
        self.assertEqual(self.controller._compensated_temp_value, -5)
        self.assertFalse(self.controller.pid.auto_mode)
        self.values['sensor.indoor'] = state('unavailable')
        self.values['sensor.outdoor'] = state(-8)
        await self.update()
        self.assertEqual(self.controller._compensated_temp_value, -8)

    async def test_long_off_does_not_integrate_downtime(self):
        self.controller.pid.tunings = (-2, -0.01, 0)
        await self.update()
        await self.mode('off')
        self.now += 86400
        await self.mode('heat')
        self.assertAlmostEqual(self.controller.pid.components[1], 0, places=6)
        self.assertEqual(self.controller._compensated_temp_value, -7)

    async def test_long_sensor_outage_does_not_integrate_downtime(self):
        self.controller.pid.tunings = (-2, -0.01, 0)
        await self.update()
        self.values['sensor.outdoor'] = state('unavailable')
        await self.update()
        self.values['sensor.outdoor'] = state(-5)
        await self.update(seconds=86400)
        self.assertAlmostEqual(self.controller.pid.components[1], 0, places=6)

    async def test_factor_scaled_limits_and_integral_anti_windup(self):
        self.values['number.test_weather_factor'] = state(2)
        self.controller.pid.tunings = (-10, -1, 0)
        await self.update(seconds=3600)
        self.assertEqual(self.controller._compensated_temp_value, -15)
        self.assertEqual(self.controller.pid.components[1], -5)
        self.values['sensor.indoor'] = state(30)
        await self.update(seconds=3600)
        self.assertEqual(self.controller._compensated_temp_value, 0)
        self.assertEqual(self.controller.pid.components[1], 2.5)
        self.values['sensor.outdoor'] = state(5)
        await self.update(seconds=3600)
        self.assertEqual(self.controller._compensated_temp_value, 15)

    async def test_zero_factor_disables_pid_and_negative_factor_does_not_reverse(self):
        self.values['number.test_weather_factor'] = state(0)
        await self.update()
        self.assertEqual(self.controller._compensated_temp_value, -5)
        self.assertFalse(self.controller.pid.auto_mode)
        self.values['number.test_weather_factor'] = state(-2)
        await self.update()
        self.assertEqual(self.controller._compensated_temp_value, -7)

    async def test_number_restore_validates_saved_value(self):
        for saved, expected in [('1.5', 1.5), ('-1', 1), ('nan', 1), ('inf', 1), ('3', 1)]:
            entity = number.PIDParameterNumber(self.entry, 'Weather Factor', 1, 0, 2)
            entity.last_state = state(saved)
            await entity.async_added_to_hass()
            self.assertEqual(entity._attr_native_value, expected)
        with self.assertRaises(ValueError):
            await entity.async_set_native_value(-1)

    async def test_restart_restores_target_and_off_mode(self):
        self.controller.last_state = state('off', temperature=22)
        constants = SimpleNamespace(STATE_UNAVAILABLE='unavailable', STATE_UNKNOWN='unknown')
        with patch.dict(sys.modules, {'homeassistant.const': constants}):
            await self.controller.async_added_to_hass()
        self.assertEqual(self.controller.pid.setpoint, 22)
        self.assertEqual(self.controller._attr_hvac_mode, 'off')
        self.assertEqual(self.controller._compensated_temp_value, -5)
        self.assertFalse(self.controller.pid.auto_mode)

    async def test_restart_with_invalid_target_uses_default(self):
        self.controller.last_state = state('heat', temperature='nan')
        constants = SimpleNamespace(STATE_UNAVAILABLE='unavailable', STATE_UNKNOWN='unknown')
        with patch.dict(sys.modules, {'homeassistant.const': constants}):
            await self.controller.async_added_to_hass()
        self.assertEqual(self.controller.pid.setpoint, 20)

    async def test_sensor_invalidates_and_recovers(self):
        self.hass.registry.async_get_entity_id = lambda *args: 'climate.test'
        entity = sensor.PIDCompensatedTempSensor(self.hass, self.entry, 'test_pid_climate', 'Test')
        await entity.async_added_to_hass()
        listener = events.async_track_state_change_event.call_args.args[2]
        listener({'new_state': state('heat', compensated_outdoor_temperature=-7)})
        self.assertEqual(entity.native_value, -7)
        self.assertTrue(entity._attr_available)
        for invalid in (None, state('unavailable'), state('heat', compensated_outdoor_temperature='nan'),
                        state('heat', compensated_outdoor_temperature=None)):
            listener({'new_state': invalid})
            self.assertIsNone(entity.native_value)
            self.assertFalse(entity._attr_available)
        listener({'new_state': state('heat', compensated_outdoor_temperature=-5)})
        self.assertEqual(entity.native_value, -5)
        self.assertTrue(entity._attr_available)


if __name__ == '__main__':
    unittest.main()
