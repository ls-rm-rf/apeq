// ============================================================================
// volepsi_eq.cpp -- equality baseline derived from the OPRF layer of volepsi
// (Rindal-Schoppmann, reference [54]).
//
// WHY THE OPRF LAYER AND NOT PSI
//
// volepsi implements set intersection, not a batch equality with one-sided
// output. Running PSI on t singleton sets would measure the OKVS encoding and
// set-handling machinery that a standalone equality test does not need, and
// would overstate this baseline's cost. We therefore drive the OPRF layer
// directly: the holder evaluates the OPRF on alpha_i, the querier obliviously
// evaluates it on beta_i, and equality is the equality of the two outputs.
//
// This is the fairer comparison, and it is also the construction our own VOLE
// variant is built from -- so the two rows differ only in what we added, which
// is the point.
// ============================================================================

#include "driver_common.h"

#include <volePSI/RsOprf.h>
#include <coproto/Socket/AsioSocket.h>
#include <macoro/sync_wait.h>

#include <limits>

namespace oc = osuCrypto;

namespace bench {

ProtocolResult run_protocol(const Config& c, const Inputs& in) {
    ProtocolResult res;
    if (c.field_bits != 128)
        throw std::invalid_argument("volepsi RsOprf requires --field-bits 128");
    if (c.security_param != 128)
        throw std::invalid_argument("this volepsi build requires --kappa 128");
    if (c.batch > static_cast<uint64_t>(std::numeric_limits<oc::u64>::max()))
        throw std::invalid_argument("volepsi batch exceeds u64");

    // TCP establishment is transport initialization and is excluded from the
    // protocol timers, consistently with the other baseline drivers.
    const std::string endpoint = c.host + ":" + std::to_string(c.port);
    coproto::Socket chl = coproto::asioConnect(endpoint, c.party == 1);

    // Keep protocol coins private. The CSV seed reproduces only the workload;
    // deriving OPRF/VOLE coins from that public value would let either party
    // reconstruct its peer's masks from the published benchmark row.
    oc::PRNG prng(oc::sysRandomSeed());
    volePSI::RsOprfSender sender;
    volePSI::RsOprfReceiver receiver;
    sender.mMalicious = false;
    receiver.mMalicious = false;
    sender.mSsp = 40;
    receiver.mSsp = 40;
    sender.setMultType(oc::DefaultMultType);
    receiver.setMultType(oc::DefaultMultType);

    // ---- setup: input-independent silent-VOLE preprocessing -------------
    // Pinned RsOprf exposes genVole(), but its send/receive path normally
    // invokes it lazily.  The audited volepsi-rsoprf-preprocess.patch lets the
    // next OPRF call consume this preprocessed correlation, so base OT and the
    // complete silent-VOLE expansion are measured in setup for both parties.
    Timer t;
    t.start();
    // Use the same forked sub-channel as the upstream lazy path. Besides
    // preserving message ordering, this keeps framing bytes byte-for-byte
    // identical so the fairness audit can prove that only the phase boundary
    // moved.
    auto vole_chl = chl.fork();
    if (c.party == 1) {
        sender.mPaxos.init(c.batch, sender.mBinSize, 3, sender.mSsp,
                           volePSI::PaxosParam::GF128, oc::ZeroBlock);
        sender.mD = prng.get();
        macoro::sync_wait(sender.genVole(prng, vole_chl,
                                         /*reducedRounds=*/false));
        sender.mVolePreprocessed = true;
    } else {
        volePSI::Baxos sizing;
        sizing.init(c.batch, receiver.mBinSize, 3, receiver.mSsp,
                    volePSI::PaxosParam::GF128, oc::ZeroBlock);
        macoro::sync_wait(receiver.genVole(sizing.size(), prng, vole_chl,
                                           /*reducedRounds=*/false));
        receiver.mVolePreprocessed = true;
    }
    macoro::sync_wait(vole_chl.flush());
    macoro::sync_wait(chl.flush());
    res.setup_ms = t.stop_ms();

    const uint64_t setup_sent = chl.bytesSent();
    const uint64_t setup_recv = chl.bytesReceived();
    res.setup_bytes_sent = setup_sent;
    res.setup_bytes_recv = setup_recv;

    // ---- online ----------------------------------------------------------
    t.start();

    std::vector<oc::block> keys(c.batch);
    std::vector<uint8_t> out;

    if (c.party == 1) {
        // Holder: acts as OPRF sender, then evaluates on its own inputs.
        macoro::sync_wait(sender.send(c.batch, prng, chl));
        std::vector<oc::block> alpha_blk(c.batch);
        for (uint64_t i = 0; i < c.batch; ++i)
            // RsOprf uses a Paxos set encoder and therefore requires distinct
            // keys.  Domain-separating by coordinate preserves coordinate-wise
            // equality while allowing repeated values in a batch.
            alpha_blk[i] = oc::block(i, in.alpha[i].as_u64());
        sender.eval(alpha_blk, keys);
        // Send the holder's OPRF outputs so the querier can compare. This is
        // the same one-message pattern our VOLE variant uses.
        macoro::sync_wait(chl.send(keys));
    } else {
        // Querier: obliviously evaluates the OPRF at its own inputs.
        std::vector<oc::block> beta_blk(c.batch);
        for (uint64_t i = 0; i < c.batch; ++i)
            beta_blk[i] = oc::block(i, in.beta[i].as_u64());
        macoro::sync_wait(receiver.receive(beta_blk, keys, prng, chl));

        std::vector<oc::block> theirs(c.batch);
        macoro::sync_wait(chl.recv(theirs));

        out.resize(c.batch);
        for (uint64_t i = 0; i < c.batch; ++i)
            out[i] = (keys[i] == theirs[i]) ? 1 : 0;
    }

    macoro::sync_wait(chl.flush());
    res.online_ms = t.stop_ms();

    res.bytes_sent = chl.bytesSent();
    res.bytes_recv = chl.bytesReceived();
    res.online_bytes_sent = res.bytes_sent - res.setup_bytes_sent;
    res.online_bytes_recv = res.bytes_recv - res.setup_bytes_recv;
    res.n_ot = 0;
    res.n_field_ops = -1;
    if (c.party == 2) res.output = std::move(out);

    // The holder's final OPRF-output vector has the same one-way large-message
    // lifecycle risk as APEQ-VOLE: flush completion does not imply that the
    // querier has consumed and compared the full vector.  Synchronize only
    // after all timers and counters are sampled, keeping this barrier outside
    // the measured protocol transcript.
    std::vector<std::uint8_t> liveness_token(1, 0xa5U);
    if (c.party == 1) {
        macoro::sync_wait(chl.send(liveness_token));
        macoro::sync_wait(chl.recv(liveness_token));
    } else {
        macoro::sync_wait(chl.recv(liveness_token));
        macoro::sync_wait(chl.send(liveness_token));
    }
    macoro::sync_wait(chl.flush());

    char buf[256];
    std::snprintf(buf, sizeof buf,
                  "rs_oprf semi_honest kappa=128 ssp=40 mult=libote_default "
                  "setup_sent=%llu setup_recv=%llu "
                  "coordinate_domain_separated explicit_silent_vole_setup "
                  "private_protocol_coins_not_logged plaintext_output_to_B "
                  "independent_session_setup post_metric_liveness_barrier",
                  (unsigned long long)setup_sent,
                  (unsigned long long)setup_recv);
    res.note = buf;
    return res;
}

}  // namespace bench

int main(int argc, char** argv) { return bench::driver_main(argc, argv); }
