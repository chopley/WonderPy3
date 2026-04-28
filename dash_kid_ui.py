import argparse
import asyncio
import json
import queue
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from bleak import BleakClient, BleakScanner

WW_SERVICE_UUID = "af237777-879d-6186-1f49-deca0e85d9c1"
CHAR_UUID_CMD = "af230002-879d-6186-1f49-deca0e85d9c1"

INDEX_HTML = """<!doctype html>
<html><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Dash Kid Controller</title>
<style>
body{font-family:Arial,sans-serif;max-width:760px;margin:18px auto;padding:0 12px}
.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;max-width:420px}
button{padding:14px 10px;font-size:18px;border-radius:8px;border:1px solid #bbb;cursor:pointer}
.wide{grid-column:span 3}.ok{background:#e8f7e8}.warn{background:#fff7e0}.stop{background:#ffe5e5}
pre{background:#111;color:#9ef39e;padding:10px;border-radius:8px;min-height:90px;white-space:pre-wrap}
input{padding:8px;font-size:16px;width:220px}
</style></head>
<body>
<h1>Dash Kid Controller</h1>
<p>Click a button to move Dash.</p>
<p><label>Robot name: <input id="robotName" value="Stevie"/></label> <button onclick="saveSettings()">Save Settings</button> <button onclick="testApi()">Test API</button></p>
<p>
  <label>Return trim: <input id="returnTrim" value="0.6" /></label>
  <label style="margin-left:12px">Heading trim: <input id="headingTrim" value="0.97" /></label>
</p>
<div class="grid">
<button class="wide ok" onclick="runAction('forward')">Forward</button>
<button class="warn" onclick="runAction('left')">Left</button>
<button class="stop" onclick="runAction('stop')">Stop</button>
<button class="warn" onclick="runAction('right')">Right</button>
<button class="wide ok" onclick="runAction('backward')">Backward</button>
<button class="wide" onclick="runAction('dance')">Run Dance Routine</button>
<button class="wide" onclick="runAction('calibrate_translation')">Run Translation Calibration</button>
<button class="wide" onclick="runAction('calibrate_spin')">Run Spin Calibration</button>
</div>
<p><strong>Status</strong></p><pre id="log">Ready.</pre>
<script>
const log=document.getElementById("log"),nameBox=document.getElementById("robotName");
const returnTrimBox=document.getElementById("returnTrim"),headingTrimBox=document.getElementById("headingTrim");
let busy=false;
const saved=localStorage.getItem("dashRobotName"); if(saved) nameBox.value=saved;
const savedReturnTrim=localStorage.getItem("dashReturnTrim"); if(savedReturnTrim) returnTrimBox.value=savedReturnTrim;
const savedHeadingTrim=localStorage.getItem("dashHeadingTrim"); if(savedHeadingTrim) headingTrimBox.value=savedHeadingTrim;
function addLog(s){log.textContent=s+"\\n"+log.textContent;}
function saveSettings(){
  localStorage.setItem("dashRobotName",nameBox.value.trim());
  localStorage.setItem("dashReturnTrim",returnTrimBox.value.trim());
  localStorage.setItem("dashHeadingTrim",headingTrimBox.value.trim());
  addLog("Saved settings: name="+nameBox.value.trim()+", return="+returnTrimBox.value.trim()+", heading="+headingTrimBox.value.trim());
}
async function runAction(action){
  if (busy) { addLog("Busy: wait for current action to finish."); return; }
  const robot_name=nameBox.value.trim()||"Stevie"; addLog("Running "+action+" on "+robot_name+" ...");
  const return_trim=Number(returnTrimBox.value.trim() || "0.6");
  const heading_trim=Number(headingTrimBox.value.trim() || "0.97");
  if (!Number.isFinite(return_trim) || !Number.isFinite(heading_trim)) { addLog("ERROR: trims must be numbers"); return; }
  busy=true;
  try{
    const res=await fetch("/api/run",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({action,robot_name,return_trim,heading_trim})});
    const data=await res.json().catch(() => ({error: "Non-JSON response from server"}));
    if(!res.ok){addLog("ERROR: "+(data.error||res.statusText));} else {addLog("OK: "+data.message);}
  }catch(e){addLog("ERROR: "+e);}
  finally{busy=false;}
}
async function testApi(){
  addLog("Testing API...");
  try{
    const res=await fetch("/api/ping");
    const data=await res.json().catch(() => ({error: "Non-JSON response from server"}));
    if(!res.ok){addLog("ERROR: "+(data.error||res.statusText)); return;}
    addLog("API OK: "+(data.message||"pong"));
  }catch(e){addLog("ERROR: "+e);}
}
</script></body></html>"""


