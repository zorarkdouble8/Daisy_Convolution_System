# Impulse_sender

`send_impulse.py` is a PC audio-output measurement stimulus generator. It is
not Daisy firmware and does not record audio. Each terminal trigger sends one
positive float32 sample at 32 kHz, followed by 100 ms of digital silence.

## Use

From the workspace root:

```sh
python3 Impulse_sender/send_impulse.py
```

Press Enter to play one impulse repeatedly. Type `q` or `quit`, or use Ctrl-C,
to stop. The default amplitude is 0.5 full scale to preserve headroom at the
Daisy input. Select a different ALSA PCM device or level when necessary:

```sh
python3 Impulse_sender/send_impulse.py --device hw:1,0 --amplitude 0.25
```

List ALSA playback devices with `aplay -L`. The tool uses the installed `aplay`
program and only Python's standard library.

## Measuring the Daisy reverb

Connect the selected PC output to Daisy input 0 at a safe level, run the
reverb firmware, and record either Daisy output. A one-sample digital impulse
is changed by DACs, ADCs, analog circuitry, anti-alias filters, and gain
staging. After aligning the recorded signal for interface/filter latency, its
response should match the shape of the stored IR (for example,
`Impulse_Converter/output/church_ir_preview.wav`) at a possibly different
level. Start at low volume and avoid connecting a headphone/speaker-power
output directly to a sensitive line-level input without attenuation.

## Test

```sh
python3 -m unittest Impulse_sender/tests/test_send_impulse.py
```
