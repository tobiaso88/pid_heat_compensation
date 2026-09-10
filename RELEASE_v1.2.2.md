# PID Heat Compensation v1.2.2

This release fixes stale control values during sensor failures, limits the final temperature correction, and adds explicit climate on/off support.

## Fixed

- Missing or invalid indoor readings now suspend PID and publish the actual outdoor temperature, allowing the heat pump to use its normal heating curve.
- Missing or invalid outdoor readings now clear the compensated value and mark the output sensor unavailable instead of retaining an old value. The sensor recovers when valid readings return.
- OFF immediately disables compensation, including when the indoor sensor is unavailable. It does not switch off the heat pump.
- PID pauses during OFF, sensor failures, and a zero weather factor. Resuming resets the integral and timer so downtime does not cause an integral jump.
- The final correction is limited to ±10 °C after applying the weather factor. Integral limits account for the multiplier and the existing freezing cap.
- Non-finite sensor readings, tuning values, and target temperatures are rejected. Invalid restored tuning values retain their defaults.
- Climate state restoration calls the parent lifecycle hook and tolerates invalid saved targets. Partial options are merged with the original configuration.
- PID parameter callbacks run on the Home Assistant event loop.

## Compatibility

- Added `TURN_ON` and `TURN_OFF` feature flags and explicit handlers for `climate.turn_on` and `climate.turn_off`.
- Reviewed relevant Home Assistant Core 2026.9.1 APIs and release notes. No live Home Assistant 2026.9.1 runtime validation has been performed.

## Upgrade notes

- Weather Factor now accepts 0–2. Previously saved negative or invalid values fall back to 1; review your tuning if you used a negative factor. Zero disables compensation.
- With factors above 1, the final correction can be smaller than before because the ±10 °C limit now applies after multiplication.
- The README automation now reacts to sensor changes, retries every 15 minutes, and skips unavailable values. Existing automations must be updated manually to adopt this behavior.
- Skipping an unavailable output cannot clear a value already stored in an external device. Configure that device's watchdog or physical-sensor fallback separately if supported.
- Missing, unknown, unavailable, and non-finite readings are handled. A sensor that continues reporting a plausible but frozen value is not detected.

## Validation

- All 16 tests pass, including 13 behavior tests using the pinned `simple-pid==2.0.1` library and a minimal Home Assistant API double.
- Behavior coverage includes sensor failure and recovery, OFF/ON, restart restoration, long downtime, scaled correction limits, and invalid values.
- Test setup and updated operating behavior are documented in the README.
