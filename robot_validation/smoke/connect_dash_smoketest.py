import os
import time

from WonderPy.core import wwMain


class DashSmokeDelegate:
    def __init__(self, max_sensor_updates=20):
        self.max_sensor_updates = max_sensor_updates
        self._sensor_updates = 0
        self._connected_at = None

    def on_connect(self, robot):
        self._connected_at = time.time()
        print("CONNECTED:", robot.robot_type_name, repr(robot.name))

        # Quick visible confirmation on a successful connection.
        if hasattr(robot.cmds, "monoLED"):
            robot.cmds.monoLED.stage_button_main(1.0)

    def on_sensors(self, robot):
        self._sensor_updates += 1
        if self._sensor_updates == 1:
            pose = robot.sensors.pose
            if pose and pose.valid:
                print(
                    "FIRST SENSOR: x=%.2f y=%.2f deg=%.2f"
                    % (pose.x, pose.y, pose.degrees)
                )
            else:
                print("FIRST SENSOR: received (pose not yet valid)")

        if self._sensor_updates >= self.max_sensor_updates:
            elapsed = time.time() - self._connected_at if self._connected_at else 0.0
            print(
                "SUCCESS: received %d sensor updates in %.2fs, exiting."
                % (self._sensor_updates, elapsed)
            )
            os._exit(0)


if __name__ == "__main__":
    delegate = DashSmokeDelegate(max_sensor_updates=20)
    wwMain.start(delegate)
