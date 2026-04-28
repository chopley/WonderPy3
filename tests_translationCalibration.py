import argparse
import asyncio

from bleak import BleakClient, BleakScanner

WW_SERVICE_UUID = "af237777-879d-6186-1f49-deca0e85d9c1"
CHAR_UUID_CMD = "af230002-879d-6186-1f49-deca0e85d9c1"


def encode_signed_11(value):
    iv = int(round(value))
    # Stevie firmware expects 11-bit two's complement for signed drive fields.
    iv = max(-1024, min(1023, iv))
    if iv < 0:
        iv = (1 << 11) + iv
    return iv & 0x7FF


def drive_packet(linear):
    lin = encode_signed_11(linear)
    b0 = lin & 0xFF
    b1 = 0x00
    b2 = (lin & 0x0F00) >> 8
    return bytes([0x02, b0, b1, b2])


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


async def stop(client):
    await client.write_gatt_char(CHAR_UUID_CMD, drive_packet(0))


async def run():
    parser = argparse.ArgumentParser(
        description="Calibrate translation by tuning backward trim against forward leg."
    )
    parser.add_argument("--connect-name", default="Stevie")
    parser.add_argument("--scan-timeout", type=float, default=8.0)
    parser.add_argument("--linear-cmd", type=float, default=320.0,
                        help="raw linear command magnitude (default: 320)")
    parser.add_argument("--forward-seconds", type=float, default=0.6,
                        help="forward leg duration per cycle (default: 0.6)")
    parser.add_argument("--backward-trim", type=float, default=0.6,
                        help="multiplier on backward duration (default: 0.6)")
    parser.add_argument("--cycles", type=int, default=3,
                        help="number of forward/back cycles (default: 3)")
    parser.add_argument("--pause-seconds", type=float, default=1.0,
                        help="pause after each leg (default: 1.0)")
    args = parser.parse_args()

    backward_seconds = args.forward_seconds * args.backward_trim

    print("Calibration settings:")
    print(f"  linear_cmd     = {args.linear_cmd}")
    print(f"  forward_secs   = {args.forward_seconds:.3f}")
    print(f"  backward_secs  = {backward_seconds:.3f}  (trim={args.backward_trim:.3f})")
    print(f"  cycles         = {args.cycles}")
    print(f"  pause_secs     = {args.pause_seconds:.3f}")

    addr, name, rssi = await find_robot(args.connect_name, args.scan_timeout)
    print(f"Connecting to '{name}' ({addr}), RSSI={rssi}")

    async with BleakClient(addr) as client:
        connected_attr = getattr(client, "is_connected")
        connected = await connected_attr() if callable(connected_attr) else bool(connected_attr)
        print("Connected:", connected)

        for cycle in range(1, args.cycles + 1):
            print(f"\nCYCLE {cycle}/{args.cycles}: forward")
            await client.write_gatt_char(CHAR_UUID_CMD, drive_packet(args.linear_cmd))
            await asyncio.sleep(args.forward_seconds)
            await stop(client)
            await asyncio.sleep(args.pause_seconds)

            print(f"CYCLE {cycle}/{args.cycles}: backward")
            await client.write_gatt_char(CHAR_UUID_CMD, drive_packet(-args.linear_cmd))
            await asyncio.sleep(backward_seconds)
            await stop(client)
            await asyncio.sleep(args.pause_seconds)

        await stop(client)
        print("\nCalibration run complete.")
        print("Tip: if robot ends forward of start, increase --backward-trim.")
        print("Tip: if robot ends behind start, decrease --backward-trim.")


if __name__ == "__main__":
    asyncio.run(run())
