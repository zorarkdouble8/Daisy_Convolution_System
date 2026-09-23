# Test results

## Completed locally

- The offline converter's existing Python suite passed before this milestone:
  8 tests, including packing, header/payload CRCs, reconstruction, partition
  boundaries, fades, onset detection, and the actual church conversion.
- `tests/test_host_protocol.py` passed: 4 tests. It checks the temporary host frame serializer, fragmented replies, and
  validates the actual `church_ir.bin` dimensions (94 partitions, 192,512-byte
  payload, 192,768 total bytes), including a corrupt-payload rejection.

Run it from this directory with:

```sh
python3 -m unittest tests/test_host_protocol.py
```

## Firmware tests and hardware acceptance still required

`APP=selftest` executes the actual CMSIS 512-point RFFT convolution core on the
Seed and checks identity filtering with a `1e-4` maximum-error limit. The
planned extended board fixtures (two taps, delays 255/256/257, random signal,
history wrap, DC/alternating input, and complete tail flushing) require a board
run and are intentionally not claimed as complete here.

Likewise, upload persistence, silent input, matching stereo wet output, audible
church decay, sustained-input finiteness/dropouts, and actual callback timing
must be measured on the connected Seed. The reverb image tracks peak callback
cycles and 8 ms deadline overruns in volatile counters; foreground USB status
exposure is reserved for the next diagnostic revision because this milestone's
uploader and audio programs are intentionally separate images.

All three firmware targets cross-built successfully with the installed
`arm-none-eabi` toolchain. Reported internal-flash use was 86,840 bytes for
reverb (66.25%), 82,724 for uploader (63.11%), and 89,016 for selftest
(67.91%); each is below the 128 KiB limit. The linker reported 376 KiB SDRAM
for reverb/selftest and 192,768 bytes for the uploader staging buffer.
