// ============================================================================
// apeq_vole_eq.cpp -- end-to-end APEQ equality using random silent VOLE.
//
// Preprocessing gives Alice (Delta, B_i) and Bob (C_i, A_i) such that
//
//                    A_i = B_i + C_i * Delta  in GF(2^128).
//
// Online, Bob sends D_i = C_i + beta_i. Alice replies with
//
//     H(sid, context, i, B_i + Delta * (D_i + alpha_i)).
//
// Bob compares this digest with H(sid, context, i, A_i). For equal inputs the two
// values are identical. For unequal inputs, non-zero Delta makes their field
// values distinct and the only false-positive event is a 128-bit hash
// collision (random-oracle model). Alice samples Delta until it is non-zero.
// ============================================================================

#include "driver_common.h"
#include "request_socket.h"
#include "apeq_vole_digest.h"

#include <coproto/Socket/AsioSocket.h>
#include <cryptoTools/Crypto/RandomOracle.h>
#include <libOTe/TwoChooseOne/SoftSpokenOT/SoftSpokenMalOtExt.h>
#include <libOTe/Vole/Silent/SilentVoleReceiver.h>
#include <libOTe/Vole/Silent/SilentVoleSender.h>
#include <macoro/sync_wait.h>

#include <limits>

namespace oc = osuCrypto;

