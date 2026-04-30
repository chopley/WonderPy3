# WonderPy3

**Canonical source code:** **[github.com/chopley/WonderPy3](https://github.com/chopley/WonderPy3)** (issues & pull requests belong there.)

WonderPy3 is a Python package that talks to Wonder Workshop robots **Dash**, **Dot**, and **Cue**: commands and sensors are exposed at a granular level. Examples and tutorials live in **[WonderPyExamples](https://github.com/playi/WonderPyExamples)** (upstream; still usable).

This codebase is an actively maintained **Python 3 port and continuation** of Wonder Workshop’s open-source **[WonderPy](https://github.com/playi/WonderPy)**, which was originally Python 2-era and has little recent upstream activity. The **MIT License** applies; see [`LICENSE`](LICENSE).

Comfort with Python and the terminal is assumed.


## Project status

Roughly **alpha** quality: good for experimentation; expect rough edges. Track work on the **[issue tracker](https://github.com/chopley/WonderPy3/issues)**.

**Command categories:** eyering, head, media, monoLED, body, RGB, accessory  

**Sensor categories:** accelerometer / gyroscope, beacon, buttons, distance, head angles, pose, speaker, wheels


## Setup

### Prerequisites

1. **macOS** (primary target today; broader OS support has been a longstanding goal upstream.)
2. **Python 3.9+** (3.11+ recommended.)
3. **pip**, **venv** (recommended), **[Xcode Command Line Tools](https://developer.apple.com/download/more)** (`xcode-select --install`).

### Dependencies

Install **pip / venv** the usual way for your machine ([pip install guidance](https://www.google.com/search?q=how+to+install+pip)).

This project needs Wonder Workshop’s Python 3–compatible **[Adafruit_Python_BluefruitLE fork](https://github.com/playi/Adafruit_Python_BluefruitLE)** plus the packages declared in **`requirements.txt`**.

From a local checkout:

```bash
pip install -r requirements.txt
```

Or install Adafruit BLE alone:

```bash
pip install git+https://github.com/playi/Adafruit_Python_BluefruitLE@928669a#egg=Adafruit_BluefruitLE
```

### Virtual environment

```bash
python3 -m venv venv
source venv/bin/activate
```

### Install this library from GitHub

Use the **`WonderPy3`** repository (maintained fork), not PyPI installs that may lag or omit your changes.
The distribution/import name remains `WonderPy` for compatibility:

```bash
pip install "WonderPy @ git+https://github.com/chopley/WonderPy3.git@master"
```

`setup.py` lists core dependencies (Bleak, PyObjC, etc.) but **not** Adafruit BLE; install that fork separately (above) **or** use a **`git clone`** plus `pip install -r requirements.txt` and then `pip install .` so everything resolves.

For local development against a clone:

```bash
pip install -r requirements.txt
pip install -e .
```

### Optional: Bleak backend

On newer macOS (including Apple Silicon), the legacy Adafruit stack can be unstable. Experimental **Bleak** support:

```bash
WONDERPY_BLE_BACKEND=bleak python your_script.py
```

Quick connectivity probe:

```bash
python connect_dash_bleak_smoketest.py --connect-name "Stevie" --connect-ask
```

## Web UI (Dash Kid Controller)

This repo includes a browser-based controller in `dash_kid_ui.py` with:

- connect / disconnect
- one-tap movement commands
- drawable path following with distance calibration and max-travel limits
- optional must-hit markers on the canvas
- encoder before/after logging per run

Start it from the repository root (inside your activated virtualenv):

```bash
python dash_kid_ui.py
```

Then open:

- `http://127.0.0.1:8765`

Optional host/port override:

```bash
python dash_kid_ui.py --host 0.0.0.0 --port 8765
```


## Documentation

- [Robot reference (`doc/WonderPy.md`)](doc/WonderPy.md) *(also on [GitHub](https://github.com/chopley/WonderPy3/blob/master/doc/WonderPy.md))*  
- **[WonderPyExamples](https://github.com/playi/WonderPyExamples)** — tutorials strongly recommended  

Download the hello-world snippet and run inside your activated venv:

```bash
curl -o 01_hello_world.py https://raw.githubusercontent.com/playi/WonderPyExamples/master/tutorial/01_hello_world.py
python 01_hello_world.py
```


## Robot connection

Scans typically run **about 5–20 seconds**, then selects the strongest RSSI match among filtered robots (“closest approx.”).

```
[--connect-type cue | dot | dash]
  Only connect to the listed robot type(s).

[--connect-name MY_ROBOT | MY_OTHER_ROBOT | ...]
  Only robots with these Bluetooth names.

[--connect-eager]
  Connect as soon as a match appears (still picks best RSSI if several qualify).

[--connect-ask]
  List qualifying robots interactively before connecting.
```

**Examples (scripts in repo):**

```bash
python connect_dash_bleak_smoketest.py --connect-name "Stevie" --connect-ask
python connect_dash_smoketest.py --connect-name "Stevie" --connect-ask
```

For richer demos with the flags above (e.g. `--connect-type`, `--connect-eager`), use the **`roboFun.py`** and similar scripts shipped with **[WonderPyExamples](https://github.com/playi/WonderPyExamples)**—not in this repo.


## Contributing

Pull requests welcome: check **[open issues](https://github.com/chopley/WonderPy3/issues)** first. Extra examples belong in **[WonderPyExamples](https://github.com/playi/WonderPyExamples)** upstream when possible.


## Troubleshooting / help

- **Bugs:** [Issues on WonderPy3](https://github.com/chopley/WonderPy3/issues)  
- **How-to questions:** [Stack Overflow](https://stackoverflow.com/) with tag **`wonderworkshop`** (community support; upstream brand).  

Legacy Wonder Workshop outreach (survey, old contact flows) tied to **[playi/WonderPy](https://github.com/playi/WonderPy)** is no longer the right channel for maintained use of **`WonderPy3`**—prefer GitHub issues here.
