#!/usr/bin/env python3
"""Convert an audio impulse response into a Daisy packed-RFFT asset."""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

try:
    import numpy as np
except ImportError as error:  # pragma: no cover - exercised by CLI users
    raise SystemExit("NumPy is required. Install it with: python3 -m pip install -r "
                     "Impulse_Converter/requirements.txt") from error


SAMPLE_RATE = 32_000
PARTITION_SIZE = 256
FFT_SIZE = 512
ONSET_RELATIVE_THRESHOLD = 0.001  # -60 dB relative to the peak
ONSET_PREROLL_SAMPLES = 32
RESPONSE_FFT_SIZE = 32_768
MAGIC = b"DIRF"
VERSION = 1
FORMAT_CMSIS_PACKED_F32 = 1
HEADER_SIZE = 256
HEADER_FORMAT = "<4s10IfI"
HEADER_FIELDS_SIZE = struct.calcsize(HEADER_FORMAT)
HEADER_CRC_OFFSET = 48


class ConversionError(ValueError):
    """Raised when an input or output cannot form a valid IR asset."""


@dataclass(frozen=True)
class SourceInfo:
    codec: str
    sample_rate: str
    channels: str
    duration_seconds: str


@dataclass(frozen=True)
class ProcessedIR:
    samples: np.ndarray
    start_sample: int
    start_mode: str
    requested_samples: int
    source_samples_available: int
    padded_samples: int
    fade_samples: int
    normalization_multiplier: float


@dataclass(frozen=True)
class AssetMetadata:
    sample_rate: int
    retained_samples: int
    partition_size: int
    fft_size: int
    partition_count: int
    payload_bytes: int
    payload_crc32: int
    normalization_multiplier: float
    header_crc32: int


def require_command(command: str) -> None:
    if shutil.which(command) is None:
        raise ConversionError(f"Required command '{command}' was not found on PATH.")


def rounded_samples(seconds: float, label: str) -> int:
    if not math.isfinite(seconds) or seconds < 0:
        raise ConversionError(f"{label} must be a finite nonnegative value.")
    return math.floor(seconds * SAMPLE_RATE + 0.5)