namespace bench {

namespace {

oc::block encode_input(const InputValue& value) {
    return oc::block(value.high, value.low);
}

bool is_zero(const oc::block& value) {
    return value == oc::ZeroBlock;
}

uint64_t logical_ot_count(uint64_t silent_base_count) {
    // genSilentBaseOts first seeds one SoftSpoken direction with direct base
    // OTs, extends `silent_base_count` PPRF OTs plus a reverse-direction base,
    // and the reverse direction then supplies 128 OTs to noisy VOLE.
    oc::SoftSpokenMalOtSender extension;
    const uint64_t base = extension.baseOtCount();
    return base + silent_base_count + base + 128;
}

}  // namespace

ProtocolResult run_protocol(const Config& c, const Inputs& in) {
    ProtocolResult res;
    if (c.variant != "vole_hash" || c.backend != "ferret_vole")
        throw std::invalid_argument("APEQ-VOLE requires vole_hash/ferret_vole");
    if (c.field_bits != 128)
        throw std::invalid_argument("APEQ-VOLE requires --field-bits 128");
    if (c.security_param != 128)
        throw std::invalid_argument("APEQ-VOLE requires --kappa 128");
    if (c.batch > static_cast<uint64_t>(std::numeric_limits<oc::u64>::max()))
        throw std::invalid_argument("APEQ-VOLE batch exceeds u64");

    coproto::Socket chl = request_socket(c);
    const auto sent_before = chl.bytesSent();
    const auto recv_before = chl.bytesReceived();
    const auto request_domain = c.sequence_requests ? c.request_index : UINT64_MAX;

    // Protocol coins are private and intentionally not derived from the public
    // workload seed recorded in CSV. Repetitions remain input-reproducible
    // without making either party's VOLE state reconstructible by its peer.
    oc::PRNG prng(oc::sysRandomSeed());
    oc::CoeffCtxGF128 field;
    oc::SilentVoleSender<oc::block, oc::block, oc::CoeffCtxGF128> sender;
    oc::SilentVoleReceiver<oc::block, oc::block, oc::CoeffCtxGF128> receiver;
    sender.mMultType = oc::DefaultMultType;
    receiver.mMultType = oc::DefaultMultType;
    sender.mMalType = oc::SilentSecType::SemiHonest;
    receiver.mMalType = oc::SilentSecType::SemiHonest;
    sender.configure(c.batch, oc::SilentBaseType::BaseExtend, 128);
    receiver.configure(c.batch, oc::SilentBaseType::BaseExtend, 128);

    oc::AlignedUnVector<oc::block> sender_b(c.party == 1 ? c.batch : 0);
    oc::AlignedUnVector<oc::block> receiver_c(c.party == 2 ? c.batch : 0);
    oc::AlignedUnVector<oc::block> receiver_a(c.party == 2 ? c.batch : 0);
    oc::block delta = oc::ZeroBlock;
    if (c.party == 1) {
        do delta = prng.get<oc::block>(); while (is_zero(delta));
    }

    // ---- setup: base-OT bootstrap, then silent-VOLE generation ----------
    Timer timer;
    timer.start();
    // Each role contributes a fresh private 256-bit nonce. Both nonces and
    // their transport are charged to setup; the workload seed is never a sid.
    std::vector<std::uint8_t> local_nonce(32), peer_nonce(32);
    prng.get(local_nonce.data(), local_nonce.size());
    macoro::sync_wait(chl.send(local_nonce));
    macoro::sync_wait(chl.recv(peer_nonce));
    VoleSessionId sid{};
    const auto& holder_nonce = c.party == 1 ? local_nonce : peer_nonce;
    const auto& querier_nonce = c.party == 2 ? local_nonce : peer_nonce;
    std::copy(holder_nonce.begin(), holder_nonce.end(), sid.begin());
    std::copy(querier_nonce.begin(), querier_nonce.end(), sid.begin() + 32);
    const double session_bind_ms = timer.stop_ms();
    const auto session_bind_sent = chl.bytesSent() - sent_before;
    const auto session_bind_recv = chl.bytesReceived() - recv_before;
    timer.start();
    uint64_t silent_base_count = 0;
    if (c.party == 1) {
        silent_base_count = sender.silentBaseOtCount();
        macoro::sync_wait(sender.genSilentBaseOts(prng, chl, delta));
    } else {
        silent_base_count = receiver.silentBaseOtCount();
        macoro::sync_wait(receiver.genSilentBaseOts(prng, chl));
    }
    const double base_ot_ms = timer.stop_ms();
    const uint64_t base_ot_sent = chl.bytesSent() - sent_before - session_bind_sent;
    const uint64_t base_ot_recv = chl.bytesReceived() - recv_before - session_bind_recv;

    timer.start();
    if (c.party == 1) {
        macoro::sync_wait(sender.silentSend(delta, sender_b, prng, chl));
    } else {
        macoro::sync_wait(receiver.silentReceive(receiver_c, receiver_a,
                                                 prng, chl));
    }
    macoro::sync_wait(chl.flush());
    const double silent_vole_ms = timer.stop_ms();
    res.setup_ms = session_bind_ms + base_ot_ms + silent_vole_ms;
    res.setup_bytes_sent = chl.bytesSent() - sent_before;
    res.setup_bytes_recv = chl.bytesReceived() - recv_before;
    const uint64_t silent_vole_sent = res.setup_bytes_sent - base_ot_sent - session_bind_sent;
    const uint64_t silent_vole_recv = res.setup_bytes_recv - base_ot_recv - session_bind_recv;
    res.n_ot = logical_ot_count(silent_base_count);

    // ---- online: one correction message and one digest reply -----------
    timer.start();
    std::vector<uint8_t> output;
    if (c.party == 2) {
        std::vector<oc::block> corrections(c.batch);
        std::vector<oc::block> expected_hashes(c.batch);
        for (uint64_t i = 0; i < c.batch; ++i) {
            oc::block beta = encode_input(in.beta[i]);
            field.plus(corrections[i], receiver_c[i], beta);
            expected_hashes[i] = vole_digest(sid, c.bits, c.batch, i, receiver_a[i], request_domain);
        }
        macoro::sync_wait(chl.send(corrections));

        std::vector<oc::block> holder_hashes(c.batch);
        macoro::sync_wait(chl.recv(holder_hashes));
        output.resize(c.batch);
        for (uint64_t i = 0; i < c.batch; ++i)
            output[i] = (expected_hashes[i] == holder_hashes[i]) ? 1 : 0;
        res.n_field_ops = static_cast<int64_t>(c.batch);
    } else {
        std::vector<oc::block> corrections(c.batch);
        macoro::sync_wait(chl.recv(corrections));
        std::vector<oc::block> hashes(c.batch);
        for (uint64_t i = 0; i < c.batch; ++i) {
            oc::block alpha = encode_input(in.alpha[i]);
            oc::block adjusted_input;
            oc::block product;
            oc::block adjusted_share;
            field.plus(adjusted_input, corrections[i], alpha);
            field.mul(product, delta, adjusted_input);
            field.plus(adjusted_share, sender_b[i], product);
            hashes[i] = vole_digest(sid, c.bits, c.batch, i, adjusted_share, request_domain);
        }
        macoro::sync_wait(chl.send(hashes));
        res.n_field_ops = static_cast<int64_t>(3 * c.batch);
    }
    macoro::sync_wait(chl.flush());
    res.online_ms = timer.stop_ms();

    res.bytes_sent = chl.bytesSent() - sent_before;
    res.bytes_recv = chl.bytesReceived() - recv_before;
    res.online_bytes_sent = res.bytes_sent - res.setup_bytes_sent;
    res.online_bytes_recv = res.bytes_recv - res.setup_bytes_recv;
    if (c.party == 2) res.output = std::move(output);

    // A large final hash vector can still be in the receiver's TCP/coproto
    // pipeline after the holder has flushed and sampled its counters.  Keep
    // the holder alive until the querier has consumed that vector and finished
    // its local comparison.  The barrier is deliberately after every metric
    // snapshot, so its time and bytes are lifecycle-only and never reported as
    // protocol work.
    std::vector<std::uint8_t> liveness_token(1, 0xa5U);
    if (c.party == 1) {
        macoro::sync_wait(chl.send(liveness_token));
        macoro::sync_wait(chl.recv(liveness_token));
    } else {
        macoro::sync_wait(chl.recv(liveness_token));
        macoro::sync_wait(chl.send(liveness_token));
    }
    macoro::sync_wait(chl.flush());

    char note[800];
    std::snprintf(note, sizeof note,
                  "silent_vole gf128 semi_honest nonzero_delta blake2b_128 "
                  "rom_error_2^-128 explicit_complete_vole_setup "
                  "sid=two_private_256_bit_nonces context=v2_bits_batch_coordinate "
                  "session_bind_ms=%.3f session_bind_sent=%llu session_bind_recv=%llu "
                  "base_ot_ms=%.3f base_ot_sent=%llu base_ot_recv=%llu "
                  "silent_vole_ms=%.3f silent_vole_sent=%llu "
                  "silent_vole_recv=%llu "
                  "logical_ot_count=%llu private_protocol_coins_not_logged "
                  "plaintext_output_to_B independent_session_setup "
                  "post_metric_liveness_barrier",
                  session_bind_ms,
                  static_cast<unsigned long long>(session_bind_sent),
                  static_cast<unsigned long long>(session_bind_recv),
                  base_ot_ms,
                  static_cast<unsigned long long>(base_ot_sent),
                  static_cast<unsigned long long>(base_ot_recv),
                  silent_vole_ms,
                  static_cast<unsigned long long>(silent_vole_sent),
                  static_cast<unsigned long long>(silent_vole_recv),
                  static_cast<unsigned long long>(res.n_ot));
    res.note = note;
    if (c.sequence_requests)
        res.note += " request_domain=v3 fresh_crypto_setup_per_request opened_connections=" +
                    std::to_string(opened_request_connections());
    return res;
}

}  // namespace bench

int main(int argc, char** argv) { return bench::driver_main(argc, argv); }
