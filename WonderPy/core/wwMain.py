import threading
import os


def start(delegate_instance, arguments=None):
    backend = os.environ.get("WONDERPY_BLE_BACKEND", "adafruit").strip().lower()
    if backend == "bleak":
        from WonderPy.core.wwBleakMgr import WWBleakManager
        WWBleakManager(delegate_instance, arguments).run()
    else:
        from WonderPy.core.wwBTLEMgr import WWBTLEManager
        WWBTLEManager(delegate_instance, arguments).run()


thread_local_data = threading.local()
