#include "daisy_seed.h"
#include "partitioned_convolver.h"
#include <cmath>
#include <cstring>
using namespace daisy;
namespace {
float identity[ir::kFftSize];
float input[ir::kPartitionSize], output[ir::kPartitionSize];
}
int main(void) {
    DaisySeed hw; hw.Init();
    // RFFT packed identity spectrum: DC and Nyquist are real scalars; all
    // remaining bins are complex 1 + j0.
    identity[0] = identity[1] = 1.0f;
    for(uint32_t bin = 1; bin < ir::kFftSize / 2; ++bin) { identity[2 * bin] = 1.0f; identity[2 * bin + 1] = 0.0f; }
    for(uint32_t i = 0; i < ir::kPartitionSize; ++i) input[i] = (float(int(i % 31) - 15)) / 16.0f;
    PartitionedConvolver test; bool passed = test.Init(identity, 1) && test.Process(input, output);
    float max_error = 0.0f; for(uint32_t i = 0; i < ir::kPartitionSize; ++i) { float e = std::fabs(output[i] - input[i]); if(e > max_error) max_error = e; }
    passed = passed && max_error < 1.0e-4f;
    hw.StartLog(); hw.PrintLine("FFT IR self-test %s, identity max error %.8f", passed ? "PASS" : "FAIL", max_error);
    hw.SetLed(passed); while(1) System::Delay(250);
}
