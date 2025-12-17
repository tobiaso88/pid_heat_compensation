# PID Heat Compensation Controller
Smart Heating Control for Home Assistant

This Home Assistant Custom Integration optimizes heat pump performance by calculating a **Compensated Outdoor Temperature** ($T_{comp}$). 

Instead of relying solely on the heat pump's static heating curve, this integration uses a **PID (Proportional-Integral-Derivative) Controller** to dynamically adjust the control signal based on the actual real-time indoor temperature.



## How It Works

Most heat pumps are governed by an outdoor sensor and a pre-defined heating curve. By providing the heat pump with a modified outdoor temperature value ($T_{comp}$), we can "nudge" the system to increase or decrease production more intelligently than a standard binary thermostat.

* **If Indoor < Setpoint:** $T_{comp}$ is lowered (The heat pump believes it is colder outside than it actually is and increases heat production).
* **If Indoor > Setpoint:** $T_{comp}$ is raised (The heat pump believes it is warmer outside and decreases production).

## Installation

1.  Copy the `smart_heating` folder to your Home Assistant `/config/custom_components/` directory.
2.  Ensure your entity IDs in `sensor.py` match your actual Home Assistant sensors:
    * `sensor.indoor_temperature`
    * `sensor.outdoor_temperature`
    * `input_number.heating_setpoint`
3.  Restart Home Assistant.
4.  Add the sensor via your `configuration.yaml` or through the Integrations UI.

## Configuration (PID Tuning)

In `sensor.py`, you will find three primary parameters that dictate how the system reacts. Adjust these to suit your home's specific thermal mass:

| Parameter | Name | Description | Default |
| :--- | :--- | :--- | :--- |
| **Kp** | Proportional | Reacts to the current error. Higher value = faster, more aggressive reaction. | `2.0` |
| **Ki** | Integral | Eliminates residual error over time. Prevents the temperature from "stalling" just below the target. | `0.1` |
| **Kd** | Derivative | Dampens the reaction if the temperature changes too quickly, preventing "overshoot." | `0.5` |

## Automation Example

To send the calculated value to your heat pump, create an automation that triggers whenever the sensor state changes:

```yaml
alias: "Update Heatpump T-Comp"
description: "Sends the calculated optimal temperature to the heat pump"
trigger:
  - platform: state
    entity_id: sensor.optimal_heating_temperature
action:
  - service: climate.set_temperature # Or the specific service for your heat pump
    target:
      entity_id: climate.my_heatpump
    data:
      temperature: "{{ states('sensor.optimal_heating_temperature') | float }}"
