import os
import time
import threading

from WonderPy.core import wwMain


class DashBleakSmokeDelegate:
    def __init__(self, max_sensor_updates=20):
        self.max_sensor_updates = max_sensor_updates
        self._sensor_updates = 0
        self._connected_at = None
        self._fallback_timer = None

    def on_connect(self, robot):
        self._connected_at = time.time()
        print("CONNECTED:", robot.robot_type_name, repr(robot.name))
        # If HAL decoding is unavailable we may not receive parsed sensor callbacks.
        self._fallback_timer = threading.Timer(10.0, self._exit_with_connect_only_success)
        self._fallback_timer.daemon = True
        self._fallback_timer.start()

    def _exit_with_connect_only_success(self):
        print("SUCCESS: connected (no parsed sensors within timeout), exiting.")
        os._exit(0)

    def on_sensors(self, robot):
        if self._fallback_timer is not None:
            self._fallback_timer.cancel()
            self._fallback_timer = None
        self._sensor_updates += 1
        if self._sensor_updates == 1:
            pose = robot.sensors.pose
            if pose and pose.valid:
                print("FIRST SENSOR: x=%.2f y=%.2f deg=%.2f" % (pose.x, pose.y, pose.degrees))
            else:
                print("FIRST SENSOR: received")

        if self._sensor_updates >= self.max_sensor_updates:
            elapsed = time.time() - self._connected_at if self._connected_at else 0.0
            print("SUCCESS: received %d sensor updates in %.2fs, exiting." % (self._sensor_updates, elapsed))
            os._exit(0)


if __name__ == "__main__":
    os.environ["WONDERPY_BLE_BACKEND"] = "bleak"
    delegate = DashBleakSmokeDelegate(max_sensor_updates=20)
    wwMain.start(delegate)
