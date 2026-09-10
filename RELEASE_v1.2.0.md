## PID Heat Compensation `v1.2.0`

This release focuses on stability, compatibility, and clearer documentation.

### Added and improved
- Improved robustness for PID helper entities (`Kp`, `Ki`, `Kd`, `Weather Factor`) with better entity ID handling.
- More resilient sensor startup during restart/reload (better race-condition handling when the climate entity is not registered yet).
- Thread-safe scheduling updates for Home Assistant `2026.3.x` to avoid async/thread warnings.
- Reduced startup log noise while temperature sensors are still loading.

### Fixed
- PID settings now persist correctly across restarts instead of resetting to defaults.
- Fixed a regression where the compensated sensor could appear as “no longer provided” in existing installations.
- Updated README to better match actual PID behavior and tuning logic.

### Compatibility
- Backward compatible with existing installations.
- No manual migration required.
