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


def drive_packet(linear, angular):
    lin = encode_signed_11(linear)
    ang = encode_signed_11(angular)
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


async def find_robot(connect_name, scan_timeout):
    found = await BleakScanner.discover(timeout=scan_timeout, return_adv=True)
    matches = []
    skipped = []
    for addr, (dev, adv) in found.items():
        name = dev.name or "(unnamed)"
        suuids = [s.lower() for s in (adv.service_uuids or [])]
        if WW_SERVICE_UUID not in suuids:
            continue
        if connect_name.lower() in name.lower():
            matches.append((addr, name, adv.rssi))
        else:
            skipped.append(name)

    if skipped:
        print("found but skipping:", ", ".join("'%s'" % n for n in skipped) + ".")
    if not matches:
        raise RuntimeError("No matching Wonder robot found for name '%s'" % connect_name)
    matches.sort(key=lambda x: x[2], reverse=True)
    return matches[0]


async def run():
    parser = argparse.ArgumentParser()
    parser.add_argument("--connect-name", default="Stevie")
    parser.add_argument("--scan-timeout", type=float, default=8.0)
    parser.add_argument("--return-trim", type=float, default=1.05,
                        help="scale factor for 'return to start' legs (default 1.05)")
    parser.add_argument("--heading-trim", type=float, default=0.97,
                        help="scale factor for final heading correction turn (default 0.97)")
    args = parser.parse_args()

    addr, name, rssi = await find_robot(args.connect_name, args.scan_timeout)
    print("Connecting to '%s' (%s), RSSI=%s" % (name, addr, rssi))

    # Requested choreography:
    # 1) move forward, 2) move backward, 3) move back to start,
    # 4) turn left (180),
    # 5) move forward, 6) move backward, 7) move back to start,
    # 8) turn to initial heading (180).
    rt = args.return_trim
    ht = args.heading_trim
    sequence = [
        ("forward", 320, 0, 0.5),
        ("backward", -320, 0, 1.0),
        ("return to start", 320, 0, 0.5 * rt),
        ("turn left 180", 0, 420, 1.2),
        ("forward (left-facing)", 320, 0, 0.5),
        ("backward (left-facing)", -320, 0, 1.0),
        ("return to start (left-facing)", 320, 0, 0.5 * rt),
        ("turn right 180 to initial heading", 0, -420, 1.2 * ht),
    ]

    async with BleakClient(addr) as client:
        print("Connected:", bool(getattr(client, "is_connected", True)))
        for idx, (label, linear, angular, seconds) in enumerate(sequence, start=1):
            print("STEP %d/%d: %s for %.1fs" % (idx, len(sequence), label, seconds))
            await client.write_gatt_char(CHAR_UUID_CMD, drive_packet(linear, angular))
            await asyncio.sleep(seconds)
            await client.write_gatt_char(CHAR_UUID_CMD, drive_packet(0, 0))
            await asyncio.sleep(1.0)

        await client.write_gatt_char(CHAR_UUID_CMD, drive_packet(0, 0))
        print("SEQUENCE COMPLETE: robot stopped.")


if __name__ == "__main__":
    asyncio.run(run())