def encode_signed_11(value):
    iv = max(-1024, min(1023, int(round(value))))
    if iv < 0:
        iv = (1 << 11) + iv
    return iv & 0x7FF


def drive_packet(linear, angular):
    lin, ang = encode_signed_11(linear), encode_signed_11(angular)
    if angular == 0:
        b0, b1, b2 = lin & 0xFF, 0x00, (lin & 0x0F00) >> 8
    elif linear == 0:
        b0, b1, b2 = 0x00, ang & 0xFF, (ang & 0xFF00) >> 5
    else:
        b0, b1, b2 = lin & 0xFF, ang & 0xFF, ((lin & 0x0F00) >> 8) | ((ang & 0xFF00) >> 5)
    return bytes([0x02, b0, b1, b2])


class RobotController:
    def __init__(self, scan_timeout=8.0):
        self.scan_timeout = scan_timeout
        self._cache = {}
        self._lock = threading.Lock()

    async def _scan_for_robot(self, robot_name):
        found = await BleakScanner.discover(timeout=self.scan_timeout, return_adv=True)
        strict_matches = []
        loose_matches = []
        target = robot_name.lower()
        for addr, (dev, adv) in found.items():
            if not dev.name:
                continue
            if target not in dev.name.lower():
                continue
            rssi = adv.rssi if adv and adv.rssi is not None else -999
            suuids = [s.lower() for s in (adv.service_uuids or [])]
            if WW_SERVICE_UUID in suuids:
                strict_matches.append((addr, dev.name, rssi))
            else:
                loose_matches.append((addr, dev.name, rssi))

        # Prefer explicit Wonder service UUID, but fall back to name match on macOS
        # where service UUIDs can be inconsistently populated in scan results.
        matches = strict_matches or loose_matches
        if not matches:
            return None
        matches.sort(key=lambda x: x[2], reverse=True)
        return matches[0][0]

    async def _find_robot(self, robot_name):
        with self._lock:
            if robot_name in self._cache:
                return self._cache[robot_name]

        addr = await self._scan_for_robot(robot_name)
        if addr is None:
            raise RuntimeError(
                "No matching robot found for '%s'. Confirm power is on and name is exact."
                % robot_name
            )
        with self._lock:
            self._cache[robot_name] = addr
        return addr

    async def _move_once(self, robot_name, linear, angular, seconds):
        addr = await self._find_robot(robot_name)
        async with BleakClient(addr) as client:
            await client.write_gatt_char(CHAR_UUID_CMD, drive_packet(linear, angular))
            await asyncio.sleep(seconds)
            await client.write_gatt_char(CHAR_UUID_CMD, drive_packet(0, 0))

    async def run_action(self, robot_name, action, return_trim=0.6, heading_trim=0.97):
        # Durations are intentionally short for child-safe interaction.
        actions = {
            "forward": (300, 0, 0.6),
            "backward": (-300, 0, 0.6),
            "left": (0, 420, 0.5),
            "right": (0, -420, 0.5),
            "stop": (0, 0, 0.1),
        }
        if action == "dance":
            rt = max(0.1, min(2.0, float(return_trim)))
            ht = max(0.1, min(2.0, float(heading_trim)))
            steps = [
                ("forward", 300, 0, 0.5),
                ("backward", -300, 0, 0.5),
                ("return to start", 300, 0, 0.5 * rt),
                ("turn left 180", 0, 420, 1.2),
                ("forward (left-facing)", 300, 0, 0.5),
                ("backward (left-facing)", -300, 0, 0.5),
                ("return to start (left-facing)", 300, 0, 0.5 * rt),
                ("turn right 180 to heading", 0, -420, 1.2 * ht),
            ]
            try:
                for _, linear, angular, seconds in steps:
                    await self._move_once(robot_name, linear, angular, seconds)
                    await asyncio.sleep(0.3)
            except Exception:
                # Clear cached address and retry once in case the cached discovery
                # entry is stale or the device changed BLE address.
                with self._lock:
                    self._cache.pop(robot_name, None)
                for _, linear, angular, seconds in steps:
                    await self._move_once(robot_name, linear, angular, seconds)
                    await asyncio.sleep(0.3)
            return "Dance done! (return_trim=%.2f, heading_trim=%.2f)" % (rt, ht)
        if action == "calibrate_translation":
            rt = max(0.1, min(2.0, float(return_trim)))
            linear_cmd = 320
            forward_seconds = 0.6
            backward_seconds = forward_seconds * rt
            pause_seconds = 1.0
            cycles = 3
            steps = []
            for _ in range(cycles):
                steps.append(("forward", linear_cmd, 0, forward_seconds))
                steps.append(("backward", -linear_cmd, 0, backward_seconds))
            try:
                for _, linear, angular, seconds in steps:
                    await self._move_once(robot_name, linear, angular, seconds)
                    await asyncio.sleep(pause_seconds)
            except Exception:
                with self._lock:
                    self._cache.pop(robot_name, None)
                for _, linear, angular, seconds in steps:
                    await self._move_once(robot_name, linear, angular, seconds)
                    await asyncio.sleep(pause_seconds)
            return "Translation calibration done! (backward_trim=%.2f, cycles=%d)" % (rt, cycles)
        if action == "calibrate_spin":
            ht = max(0.1, min(2.0, float(heading_trim)))
            angular_cmd = 420
            left_seconds = 1.2
            right_seconds = left_seconds * ht
            pause_seconds = 1.0
            cycles = 3
            steps = []
            for _ in range(cycles):
                steps.append(("spin left", 0, angular_cmd, left_seconds))
                steps.append(("spin right", 0, -angular_cmd, right_seconds))
            try:
                for _, linear, angular, seconds in steps:
                    await self._move_once(robot_name, linear, angular, seconds)
                    await asyncio.sleep(pause_seconds)
            except Exception:
                with self._lock:
                    self._cache.pop(robot_name, None)
                for _, linear, angular, seconds in steps:
                    await self._move_once(robot_name, linear, angular, seconds)
                    await asyncio.sleep(pause_seconds)
            return "Spin calibration done! (right_trim=%.2f, cycles=%d)" % (ht, cycles)
        if action not in actions:
            raise ValueError("Unknown action '%s'" % action)
        linear, angular, seconds = actions[action]
        try:
            await self._move_once(robot_name, linear, angular, seconds)
        except Exception:
            with self._lock:
                self._cache.pop(robot_name, None)
            await self._move_once(robot_name, linear, angular, seconds)
        return "Ran %s." % action


