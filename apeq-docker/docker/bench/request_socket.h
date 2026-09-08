#pragma once
#include "driver_common.h"
#include <coproto/Socket/AsioSocket.h>

namespace bench {
inline uint64_t& opened_request_connections() {
    static uint64_t count = 0;
    return count;
}

// Transport state only. Every run_protocol call still creates a new PRNG,
// OT/VOLE object, base OTs, masks and (for VOLE) request nonces.
inline coproto::Socket request_socket(const Config& c) {
    auto connect = [&]() {
        auto result = coproto::asioConnect(c.host+":"+std::to_string(c.port), c.party == 1);
        ++opened_request_connections();
        return result;
    };
    if (c.sequence_requests <= 1) return connect();
    static coproto::Socket retained;
    if (c.request_index == 0) {
        if (retained.mImpl) die("previous sequence transport is still open");
        retained = connect();
    } else if (!retained.mImpl) die("missing sequential request transport");
    // Socket copies share the same underlying scheduler and TCP connection.
    auto result = retained;
    if (c.request_index + 1 == c.sequence_requests)
        retained = coproto::Socket{};  // final call owns the last live reference
    return result;
}
}  // namespace bench
