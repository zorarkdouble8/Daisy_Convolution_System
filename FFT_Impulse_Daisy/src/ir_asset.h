#pragma once
#include <cstddef>
#include <cstdint>

namespace ir {
constexpr uint32_t kSampleRate = 32000;
constexpr uint32_t kPartitionSize = 256;
constexpr uint32_t kFftSize = 512;
constexpr uint32_t kMaxPartitions = 94;
constexpr uint32_t kHeaderSize = 256;
constexpr uint32_t kMaxPayloadBytes = kMaxPartitions * kFftSize * sizeof(float);
constexpr uint32_t kMaxAssetBytes = kHeaderSize + kMaxPayloadBytes;
constexpr uint32_t kQspiOffset = 0;
constexpr uint32_t kQspiSlotBytes = 192 * 1024;

enum class Error : uint32_t { Ok, TooSmall, HeaderCrc, Magic, Version, Reserved, Dimensions, Length, PayloadCrc, Nonfinite };
struct Metadata { uint32_t retained_samples, partitions, payload_bytes, payload_crc; float normalization; };
uint32_t Crc32(const uint8_t* data, size_t size);
Error Validate(const uint8_t* asset, size_t available, Metadata* metadata);
const char* ErrorName(Error error);
} // namespace ir
