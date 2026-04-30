import argparse
import asyncio

from bleak import BleakClient, BleakScanner

WW_SERVICE_UUID = "af237777-879d-6186-1f49-deca0e85d9c1"
CHAR_UUID_CMD = "af230002-879d-6186-1f49-deca0e85d9c1"


def encode_signed_11(value):
    iv = int(round(value))
    iv = max(-1024, min(1023, iv))
    if iv < 0:
        iv = (1 << 11) + iv
    return iv & 0x7FF


def spin_packet(angular):
    ang = encode_signed_11(angular)
    b0 = 0x00
    b1 = ang & 0xFF
    b2 = (ang & 0xFF00) >> 5
    return bytes([0x02, b0, b1, b2])


def stop_packet():
    return bytes([0x02, 0x00, 0x00, 0x00])


async def find_robot(connect_name, scan_timeout):
    found = await BleakScanner.discover(timeout=scan_timeout, return_adv=True)
    matches = []
    for addr, (dev, adv) in found.items():
        name = dev.name or ""
        suuids = [s.lower() for s in (adv.service_uuids or [])]
        if connect_name.lower() in name.lower() and WW_SERVICE_UUID in suuids:
            matches.append((addr, dev.name or "(unnamed)", adv.rssi))
    if not matches:
        raise RuntimeError(f"No Wonder robot found matching '{connect_name}'")
    matches.sort(key=lambda x: x[2], reverse=True)
    return matches[0]


async def run():
    parser = argparse.ArgumentParser(
        description="Calibrate 180-degree spin return-to-heading using left/right time trim."
    )
    parser.add_argument("--connect-name", default="Stevie")
    parser.add_argument("--scan-timeout", type=float, default=8.0)
    parser.add_argument("--angular-cmd", type=float, default=420.0,
                        help="raw angular command magnitude (default: 420)")
    parser.add_argument("--left-seconds", type=float, default=1.2,
                        help="left spin duration per cycle for ~180deg (default: 1.2)")
    parser.add_argument("--right-trim", type=float, default=0.97,
                        help="multiplier on right-spin duration (default: 0.97)")
    parser.add_argument("--cycles", type=int, default=3,
                        help="number of left/right cycles (default: 3)")
    parser.add_argument("--pause-seconds", type=float, default=1.0,
                        help="pause after each leg (default: 1.0)")
    args = parser.parse_args()

    right_seconds = args.left_seconds * args.right_trim

    print("Spin calibration settings:")
    print(f"  angular_cmd    = {args.angular_cmd}")
    print(f"  left_secs      = {args.left_seconds:.3f}")
    print(f"  right_secs     = {right_seconds:.3f}  (trim={args.right_trim:.3f})")
    print(f"  cycles         = {args.cycles}")
    print(f"  pause_secs     = {args.pause_seconds:.3f}")

    addr, name, rssi = await find_robot(args.connect_name, args.scan_timeout)
    print(f"Connecting to '{name}' ({addr}), RSSI={rssi}")

    async with BleakClient(addr) as client:
        connected_attr = getattr(client, "is_connected")
        connected = await connected_attr() if callable(connected_attr) else bool(connected_attr)
        print("Connected:", connected)

        for cycle in range(1, args.cycles + 1):
            print(f"\nCYCLE {cycle}/{args.cycles}: spin left (~180)")
            await client.write_gatt_char(CHAR_UUID_CMD, spin_packet(args.angular_cmd))
            await asyncio.sleep(args.left_seconds)
            await client.write_gatt_char(CHAR_UUID_CMD, stop_packet())
            await asyncio.sleep(args.pause_seconds)

            print(f"CYCLE {cycle}/{args.cycles}: spin right (~180)")
            await client.write_gatt_char(CHAR_UUID_CMD, spin_packet(-args.angular_cmd))
            await asyncio.sleep(right_seconds)
            await client.write_gatt_char(CHAR_UUID_CMD, stop_packet())
            await asyncio.sleep(args.pause_seconds)

        await client.write_gatt_char(CHAR_UUID_CMD, stop_packet())
        print("\nSpin calibration run complete.")
        print("Tip: if final heading is left of start, increase --right-trim.")
        print("Tip: if final heading is right of start, decrease --right-trim.")


if __name__ == "__main__":
    asyncio.run(run())
