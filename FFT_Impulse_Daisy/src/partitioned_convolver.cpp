#include "partitioned_convolver.h"
#include "arm_const_structs.h"
#include <cmath>
#include <cstring>
extern "C" { extern const arm_rfft_fast_instance_f32 arm_rfft_fast_sR_f32_len512; }
DSY_SDRAM_BSS static float impulse_spectra[ir::kMaxPartitions][ir::kFftSize];
DSY_SDRAM_BSS static float input_history[ir::kMaxPartitions][ir::kFftSize];

bool PartitionedConvolver::Init(const float* spectra, uint32_t partitions) {
    if(!spectra || partitions == 0 || partitions > ir::kMaxPartitions) return false;
    std::memcpy(impulse_spectra, spectra, partitions * ir::kFftSize * sizeof(float));
    partitions_ = partitions; rfft_ = arm_rfft_fast_sR_f32_len512; Reset(); return true;
}
void PartitionedConvolver::Reset() { index_ = 0; std::memset(input_history, 0, sizeof(input_history)); std::memset(overlap_, 0, sizeof(overlap_)); }
void PartitionedConvolver::MultiplyAccumulate(const float* x, const float* h) {
    accumulator_[0] += x[0] * h[0]; accumulator_[1] += x[1] * h[1];
    for(uint32_t bin = 1; bin < ir::kFftSize / 2; ++bin) { uint32_t i = 2 * bin; accumulator_[i] += x[i]*h[i] - x[i+1]*h[i+1]; accumulator_[i+1] += x[i]*h[i+1] + x[i+1]*h[i]; }
}
bool PartitionedConvolver::Process(const float* input, float* output) {
    if(!input || !output || partitions_ == 0) return false;
    std::memcpy(time_, input, ir::kPartitionSize * sizeof(float)); std::memset(time_ + ir::kPartitionSize, 0, ir::kPartitionSize * sizeof(float));
    arm_rfft_fast_f32(&rfft_, time_, input_history[index_], 0); std::memset(accumulator_, 0, sizeof(accumulator_));
    for(uint32_t p = 0; p < partitions_; ++p) MultiplyAccumulate(input_history[(index_ + partitions_ - p) % partitions_], impulse_spectra[p]);
    arm_rfft_fast_f32(&rfft_, accumulator_, time_, 1);
    for(uint32_t i = 0; i < ir::kPartitionSize; ++i) { float y = time_[i] + overlap_[i]; if(!std::isfinite(y)) return false; output[i] = y; overlap_[i] = time_[i + ir::kPartitionSize]; }
    index_ = (index_ + 1) % partitions_; return true;
}
