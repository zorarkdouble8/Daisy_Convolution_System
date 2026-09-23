# Impulse-response conversion report

## Source

- File: `Impulse Responses/freesound_community-impulse-response-church-105010.mp3`
- Codec: mp3
- Original sample rate: 44100 Hz
- Channels: 1
- Duration: 5.198344 s

## Processing

- Output: mono float32 PCM at 32000 Hz
- Start sample: 1703 (0.053219 s)
- Start selection: automatic -60 dB relative onset with 32-sample preroll
- Retained samples: 24000 (0.750 s)
- Source samples used: 24000
- Zero padding after source: 0 samples
- Fade: 640 samples (0.020 s), ending at zero
- Absolute-sum normalization multiplier: 0.00273754764006

The multiplier makes `sum(abs(h))` equal to approximately 1, giving a
conservative peak bound for future convolution. It can make the preview sound
quiet; future firmware should apply a separate, intentional wet gain.

## Frequency-domain asset

- Partition size: 256 samples
- FFT size: 512 samples
- Partition count: 94
- Packed spectrum format: CMSIS RFFT `[DC, Nyquist, Re(1), Im(1), ...]`
- Payload: 192512 bytes
- Total asset: 192768 bytes
- Payload CRC32: `0xFFFF5315`
- Header CRC32: `0x25385805`

The accompanying frequency-response PNG shows magnitude relative to the peak
(clamped at −120 dB) and unwrapped phase. Phase values below −80 dB magnitude
are omitted because phase is not useful where the response is near zero.

This asset is validated on the host. Daisy CMSIS equivalence and hardware
playback remain future firmware checks.