class ActionWorker:
    def __init__(self, controller):
        self.controller = controller
        self.jobs = queue.Queue()
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()

    def _run_loop(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        while True:
            action, robot_name, return_trim, heading_trim, result_queue = self.jobs.get()
            try:
                started = time.time()
                message = self.loop.run_until_complete(
                    self.controller.run_action(
                        robot_name,
                        action,
                        return_trim=return_trim,
                        heading_trim=heading_trim,
                    )
                )
                result_queue.put((True, "%s (%.2fs)" % (message, time.time() - started)))
            except Exception as exc:
                result_queue.put((False, str(exc)))

    def run_action_blocking(
        self,
        robot_name,
        action,
        return_trim=0.6,
        heading_trim=0.97,
        timeout=20.0,
    ):
        result_queue = queue.Queue(maxsize=1)
        self.jobs.put((action, robot_name, return_trim, heading_trim, result_queue))
        try:
            ok, message = result_queue.get(timeout=timeout)
        except queue.Empty:
            raise RuntimeError("Action timed out; check robot power/Bluetooth and try again.")
        if not ok:
            raise RuntimeError(message)
        return message


class DashKidHandler(BaseHTTPRequestHandler):
    controller = RobotController()
    worker = ActionWorker(controller)

    def _json_response(self, payload, status=HTTPStatus.OK):
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/api/ping":
            self._json_response({"ok": True, "message": "pong"})
            return
        if self.path != "/":
            self.send_error(HTTPStatus.NOT_FOUND, "Not Found")
            return
        data = INDEX_HTML.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        if self.path != "/api/run":
            self.send_error(HTTPStatus.NOT_FOUND, "Not Found")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length).decode("utf-8") if length else "{}"
            payload = json.loads(body)
            action = (payload.get("action") or "").strip().lower()
            robot_name = (payload.get("robot_name") or "Stevie").strip()
            return_trim = float(payload.get("return_trim", 0.6))
            heading_trim = float(payload.get("heading_trim", 0.97))
            if not action:
                raise ValueError("Missing action")
            message = self.worker.run_action_blocking(
                robot_name,
                action,
                return_trim=return_trim,
                heading_trim=heading_trim,
            )
            self._json_response({"ok": True, "message": message})
        except Exception as exc:
            self._json_response({"ok": False, "error": str(exc)}, status=HTTPStatus.BAD_REQUEST)

    def log_message(self, fmt, *args):
        return


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), DashKidHandler)
    print("Dash Kid Controller running at http://%s:%d" % (args.host, args.port))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
