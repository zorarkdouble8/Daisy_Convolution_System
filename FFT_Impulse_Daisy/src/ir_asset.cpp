#include "ir_asset.h"
#include <cmath>
#include <cstring>

namespace {
uint32_t ReadU32(const uint8_t* p) { return uint32_t(p[0]) | (uint32_t(p[1]) << 8) | (uint32_t(p[2]) << 16) | (uint32_t(p[3]) << 24); }
float ReadF32(const uint8_t* p) { uint32_t raw = ReadU32(p); float value; std::memcpy(&value, &raw, sizeof(value)); return value; }
}
namespace ir {
uint32_t Crc32(const uint8_t* data, size_t size) {
    uint32_t crc = 0xffffffffu;
    for(size_t i = 0; i < size; ++i) { crc ^= data[i]; for(int bit = 0; bit < 8; ++bit) crc = (crc >> 1) ^ (0xedb88320u & (-(int32_t)(crc & 1u))); }
    return ~crc;
}
Error Validate(const uint8_t* a, size_t available, Metadata* out) {
    if(a == nullptr || available < kHeaderSize) return Error::TooSmall;
    uint8_t header[kHeaderSize]; std::memcpy(header, a, sizeof(header));
    uint32_t stored_header_crc = ReadU32(header + 48); std::memset(header + 48, 0, 4);
    if(Crc32(header, sizeof(header)) != stored_header_crc) return Error::HeaderCrc;
    if(std::memcmp(a, "DIRF", 4) != 0) return Error::Magic;
    if(ReadU32(a + 4) != 1 || ReadU32(a + 8) != kHeaderSize || ReadU32(a + 12) != 1) return Error::Version;
    for(size_t i = 52; i < kHeaderSize; ++i) if(a[i] != 0) return Error::Reserved;
    uint32_t retained = ReadU32(a + 20), parts = ReadU32(a + 32), bytes = ReadU32(a + 36);
    if(ReadU32(a + 16) != kSampleRate || ReadU32(a + 24) != kPartitionSize || ReadU32(a + 28) != kFftSize || retained == 0 || parts == 0 || parts > kMaxPartitions || parts != (retained + kPartitionSize - 1) / kPartitionSize) return Error::Dimensions;
    if(bytes != parts * kFftSize * sizeof(float) || bytes > kMaxPayloadBytes || available < kHeaderSize + bytes) return Error::Length;
    if(Crc32(a + kHeaderSize, bytes) != ReadU32(a + 40)) return Error::PayloadCrc;
    float norm = ReadF32(a + 44); if(!std::isfinite(norm) || norm <= 0.0f) return Error::Nonfinite;
    const float* samples = reinterpret_cast<const float*>(a + kHeaderSize);
    for(uint32_t i = 0; i < bytes / sizeof(float); ++i) if(!std::isfinite(samples[i])) return Error::Nonfinite;
    if(out) *out = {retained, parts, bytes, ReadU32(a + 40), norm};
    return Error::Ok;
}
const char* ErrorName(Error e) { static const char* names[] = {"ok","too-small","header-crc","magic","version","reserved","dimensions","length","payload-crc","nonfinite"}; return names[static_cast<uint32_t>(e)]; }
} // namespace ir
