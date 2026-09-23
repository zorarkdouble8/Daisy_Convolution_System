#pragma once
#include "ir_asset.h"
#include "daisy_seed.h"
#include "arm_math.h"

class PartitionedConvolver {
  public:
    bool Init(const float* spectra, uint32_t partitions);
    bool Process(const float* input, float* output);
    void Reset();
  private:
    void MultiplyAccumulate(const float* a, const float* b);
    uint32_t partitions_ = 0, index_ = 0;
    arm_rfft_fast_instance_f32 rfft_;
    float time_[ir::kFftSize], accumulator_[ir::kFftSize], overlap_[ir::kPartitionSize];
};
