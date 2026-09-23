# Daisy impulse-response converter

This tool converts an MP3 or WAV impulse response into a 32 kHz mono preview
and a partitioned, packed-RFFT binary asset for a future Daisy Seed reverb.

## Requirements

- Python 3.10 or later
- [NumPy](requirements.txt)
- `ffmpeg` and `ffprobe` available on `PATH`
- `gnuplot` available on `PATH` to create the frequency-response graph

Install the Python requirement:

```bash
python3 -m pip install -r Impulse_Converter/requirements.txt
```

## Convert the included church impulse response

From the workspace root:

```bash
python3 Impulse_Converter/convert_ir.py \
  "Impulse Responses/freesound_community-impulse-response-church-105010.mp3" \
  --output-prefix Impulse_Converter/output/church_ir
```

Use `--overwrite` to replace existing output. `--duration`, `--fade-duration`,
and `--start-time` alter the retained IR. The converter resamples to 32 kHz
before automatic onset detection, retains 0.75 seconds by default, applies a
20 ms fade, and scales the IR so its absolute coefficient sum is one.

## Outputs

`<prefix>.bin` contains a 256-byte `DIRF` v1 header followed by spectra.
`<prefix>_preview.wav` is the exact time-domain IR that was transformed.
`<prefix>_report.md` records source details, trim and gain choices, sizes, and
checksums. `<prefix>_frequency_response.png` shows peak-relative magnitude and
unwrapped phase from 0 Hz to the 16 kHz Nyquist limit. Phase is omitted where
the magnitude is below -80 dB.

The binary uses 256-sample partitions, zero-padded to a 512-point RFFT. Each
partition contains 512 little-endian float32 values in CMSIS packed order:

```text
[DC, Nyquist, Re(bin 1), Im(bin 1), ..., Re(bin 255), Im(bin 255)]
```

The header stores magic, version, dimensions, payload length, normalization
scale, and CRC32 values. It is designed for a later QSPI uploader and Daisy
partitioned-convolution program; this tool does not modify the board.

## Test

```bash
python3 -m unittest discover -s Impulse_Converter/tests -v
```

The tests validate packing, asset checksums, trim/fade/normalization behavior,
and frequency-domain partitioned convolution against direct convolution.
See [TEST_RESULTS.md](TEST_RESULTS.md) for the checked implementation result.
