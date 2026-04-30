import argparse
import asyncio
import json
import math
import queue
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from bleak import BleakClient, BleakScanner

WW_SERVICE_UUID = "af237777-879d-6186-1f49-deca0e85d9c1"
CHAR_UUID_CMD = "af230002-879d-6186-1f49-deca0e85d9c1"
CHAR_UUID_SENSOR1 = "af230006-879d-6186-1f49-deca0e85d9c1"

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
canvas{border:2px solid #999;border-radius:8px;background:#fff;touch-action:none}
</style></head>
<body>
<h1>Dash Kid Controller</h1>
<p>Click a button to move Dash.</p>
<p><label>Robot name: <input id="robotName" value="Stevie"/></label> <button onclick="saveSettings()">Save Settings</button> <button onclick="connectRobot()">Connect</button> <button onclick="disconnectRobot()">Disconnect</button> <button onclick="testApi()">Test API</button></p>
<p>
  <label>Return trim: <input id="returnTrim" value="0.6" /></label>
  <label style="margin-left:12px">Heading trim: <input id="headingTrim" value="0.97" /></label>
</p>
<p>
  <label>Path speed scale (sec per meter): <input id="pathScale" value="1.6" /></label>
  <label style="margin-left:12px">Canvas width (meters): <input id="canvasWidthM" value="1.5" /></label>
  <label style="margin-left:12px">Max travel (meters): <input id="maxTravelM" value="2.0" /></label>
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
<button class="wide ok" onclick="runDrawnPath()">Follow Drawn Path</button>
<button class="wide" onclick="clearPath()">Clear Drawn Path</button>
<button class="wide warn" onclick="setMarkerMode(true)">Marker Mode: ON</button>
<button class="wide" onclick="setMarkerMode(false)">Marker Mode: OFF</button>
<button class="wide" onclick="clearMarkers()">Clear Markers</button>
</div>
<p><strong>Draw Path</strong> (drag your mouse). In marker mode, click to add must-hit markers.</p>
<canvas id="pathCanvas" width="700" height="260"></canvas>
<p><strong>Status</strong></p><pre id="log">Ready.</pre>
<script>
const log=document.getElementById("log"),nameBox=document.getElementById("robotName");
const returnTrimBox=document.getElementById("returnTrim"),headingTrimBox=document.getElementById("headingTrim"),pathScaleBox=document.getElementById("pathScale");
const canvasWidthMBox=document.getElementById("canvasWidthM"),maxTravelMBox=document.getElementById("maxTravelM");
const canvas=document.getElementById("pathCanvas"),ctx=canvas.getContext("2d");
let busy=false;
let drawing=false;
let pathPoints=[];
let markerPoints=[];
let markerMode=false;
const saved=localStorage.getItem("dashRobotName"); if(saved) nameBox.value=saved;
const savedReturnTrim=localStorage.getItem("dashReturnTrim"); if(savedReturnTrim) returnTrimBox.value=savedReturnTrim;
const savedHeadingTrim=localStorage.getItem("dashHeadingTrim"); if(savedHeadingTrim) headingTrimBox.value=savedHeadingTrim;
const savedPathScale=localStorage.getItem("dashPathScale"); if(savedPathScale) pathScaleBox.value=savedPathScale;
const savedCanvasWidthM=localStorage.getItem("dashCanvasWidthM"); if(savedCanvasWidthM) canvasWidthMBox.value=savedCanvasWidthM;
const savedMaxTravelM=localStorage.getItem("dashMaxTravelM"); if(savedMaxTravelM) maxTravelMBox.value=savedMaxTravelM;
function addLog(s){log.textContent=s+"\\n"+log.textContent;}
function setMarkerMode(enabled){
  markerMode=!!enabled;
  addLog("Marker mode: "+(markerMode ? "ON" : "OFF"));
}
function redrawPath(){
  ctx.clearRect(0,0,canvas.width,canvas.height);
  ctx.fillStyle="#f7f7f7";
  ctx.fillRect(0,0,canvas.width,canvas.height);
  if(pathPoints.length>=1){
    ctx.strokeStyle="#0077cc";
    ctx.lineWidth=3;
    ctx.beginPath();
    ctx.moveTo(pathPoints[0].x,pathPoints[0].y);
    for(let i=1;i<pathPoints.length;i++){ ctx.lineTo(pathPoints[i].x,pathPoints[i].y); }
    ctx.stroke();
    ctx.fillStyle="#00aa44";
    ctx.beginPath(); ctx.arc(pathPoints[0].x,pathPoints[0].y,5,0,Math.PI*2); ctx.fill();
    const last=pathPoints[pathPoints.length-1];
    ctx.fillStyle="#cc0000";
    ctx.beginPath(); ctx.arc(last.x,last.y,5,0,Math.PI*2); ctx.fill();
  }
  ctx.strokeStyle="#cc00aa";
  ctx.fillStyle="#cc00aa";
  ctx.lineWidth=2;
  for(let i=0;i<markerPoints.length;i++){
    const m=markerPoints[i];
    ctx.beginPath();
    ctx.arc(m.x,m.y,7,0,Math.PI*2);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(m.x-5,m.y); ctx.lineTo(m.x+5,m.y);
    ctx.moveTo(m.x,m.y-5); ctx.lineTo(m.x,m.y+5);
    ctx.stroke();
  }
  const widthM = Number(canvasWidthMBox.value.trim() || "1.5");
  if (Number.isFinite(widthM) && widthM > 0) {
    ctx.fillStyle="#333";
    ctx.font="14px Arial";
    ctx.fillText("Canvas width = "+widthM.toFixed(2)+" m", 12, canvas.height - 12);
  }
}
function toCanvasPoint(ev){
  const r=canvas.getBoundingClientRect();
  return {x:ev.clientX-r.left,y:ev.clientY-r.top};
}
canvas.addEventListener("pointerdown",(ev)=>{
  const p=toCanvasPoint(ev);
  if(markerMode){
    markerPoints.push(p);
    redrawPath();
    addLog("Added marker #"+markerPoints.length);
    return;
  }
  drawing=true;
  pathPoints=[p];
  redrawPath();
});
canvas.addEventListener("pointermove",(ev)=>{
  if(!drawing){return;}
  const p=toCanvasPoint(ev);
  const prev=pathPoints[pathPoints.length-1];
  if(!prev || Math.hypot(p.x-prev.x,p.y-prev.y)>=3){ pathPoints.push(p); redrawPath(); }
});
canvas.addEventListener("pointerup",()=>{ drawing=false; });
canvas.addEventListener("pointerleave",()=>{ drawing=false; });
function clearPath(){ pathPoints=[]; redrawPath(); addLog("Cleared drawn path."); }
function clearMarkers(){ markerPoints=[]; redrawPath(); addLog("Cleared markers."); }
redrawPath();
function saveSettings(){
  localStorage.setItem("dashRobotName",nameBox.value.trim());
  localStorage.setItem("dashReturnTrim",returnTrimBox.value.trim());
  localStorage.setItem("dashHeadingTrim",headingTrimBox.value.trim());
  localStorage.setItem("dashPathScale",pathScaleBox.value.trim());
  localStorage.setItem("dashCanvasWidthM",canvasWidthMBox.value.trim());
  localStorage.setItem("dashMaxTravelM",maxTravelMBox.value.trim());
  addLog("Saved settings: name="+nameBox.value.trim()+", return="+returnTrimBox.value.trim()+", heading="+headingTrimBox.value.trim()+", pathScale="+pathScaleBox.value.trim()+", canvasWidthM="+canvasWidthMBox.value.trim()+", maxTravelM="+maxTravelMBox.value.trim());
  redrawPath();
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
    if(!res.ok){
      addLog("ERROR: "+(data.error||res.statusText));
    } else {
      addLog("OK: "+data.message);
      if(data.encoder_before || data.encoder_after){
        addLog("Encoders before: "+JSON.stringify(data.encoder_before||"n/a")+" | after: "+JSON.stringify(data.encoder_after||"n/a"));
      }
    }
  }catch(e){addLog("ERROR: "+e);}
  finally{busy=false;}
}
async function connectRobot(){
  if (busy) { addLog("Busy: wait for current action to finish."); return; }
  const robot_name=nameBox.value.trim()||"Stevie";
  addLog("Connecting to "+robot_name+" ...");
  busy=true;
  try{
    const res=await fetch("/api/connect",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({robot_name})});
    const data=await res.json().catch(() => ({error: "Non-JSON response from server"}));
    if(!res.ok){addLog("ERROR: "+(data.error||res.statusText));} else {addLog("OK: "+data.message);}
  }catch(e){addLog("ERROR: "+e);}
  finally{busy=false;}
}
async function disconnectRobot(){
  if (busy) { addLog("Busy: wait for current action to finish."); return; }
  addLog("Disconnecting ...");
  busy=true;
  try{
    const res=await fetch("/api/disconnect",{method:"POST",headers:{"Content-Type":"application/json"},body:"{}"});
    const data=await res.json().catch(() => ({error: "Non-JSON response from server"}));
    if(!res.ok){addLog("ERROR: "+(data.error||res.statusText));} else {addLog("OK: "+data.message);}
  }catch(e){addLog("ERROR: "+e);}
  finally{busy=false;}
}
async function runDrawnPath(){
  if (busy) { addLog("Busy: wait for current action to finish."); return; }
  if (pathPoints.length < 2) { addLog("ERROR: draw a path first (drag on the canvas)."); return; }
  const robot_name=nameBox.value.trim()||"Stevie";
  const return_trim=Number(returnTrimBox.value.trim() || "0.6");
  const heading_trim=Number(headingTrimBox.value.trim() || "0.97");
  const path_scale=Number(pathScaleBox.value.trim() || "1.6");
  const canvas_width_m=Number(canvasWidthMBox.value.trim() || "1.5");
  const max_travel_m=Number(maxTravelMBox.value.trim() || "2.0");
  if (!Number.isFinite(return_trim) || !Number.isFinite(heading_trim) || !Number.isFinite(path_scale) || !Number.isFinite(canvas_width_m) || !Number.isFinite(max_travel_m)) {
    addLog("ERROR: trims, path scale, canvas width, and max travel must be numbers");
    return;
  }
  if (canvas_width_m <= 0 || max_travel_m <= 0) {
    addLog("ERROR: canvas width and max travel must be > 0");
    return;
  }
  addLog("Following drawn path ("+pathPoints.length+" points, "+markerPoints.length+" markers) ...");
  busy=true;
  try{
    const res=await fetch("/api/follow_path",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({robot_name,return_trim,heading_trim,path_scale,canvas_width_m,max_travel_m,canvas_width_px:canvas.width,points:pathPoints,markers:markerPoints})});
    const data=await res.json().catch(() => ({error: "Non-JSON response from server"}));
    if(!res.ok){
      addLog("ERROR: "+(data.error||res.statusText));
    } else {
      addLog("OK: "+data.message);
      if(data.encoder_before || data.encoder_after){
        addLog("Encoders before: "+JSON.stringify(data.encoder_before||"n/a")+" | after: "+JSON.stringify(data.encoder_after||"n/a"));
      }
    }
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
        self._client = None
        self._connected_name = None
        self._encoder_latest = None

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

    async def connect_robot(self, robot_name):
        # Reuse an existing healthy connection when possible.
        if (
            self._client is not None
            and self._client.is_connected
            and self._connected_name == robot_name
        ):
            return "Already connected to '%s'." % robot_name

        await self.disconnect_robot()
        addr = await self._find_robot(robot_name)
        client = BleakClient(addr)
        await client.connect()
        if not client.is_connected:
            raise RuntimeError("Connection attempt failed for '%s'." % robot_name)
        self._encoder_latest = None
        try:
            await client.start_notify(CHAR_UUID_SENSOR1, self._on_sensor1)
        except Exception:
            # Not fatal for control; encoder logging may be unavailable on some models/firmware.
            pass
        self._client = client
        self._connected_name = robot_name
        return "Connected to '%s'." % robot_name

    async def disconnect_robot(self):
        if self._client is not None:
            try:
                if self._client.is_connected:
                    await self._client.disconnect()
            finally:
                self._client = None
                self._connected_name = None
        return "Disconnected."

    def _require_connected_robot(self, robot_name):
        if self._client is None or not self._client.is_connected:
            raise RuntimeError(
                "Not connected. Click Connect first, then run movement commands."
            )
        if self._connected_name != robot_name:
            raise RuntimeError(
                "Connected to '%s', not '%s'. Click Connect for the selected robot first."
                % (self._connected_name, robot_name)
            )

    def _on_sensor1(self, _sender, data):
        if data is None or len(data) < 18:
            return
        left_wheel = (data[15] << 8) | data[14]
        right_wheel = (data[17] << 8) | data[16]
        self._encoder_latest = {
            "left": int(left_wheel),
            "right": int(right_wheel),
            "timestamp": time.time(),
        }

    def _encoder_snapshot(self):
        if self._encoder_latest is None:
            return None
        return {
            "left": self._encoder_latest["left"],
            "right": self._encoder_latest["right"],
        }

    async def _move_once(self, robot_name, linear, angular, seconds):
        await self._drive_for(robot_name, linear, angular, seconds, stop_after=True)

    async def _drive_for(self, robot_name, linear, angular, seconds, stop_after=False):
        self._require_connected_robot(robot_name)
        await self._client.write_gatt_char(CHAR_UUID_CMD, drive_packet(linear, angular))
        await asyncio.sleep(seconds)
        if stop_after:
            await self._client.write_gatt_char(CHAR_UUID_CMD, drive_packet(0, 0))

    @staticmethod
    def _moving_average_points(points, window=5):
        if len(points) <= 2 or window <= 1:
            return points
        radius = window // 2
        smoothed = []
        for i in range(len(points)):
            start = max(0, i - radius)
            end = min(len(points), i + radius + 1)
            chunk = points[start:end]
            sx = sum(p[0] for p in chunk) / len(chunk)
            sy = sum(p[1] for p in chunk) / len(chunk)
            smoothed.append((sx, sy))
        smoothed[0] = points[0]
        smoothed[-1] = points[-1]
        return smoothed

    @staticmethod
    def _resample_points(points, step_px=18.0):
        if len(points) <= 2:
            return points
        step_px = max(6.0, float(step_px))
        sampled = [points[0]]
        carry = 0.0
        for i in range(1, len(points)):
            x1, y1 = points[i - 1]
            x2, y2 = points[i]
            dx = x2 - x1
            dy = y2 - y1
            seg_len = math.hypot(dx, dy)
            if seg_len < 1e-6:
                continue
            dist = step_px - carry
            while dist <= seg_len:
                t = dist / seg_len
                sampled.append((x1 + dx * t, y1 + dy * t))
                dist += step_px
            carry = seg_len - (dist - step_px)
        if sampled[-1] != points[-1]:
            sampled.append(points[-1])
        return sampled

    @staticmethod
    def _insert_marker_points(points, markers):
        if not markers:
            return points
        points = list(points)
        for marker in markers:
            mx, my = marker
            nearest_idx = 0
            nearest_dist = float("inf")
            for idx, (px, py) in enumerate(points):
                d = math.hypot(px - mx, py - my)
                if d < nearest_dist:
                    nearest_dist = d
                    nearest_idx = idx
            insert_at = min(len(points), nearest_idx + 1)
            points.insert(insert_at, (mx, my))
        return points

    async def run_action(self, robot_name, action, return_trim=0.6, heading_trim=0.97):
        encoder_before = self._encoder_snapshot()
        # Durations are intentionally short for child-safe interaction.
        rt = max(0.1, min(2.0, float(return_trim)))
        ht = max(0.1, min(2.0, float(heading_trim)))
        actions = {
            "forward": (300, 0, 0.6 * rt),
            "backward": (-300, 0, 0.6 * rt),
            "left": (0, 420, 0.5 * ht),
            "right": (0, -420, 0.5 * ht),
            "stop": (0, 0, 0.1),
        }
        if action == "dance":
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
            base_message = "Dance done! (return_trim=%.2f, heading_trim=%.2f)" % (rt, ht)
            return {
                "message": base_message,
                "encoder_before": encoder_before,
                "encoder_after": self._encoder_snapshot(),
            }
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
            base_message = "Translation calibration done! (backward_trim=%.2f, cycles=%d)" % (rt, cycles)
            return {
                "message": base_message,
                "encoder_before": encoder_before,
                "encoder_after": self._encoder_snapshot(),
            }
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
            base_message = "Spin calibration done! (right_trim=%.2f, cycles=%d)" % (ht, cycles)
            return {
                "message": base_message,
                "encoder_before": encoder_before,
                "encoder_after": self._encoder_snapshot(),
            }
        if action not in actions:
            raise ValueError("Unknown action '%s'" % action)
        linear, angular, seconds = actions[action]
        try:
            await self._move_once(robot_name, linear, angular, seconds)
        except Exception:
            with self._lock:
                self._cache.pop(robot_name, None)
            await self._move_once(robot_name, linear, angular, seconds)
        return {
            "message": "Ran %s." % action,
            "encoder_before": encoder_before,
            "encoder_after": self._encoder_snapshot(),
        }

    async def follow_path(
        self,
        robot_name,
        points,
        markers=None,
        return_trim=0.6,
        heading_trim=0.97,
        path_scale=1.6,
        canvas_width_m=1.5,
        max_travel_m=2.0,
        canvas_width_px=700.0,
    ):
        self._require_connected_robot(robot_name)
        encoder_before = self._encoder_snapshot()
        if not isinstance(points, list) or len(points) < 2:
            raise ValueError("Path must include at least two points.")

        rt = max(0.1, min(2.0, float(return_trim)))
        ht = max(0.1, min(2.0, float(heading_trim)))
        scale = max(0.2, min(10.0, float(path_scale)))
        width_m = max(0.1, min(20.0, float(canvas_width_m)))
        width_px = max(100.0, min(4000.0, float(canvas_width_px)))
        max_m = max(0.1, min(50.0, float(max_travel_m)))
        meters_per_px = width_m / width_px
        raw_points = []
        for p in points:
            raw_points.append((float(p.get("x")), float(p.get("y"))))
        marker_points = []
        for m in (markers or []):
            marker_points.append((float(m.get("x")), float(m.get("y"))))
        points_xy = self._moving_average_points(raw_points, window=5)
        points_xy = self._resample_points(points_xy, step_px=18.0)
        points_xy = self._insert_marker_points(points_xy, marker_points)

        linear_cmd = 300
        angular_cmd = 420
        heading_deg = 0.0
        segment_count = 0
        total_distance_m = 0.0

        try:
            for idx in range(len(points_xy) - 1):
                x1, y1 = points_xy[idx]
                x2, y2 = points_xy[idx + 1]
                dx = x2 - x1
                dy = y2 - y1
                distance_px = math.hypot(dx, dy)
                if distance_px < 2.0:
                    continue
                distance_m = distance_px * meters_per_px
                if total_distance_m + distance_m > max_m:
                    raise RuntimeError(
                        "Path exceeds max travel %.2fm. Shorten drawing or raise Max travel."
                        % max_m
                    )

                target_heading = math.degrees(math.atan2(dy, dx))
                delta = ((target_heading - heading_deg + 180.0) % 360.0) - 180.0
                if abs(delta) >= 10.0:
                    # Path interpolation emits many short segments. Use a gentler
                    # turn-time curve here than spin calibration to avoid over-rotation.
                    turn_seconds = (abs(delta) / 180.0) * 0.9 * ht
                    # Positive canvas angle is clockwise (right turn), which is negative angular command.
                    turn_angular = -angular_cmd if delta > 0 else angular_cmd
                    await self._drive_for(
                        robot_name,
                        0,
                        turn_angular,
                        turn_seconds,
                        stop_after=False,
                    )
                    await asyncio.sleep(0.04)
                heading_deg = target_heading

                forward_seconds = distance_m * scale * rt
                await self._drive_for(
                    robot_name,
                    linear_cmd,
                    0,
                    forward_seconds,
                    stop_after=False,
                )
                await asyncio.sleep(0.04)
                segment_count += 1
                total_distance_m += distance_m

            if segment_count == 0:
                raise ValueError("Path is too short. Draw a longer line.")
            return {
                "message": "Followed path with %d segment(s), %.2fm total." % (
                    segment_count,
                    total_distance_m,
                ),
                "encoder_before": encoder_before,
                "encoder_after": self._encoder_snapshot(),
            }
        finally:
            await self._client.write_gatt_char(CHAR_UUID_CMD, drive_packet(0, 0))


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
            op, robot_name, action, return_trim, heading_trim, points, markers, path_scale, canvas_width_m, max_travel_m, canvas_width_px, result_queue = self.jobs.get()
            try:
                started = time.time()
                if op == "connect":
                    message = self.loop.run_until_complete(
                        self.controller.connect_robot(robot_name)
                    )
                elif op == "disconnect":
                    message = self.loop.run_until_complete(
                        self.controller.disconnect_robot()
                    )
                elif op == "follow_path":
                    message = self.loop.run_until_complete(
                        self.controller.follow_path(
                            robot_name,
                            points,
                            markers=markers,
                            return_trim=return_trim,
                            heading_trim=heading_trim,
                            path_scale=path_scale,
                            canvas_width_m=canvas_width_m,
                            max_travel_m=max_travel_m,
                            canvas_width_px=canvas_width_px,
                        )
                    )
                else:
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

    def connect_blocking(self, robot_name, timeout=20.0):
        result_queue = queue.Queue(maxsize=1)
        self.jobs.put(("connect", robot_name, "", 0.0, 0.0, [], [], 0.0, 0.0, 0.0, 0.0, result_queue))
        try:
            ok, message = result_queue.get(timeout=timeout)
        except queue.Empty:
            raise RuntimeError("Connect timed out; check robot power/Bluetooth and try again.")
        if not ok:
            raise RuntimeError(message)
        return message

    def disconnect_blocking(self, timeout=10.0):
        result_queue = queue.Queue(maxsize=1)
        self.jobs.put(("disconnect", "", "", 0.0, 0.0, [], [], 0.0, 0.0, 0.0, 0.0, result_queue))
        try:
            ok, message = result_queue.get(timeout=timeout)
        except queue.Empty:
            raise RuntimeError("Disconnect timed out.")
        if not ok:
            raise RuntimeError(message)
        return message

    def run_action_blocking(
        self,
        robot_name,
        action,
        return_trim=0.6,
        heading_trim=0.97,
        timeout=20.0,
    ):
        result_queue = queue.Queue(maxsize=1)
        self.jobs.put(("run", robot_name, action, return_trim, heading_trim, [], [], 0.0, 0.0, 0.0, 0.0, result_queue))
        try:
            ok, message = result_queue.get(timeout=timeout)
        except queue.Empty:
            raise RuntimeError("Action timed out; check robot power/Bluetooth and try again.")
        if not ok:
            raise RuntimeError(message)
        return message

    def follow_path_blocking(
        self,
        robot_name,
        points,
        markers=None,
        return_trim=0.6,
        heading_trim=0.97,
        path_scale=1.6,
        canvas_width_m=1.5,
        max_travel_m=2.0,
        canvas_width_px=700.0,
        timeout=120.0,
    ):
        result_queue = queue.Queue(maxsize=1)
        self.jobs.put(
            (
                "follow_path",
                robot_name,
                "",
                return_trim,
                heading_trim,
                points,
                markers or [],
                path_scale,
                canvas_width_m,
                max_travel_m,
                canvas_width_px,
                result_queue,
            )
        )
        try:
            ok, message = result_queue.get(timeout=timeout)
        except queue.Empty:
            raise RuntimeError("Path run timed out; try a shorter drawing.")
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
        if self.path not in ("/api/run", "/api/connect", "/api/disconnect", "/api/follow_path"):
            self.send_error(HTTPStatus.NOT_FOUND, "Not Found")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length).decode("utf-8") if length else "{}"
            payload = json.loads(body)
            robot_name = (payload.get("robot_name") or "Stevie").strip()
            if self.path == "/api/connect":
                message = self.worker.connect_blocking(robot_name)
            elif self.path == "/api/disconnect":
                message = self.worker.disconnect_blocking()
            elif self.path == "/api/follow_path":
                points = payload.get("points") or []
                markers = payload.get("markers") or []
                return_trim = float(payload.get("return_trim", 0.6))
                heading_trim = float(payload.get("heading_trim", 0.97))
                path_scale = float(payload.get("path_scale", 1.6))
                canvas_width_m = float(payload.get("canvas_width_m", 1.5))
                max_travel_m = float(payload.get("max_travel_m", 2.0))
                canvas_width_px = float(payload.get("canvas_width_px", 700.0))
                message = self.worker.follow_path_blocking(
                    robot_name,
                    points,
                    markers=markers,
                    return_trim=return_trim,
                    heading_trim=heading_trim,
                    path_scale=path_scale,
                    canvas_width_m=canvas_width_m,
                    max_travel_m=max_travel_m,
                    canvas_width_px=canvas_width_px,
                )
            else:
                action = (payload.get("action") or "").strip().lower()
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
            if isinstance(message, dict):
                payload_out = {"ok": True}
                payload_out.update(message)
                self._json_response(payload_out)
            else:
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
