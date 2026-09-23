#include "daisy_seed.h"
#include "ir_asset.h"
#include "partitioned_convolver.h"
#include <cstring>

using namespace daisy;
namespace {
DaisySeed hw;
PartitionedConvolver convolver;
volatile uint32_t max_cycles = 0, deadline_misses = 0;
volatile bool ready = false, processing_fault = false;
// The converter normalizes the IR to an absolute coefficient sum of one. That
// is safe for convolution, but a 0.75 s church IR then has a very low RMS
// level. This is intentional playback gain, not a second IR normalization.
constexpr float kWetGain = 64.0f;

void AudioCallback(AudioHandle::InputBuffer in, AudioHandle::OutputBuffer out, size_t size) {
    uint32_t started = DWT->CYCCNT;
    bool ok = ready && size == ir::kPartitionSize && convolver.Process(in[0], out[0]);
    if(!ok) { processing_fault = ready; for(size_t i = 0; i < size; ++i) out[0][i] = 0.0f; }
    for(size_t i = 0; i < size; ++i) {
        float wet = out[0][i] * kWetGain;
        // The gain may exceed unity on unusually loud/coherent input. Clamp
        // before the codec so it cannot wrap or produce an invalid float.
        wet = wet > 1.0f ? 1.0f : (wet < -1.0f ? -1.0f : wet);
        out[0][i] = wet;
        out[1][i] = wet;
    }
    uint32_t elapsed = DWT->CYCCNT - started;
    if(elapsed > max_cycles) max_cycles = elapsed;
    if(elapsed > (System::GetSysClkFreq() / 125u)) ++deadline_misses; // 8 ms
}
}
int main(void) {
    hw.Init(); hw.SetAudioBlockSize(ir::kPartitionSize); hw.SetAudioSampleRate(SaiHandle::Config::SampleRate::SAI_32KHZ);
    DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk; DWT->CYCCNT = 0;
    const uint8_t* asset = static_cast<const uint8_t*>(hw.qspi.GetData(ir::kQspiOffset)); ir::Metadata meta;
    if(ir::Validate(asset, ir::kMaxAssetBytes, &meta) == ir::Error::Ok)
        ready = convolver.Init(reinterpret_cast<const float*>(asset + ir::kHeaderSize), meta.partitions);
    hw.SetLed(ready); // steady: ready; off: invalid asset; rapid foreground blink: processing fault
    hw.StartAudio(AudioCallback);
    while(1) { if(processing_fault) { hw.SetLed(true); System::Delay(80); hw.SetLed(false); System::Delay(80); } else System::Delay(100); }
}
