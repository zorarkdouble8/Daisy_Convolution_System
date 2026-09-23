# Test results

Run on the included converter implementation:

```text
python3 -m unittest discover -s Impulse_Converter/tests -v
```

Result: 8 tests passed.

The tests cover CMSIS packed RFFT round trips, DC and Nyquist slots, identity
and delayed-tap convolution across offsets 255--257, direct-convolution error,
trim/preroll/manual-start behavior, fade and normalization, short-input
padding, invalid input, binary dimensions, final-partition padding, CRCs,
overwrite protection, and the identity-impulse frequency response.

The generated church asset has also been parsed and validated by the converter.
These are host-side numerical checks. CMSIS-DSP equivalence and Daisy hardware
playback remain future work.
