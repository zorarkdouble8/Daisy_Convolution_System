#!/usr/bin/env python3
"""Stop-and-wait uploader for a DIRF asset and the temporary Daisy uploader app."""
import argparse
import pathlib
import struct
import sys
import time
import zlib

MAGIC = b"DIRU"
HELLO, BEGIN, DATA, COMMIT, STATUS, ACK, ERROR = 1, 2, 3, 4, 5, 0x8000, 0x8001
OK = 0
HEADER = struct.Struct("<4sIIII")
RX = bytearray()

def frame(command, sequence, payload=b""):
    if len(payload) > 1024:
        raise ValueError("frame payload exceeds 1,024 bytes")
    crc_data = struct.pack("<III", command, sequence, len(payload)) + payload
    return HEADER.pack(MAGIC, command, sequence, len(payload), zlib.crc32(crc_data) & 0xffffffff) + payload

def read_frame(port, deadline):
    while time.monotonic() < deadline:
        piece = port.read(256)
        if piece:
            RX.extend(piece)
            while len(RX) >= HEADER.size:
                if RX[:4] != MAGIC:
                    del RX[0]
                    continue
                _, command, sequence, length, crc = HEADER.unpack_from(RX)
                if length > 1024:
                    del RX[0]
                    continue
                total = HEADER.size + length
                if len(RX) < total:
                    break
                payload = bytes(RX[HEADER.size:total])
                del RX[:total]
                if zlib.crc32(struct.pack("<III", command, sequence, length) + payload) & 0xffffffff == crc:
                    return command, sequence, payload
    raise TimeoutError("no valid reply within two seconds")

def request(port, command, sequence, payload=b""):
    for _ in range(3):
        port.write(frame(command, sequence, payload))
        try:
            reply_command, reply_sequence, reply_payload = read_frame(port, time.monotonic() + 2.0)
            if reply_sequence == sequence and reply_command in (ACK, ERROR):
                status = struct.unpack("<I", reply_payload)[0] if len(reply_payload) == 4 else 1
                if reply_command == ERROR or status != OK:
                    raise RuntimeError(f"device rejected command {command}: status {status}")
                return
        except TimeoutError:
            continue
    raise TimeoutError(f"command {command} failed after three attempts")

def validate_asset(data):
    if len(data) < 256 or data[:4] != b"DIRF":
        raise ValueError("not a DIRF asset")
    version, header_size, fmt, rate, retained, part, fft, count, payload, payload_crc = struct.unpack_from("<10I", data, 4)
    norm, header_crc = struct.unpack_from("<fI", data, 44)
    header = bytearray(data[:256]); header[48:52] = b"\0" * 4
    if version != 1 or header_size != 256 or fmt != 1 or rate != 32000 or part != 256 or fft != 512:
        raise ValueError("asset dimensions are not the Daisy 32 kHz / 256 / 512 format")
    if count < 1 or count > 94 or count != (retained + 255) // 256 or payload != count * 512 * 4:
        raise ValueError("asset partition metadata is inconsistent")
    if len(data) != 256 + payload or zlib.crc32(data[256:]) & 0xffffffff != payload_crc or zlib.crc32(header) & 0xffffffff != header_crc:
        raise ValueError("asset CRC or length is invalid")
    return count, payload, norm

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("asset", type=pathlib.Path)
    parser.add_argument("--port", required=True, help="CDC serial port, e.g. /dev/ttyACM0")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--yes", action="store_true", help="skip destructive-write confirmation")
    args = parser.parse_args()
    data = args.asset.read_bytes()
    count, payload, norm = validate_asset(data)
    print(f"Asset: {len(data)} bytes, {count} partitions, normalization metadata {norm:.8g}")
    print("QSPI range to erase: 0x000000-0x02FFFF (192 KiB; single-slot update)")
    if not args.yes and input("Erase this range and upload? [y/N] ").strip().lower() not in ("y", "yes"):
        return 1
    try:
        import serial
    except ImportError as exc:
        raise SystemExit("PySerial is required: python3 -m pip install -r FFT_Impulse_Daisy/tools/requirements.txt") from exc
    with serial.Serial(args.port, args.baud, timeout=0.1) as port:
        request(port, HELLO, 0)
        request(port, BEGIN, 1, struct.pack("<II", len(data), zlib.crc32(data) & 0xffffffff))
        for sequence, offset in enumerate(range(0, len(data), 1024)):
            request(port, DATA, sequence, data[offset:offset + 1024])
        request(port, COMMIT, 2)
    print("Upload completed and QSPI asset verified by the board.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
