// Classical bit-decomposition OLE: w chosen OTs per coordinate, followed by
// one field correction. No Reed--Solomon decoding assumption is used.
#include "driver_common.h"
#include "ips_ole/core.h"
#include <coproto/Socket/AsioSocket.h>
#include <libOTe/TwoChooseOne/Iknp/IknpOtExtReceiver.h>
#include <libOTe/TwoChooseOne/Iknp/IknpOtExtSender.h>
#include <macoro/sync_wait.h>
#include <iomanip>
#include <sstream>

namespace bench {
namespace oc = osuCrypto;
namespace ips = apeq::ips_ole;
namespace {
ips::Fp from_limbs(std::uint64_t high, std::uint64_t low) {
    std::ostringstream s;
    s << std::hex << std::setfill('0') << std::setw(16) << high
      << std::setw(16) << low;
    return ips::Fp::from_hex(s.str());
}
ips::Fp from_block(const oc::block& block) {
    auto limbs = block.get<std::uint64_t>();
    return from_limbs(limbs[1], limbs[0]);
}
oc::block to_block(const ips::Fp& value) {
    auto hex = value.to_hex();
    return oc::block(std::stoull(hex.substr(0, 16), nullptr, 16),
                     std::stoull(hex.substr(16, 16), nullptr, 16));
}
}  // namespace

ProtocolResult run_protocol(const Config& c, const Inputs& in) {
    if (c.backend != "bit_ot" || c.variant != "ole" ||
        c.field_bits != 127 || c.security_param != 128)
        throw std::invalid_argument("bit-OT OLE requires bit_ot/ole, p127, kappa128");
    ProtocolResult res;
    auto socket = coproto::asioConnect(c.host + ":" + std::to_string(c.port),
                                       c.party == 1);
    oc::PRNG prng(oc::sysRandomSeed());
    oc::IknpOtExtSender sender;
    oc::IknpOtExtReceiver receiver;
    Timer timer;
    timer.start();
    if (c.party == 1) macoro::sync_wait(sender.genBaseOts(prng, socket));
    else macoro::sync_wait(receiver.genBaseOts(prng, socket));
    macoro::sync_wait(socket.flush());
    res.setup_ms = timer.stop_ms();
    res.setup_bytes_sent = socket.bytesSent();
    res.setup_bytes_recv = socket.bytesReceived();

    timer.start();
    const std::size_t count = c.batch * c.bits;
    if (c.party == 1) {
        ips::Prng field_prng(ips::random_master_seed());
        oc::AlignedUnVector<std::array<oc::block, 2>> messages(count);
        std::vector<oc::block> corrections(c.batch);
        for (std::size_t i = 0; i < c.batch; ++i) {
            auto a = ips::Fp::zero();
            do { a = field_prng.random_fp(); } while (a.is_zero());
            auto correction = ips::Fp::zero() - a * from_limbs(in.alpha[i].high, in.alpha[i].low);
            auto weight = a;
            for (std::size_t j = 0; j < c.bits; ++j) {
                const auto r = field_prng.random_fp();
                messages[i * c.bits + j] = {to_block(r), to_block(r + weight)};
                correction = correction - r;
                weight = weight + weight;
            }
            corrections[i] = to_block(correction);
        }
        macoro::sync_wait(sender.sendChosen(messages, prng, socket));
        macoro::sync_wait(socket.send(corrections));
        macoro::sync_wait(socket.flush());
    } else {
        oc::BitVector choices(count);
        for (std::size_t i = 0; i < c.batch; ++i) {
            for (std::size_t j = 0; j < c.bits; ++j) {
                const auto limb = j < 64 ? in.beta[i].low : in.beta[i].high;
                choices[i * c.bits + j] = (limb >> (j % 64)) & 1;
            }
        }
        oc::AlignedUnVector<oc::block> received(count);
        macoro::sync_wait(receiver.receiveChosen(choices, received, prng, socket));
        std::vector<oc::block> corrections(c.batch);
        macoro::sync_wait(socket.recv(corrections));
        res.output.reserve(c.batch);
        for (std::size_t i = 0; i < c.batch; ++i) {
            auto y = from_block(corrections[i]);
            for (std::size_t j = 0; j < c.bits; ++j)
                y = y + from_block(received[i * c.bits + j]);
            res.output.push_back(y.is_zero());
        }
    }
    res.online_ms = timer.stop_ms();
    res.bytes_sent = socket.bytesSent();
    res.bytes_recv = socket.bytesReceived();
    res.online_bytes_sent = res.bytes_sent - res.setup_bytes_sent;
    res.online_bytes_recv = res.bytes_recv - res.setup_bytes_recv;
    res.n_ot = count + (c.party == 1 ? sender.baseOtCount() : receiver.baseOtCount());
    res.n_field_ops = -1;
    std::vector<std::uint8_t> token(1, 0xa5);
    if (c.party == 1) {
        macoro::sync_wait(socket.send(token));
        macoro::sync_wait(socket.recv(token));
    } else {
        macoro::sync_wait(socket.recv(token));
        macoro::sync_wait(socket.send(token));
    }
    macoro::sync_wait(socket.flush());
    res.note = "classical_bit_decomposition_ole chosen_iknp independent_nonzero_slopes "
               "private_rng=os_csprng no_noisy_code_assumption independent_session_setup "
               "post_metric_liveness_barrier";
    return res;
}
}  // namespace bench
int main(int argc, char** argv) { return bench::driver_main(argc, argv); }
