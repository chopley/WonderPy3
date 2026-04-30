# Robot Validation Scripts

These scripts validate behavior on a real robot (Dash/Dot/Cue), including raw command behavior, BLE connectivity, and calibration loops.

They are intentionally separate from software-only tests under `test/`.

## Layout

- `smoke/` - quick connect/control sanity checks
- `probes/` - low-level packet/behavior probes
- `calibration/` - translation/heading calibration loops
- `scenarios/` - composed movement sequences

## Usage Notes

- Requires a powered robot and Bluetooth access.
- Prefer Bleak backend on modern macOS:

```bash
WONDERPY_BLE_BACKEND=bleak
```

- Run from repo root (or set `PYTHONPATH` accordingly).
- These scripts are hardware-dependent and not intended for CI.
