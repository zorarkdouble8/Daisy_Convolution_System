#include "upload_protocol.h"
#include "ir_asset.h"
#include <cstring>

namespace {
uint32_t ReadU32(const uint8_t* p) { return uint32_t(p[0]) | (uint32_t(p[1]) << 8) | (uint32_t(p[2]) << 16) | (uint32_t(p[3]) << 24); }
void WriteU32(uint8_t* p, uint32_t v) { p[0] = v; p[1] = v >> 8; p[2] = v >> 16; p[3] = v >> 24; }
}
namespace upload {
uint32_t FrameCrc(uint32_t command, uint32_t sequence, const uint8_t* payload, uint32_t length) {
    uint8_t words[12]; WriteU32(words, command); WriteU32(words + 4, sequence); WriteU32(words + 8, length);
    // zlib CRC is not composable by feeding its final value, so form the bounded
    // serialization in the caller-independent local buffer instead.
    uint8_t bytes[kMaxFrame]; std::memcpy(bytes, words, sizeof(words));
    if(length) std::memcpy(bytes + sizeof(words), payload, length);
    return ir::Crc32(bytes, sizeof(words) + length);
}
size_t Encode(uint8_t* out, size_t cap, uint32_t command, uint32_t sequence, const uint8_t* payload, uint32_t length) {
    if(!out || length > kMaxPayload || cap < kHeaderBytes + length || (length && !payload)) return 0;
    WriteU32(out, kMagic); WriteU32(out + 4, command); WriteU32(out + 8, sequence); WriteU32(out + 12, length);
    WriteU32(out + 16, FrameCrc(command, sequence, payload, length));
    if(length) std::memcpy(out + kHeaderBytes, payload, length);
    return kHeaderBytes + length;
}
bool Decode(const uint8_t* data, size_t size, Frame* frame, size_t* consumed) {
    if(consumed) *consumed = 0;
    if(!data || size < 4) return false;
    if(ReadU32(data) != kMagic) { if(consumed) *consumed = 1; return false; }
    if(size < kHeaderBytes) return false;
    uint32_t length = ReadU32(data + 12);
    if(length > kMaxPayload) { if(consumed) *consumed = 1; return false; }
    size_t total = kHeaderBytes + length;
    if(size < total) return false;
    uint32_t command = ReadU32(data + 4), sequence = ReadU32(data + 8);
    if(FrameCrc(command, sequence, data + kHeaderBytes, length) != ReadU32(data + 16)) { if(consumed) *consumed = 1; return false; }
    if(frame) *frame = {command, sequence, length, data + kHeaderBytes};
    if(consumed) *consumed = total;
    return true;
}
} // namespace upload
