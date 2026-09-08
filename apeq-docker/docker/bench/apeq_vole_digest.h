#pragma once

#include <cryptoTools/Crypto/RandomOracle.h>
#include <array>
#include <cstdint>

namespace bench {
using VoleSessionId = std::array<std::uint8_t, 64>;

// Fixed-width, big-endian context; field limbs are serialized explicitly.
inline osuCrypto::block vole_digest(const VoleSessionId& sid,
                                    std::uint64_t bits, std::uint64_t batch,
                                    std::uint64_t coordinate,
                                    const osuCrypto::block& value,
                                    std::uint64_t request_index = UINT64_MAX) {
    static constexpr char domain[] = "APEQ-v2/vole-equality/holder-tag";
    osuCrypto::RandomOracle hash(sizeof(osuCrypto::block));
    hash.Update(domain, sizeof(domain) - 1);
    hash.Update(sid.data(), sid.size());
    auto integer = [&](std::uint64_t x) {
        std::array<std::uint8_t, 8> bytes{};
        for (std::size_t i = 0; i < 8; ++i) {
            bytes[7 - i] = static_cast<std::uint8_t>(x);
            x >>= 8;
        }
        hash.Update(bytes.data(), bytes.size());
    };
    integer(bits);
    integer(batch);
    // Ordinary E1 calls retain the exact v2 byte string. E3 additionally uses
    // an explicit versioned request domain and a fixed-width request ordinal.
    if (request_index != UINT64_MAX) {
        static constexpr char request_domain[] = "APEQ-v3/sequential-request";
        hash.Update(request_domain, sizeof(request_domain)-1);
        integer(request_index);
    }
    integer(coordinate);
    const auto limbs = value.get<std::uint64_t>();
    integer(limbs[1]);
    integer(limbs[0]);
    osuCrypto::block out;
    hash.Final(out);
    return out;
}
}  // namespace bench
