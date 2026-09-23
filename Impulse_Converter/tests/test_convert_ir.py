import math
import tempfile
import unittest
import zlib
from pathlib import Path

import numpy as np

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import convert_ir as ir


def packed_multiply(left, right):
    result = np.empty_like(left)
    result[..., 0] = left[..., 0] * right[..., 0]
    result[..., 1] = left[..., 1] * right[..., 1]
    real = left[..., 2::2] * right[..., 2::2] - left[..., 3::2] * right[..., 3::2]
    imag = left[..., 2::2] * right[..., 3::2] + left[..., 3::2] * right[..., 2::2]
    result[..., 2::2] = real
    result[..., 3::2] = imag
    return result


def partitioned_convolution(signal, impulse):
    spectra, partition_count = ir.partition_and_transform(impulse)
    history = np.zeros_like(spectra)
    overlap = np.zeros(ir.PARTITION_SIZE, dtype=np.float32)
    output = []
    blocks = math.ceil(len(signal) / ir.PARTITION_SIZE)
    for block in range(blocks + partition_count):
        time = np.zeros(ir.PARTITION_SIZE, dtype=np.float32)
        start = block * ir.PARTITION_SIZE
        if start < len(signal):
            time[:min(ir.PARTITION_SIZE, len(signal) - start)] = signal[start:start + ir.PARTITION_SIZE]
        padded = np.zeros(ir.FFT_SIZE, dtype=np.float32)
        padded[:ir.PARTITION_SIZE] = time
        current = ir.pack_rfft(np.fft.rfft(padded))[None, :][0]
        history[block % partition_count] = current
        accumulator = np.zeros(ir.FFT_SIZE, dtype=np.float32)
        for partition in range(partition_count):
            accumulator += packed_multiply(history[(block - partition) % partition_count], spectra[partition])
        rendered = np.fft.irfft(ir.unpack_rfft(accumulator), n=ir.FFT_SIZE).astype(np.float32)
        output.extend(rendered[:ir.PARTITION_SIZE] + overlap)
        overlap = rendered[ir.PARTITION_SIZE:]
    return np.asarray(output, dtype=np.float32)


