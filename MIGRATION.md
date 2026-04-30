# WonderPy3 Migration Notes

## Scope

This document summarizes the migration from upstream `playi/WonderPy` (Python 2-era assumptions) to `chopley/WonderPy3` (Python 3 + modern macOS/Apple Silicon).

## Why a Migration Was Needed

- Upstream code paths included Python 2-era patterns and dependencies.
- `libWWHAL.dylib` available in-repo is x86_64 only, which is incompatible with native arm64 Python.
- The legacy Adafruit BLE path was unstable on this Apple Silicon setup (including scan-time crashes under Rosetta in some runs).

## High-Level Outcomes

- Core code paths and tests now run on Python 3.
- A Bleak-based BLE backend was introduced and is the recommended path on modern macOS.
- Manufacturer data parsing was updated for newer advertisement layouts so Dash devices (including Stevie) classify correctly.
- HAL-lite Python fallback paths were added for practical command/sensor operation when HAL dylib is unavailable.
- Motion behavior was tuned with repeatable calibration scripts.

## Migration Areas and Changes

### 1) Python 2 -> Python 3 modernization

- Removed Python 2-style constructs and updated equivalent Python 3 patterns.
- Updated test usage to modern `unittest.mock` patterns.
- Documentation and packaging metadata now target Python 3.9+.
- Internal synchronization in robot sensor waiting/notification paths was improved.

### 2) Apple Silicon and HAL compatibility

- Existing HAL binary in this repo is x86_64 only.
- On native arm64 Python, HAL loading fails; on translated x86 workflows, BLE stability remained inconsistent.
- Result: added runtime fallback behavior that does not require HAL for common control paths.

### 3) New Bleak backend

- Added `WonderPy/core/wwBleakMgr.py`.
- Added backend selection in `WonderPy/core/wwMain.py` via:

```bash
WONDERPY_BLE_BACKEND=bleak
```

Capabilities implemented:

- scan/discover with name/type filtering
- connect to selected robot
- subscribe to sensor notifications
- write command characteristic packets

### 4) HAL-lite Python fallback codec coverage

When HAL is unavailable, common command and sensor flows are translated in Python for practical operation:

- drive/body command encoding for common movement patterns
- basic sensor channel decode coverage used by current tools
- thread-safe dispatch from non-async code paths into BLE event-loop operations

This is intentionally not full HAL parity yet.

### 5) Robot type parsing updates

`WWRobot.robot_type_from_manufacturer_data()` was updated to accept newer manufacturer-data layouts in addition to legacy layout assumptions.

This fixed real-device classification issues on Stevie (Dash), allowing normal Dash command/sensor paths.

### 6) Motion tuning and calibration tooling

Calibration/probe scripts were added to make behavior repeatable:

- `connect_dash_bleak_smoketest.py`
- `connect_dash_smoketest.py`
- `tests_rawMotionProbe.py`
- `tests_reverseProbe.py`
- `tests_translationCalibration.py`
- `tests_spinCalibration.py`
- `tests_stevieTests.py`

Current tuned defaults used in Stevie-oriented choreography/testing:

- translation return trim: `0.6`
- heading trim: `0.97`

## Notable Device Finding (Stevie)

For the direct drive opcode path, reverse motion behavior aligned with 11-bit two's-complement encoding expectations on Stevie firmware.

This materially improved backward movement consistency during migration testing.

## Current Recommended Runtime

For current development on this machine:

- Python 3 virtualenv
- Bleak backend enabled

```bash
WONDERPY_BLE_BACKEND=bleak python your_script.py
```

## Remaining Migration Work

1. Complete full HAL parity in Python codec paths (`json2Packets`/`packets2Json` equivalent coverage).
2. Expand movement regression tests for repeatability across firmware/robot variants.
3. Decide long-term direction:
   - ship/obtain arm64 HAL binary, or
   - fully retire HAL dependency once Python codec parity is sufficient.