def probe_audio(source: Path) -> SourceInfo:
    require_command("ffprobe")
    command = [
        "ffprobe", "-v", "error", "-select_streams", "a:0",
        "-show_entries", "stream=codec_name,sample_rate,channels:format=duration",
        "-of", "json", str(source),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise ConversionError(f"ffprobe failed for '{source}': {result.stderr.strip()}")
    try:
        data = json.loads(result.stdout)
        stream = data["streams"][0]
    except (KeyError, IndexError, json.JSONDecodeError) as error:
        raise ConversionError(f"No readable audio stream found in '{source}'.") from error
    return SourceInfo(
        codec=str(stream.get("codec_name", "unknown")),
        sample_rate=str(stream.get("sample_rate", "unknown")),
        channels=str(stream.get("channels", "unknown")),
        duration_seconds=str(data.get("format", {}).get("duration", "unknown")),
    )


def decode_audio(source: Path) -> np.ndarray:
    """Decode first stream as 32 kHz mono float32 PCM using ffmpeg."""
    if not source.is_file():
        raise ConversionError(f"Input audio file does not exist: {source}")
    require_command("ffmpeg")
    command = [
        "ffmpeg", "-v", "error", "-nostdin", "-i", str(source), "-map", "0:a:0",
        "-ac", "1", "-ar", str(SAMPLE_RATE), "-f", "f32le", "pipe:1",
    ]
    result = subprocess.run(command, capture_output=True, check=False)
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace").strip()
        raise ConversionError(f"ffmpeg failed for '{source}': {stderr}")
    if not result.stdout or len(result.stdout) % np.dtype("<f4").itemsize:
        raise ConversionError("ffmpeg produced empty or malformed PCM output.")
    samples = np.frombuffer(result.stdout, dtype="<f4").copy()
    if not np.isfinite(samples).all():
        raise ConversionError("Decoded audio contains nonfinite samples.")
    peak = float(np.max(np.abs(samples)))
    if peak == 0.0:
        raise ConversionError("Decoded audio is silent.")
    return samples


def prepare_ir(audio: np.ndarray, duration_seconds: float, fade_seconds: float,
               start_time: float | None) -> ProcessedIR:
    """Trim, pad, fade, and conservatively normalize a real PCM IR."""
    audio = np.asarray(audio, dtype=np.float32)
    if audio.ndim != 1 or audio.size == 0 or not np.isfinite(audio).all():
        raise ConversionError("Audio must be a nonempty finite mono sample array.")
    requested_samples = rounded_samples(duration_seconds, "duration")
    fade_samples = rounded_samples(fade_seconds, "fade duration")
    if requested_samples <= 0:
        raise ConversionError("duration must retain at least one sample.")
    if fade_samples > requested_samples:
        raise ConversionError("fade duration cannot exceed retained duration.")
    if fade_samples == 1:
        raise ConversionError("fade duration must produce zero or at least two samples.")

    if start_time is None:
        peak = float(np.max(np.abs(audio)))
        if peak == 0.0:
            raise ConversionError("Audio is silent.")
        onset = int(np.flatnonzero(np.abs(audio) >= peak * ONSET_RELATIVE_THRESHOLD)[0])
        start_sample = max(0, onset - ONSET_PREROLL_SAMPLES)
        start_mode = "automatic -60 dB relative onset with 32-sample preroll"
    else:
        start_sample = rounded_samples(start_time, "start time")
        if start_sample >= audio.size:
            raise ConversionError("start time lies outside decoded audio.")
        start_mode = "manual"

    available = min(requested_samples, audio.size - start_sample)
    retained = np.zeros(requested_samples, dtype=np.float64)
    retained[:available] = audio[start_sample:start_sample + available]
    if fade_samples:
        retained[-fade_samples:] *= np.linspace(1.0, 0.0, fade_samples, dtype=np.float64)

    absolute_sum = float(np.sum(np.abs(retained), dtype=np.float64))
    if not math.isfinite(absolute_sum) or absolute_sum == 0.0:
        raise ConversionError("The trimmed and faded impulse response is silent.")
    normalization_multiplier = 1.0 / absolute_sum
    normalized = (retained * normalization_multiplier).astype(np.float32)
    if not np.isfinite(normalized).all():
        raise ConversionError("Normalization produced nonfinite samples.")

    return ProcessedIR(
        samples=normalized,
        start_sample=start_sample,
        start_mode=start_mode,
        requested_samples=requested_samples,
        source_samples_available=available,
        padded_samples=requested_samples - available,
        fade_samples=fade_samples,
        normalization_multiplier=normalization_multiplier,
    )


def pack_rfft(spectrum: np.ndarray) -> np.ndarray:
    """Pack NumPy rfft bins into CMSIS's [DC, Nyquist, Re/Im...] layout."""
    spectrum = np.asarray(spectrum)
    if spectrum.shape[-1] != FFT_SIZE // 2 + 1:
        raise ConversionError("Unexpected RFFT bin count.")
    packed = np.empty(spectrum.shape[:-1] + (FFT_SIZE,), dtype="<f4")
    packed[..., 0] = spectrum[..., 0].real
    packed[..., 1] = spectrum[..., -1].real
    packed[..., 2::2] = spectrum[..., 1:-1].real
    packed[..., 3::2] = spectrum[..., 1:-1].imag
    return packed


def unpack_rfft(packed: np.ndarray) -> np.ndarray:
    """Reconstruct NumPy rfft bins from CMSIS packed floats."""
    packed = np.asarray(packed, dtype=np.float32)
    if packed.shape[-1] != FFT_SIZE:
        raise ConversionError("Unexpected packed RFFT length.")
    spectrum = np.empty(packed.shape[:-1] + (FFT_SIZE // 2 + 1,), dtype=np.complex64)
    spectrum[..., 0] = packed[..., 0]
    spectrum[..., -1] = packed[..., 1]
    spectrum[..., 1:-1] = packed[..., 2::2] + 1j * packed[..., 3::2]
    return spectrum


def partition_and_transform(samples: np.ndarray) -> tuple[np.ndarray, int]:
    """Create zero-padded partitions and return their packed RFFT spectra."""
    samples = np.asarray(samples, dtype=np.float32)
    count = math.ceil(samples.size / PARTITION_SIZE)
    if count <= 0:
        raise ConversionError("No samples available to partition.")
    padded = np.zeros(count * PARTITION_SIZE, dtype=np.float32)
    padded[:samples.size] = samples
    partitions = padded.reshape(count, PARTITION_SIZE)
    transform_input = np.zeros((count, FFT_SIZE), dtype=np.float32)
    transform_input[:, :PARTITION_SIZE] = partitions
    return pack_rfft(np.fft.rfft(transform_input, n=FFT_SIZE, axis=1)), count


def build_header(metadata: AssetMetadata) -> bytes:
    header = bytearray(HEADER_SIZE)
    struct.pack_into(
        HEADER_FORMAT, header, 0, MAGIC, VERSION, HEADER_SIZE,
        FORMAT_CMSIS_PACKED_F32, metadata.sample_rate, metadata.retained_samples,
        metadata.partition_size, metadata.fft_size, metadata.partition_count,
        metadata.payload_bytes, metadata.payload_crc32,
        metadata.normalization_multiplier, 0,
    )
    crc = zlib.crc32(header) & 0xFFFFFFFF
    struct.pack_into("<I", header, HEADER_CRC_OFFSET, crc)
    return bytes(header)


def parse_asset(asset: bytes) -> tuple[AssetMetadata, np.ndarray]:
    """Validate and decode an asset for tests and future uploader tooling."""
    if len(asset) < HEADER_SIZE:
        raise ConversionError("Asset is smaller than its header.")
    header = asset[:HEADER_SIZE]
    mutable = bytearray(header)
    stored_header_crc = struct.unpack_from("<I", mutable, HEADER_CRC_OFFSET)[0]
    struct.pack_into("<I", mutable, HEADER_CRC_OFFSET, 0)
    if zlib.crc32(mutable) & 0xFFFFFFFF != stored_header_crc:
        raise ConversionError("Header CRC32 does not match.")
    if any(header[52:]):
        raise ConversionError("Reserved header bytes must be zero.")
    fields = struct.unpack_from(HEADER_FORMAT, header)
    (magic, version, header_size, format_id, sample_rate, retained_samples,
     partition_size, fft_size, partition_count, payload_bytes, payload_crc,
     normalization_multiplier, _) = fields
    if magic != MAGIC or version != VERSION or header_size != HEADER_SIZE:
        raise ConversionError("Unsupported asset magic, version, or header size.")
    if format_id != FORMAT_CMSIS_PACKED_F32:
        raise ConversionError("Unsupported spectrum format.")
    if (sample_rate != SAMPLE_RATE or partition_size != PARTITION_SIZE
            or fft_size != FFT_SIZE or partition_count <= 0):
        raise ConversionError("Asset dimensions are not supported by this converter.")
    if payload_bytes != partition_count * FFT_SIZE * 4 or len(asset) != HEADER_SIZE + payload_bytes:
        raise ConversionError("Asset payload length does not match its header.")
    payload = asset[HEADER_SIZE:]
    if zlib.crc32(payload) & 0xFFFFFFFF != payload_crc:
        raise ConversionError("Payload CRC32 does not match.")
    if not math.isfinite(normalization_multiplier) or normalization_multiplier <= 0:
        raise ConversionError("Asset normalization multiplier is invalid.")
    spectra = np.frombuffer(payload, dtype="<f4").copy().reshape(partition_count, FFT_SIZE)
    if not np.isfinite(spectra).all():
        raise ConversionError("Asset spectra contain nonfinite values.")
    return AssetMetadata(sample_rate, retained_samples, partition_size, fft_size,
                         partition_count, payload_bytes, payload_crc,
                         normalization_multiplier, stored_header_crc), spectra


def write_preview_wav(samples: np.ndarray, destination: Path) -> None:
    require_command("ffmpeg")
    raw_path = destination.with_suffix(".f32le")
    raw_path.write_bytes(np.asarray(samples, dtype="<f4").tobytes())
    command = [
        "ffmpeg", "-v", "error", "-nostdin", "-f", "f32le", "-ar", str(SAMPLE_RATE),
        "-ac", "1", "-i", str(raw_path), "-c:a", "pcm_f32le", "-y", str(destination),
    ]
    result = subprocess.run(command, capture_output=True, check=False)
    raw_path.unlink(missing_ok=True)
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace").strip()
        raise ConversionError(f"ffmpeg could not create preview WAV: {stderr}")


def frequency_response(samples: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return frequency, peak-relative magnitude, and unwrapped phase arrays."""
    samples = np.asarray(samples, dtype=np.float32)
    spectrum = np.fft.rfft(samples, n=RESPONSE_FFT_SIZE)
    frequency = np.fft.rfftfreq(RESPONSE_FFT_SIZE, d=1.0 / SAMPLE_RATE)
    magnitude = np.abs(spectrum)
    peak = float(np.max(magnitude))
    if not math.isfinite(peak) or peak == 0.0:
        raise ConversionError("Cannot graph a silent frequency response.")
    magnitude_db = 20.0 * np.log10(np.maximum(magnitude / peak, 1e-6))
    magnitude_db = np.maximum(magnitude_db, -120.0)
    phase = np.unwrap(np.angle(spectrum))
    phase[magnitude_db <= -80.0] = np.nan
    return frequency, magnitude_db, phase


def gnuplot_quote(path: Path) -> str:
    return str(path).replace("\\", "\\\\").replace("'", "\\'")


def write_frequency_response_graph(samples: np.ndarray, destination: Path) -> None:
    """Create a PNG with the processed IR's magnitude and phase response."""
    require_command("gnuplot")
    frequency, magnitude_db, phase = frequency_response(samples)
    data_path = destination.with_suffix(".response.tsv")
    script_path = destination.with_suffix(".gnuplot")
    np.savetxt(data_path, np.column_stack((frequency, magnitude_db, phase)),
               fmt="%.10g", delimiter="\t")
    script = f"""set terminal pngcairo size 1600,1000 enhanced font 'Sans,12'
set output '{gnuplot_quote(destination)}'
set datafile separator '\\t'
set grid xtics ytics
set xrange [0:{SAMPLE_RATE / 2}]
set key off
set multiplot layout 2,1 title 'Impulse-response frequency response (32 kHz)'
set title 'Magnitude relative to peak'
set xlabel 'Frequency (Hz)'
set ylabel 'Magnitude (dB)'
set yrange [-120:5]
plot '{gnuplot_quote(data_path)}' using 1:2 with lines lw 1.5 lc rgb '#2266aa'
set title 'Unwrapped phase'
set xlabel 'Frequency (Hz)'
set ylabel 'Phase (radians)'
set yrange [*:*]
plot '{gnuplot_quote(data_path)}' using 1:3 with lines lw 1.5 lc rgb '#aa5522'
unset multiplot
"""
    script_path.write_text(script, encoding="utf-8")
    result = subprocess.run(["gnuplot", str(script_path)], capture_output=True, check=False)
    data_path.unlink(missing_ok=True)
    script_path.unlink(missing_ok=True)
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace").strip()
        raise ConversionError(f"gnuplot could not create frequency-response graph: {stderr}")


def build_report(source: Path, source_info: SourceInfo, processed: ProcessedIR,
                 metadata: AssetMetadata) -> str:
    return f"""# Impulse-response conversion report

## Source

- File: `{source}`
- Codec: {source_info.codec}
- Original sample rate: {source_info.sample_rate} Hz
- Channels: {source_info.channels}
- Duration: {source_info.duration_seconds} s

## Processing

- Output: mono float32 PCM at {SAMPLE_RATE} Hz
- Start sample: {processed.start_sample} ({processed.start_sample / SAMPLE_RATE:.6f} s)
- Start selection: {processed.start_mode}
- Retained samples: {processed.requested_samples} ({processed.requested_samples / SAMPLE_RATE:.3f} s)
- Source samples used: {processed.source_samples_available}
- Zero padding after source: {processed.padded_samples} samples
- Fade: {processed.fade_samples} samples ({processed.fade_samples / SAMPLE_RATE:.3f} s), ending at zero
- Absolute-sum normalization multiplier: {processed.normalization_multiplier:.12g}

The multiplier makes `sum(abs(h))` equal to approximately 1, giving a
conservative peak bound for future convolution. It can make the preview sound
quiet; future firmware should apply a separate, intentional wet gain.

## Frequency-domain asset

- Partition size: {metadata.partition_size} samples
- FFT size: {metadata.fft_size} samples
- Partition count: {metadata.partition_count}
- Packed spectrum format: CMSIS RFFT `[DC, Nyquist, Re(1), Im(1), ...]`
- Payload: {metadata.payload_bytes} bytes
- Total asset: {HEADER_SIZE + metadata.payload_bytes} bytes
- Payload CRC32: `0x{metadata.payload_crc32:08X}`
- Header CRC32: `0x{metadata.header_crc32:08X}`

The accompanying frequency-response PNG shows magnitude relative to the peak
(clamped at −120 dB) and unwrapped phase. Phase values below −80 dB magnitude
are omitted because phase is not useful where the response is near zero.

This asset is validated on the host. Daisy CMSIS equivalence and hardware
playback remain future firmware checks.
"""


def convert_file(source: Path, output_prefix: Path, duration: float = 0.75,
                 fade_duration: float = 0.020, start_time: float | None = None,
                 overwrite: bool = False) -> tuple[Path, Path, Path, Path]:
    """Run a complete conversion and atomically publish three output files."""
    binary_path = output_prefix.with_suffix(".bin")
    preview_path = output_prefix.parent / f"{output_prefix.name}_preview.wav"
    report_path = output_prefix.parent / f"{output_prefix.name}_report.md"
    graph_path = output_prefix.parent / f"{output_prefix.name}_frequency_response.png"
    destinations = (binary_path, preview_path, report_path, graph_path)
    if not overwrite:
        existing = [str(path) for path in destinations if path.exists()]
        if existing:
            raise ConversionError("Refusing to overwrite existing output(s): " + ", ".join(existing))

    source_info = probe_audio(source)
    audio = decode_audio(source)
    processed = prepare_ir(audio, duration, fade_duration, start_time)
    spectra, partition_count = partition_and_transform(processed.samples)
    payload = np.ascontiguousarray(spectra, dtype="<f4").tobytes()
    metadata = AssetMetadata(
        SAMPLE_RATE, processed.requested_samples, PARTITION_SIZE, FFT_SIZE,
        partition_count, len(payload), zlib.crc32(payload) & 0xFFFFFFFF,
        processed.normalization_multiplier, 0,
    )
    header = build_header(metadata)
    metadata, _ = parse_asset(header + payload)

    output_prefix.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(dir=output_prefix.parent, prefix=".ir-convert-") as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        temp_binary = temp_dir / binary_path.name
        temp_preview = temp_dir / preview_path.name
        temp_report = temp_dir / report_path.name
        temp_graph = temp_dir / graph_path.name
        temp_binary.write_bytes(header + payload)
        write_preview_wav(processed.samples, temp_preview)
        write_frequency_response_graph(processed.samples, temp_graph)
        temp_report.write_text(build_report(source, source_info, processed, metadata), encoding="utf-8")
        for temporary, destination in zip((temp_binary, temp_preview, temp_report, temp_graph), destinations):
            os.replace(temporary, destination)
    return destinations


def parse_arguments(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Source MP3 or WAV impulse response")
    parser.add_argument("--output-prefix", type=Path, required=True,
                        help="Output path without extension")
    parser.add_argument("--duration", type=float, default=0.75,
                        help="Retained duration in seconds (default: 0.75)")
    parser.add_argument("--fade-duration", type=float, default=0.020,
                        help="Fade length in seconds (default: 0.020)")
    parser.add_argument("--start-time", type=float,
                        help="Manual start time in decoded 32 kHz audio")
    parser.add_argument("--overwrite", action="store_true", help="Replace existing outputs")
    return parser.parse_args(arguments)


def main(arguments: Sequence[str] | None = None) -> int:
    args = parse_arguments(arguments)
    try:
        binary, preview, report, graph = convert_file(
            args.input, args.output_prefix, args.duration, args.fade_duration,
            args.start_time, args.overwrite,
        )
    except ConversionError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(f"Created {binary}")
    print(f"Created {preview}")
    print(f"Created {report}")
    print(f"Created {graph}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
