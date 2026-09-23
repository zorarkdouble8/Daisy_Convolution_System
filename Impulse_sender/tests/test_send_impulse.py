import importlib.util
import pathlib
import struct
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("send_impulse", ROOT / "send_impulse.py")
impulse = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(impulse)


class ImpulseWavTests(unittest.TestCase):
    def test_wav_is_32khz_float_impulse_then_silence(self):
        wav = impulse.build_impulse_wav(0.5)
        riff, size, wave, fmt, fmt_size, encoding, channels, rate, byte_rate, align, bits, data, data_size = struct.unpack("<4sI4s4sIHHIIHH4sI", wav[:44])
        self.assertEqual((riff, wave, fmt, fmt_size, encoding, channels, rate, byte_rate, align, bits, data),
                         (b"RIFF", b"WAVE", b"fmt ", 16, 3, 1, 32000, 128000, 4, 32, b"data"))
        self.assertEqual(size, len(wav) - 8)
        self.assertEqual(data_size, len(wav) - 44)
        self.assertAlmostEqual(struct.unpack("<f", wav[44:48])[0], 0.5)
        self.assertEqual(wav[48:], b"\0" * (impulse.TAIL_SAMPLES * 4))

    def test_invalid_amplitudes_are_rejected(self):
        for value in ("0", "-0.1", "1.1", "nan", "inf", "nope"):
            with self.assertRaises(Exception):
                impulse.amplitude_argument(value)
        with self.assertRaises(ValueError):
            impulse.build_impulse_wav(float("nan"))

    def test_parse_arguments(self):
        parsed = impulse.parse_args(["--device", "hw:1,0", "--amplitude", "0.25"])
        self.assertEqual((parsed.device, parsed.amplitude), ("hw:1,0", 0.25))

    @mock.patch.object(impulse.subprocess, "run")
    def test_play_uses_aplay_and_reports_failure(self, run):
        run.return_value = mock.Mock(returncode=0, stderr=b"")
        impulse.play_impulse(0.5, "hw:1,0")
        self.assertEqual(run.call_args.args[0], ["aplay", "-q", "-D", "hw:1,0", "-"])
        run.return_value = mock.Mock(returncode=1, stderr=b"bad device")
        with self.assertRaisesRegex(RuntimeError, "bad device"):
            impulse.play_impulse(0.5)

    @mock.patch.object(impulse, "play_impulse")
    @mock.patch("builtins.input", side_effect=["", "quit"])
    def test_terminal_enter_triggers_once(self, _input, play):
        self.assertEqual(impulse.main([]), 0)
        play.assert_called_once_with(0.5, None)


if __name__ == "__main__":
    unittest.main()
