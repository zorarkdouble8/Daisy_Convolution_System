#pragma once
#include <cstddef>
#include <cstdint>

// The wire format is deliberately small and independent of USB packet boundaries.
namespace upload {
constexpr uint32_t kMagic = 0x55524944u; // little-endian bytes: "DIRU"
constexpr size_t kHeaderBytes = 20;
constexpr size_t kMaxPayload = 1024;
constexpr size_t kMaxFrame = kHeaderBytes + kMaxPayload;

enum Command : uint32_t { Hello = 1, Begin = 2, Data = 3, Commit = 4, Status = 5,
                          Ack = 0x8000, Error = 0x8001 };
enum StatusCode : uint32_t { Ok = 0, BadFrame = 1, BadSequence = 2, BadAsset = 3,
                             TooLarge = 4, Incomplete = 5, Programming = 6,
                             FlashFailure = 7, Busy = 8, RxOverflow = 9 };
struct Frame { uint32_t command, sequence, payload_length; const uint8_t* payload; };

uint32_t FrameCrc(uint32_t command, uint32_t sequence, const uint8_t* payload, uint32_t length);
size_t Encode(uint8_t* destination, size_t capacity, uint32_t command, uint32_t sequence,
              const uint8_t* payload, uint32_t length);
// Returns true only for one complete valid frame. `consumed` discards either a
// complete frame or one corrupt byte, making it safe for arbitrary fragments.
bool Decode(const uint8_t* data, size_t size, Frame* frame, size_t* consumed);
} // namespace upload
