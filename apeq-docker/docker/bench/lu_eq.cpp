// Unified benchmark adapter for the official Lu et al. equality artifact.
#include "driver_common.h"

#include "neweq.h"

uint8_t Zp::p;

namespace bench {

ProtocolResult run_protocol(const Config& c, const Inputs& in) {
    ProtocolResult res;
    if (c.protocol != "lu_eq" || c.backend != "n/a" || c.variant != "n/a")
        throw std::invalid_argument("Lu adapter requires lu_eq/n/a/n/a");
    if (c.security_param != 128)
        throw std::invalid_argument("Lu adapter requires --kappa 128");
    if (c.bits > 64)
        throw std::invalid_argument("Lu adapter currently supports at most 64-bit harness inputs");

    const Role role = c.party == 1 ? Role::Sender : Role::Receiver;
    const std::string endpoint = c.host + ":" + std::to_string(c.port);
    std::vector<osuCrypto::block> data(c.batch);
    for (uint64_t i = 0; i < c.batch; ++i) {
        const uint64_t value = c.party == 1 ? in.alpha[i].as_u64()
                                            : in.beta[i].as_u64();
        data[i] = osuCrypto::toBlock(0, value);
    }

    osuCrypto::BitVector output(c.batch);
    eq2<uint8_t> equality(role, endpoint, nullptr, nullptr);
    equality.run(data, output, c.bits, 1, false);
    const Eq2PhaseStats& stats = equality.stats();

    res.setup_ms = stats.setup_ms;
    res.online_ms = stats.online_ms;
    res.setup_bytes_sent = stats.setup_bytes_sent;
    res.setup_bytes_recv = stats.setup_bytes_recv;
    res.online_bytes_sent = stats.online_bytes_sent;
    res.online_bytes_recv = stats.online_bytes_recv;
    res.bytes_sent = res.setup_bytes_sent + res.online_bytes_sent;
    res.bytes_recv = res.setup_bytes_recv + res.online_bytes_recv;
    res.n_ot = stats.n_ot;
    res.n_field_ops = -1;

    if (c.party == 2) {
        res.output.resize(c.batch);
        for (uint64_t i = 0; i < c.batch; ++i)
            res.output[i] = output[i] ? 1 : 0;
    }

    char note[320];
    std::snprintf(note, sizeof note,
                  "official_lu_artifact patched_adapter base_ot_ms=%.3f "
                  "offline_in_setup one_sided_output_reconstruction "
                  "logical_ot_count=%llu private_protocol_coins_not_logged "
                  "independent_session_setup",
                  stats.base_ot_ms,
                  static_cast<unsigned long long>(stats.n_ot));
    res.note = note;
    return res;
}

}  // namespace bench

int main(int argc, char** argv) { return bench::driver_main(argc, argv); }
