from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class RegressionGuards(unittest.TestCase):
    def test_number_entities_restore_state_on_restart(self):
        number_py = (ROOT / "custom_components/pid_heat_compensation/number.py").read_text()
        self.assertIn("class PIDParameterNumber(NumberEntity, RestoreEntity)", number_py)
        self.assertIn("async def async_added_to_hass", number_py)
        self.assertIn("await self.async_get_last_state()", number_py)

    def test_sync_callback_uses_thread_safe_scheduler(self):
        climate_py = (ROOT / "custom_components/pid_heat_compensation/climate.py").read_text()
        self.assertIn("self.hass.add_job(self._async_update_loop(event))", climate_py)

    def test_compensated_temp_uses_pid_output_sign(self):
        climate_py = (ROOT / "custom_components/pid_heat_compensation/climate.py").read_text()
        self.assertIn("T_comp = T_real_outdoor + (delta_T * self._weather_factor)", climate_py)


if __name__ == "__main__":
    unittest.main()
