# Daisy partitioned IR reverb

This is the firmware milestone that consumes `DIRF` assets produced by
[`../Impulse_Converter`](../Impulse_Converter/README.md). It performs 256-sample
partitioned overlap-add convolution at 32 kHz with a 512-point real FFT. The
church asset remains external to firmware and is stored in the first 192 KiB of
QSPI.

## Build and flash

From this directory, build one isolated image at a time:

```sh
cp Makefile.template Makefile
```

Before building, edit the local `Makefile` paths if your ARM compiler or
libDaisy installation differs. `Makefile` is ignored by Git; the tracked
`Makefile.template` is the shareable setup file.

```sh
make APP=reverb
make APP=uploader
make APP=selftest
make APP=reverb program-dfu
```

`APP=reverb` is the default. The generated files live below `build/<app>/`; no
command flashes automatically. Use the uploader image first, put the Seed in
normal firmware mode, then transfer the converted asset:

```sh
python3 -m pip install -r tools/requirements.txt
python3 tools/upload_ir.py --port /dev/ttyACM0 \
  ../Impulse_Converter/output/church_ir.bin
```

The program shows the 0x000000–0x02FFFF erase range and asks before doing a
single-slot update. `--yes` deliberately bypasses that prompt.

When uploader firmware is flashed, its Seed LED slowly blinks while it is ready
to receive an asset. After a complete upload has been written, read back, and
validated, it switches to a deliberately fast blink. Reflash `APP=reverb` to
run the effect after a successful upload.

## Firmware behavior

Reverb reads channel 0, produces wet-only output, and copies it to both
outputs. The offline asset has absolute-sum normalization for safe convolution;
the firmware therefore applies a separate `kWetGain = 64.0` and clamps the
codec output to `[-1, 1]`. Reduce that constant if sustained loud input clips.
One 256-sample block is 8 ms at 32 kHz. That block interval is a scheduling
deadline, not the entire converter/filter latency. The Seed LED means a valid
asset was loaded. Off means invalid/missing asset. A rapid blink means a
nonfinite processing result was muted and latched.

The temporary USB protocol is documented in [MEMORY_STRUCTURE.md](MEMORY_STRUCTURE.md).
It is deliberately not active in the audio application: USB, QSPI writes, and
logging never run from the audio callback.
