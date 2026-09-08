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
                                    const osuCrypto::block& value) {
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
    integer(coordinate);
    const auto limbs = value.get<std::uint64_t>();
    integer(limbs[1]);
    integer(limbs[0]);
    osuCrypto::block out;
    hash.Final(out);
    return out;
}
}  // namespace bench
