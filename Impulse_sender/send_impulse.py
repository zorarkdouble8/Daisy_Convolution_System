#!/usr/bin/env python3
"""Play a repeatable 32 kHz, single-sample impulse through ALSA/aplay."""

import argparse
import math
import struct
import subprocess
import sys

SAMPLE_RATE = 32_000
DEFAULT_AMPLITUDE = 0.5
TAIL_SAMPLES = 3_200  # 100 ms: keeps the WAV well formed without adding sound.


def amplitude_argument(value: str) -> float:
    """Parse a safe normalized floating-point amplitude."""
    try:
        amplitude = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("amplitude must be a number") from exc
    if not math.isfinite(amplitude) or not 0.0 < amplitude <= 1.0:
        raise argparse.ArgumentTypeError("amplitude must be finite and in (0, 1]")
    return amplitude


def build_impulse_wav(amplitude: float = DEFAULT_AMPLITUDE) -> bytes:
    """Return a mono IEEE-float32 WAV: one nonzero sample followed by silence."""
    if not isinstance(amplitude, (int, float)) or not math.isfinite(amplitude) or not 0.0 < amplitude <= 1.0:
        raise ValueError("amplitude must be finite and in (0, 1]")
    samples = struct.pack("<f", float(amplitude)) + (b"\0" * (TAIL_SAMPLES * 4))
    # WAVE_FORMAT_IEEE_FLOAT = 3, mono, 32-bit floats. This standard 44-byte
    # header is recognized by ALSA's aplay WAV reader.
    byte_rate = SAMPLE_RATE * 4
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36 + len(samples), b"WAVE", b"fmt ", 16,
        3, 1, SAMPLE_RATE, byte_rate, 4, 32, b"data", len(samples),
    )
    return header + samples


def play_impulse(amplitude: float, device: str | None = None) -> None:
    """Send the generated WAV to aplay and raise RuntimeError on failure."""
    command = ["aplay", "-q"]
    if device:
        command.extend(["-D", device])
    command.append("-")
    try:
        completed = subprocess.run(command, input=build_impulse_wav(amplitude),
                                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                   check=False)
    except FileNotFoundError as exc:
        raise RuntimeError("aplay is not installed or not available on PATH") from exc
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"aplay failed ({completed.returncode}): {detail or 'no diagnostic'}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", help="ALSA PCM device name, e.g. hw:1,0")
    parser.add_argument("--amplitude", type=amplitude_argument, default=DEFAULT_AMPLITUDE,
                        help="normalized positive output amplitude; default: 0.5")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    destination = args.device or "default ALSA output"
    print(f"Impulse_sender: 32 kHz mono, one sample at +{args.amplitude:g}; output: {destination}")
    print("Press Enter to play an impulse. Type q or quit then Enter to exit.")
    try:
        while True:
            try:
                command = input("> ").strip().lower()
            except EOFError:
                print()
                return 0
            if command in ("q", "quit"):
                return 0
            if command:
                print("Use Enter to trigger, or q to quit.")
                continue
            try:
                play_impulse(args.amplitude, args.device)
                print("Impulse sent.")
            except RuntimeError as exc:
                print(f"Could not send impulse: {exc}", file=sys.stderr)
    except KeyboardInterrupt:
        print("\nStopped.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
