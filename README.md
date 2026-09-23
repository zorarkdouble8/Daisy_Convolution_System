# Daisy Convolution System

This folder contains the complete mono Daisy Seed convolution-reverb workflow:

```text
Impulse response WAV/MP3
        │
        ▼
Impulse_Converter  ──► DIRF `.bin` asset ──► FFT_Impulse_Daisy uploader ──► QSPI
                                                                        │
PC / instrument input ─────────────────────────────────────────────────┘
                                                                        ▼
                                                        FFT_Impulse_Daisy reverb
                                                                        ▼
                                                           both Daisy outputs
```

All firmware processing is 32 kHz mono input (`input 0`) with the wet result
copied to both outputs. The current church reverb uses a 0.75-second IR.

## Projects

| Project | Purpose | Run it when… |
|---|---|---|
| [`Impulse_Converter`](Impulse_Converter/README.md) | Converts a WAV/MP3 IR to a 32 kHz `DIRF` QSPI asset, preview WAV, graph, and report. | You want a new reverb space or object. |
| [`FFT_Impulse_Daisy`](FFT_Impulse_Daisy/README.md) | Daisy firmware: temporary USB uploader, real-time partitioned-convolution reverb, and on-board self-test. | You need to upload an IR or run the reverb. |
| [`Impulse_sender`](Impulse_sender/README.md) | PC terminal tool that plays a one-sample test impulse from an ALSA output. | You want to test the hardware reverb response. |

## First-time setup and run

Run these commands from this directory (`Daisy_Convolution_System/`). You need
Python 3, NumPy, FFmpeg/FFprobe for conversion, the ARM/libDaisy toolchain used
by the Makefile, and PySerial for upload.

Before the first firmware build, create your local firmware Makefile from the
tracked template and update its three path variables if your compiler/libDaisy
installation is elsewhere:

```sh
cd FFT_Impulse_Daisy
cp Makefile.template Makefile
# Edit GCC_PATH, LIBDAISY_DIR, and DAISYSP_DIR in Makefile if needed.
cd ..
```

`Makefile` is intentionally ignored by Git; `Makefile.template` is the
portable version kept in the repository.

### 1. Convert an impulse response

The included church source is already converted in `Impulse_Converter/output/`.
To regenerate it or convert another WAV/MP3:

```sh
python3 -m pip install -r Impulse_Converter/requirements.txt
python3 Impulse_Converter/convert_ir.py \
  "Impulse Responses/freesound_community-impulse-response-church-105010.mp3" \
  --output-prefix Impulse_Converter/output/church_ir --overwrite
```

The important output is `Impulse_Converter/output/church_ir.bin`. Do not put
the Daisy into boot mode for this host-only conversion step.

### 2. Flash uploader firmware

Enter the Daisy Seed's **boot/DFU mode** before every `program-dfu` command:

1. Hold **BOOT**.
2. Tap and release **RESET**.
3. Release **BOOT**.

Then flash the uploader:

```sh
cd FFT_Impulse_Daisy
make APP=uploader program-dfu
cd ..
```

Wait for the Seed to boot normally. The uploader LED should slowly blink: this
means the uploader is running and ready. **Do not leave it in boot mode** for
the next step.

### 3. Upload the converted IR to QSPI

Install the host uploader dependency once, then run the transfer while the
uploader firmware is running normally:

```sh
python3 -m pip install -r FFT_Impulse_Daisy/tools/requirements.txt
python3 FFT_Impulse_Daisy/tools/upload_ir.py --port /dev/ttyACM0 \
  Impulse_Converter/output/church_ir.bin
```

Use the actual serial device if it differs; `ls /dev/ttyACM*` can help identify
it. The script asks before erasing the dedicated QSPI slot. A rapid LED blink
means the asset was written, read back, and validated successfully.

### 4. Flash and run reverb

Put the Seed into **boot/DFU mode again** using the BOOT/RESET sequence above,
then flash reverb:

```sh
cd FFT_Impulse_Daisy
make APP=reverb program-dfu
cd ..
```

After it reboots normally, a steady LED means the QSPI IR passed validation.
Off means the reverb found no valid IR and deliberately mutes output; rapid
blinking means a processing fault. No IR upload is needed again unless you are
changing the asset.

## Audio and impulse test

Connect your audio source to Daisy input 0. Reverb is wet-only and sends the
same processed signal to both outputs. Start with a low input/output level;
the firmware has a 64x wet gain and clamps the final signal to prevent invalid
output, but hard clipping can still sound unpleasant.

To send a test impulse from the PC's default ALSA output:

```sh
python3 Impulse_sender/send_impulse.py
```

Press Enter for each impulse and `q` to exit. Connect that output safely to
Daisy input 0—attenuate headphone/speaker outputs before a line-level input.
To choose a device or lower the level:

```sh
python3 Impulse_sender/send_impulse.py --device hw:1,0 --amplitude 0.25
```

## Regular workflow

- For a new IR: convert it, flash uploader in boot mode, upload while it runs
  normally, then flash reverb in boot mode.
- For an existing uploaded IR after power cycling: only flash/run reverb; the
  IR remains in QSPI.
- To check converter, host-protocol, and impulse-sender tests:

  ```sh
  python3 -m unittest discover -s Impulse_Converter/tests -v
  python3 -m unittest FFT_Impulse_Daisy/tests/test_host_protocol.py
  python3 -m unittest Impulse_sender/tests/test_send_impulse.py
  ```

See each project README for format, memory, protocol, and troubleshooting
details.
