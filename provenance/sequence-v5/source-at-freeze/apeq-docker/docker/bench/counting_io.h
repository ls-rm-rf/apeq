// ============================================================================
// counting_io.h -- the ONLY place bytes are counted.
//
// Per spec section 3: count application payload inside the protocol, never with
// an external sniffer. The previous version of this work measured with iftop
// and reported 8.4 bytes per comparison at batch size 10000 -- physically
// impossible for the message structure. This wrapper makes that class of error
// unreachable.
//
// Every baseline either uses this wrapper or reads the library's own counters;
// in the latter case, verify the library counts payload (not framing) before
// mixing its numbers with these.
// ============================================================================
#pragma once

#include <cstdint>
#include <cstddef>

namespace bench {

template <typename Inner>
class CountingIO {
public:
    explicit CountingIO(Inner* inner) : inner_(inner) {}

    void send_data(const void* buf, size_t n) {
        bytes_sent_ += n;
        inner_->send_data(buf, n);
    }
    void recv_data(void* buf, size_t n) {
        bytes_recv_ += n;
        inner_->recv_data(buf, n);
    }
    void flush() { inner_->flush(); }

    uint64_t bytes_sent() const { return bytes_sent_; }
    uint64_t bytes_recv() const { return bytes_recv_; }
    void reset() { bytes_sent_ = bytes_recv_ = 0; }

    // Call between setup and online so the split can be attributed. Do NOT
    // reset the counters -- validate.py checks that total bytes are
    // non-decreasing in batch size, and a mid-run reset trips it.
    void mark_online_start() {
        setup_sent_ = bytes_sent_;
        setup_recv_ = bytes_recv_;
    }
    uint64_t setup_bytes() const { return setup_sent_ + setup_recv_; }
    uint64_t online_bytes() const {
        return (bytes_sent_ - setup_sent_) + (bytes_recv_ - setup_recv_);
    }

    Inner* inner() { return inner_; }

private:
    Inner* inner_;
    uint64_t bytes_sent_ = 0, bytes_recv_ = 0;
    uint64_t setup_sent_ = 0, setup_recv_ = 0;
};

}  // namespace bench
