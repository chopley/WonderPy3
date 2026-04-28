# Stevie Migration Findings (Python 3 + Apple Silicon)

## Goal

Get WonderPy controlling Dash robot `Stevie` on modern Python 3/macOS, despite legacy Python 2.7 assumptions and x86-only HAL dependency.

## Key Outcomes

- Python 3 migration baseline was completed for core code paths and tests.
- Legacy Adafruit BLE path remained unstable on this Apple Silicon setup (segfaults during scan under Rosetta).
- New `bleak` backend was added and proved stable for:
  - scan
  - connect
  - notification callbacks
  - command writes
- `Stevie` was verified as the correct Wonder robot (AF23 service UUID).
- Robot type parsing was fixed for newer manufacturer-data layout, so `Stevie` now classifies as `WW_ROBOT_DASH`.
- Motion behavior in fallback mode is functional via drive-style packets; pure HAL parity is still in-progress.
- Reverse motion on `Stevie` specifically required **11-bit two's complement** encoding (not sign-magnitude).
- A practical calibrated motion profile was established for `Stevie` using raw drive packets.

## Root Causes Identified

1. **Architecture mismatch**
   - `libWWHAL.dylib` in repo is x86_64 only.
   - Native arm64 Python cannot load it.

2. **Legacy BLE stack instability**
   - Adafruit CoreBluetooth path under Rosetta intermittently segfaulted during scan/connect.

3. **HAL dependency for packet translation**
   - Original code requires `json2Packets` / `packets2Json` from HAL dylib.
   - Without HAL, command/sensor translation must be handled in Python.

## What Was Implemented

### 1) Python 3 modernization (core migration)

- Removed Python 2 constructs (`raw_input`, `xrange`, old dict indexing patterns).
- Updated tests to use `unittest.mock`.
- Updated packaging/docs toward Python 3.9+.
- Improved internal sensor wait coordination in `WWRobot` with condition-based signaling.

### 2) New Bleak backend

Added:

- `WonderPy/core/wwBleakMgr.py`
- backend switch in `WonderPy/core/wwMain.py` via:

`WONDERPY_BLE_BACKEND=bleak`

Capabilities:

- scan/discover with name/type filters
- connect to selected robot
- subscribe to sensor characteristics
- send command characteristic writes

### 3) HAL-lite Python fallback

When HAL dylib is unavailable:

- sensor decode fallback for common channels
- command encode fallback for common control paths
- thread-safe dispatch from non-async threads into BLE loop

### 4) Manufacturer-data parsing fix

`WWRobot.robot_type_from_manufacturer_data()` now handles both legacy and newer advertisement layouts.

Observed payload from Stevie:

`011103000f7b0d0000000000000023000000000000000000`

Now resolves correctly to `WW_ROBOT_DASH`.

### 5) Debug/probe tools

Added test/probe scripts to accelerate verification:

- `connect_dash_bleak_smoketest.py`
- `tests_rawMotionProbe.py` (raw packet A/B probe)
- `tests_reverseProbe.py` (focused reverse encoding probe)
- `tests_stevieTests.py` (timed step sequence)

## Additional Stevie-specific Findings

### Reverse encoding

From probe runs on `Stevie`, the working reverse packet was:

- `PROBE: reverse B (drive two's-comp -600)`
- raw packet: `02a80005`

This indicates `Stevie` firmware expects signed drive fields in **11-bit two's complement** format for opcode `0x02`.

### Motion calibration profile (current)

`tests_stevieTests.py` was tuned to a safer, observable profile:

- translational legs:
  - forward: `linear=320` for `0.5s`
  - backward: `linear=-320` for `1.0s`
  - forward: `linear=320` for `0.5s`
- spin legs:
  - left (180): `angular=420` for `1.2s`
  - right (180): `angular=-420` for `1.2s * heading_trim`
- sequence includes explicit stop command and a `1.0s` pause between each step.
- current tuned defaults:
  - translation `backward-trim = 0.6`
  - heading `right/heading-trim = 0.97`

This profile produced reliable forward/back and improved turn completion compared with earlier conservative settings.

## Calibration Process (Stevie)

The calibration was done in two independent loops, then merged into the choreography script.

### 1) Translation calibration (forward/back only)

Script: `tests_translationCalibration.py`

Run:

```bash
PYTHONPATH="$(pwd)" python3 tests_translationCalibration.py --connect-name Stevie --scan-timeout 8 --linear-cmd 320 --forward-seconds 0.6 --cycles 3
```

Tune using `--backward-trim`:

- if robot ends **forward** of start: increase `backward-trim`
- if robot ends **behind** start: decrease `backward-trim`

Final tuned value:

- `backward-trim = 0.6`

### 2) Spin calibration (left/right only, 180-degree target)

Script: `tests_spinCalibration.py`

Run:

```bash
PYTHONPATH="$(pwd)" python3 tests_spinCalibration.py --connect-name Stevie --scan-timeout 8 --angular-cmd 420 --left-seconds 1.2 --cycles 3
```

Tune using `--right-trim`:

- if final heading is **left** of start: increase `right-trim`
- if final heading is **right** of start: decrease `right-trim`

Final tuned value:

- `right-trim = 0.97`

### 3) Integrate into full choreography

Script: `tests_stevieTests.py`

Use tuned defaults (already set in script):

- `return-trim` based on translation calibration
- `heading-trim` based on spin calibration

Validation criterion:

- robot returns to near starting position and initial heading after complete 8-step sequence.

## Verified Working Commands/Flows

### Scan-only (bleak)

```bash
PYTHONUNBUFFERED=1 PYTHONPATH="$(pwd)" WONDERPY_BLE_BACKEND=bleak python3 connect_dash_bleak_smoketest.py --scan-only --scan-timeout 8
```

### Connect to Stevie

```bash
PYTHONPATH="$(pwd)" WONDERPY_BLE_BACKEND=bleak python3 connect_dash_bleak_smoketest.py --connect-name Stevie --connect-ask --scan-timeout 8
```

### Raw motion probe (known-good packet validation)

```bash
PYTHONPATH="$(pwd)" python3 tests_rawMotionProbe.py --connect-name Stevie --scan-timeout 8
```

## Behavioral Notes

- Connection is reliable through `bleak`.
- Motion command behavior required iterative packet tuning.
- Raw probe indicated usable motion packets; higher-level fallback now aligns toward those packet forms.
- Remaining differences vs full HAL behavior are expected until complete parity codec is implemented.

## Remaining Work

1. **Complete HAL replacement in Python**
   - full `json2Packets` parity
   - full `packets2Json` parity
   - broader command/sensor coverage

2. **Stabilize movement semantics**
   - finalize sign/axis handling for all motion combinations
   - add repeatable motion regression tests

3. **Optional**
   - provide arm64-compatible HAL binary (if source available), or retire HAL path entirely once codec parity is complete.

## Practical Recommendation

For current development on this machine, prefer:

- Python 3
- `WONDERPY_BLE_BACKEND=bleak`

and use the provided probe/test scripts while finalizing fallback motion/sensor parity.
