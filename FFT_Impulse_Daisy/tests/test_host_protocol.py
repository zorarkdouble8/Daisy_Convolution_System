import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("upload_ir", ROOT / "tools" / "upload_ir.py")
upload = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(upload)

class ProtocolTests(unittest.TestCase):
    def test_frame_round_trip_and_crc(self):
        raw = upload.frame(upload.DATA, 7, b"abc")
        self.assertEqual(raw[:4], b"DIRU")
        _, command, sequence, length, _ = upload.HEADER.unpack_from(raw)
        self.assertEqual((command, sequence, length), (upload.DATA, 7, 3))
        self.assertNotEqual(raw[-1], 0)

    def test_fragmented_reply(self):
        class FakePort:
            def __init__(self, chunks): self.chunks = chunks
            def read(self, _): return self.chunks.pop(0) if self.chunks else b""
        raw = upload.frame(upload.ACK, 3, (0).to_bytes(4, "little"))
        upload.RX.clear()
        reply = upload.read_frame(FakePort([raw[:3], raw[3:17], raw[17:]]), __import__("time").monotonic() + 0.1)
        self.assertEqual(reply, (upload.ACK, 3, b"\0\0\0\0"))

    def test_actual_church_asset(self):
        data = (ROOT.parent / "Impulse_Converter" / "output" / "church_ir.bin").read_bytes()
        count, payload, _ = upload.validate_asset(data)
        self.assertEqual((count, payload, len(data)), (94, 192512, 192768))

    def test_corrupt_asset_rejected(self):
        data = bytearray((ROOT.parent / "Impulse_Converter" / "output" / "church_ir.bin").read_bytes())
        data[-1] ^= 1
        with self.assertRaises(ValueError):
            upload.validate_asset(data)

if __name__ == "__main__":
    unittest.main()
