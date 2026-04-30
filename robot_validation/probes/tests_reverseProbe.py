import argparse
import asyncio

from bleak import BleakClient, BleakScanner

WW_SERVICE_UUID = "af237777-879d-6186-1f49-deca0e85d9c1"
CHAR_UUID_CMD = "af230002-879d-6186-1f49-deca0e85d9c1"


def encode_signed_11_signmag(value):
    iv = int(round(value))
    iv = max(-2047, min(2047, iv))
    if iv < 0:
        return 0x800 | (abs(iv) & 0x7FF)
    return iv & 0x7FF


def encode_signed_11_twos(value):
    iv = int(round(value))
    iv = max(-1024, min(1023, iv))
    if iv < 0:
        iv = (1 << 11) + iv
    return iv & 0x7FF


def drive_packet(encoded_value):
    # straight drive packet for opcode 0x02
    b0 = encoded_value & 0xFF
    b1 = 0x00
    b2 = (encoded_value & 0x0F00) >> 8
    return bytes([0x02, b0, b1, b2])


def move_packet(distance_mm, ms, flag):
    # opcode 0x23 known format for straight motion
    dist = abs(int(distance_mm))
    dist_lo = dist & 0xFF
    dist_hi = (dist & 0x3F00) >> 8
    t = max(0, int(ms))
    t_lo = t & 0xFF
    t_hi = (t & 0xFF00) >> 8
    return bytes([0x23, dist_lo, 0x00, 0x00, t_hi, t_lo, dist_hi, 0x00, flag])


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


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--connect-name", default="Stevie")
    parser.add_argument("--scan-timeout", type=float, default=8.0)
    args = parser.parse_args()

    addr, name, rssi = await find_robot(args.connect_name, args.scan_timeout)
    print(f"Connecting to {name} ({addr}) RSSI={rssi}")

    probes = [
        ("forward baseline (drive sign-mag +600)", drive_packet(encode_signed_11_signmag(600)), 1.0),
        ("stop", drive_packet(encode_signed_11_signmag(0)), 1.0),
        ("reverse A (drive sign-mag -600)", drive_packet(encode_signed_11_signmag(-600)), 1.2),
        ("stop", drive_packet(encode_signed_11_signmag(0)), 1.0),
        ("reverse B (drive two's-comp -600)", drive_packet(encode_signed_11_twos(-600)), 1.2),
        ("stop", drive_packet(encode_signed_11_signmag(0)), 1.0),
        ("reverse C (move 0x23 flag81)", move_packet(300, 1000, 0x81), 1.2),
        ("stop", drive_packet(encode_signed_11_signmag(0)), 1.0),
        ("reverse D (move 0x23 flag80)", move_packet(300, 1000, 0x80), 1.2),
        ("stop", drive_packet(encode_signed_11_signmag(0)), 1.0),
    ]

    async with BleakClient(addr) as client:
        connected_attr = getattr(client, "is_connected")
        connected = await connected_attr() if callable(connected_attr) else bool(connected_attr)
        print("Connected:", connected)

        for label, pkt, wait_s in probes:
            print(f"\nPROBE: {label}")
            print("packet:", pkt.hex())
            await client.write_gatt_char(CHAR_UUID_CMD, pkt)
            await asyncio.sleep(wait_s)

    print("\nDone. Please report which reverse probe actually moved backward.")


if __name__ == "__main__":
    asyncio.run(main())
