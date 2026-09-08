// End-to-end APEQ equality over the audited IPS-OLE/libOTe backend.
// Alice holds alpha, Bob holds beta. Alice samples nonzero a and sets
// b=-a*alpha; Bob receives y=a*beta+b=a*(beta-alpha), hence y=0 iff equal.

#include "driver_common.h"

#include "ips_ole/core.h"
#include "ips_ole/labels.h"
#include "libote_retriever.h"

#include <coproto/Socket/AsioSocket.h>
#include <cryptoTools/Crypto/PRNG.h>
#include <macoro/sync_wait.h>

#include <algorithm>
#include <array>
#include <cstdint>
#include <iomanip>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <vector>

namespace oc = osuCrypto;
namespace ips = apeq::ips_ole;

namespace bench {
namespace {

std::vector<std::uint8_t> be64(std::uint64_t value) {
    std::vector<std::uint8_t> result(8);
    for (std::size_t i = 0; i < result.size(); ++i) {
        result[result.size() - 1 - i] =
            static_cast<std::uint8_t>(value & 0xffU);
        value >>= 8U;
    }
    return result;
}

oc::block fp_to_block(const ips::Fp& value) {
    const std::string hex = value.to_hex();
    const auto high = std::stoull(hex.substr(0, 16), nullptr, 16);
    const auto low = std::stoull(hex.substr(16, 16), nullptr, 16);
    return oc::block(high, low);
}

ips::Fp block_to_fp(const oc::block& value) {
    const auto words = value.get<std::uint64_t>();
    std::ostringstream encoded;
    encoded << std::hex << std::setfill('0') << std::setw(16) << words[1]
            << std::setw(16) << words[0];
    return ips::Fp::from_hex(encoded.str());
}

std::uint64_t splitmix64(std::uint64_t value) {
    value += 0x9e3779b97f4a7c15ULL;
    value = (value ^ (value >> 30U)) * 0xbf58476d1ce4e5b9ULL;
    value = (value ^ (value >> 27U)) * 0x94d049bb133111ebULL;
    return value ^ (value >> 31U);
}

InputValue dummy_value(const Config& c, std::uint64_t index, int party) {
    const auto base = c.seed ^ (index * 0xd6e8feb86659fd93ULL) ^
                      static_cast<std::uint64_t>(party);
    InputValue value;
    value.low = splitmix64(base);
    if (c.bits > 64) value.high = splitmix64(base ^ 0xa0761d6478bd642fULL);
    return mask_input(value, c.bits);
}

ips::Fp input_to_fp(const InputValue& value) {
    if (value.high == 0) return ips::Fp::from_u64(value.low);
    std::ostringstream encoded;
    encoded << std::hex << std::setfill('0') << std::setw(16) << value.high
            << std::setw(16) << value.low;
    return ips::Fp::from_hex(encoded.str());
}

}  // namespace

ProtocolResult run_protocol(const Config& c, const Inputs& in) {
    if (c.variant != "ole" || c.backend != "ips_ole") {
        throw std::invalid_argument("APEQ IPS-OLE requires ole/ips_ole labels");
    }
    if (c.field_bits != 127 || c.security_param != 128) {
        throw std::invalid_argument(
            "APEQ IPS-OLE requires field_bits=127 and kappa=128");
    }

    ProtocolResult res;
    const ips::OleParams params{
        c.ole_n, c.ole_rho, c.ole_ell, c.ole_k, c.ole_t};
    params.validate();
    const std::uint64_t groups = (c.batch + params.t - 1) / params.t;
    const std::uint64_t padded = groups * params.t;

    const std::string endpoint = c.host + ":" + std::to_string(c.port);
    coproto::Socket socket = coproto::asioConnect(endpoint, c.party == 1);

    std::unique_ptr<ips::OleReceiver> ole_receiver;
    std::unique_ptr<ips::OleSender> ole_sender;
    std::unique_ptr<ips::LibOteReceiverRetriever> ot_receiver;
    std::unique_ptr<ips::LibOteSenderRetriever> ot_sender;
    std::unique_ptr<ips::Prng> coefficient_prng;

    Timer timer;
    timer.start();
    const auto private_seed = ips::random_master_seed();
    oc::PRNG libote_prng(oc::sysRandomSeed());
    if (c.party == 1) {
        std::vector<oc::block> wire_points(params.k + params.n);
        macoro::sync_wait(socket.recv(wire_points));
        std::vector<ips::Fp> input_points, codeword_points;
        for (std::size_t i = 0; i < wire_points.size(); ++i) {
            (i < params.k ? input_points : codeword_points)
                .push_back(block_to_fp(wire_points[i]));
        }
        ips::PublicPoints points(params, std::move(input_points),
                                 std::move(codeword_points));
        ole_sender = std::make_unique<ips::OleSender>(
            params, std::move(points), private_seed, c.seed);
        coefficient_prng = std::make_unique<ips::Prng>(ips::derive_key(
            private_seed, std::string(ips::labels::kEqualityA), be64(c.seed)));
        ot_sender = std::make_unique<ips::LibOteSenderRetriever>(socket, libote_prng);
        ot_sender->setup();
    } else {
        auto points = ips::PublicPoints::random(params);
        std::vector<oc::block> wire_points;
        wire_points.reserve(params.k + params.n);
        for (const auto& point : points.input_points())
            wire_points.push_back(fp_to_block(point));
        for (const auto& point : points.codeword_points())
            wire_points.push_back(fp_to_block(point));
        macoro::sync_wait(socket.send(wire_points));
        ole_receiver = std::make_unique<ips::OleReceiver>(
            params, std::move(points), private_seed, c.seed);
        ot_receiver =
            std::make_unique<ips::LibOteReceiverRetriever>(socket, libote_prng);
        ot_receiver->setup();
    }
    macoro::sync_wait(socket.flush());
    res.setup_ms = timer.stop_ms();
    res.setup_bytes_sent = socket.bytesSent();
    res.setup_bytes_recv = socket.bytesReceived();

    timer.start();
    if (c.party == 2) {
        res.output.reserve(c.batch);
    }
    if (c.party == 2) {
        std::vector<oc::block> wire_encodings;
        wire_encodings.reserve(groups * params.n);
        std::vector<std::vector<ips::Fp>> all_x;
        all_x.reserve(groups);
        for (std::uint64_t group = 0; group < groups; ++group) {
            std::vector<ips::Fp> x(params.t, ips::Fp::zero());
            for (std::size_t slot = 0; slot < params.t; ++slot) {
                const auto index = group * params.t + slot;
                const auto value = index < c.batch
                    ? in.beta[index]
                    : dummy_value(c, index, 2);
                x[slot] = input_to_fp(value);
            }
            all_x.push_back(std::move(x));
        }
        const auto encodings = ole_receiver->encode_many(all_x);
        for (const auto& encoding : encodings) {
            for (const auto& value : encoding.values) {
                wire_encodings.push_back(fp_to_block(value));
            }
        }
        macoro::sync_wait(socket.send(wire_encodings));
        const auto retrieved = ole_receiver->retrieve_many(*ot_receiver);
        const auto outputs = ole_receiver->reconstruct_many(retrieved);
        for (std::uint64_t group = 0; group < groups; ++group) {
            const auto& y = outputs[group];
            const auto active = static_cast<std::size_t>(
                std::min<std::uint64_t>(params.t, c.batch - group * params.t));
            for (std::size_t slot = 0; slot < active; ++slot) {
                res.output.push_back(y[slot].is_zero() ? 1U : 0U);
            }
        }
    } else {
        std::vector<oc::block> wire_encodings(groups * params.n);
        macoro::sync_wait(socket.recv(wire_encodings));
        std::vector<ips::Fp> all_offered;
        all_offered.reserve(groups * params.n);
        for (std::uint64_t group = 0; group < groups; ++group) {
            ips::Encoding encoding;
            encoding.batch_counter = group + 1;
            encoding.values.reserve(params.n);
            const auto begin = wire_encodings.begin() + group * params.n;
            for (auto it = begin; it != begin + params.n; ++it) {
                encoding.values.push_back(block_to_fp(*it));
            }

            std::vector<ips::Fp> a(params.t, ips::Fp::zero());
            std::vector<ips::Fp> b(params.t, ips::Fp::zero());
            for (std::size_t slot = 0; slot < params.t; ++slot) {
                const auto index = group * params.t + slot;
                do {
                    a[slot] = coefficient_prng->random_fp();
                } while (a[slot].is_zero());
                const auto alpha = input_to_fp(
                    index < c.batch ? in.alpha[index]
                                    : dummy_value(c, index, 1));
                b[slot] = ips::Fp::zero() - a[slot] * alpha;
            }
            const auto offered = ole_sender->respond(encoding, a, b);
            all_offered.insert(all_offered.end(), offered.begin(), offered.end());
        }
        ot_sender->send(all_offered);
    }
    // The OT sender owns the large final outbound message.  Flush it before
    // taking the metric snapshot so the sender's counter mirrors what the
    // receiver consumed.  The receiver must stay out of a pre-barrier flush:
    // it still has local reconstruction work after the OT transcript ends.
    if (c.party == 1) {
        macoro::sync_wait(socket.flush());
    }
    res.online_ms = timer.stop_ms();
    res.bytes_sent = socket.bytesSent();
    res.bytes_recv = socket.bytesReceived();
    res.online_bytes_sent = res.bytes_sent - res.setup_bytes_sent;
    res.online_bytes_recv = res.bytes_recv - res.setup_bytes_recv;
    res.n_ot = c.party == 1 ? ot_sender->ots_consumed()
                            : ot_receiver->ots_consumed();
    res.n_field_ops = -1;

    // Keep the holder alive until the querier has finished its local
    // reconstruction.  This liveness-only barrier is deliberately after all
    // metric snapshots, so it cannot inflate the protocol's measured bytes or
    // effective round count.
    std::vector<std::uint8_t> liveness_token(1, 0xa5U);
    if (c.party == 1) {
        macoro::sync_wait(socket.send(liveness_token));
        macoro::sync_wait(socket.recv(liveness_token));
    } else {
        macoro::sync_wait(socket.recv(liveness_token));
        macoro::sync_wait(socket.send(liveness_token));
    }
    macoro::sync_wait(socket.flush());

    char note[512];
    std::snprintf(note, sizeof note,
                  "apeq_ole perfect_correctness groups=%llu padded=%llu "
                  "all_groups_one_encoding_message one_batched_iknp_extension "
                  "dummy_deterministic dummy_cost_counted private_rng=os_csprng "
                  "independent_session_setup post_metric_liveness_barrier "
                  "public_points=private_seed_sampler_explicit_wire_v2 "
                  "ole_n=%zu ole_rho=%zu ole_ell=%zu ole_k=%zu ole_t=%zu",
                  (unsigned long long)groups, (unsigned long long)padded,
                  params.n, params.rho, params.ell, params.k, params.t);
    res.note = note;
    return res;
}

}  // namespace bench

int main(int argc, char** argv) { return bench::driver_main(argc, argv); }
