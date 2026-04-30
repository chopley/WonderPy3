import argparse
import asyncio

from bleak import BleakClient, BleakScanner

WW_SERVICE_UUID = "af237777-879d-6186-1f49-deca0e85d9c1"
CHAR_UUID_CMD = "af230002-879d-6186-1f49-deca0e85d9c1"


def build_drive(linear, angular):
    """
    Build opcode 0x02 payload from reverse-engineered Dash drive command.
    linear, angular: signed 11-bit-ish values.
    """
    def enc(v):
        iv = int(round(v))
        iv = max(-2047, min(2047, iv))
        if iv < 0:
            return 0x800 | (abs(iv) & 0x7FF)
        return iv & 0x7FF

    lin = enc(linear)
    ang = enc(angular)

    # straight / spin dominant packing
    if angular == 0:
        b0 = lin & 0xFF
        b1 = 0x00
        b2 = (lin & 0x0F00) >> 8
    elif linear == 0:
        b0 = 0x00
        b1 = ang & 0xFF
        b2 = (ang & 0xFF00) >> 5
    else:
        b0 = lin & 0xFF
        b1 = ang & 0xFF
        b2 = ((lin & 0x0F00) >> 8) | ((ang & 0xFF00) >> 5)

    return bytes([0x02, b0, b1, b2])


def build_move(distance_mm, centiradians, ms, flag):
    """
    Build opcode 0x23 payload from known move packet structure.
    """
    dist = abs(int(distance_mm))
    turn = int(centiradians)
    t = max(0, int(ms))

    dist_lo = dist & 0xFF
    dist_hi = (dist & 0x3F00) >> 8
    turn_lo = turn & 0xFF
    turn_hi = (turn & 0x0300) >> 2
    t_lo = t & 0xFF
    t_hi = (t & 0xFF00) >> 8
    seventh = 0xC0 if turn < 0 else 0x00
    sixth = dist_hi | turn_hi

    return bytes([0x23, dist_lo, 0x00, turn_lo, t_hi, t_lo, sixth, seventh, flag])


async def find_device_by_name(name, timeout):
    found = await BleakScanner.discover(timeout=timeout, return_adv=True)
    matches = []
    for addr, (dev, adv) in found.items():
        if not dev.name:
            continue
        if name.lower() in dev.name.lower():
            su = [s.lower() for s in (adv.service_uuids or [])]
            if WW_SERVICE_UUID in su:
                matches.append((addr, dev.name, adv.rssi))
    if not matches:
        raise RuntimeError(f"No Wonder device found matching '{name}'")
    matches.sort(key=lambda x: x[2], reverse=True)
    return matches[0]


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--connect-name", default="Stevie")
    parser.add_argument("--scan-timeout", type=float, default=8.0)
    args = parser.parse_args()

    addr, name, rssi = await find_device_by_name(args.connect_name, args.scan_timeout)
    print(f"Connecting to {name} ({addr}) RSSI={rssi}")

    probes = [
        ("drive forward", build_drive(600, 0), 1.0),
        ("drive stop", build_drive(0, 0), 0.4),
        ("drive backward", build_drive(-600, 0), 1.0),
        ("drive stop", build_drive(0, 0), 0.4),
        ("drive left spin", build_drive(0, 700), 1.0),
        ("drive stop", build_drive(0, 0), 0.4),
        ("drive right spin", build_drive(0, -700), 1.0),
        ("drive stop", build_drive(0, 0), 0.6),
        ("move forward flag80", build_move(300, 0, 1000, 0x80), 1.2),
        ("move backward flag81", build_move(300, 0, 1000, 0x81), 1.2),
        ("move left turn", build_move(0, 180, 1000, 0x80), 1.2),
        ("move right turn", build_move(0, -180, 1000, 0x80), 1.2),
        ("final stop", build_drive(0, 0), 0.2),
    ]

    async with BleakClient(addr) as client:
        connected_attr = getattr(client, "is_connected")
        connected = await connected_attr() if callable(connected_attr) else bool(connected_attr)
        print(f"Connected: {connected}")
        for label, packet, wait_s in probes:
            print(f"\nPROBE: {label}")
            print("packet:", packet.hex())
            await client.write_gatt_char(CHAR_UUID_CMD, packet)
            await asyncio.sleep(wait_s)

    print("Probe complete.")


if __name__ == "__main__":
    asyncio.run(main())
