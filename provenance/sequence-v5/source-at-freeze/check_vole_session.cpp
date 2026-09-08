#include "apeq_vole_digest.h"
#include <iostream>
#include <stdexcept>

int main() {
    bench::VoleSessionId sid{};
    const osuCrypto::block value(0x123456789abcdef0ULL, 0xfedcba9876543210ULL);
    const auto original = bench::vole_digest(sid, 64, 100, 0, value);
    auto require_different = [&](const osuCrypto::block& candidate) {
        if (candidate == original) throw std::runtime_error("namespace separation failed");
    };
    for (std::size_t bit = 0; bit < 512; ++bit) {
        auto other = sid;
        other[bit / 8] ^= 1U << (bit % 8);
        require_different(bench::vole_digest(other, 64, 100, 0, value));
    }
    require_different(bench::vole_digest(sid, 16, 100, 0, value));
    require_different(bench::vole_digest(sid, 64, 101, 0, value));
    require_different(bench::vole_digest(sid, 64, 100, 1, value));
    require_different(bench::vole_digest(sid, 64, 100, 0, osuCrypto::ZeroBlock));
    if (bench::vole_digest(sid, 64, 100, 0, value) != original)
        throw std::runtime_error("same-context repeat changed digest");
    std::array<osuCrypto::block, 20> requests;
    for (std::size_t i = 0; i < requests.size(); ++i) {
        requests[i] = bench::vole_digest(sid, 64, 100, 0, value, i);
        require_different(requests[i]);
        for (std::size_t j = 0; j < i; ++j)
            if (requests[i] == requests[j]) throw std::runtime_error("request domains collided");
        if (bench::vole_digest(sid, 64, 100, 0, value, i) != requests[i])
            throw std::runtime_error("request context is not deterministic");
    }
    std::cout << "516 namespace changes rejected; same-context repeat passed; 20 request domains distinct and separate from v2\n";
}
