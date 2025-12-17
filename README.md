# PID Heat Compensation Controller

## Instructions
* Copy the contents of other/packages.yaml to packages/pid_heat_compensation.yaml to setup the setting entities, then restart HA.
* Install the integration, select the indor and outdoor sensors. The P-I-D sensors should be auto-selected if the packages/pid_heat_compensation.yaml was added.
* Adjust the P-I-D sensors. P=-1, I=0, D=0. The can be adjusted from the developer tools.
* Set the weather_factor setting to 1 to begin with.