class ConverterTests(unittest.TestCase):
    def test_pack_round_trip_and_special_bins(self):
        source = np.linspace(-0.4, 0.6, ir.FFT_SIZE, dtype=np.float32)
        spectrum = np.fft.rfft(source)
        packed = ir.pack_rfft(spectrum)
        self.assertAlmostEqual(float(packed[0]), float(spectrum[0].real), places=5)
        self.assertAlmostEqual(float(packed[1]), float(spectrum[-1].real), places=5)
        np.testing.assert_allclose(ir.unpack_rfft(packed), spectrum, atol=1e-6)

    def test_frequency_response_of_identity_impulse(self):
        frequency, magnitude_db, phase = ir.frequency_response(
            np.array([1.0], dtype=np.float32))
        self.assertEqual(len(frequency), ir.RESPONSE_FFT_SIZE // 2 + 1)
        np.testing.assert_allclose(magnitude_db, 0.0, atol=1e-6)
        np.testing.assert_allclose(phase, 0.0, atol=1e-6)

    def test_partitioned_convolution_matches_direct_at_boundaries(self):
        random = np.random.default_rng(2026)
        signal = random.uniform(-0.1, 0.1, 750).astype(np.float32)
        impulse = np.zeros(400, dtype=np.float32)
        impulse[0], impulse[255], impulse[256], impulse[257] = 0.1, -0.2, 0.3, -0.15
        impulse[399] = 0.05
        actual = partitioned_convolution(signal, impulse)
        expected = np.convolve(signal, impulse)
        np.testing.assert_allclose(actual[:len(expected)], expected, atol=1e-4)

    def test_identity_and_two_tap_fixtures(self):
        source = np.zeros(400, dtype=np.float32)
        source[0], source[20], source[300] = 0.4, -0.25, 0.1
        for impulse in (np.array([1.0], dtype=np.float32),
                        np.array([0.5, 0.0, 0.5], dtype=np.float32)):
            actual = partitioned_convolution(source, impulse)
            expected = np.convolve(source, impulse)
            np.testing.assert_allclose(actual[:len(expected)], expected, atol=1e-5)

    def test_prepare_auto_onset_fade_and_normalization(self):
        audio = np.zeros(1_000, dtype=np.float32)
        audio[100] = 0.5
        audio[101:400] = 0.1
        processed = ir.prepare_ir(audio, 0.01, 0.002, None)
        self.assertEqual(processed.start_sample, 68)
        self.assertEqual(processed.fade_samples, 64)
        self.assertAlmostEqual(float(np.sum(np.abs(processed.samples))), 1.0, places=6)
        self.assertEqual(float(processed.samples[-1]), 0.0)

    def test_short_input_padding_and_invalid_inputs(self):
        processed = ir.prepare_ir(np.array([1.0, 0.5], dtype=np.float32), 0.01, 0.0, 0.0)
        self.assertEqual(processed.padded_samples, 318)
        manual = ir.prepare_ir(np.ones(300, dtype=np.float32), 0.005, 0.0, 0.003125)
        self.assertEqual(manual.start_sample, 100)
        with self.assertRaises(ir.ConversionError):
            ir.prepare_ir(np.zeros(10, dtype=np.float32), 0.01, 0.0, None)
        with self.assertRaises(ir.ConversionError):
            ir.prepare_ir(np.array([np.nan], dtype=np.float32), 0.01, 0.0, None)
        with self.assertRaises(ir.ConversionError):
            ir.prepare_ir(np.ones(10, dtype=np.float32), 0.01, 1 / ir.SAMPLE_RATE, None)
        with self.assertRaises(ir.ConversionError):
            ir.prepare_ir(np.ones(10, dtype=np.float32), 0.01, 0.0, 10.0)

    def test_asset_header_lengths_and_crcs(self):
        samples = np.ones(24_000, dtype=np.float32) / 24_000
        spectra, count = ir.partition_and_transform(samples)
        payload = spectra.astype("<f4", copy=False).tobytes()
        metadata = ir.AssetMetadata(ir.SAMPLE_RATE, 24_000, ir.PARTITION_SIZE,
                                    ir.FFT_SIZE, count, len(payload),
                                    zlib.crc32(payload) & 0xFFFFFFFF, 1 / 24_000, 0)
        asset = ir.build_header(metadata) + payload
        decoded, decoded_spectra = ir.parse_asset(asset)
        self.assertEqual(count, 94)
        self.assertEqual(len(payload), 192_512)
        self.assertEqual(len(asset), 192_768)
        self.assertEqual(decoded.payload_bytes, len(payload))
        np.testing.assert_array_equal(decoded_spectra, spectra)
        final_partition = np.fft.irfft(ir.unpack_rfft(decoded_spectra[-1]), n=ir.FFT_SIZE)
        np.testing.assert_allclose(final_partition[:192], samples[-192:], atol=1e-6)
        np.testing.assert_allclose(final_partition[192:ir.PARTITION_SIZE], 0.0, atol=1e-6)
        corrupt = bytearray(asset)
        corrupt[-1] ^= 1
        with self.assertRaises(ir.ConversionError):
            ir.parse_asset(bytes(corrupt))

    def test_overwrite_protection_runs_before_decode(self):
        with tempfile.TemporaryDirectory() as temporary:
            prefix = Path(temporary) / "existing"
            prefix.with_suffix(".bin").write_bytes(b"existing")
            with self.assertRaisesRegex(ir.ConversionError, "Refusing to overwrite"):
                ir.convert_file(Path("missing.mp3"), prefix)


if __name__ == "__main__":
    unittest.main()
