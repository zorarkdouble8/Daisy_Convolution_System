#include "daisy_seed.h"
#include "ir_asset.h"
#include "upload_protocol.h"
#include <cstring>

using namespace daisy;
namespace {
DaisySeed hw;
DSY_SDRAM_BSS uint8_t staged[ir::kMaxAssetBytes];
uint8_t rx[2048], tx[upload::kMaxFrame];
volatile uint32_t rx_write = 0, rx_read = 0;
volatile bool rx_overflow = false;
uint32_t expected_bytes = 0, expected_crc = 0, received_bytes = 0, next_sequence = 0;
uint32_t last_sequence = 0xffffffffu;
upload::StatusCode state = upload::Ok;
bool upload_verified = false;
constexpr uint32_t kReadyBlinkMs = 700;
constexpr uint32_t kSuccessBlinkMs = 80;

void Receive(uint8_t* bytes, uint32_t* count) {
    // ISR/callback work is intentionally limited to bounded byte enqueueing.
    for(uint32_t i = 0; i < *count; ++i) {
        uint32_t next = (rx_write + 1u) % sizeof(rx);
        if(next == rx_read) { rx_overflow = true; break; }
        rx[rx_write] = bytes[i]; rx_write = next;
    }
}
size_t Pending() { return (rx_write + sizeof(rx) - rx_read) % sizeof(rx); }
uint8_t Peek(size_t i) { return rx[(rx_read + i) % sizeof(rx)]; }
void Consume(size_t n) { rx_read = (rx_read + n) % sizeof(rx); }
void Send(uint32_t command, uint32_t sequence, upload::StatusCode result) {
    uint8_t payload[4] = {uint8_t(result), uint8_t(uint32_t(result) >> 8), uint8_t(uint32_t(result) >> 16), uint8_t(uint32_t(result) >> 24)};
    size_t n = upload::Encode(tx, sizeof(tx), command, sequence, payload, sizeof(payload));
    if(n) hw.usb_handle.TransmitInternal(tx, n);
}
bool Program() {
    state = upload::Programming; hw.SetLed(true);
    if(hw.qspi.Erase(ir::kQspiOffset, ir::kQspiSlotBytes) != QSPIHandle::Result::OK) return false;
    // Commit header last: an interrupted update cannot look like a valid asset.
    if(hw.qspi.Write(ir::kHeaderSize, expected_bytes - ir::kHeaderSize, staged + ir::kHeaderSize) != QSPIHandle::Result::OK) return false;
    if(std::memcmp(static_cast<const uint8_t*>(hw.qspi.GetData(ir::kHeaderSize)), staged + ir::kHeaderSize, expected_bytes - ir::kHeaderSize) != 0) return false;
    if(hw.qspi.Write(0, ir::kHeaderSize, staged) != QSPIHandle::Result::OK) return false;
    if(std::memcmp(static_cast<const uint8_t*>(hw.qspi.GetData(0)), staged, expected_bytes) != 0) return false;
    return ir::Validate(static_cast<const uint8_t*>(hw.qspi.GetData(0)), expected_bytes, nullptr) == ir::Error::Ok;
}
void Handle(const upload::Frame& f) {
    if(f.command == upload::Hello) { Send(upload::Ack, f.sequence, upload::Ok); return; }
    if(f.command == upload::Status) { Send(upload::Ack, f.sequence, state); return; }
    if(f.command == upload::Begin) {
        if(f.payload_length != 8) { Send(upload::Error, f.sequence, upload::BadFrame); return; }
        uint32_t bytes = uint32_t(f.payload[0]) | (uint32_t(f.payload[1]) << 8) | (uint32_t(f.payload[2]) << 16) | (uint32_t(f.payload[3]) << 24);
        uint32_t crc = uint32_t(f.payload[4]) | (uint32_t(f.payload[5]) << 8) | (uint32_t(f.payload[6]) << 16) | (uint32_t(f.payload[7]) << 24);
        if(bytes < ir::kHeaderSize || bytes > ir::kMaxAssetBytes) { Send(upload::Error, f.sequence, upload::TooLarge); return; }
        expected_bytes = bytes; expected_crc = crc; received_bytes = 0; next_sequence = 0; last_sequence = 0xffffffffu; state = upload::Ok; upload_verified = false;
        Send(upload::Ack, f.sequence, upload::Ok); return;
    }
    if(f.command == upload::Data) {
        if(f.sequence == last_sequence) { Send(upload::Ack, f.sequence, state); return; }
        if(f.sequence != next_sequence || !expected_bytes || received_bytes + f.payload_length > expected_bytes) { Send(upload::Error, f.sequence, upload::BadSequence); return; }
        std::memcpy(staged + received_bytes, f.payload, f.payload_length); received_bytes += f.payload_length; last_sequence = f.sequence; ++next_sequence;
        Send(upload::Ack, f.sequence, upload::Ok); return;
    }
    if(f.command == upload::Commit) {
        if(state == upload::Programming || state == upload::FlashFailure) { Send(upload::Ack, f.sequence, state); return; }
        if(received_bytes != expected_bytes) { state = upload::Incomplete; Send(upload::Error, f.sequence, state); return; }
        if(ir::Crc32(staged, received_bytes) != expected_crc || ir::Validate(staged, received_bytes, nullptr) != ir::Error::Ok) { state = upload::BadAsset; Send(upload::Error, f.sequence, state); return; }
        state = Program() ? upload::Ok : upload::FlashFailure;
        upload_verified = state == upload::Ok;
        Send(state == upload::Ok ? upload::Ack : upload::Error, f.sequence, state); return;
    }
    Send(upload::Error, f.sequence, upload::BadFrame);
}
void ProcessRx() {
    if(rx_overflow) { rx_overflow = false; state = upload::RxOverflow; rx_read = rx_write; }
    while(Pending()) {
        uint8_t local[upload::kMaxFrame]; size_t n = Pending(); if(n > sizeof(local)) n = sizeof(local);
        for(size_t i = 0; i < n; ++i) local[i] = Peek(i);
        upload::Frame f; size_t used = 0; bool complete = upload::Decode(local, n, &f, &used);
        if(used) { Consume(used); if(complete) Handle(f); continue; }
        break; // valid partial frame; wait for its remaining bytes
    }
}
}
int main(void) {
    hw.Init(); hw.usb_handle.Init(UsbHandle::FS_INTERNAL); hw.usb_handle.SetReceiveCallback(Receive, UsbHandle::FS_INTERNAL); hw.SetLed(false);
    // Slow blink = uploader is flashed and ready for BEGIN/DATA/COMMIT.
    // Fast blink = the full asset was written, read back, and validated.
    bool led_on = false;
    while(1) {
        ProcessRx();
        const uint32_t interval = upload_verified
                                      ? kSuccessBlinkMs : kReadyBlinkMs;
        led_on = !led_on;
        hw.SetLed(led_on);
        System::Delay(interval);
    }
}
