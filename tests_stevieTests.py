import os
import time
import threading

from WonderPy.core import wwMain


class MotionSequenceDelegate:
    # (label, forward_cm, turn_deg, duration_s)
    STEPS = [
        ("forward", 35.0, 0.0, 1.0),
        ("backward", -70.0, 0.0, 2.0),
        ("forward", 35.0, 0.0, 1.0),
        ("left", 0.0, 120.0, 1.0),
        ("right", 0.0, -240.0, 2.0),
        ("left", 0.0, 120.0, 1.0),
    ]

    def __init__(self):
        self._connected = False
        self._sequence_started = False

    def on_connect(self, robot):
        self._connected = True
        print("CONNECTED:", robot.name, robot.robot_type_name)
        if not self._sequence_started:
            self._sequence_started = True
            t = threading.Thread(target=self._run_timed_sequence, args=(robot,), daemon=True)
            t.start()

    def _run_timed_sequence(self, robot):
        for idx, (label, forward_cm, turn_deg, duration) in enumerate(self.STEPS, start=1):
            print("STEP %d/%d: %s for %.1fs" % (idx, len(self.STEPS), label, duration))
            robot.cmds.body.stage_pose(
                0.0,
                forward_cm,
                turn_deg,
                duration,
            )
            robot.send_staged()
            time.sleep(duration)

            # Short neutral stop between steps to avoid latching.
            robot.cmds.body.stage_stop()
            robot.send_staged()
            time.sleep(0.15)

        robot.cmds.body.stage_stop()
        robot.send_staged()
        print("SEQUENCE COMPLETE: robot stopped.")
        os._exit(0)

    def on_sensors(self, robot):
        # Timed sequence runs in a worker thread; sensor cadence can vary by backend.
        pass


if __name__ == "__main__":
    # Force the new backend for Apple Silicon compatibility.
    os.environ["WONDERPY_BLE_BACKEND"] = "bleak"
    wwMain.start(MotionSequenceDelegate())
    
    
    
