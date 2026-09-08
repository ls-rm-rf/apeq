// ============================================================================
// aby_eq.cpp -- equality baselines on ABY (semi-honest Yao and GMW).
//
// Verified against the ABY commit pinned in Dockerfile.aby.
//
// ABY reports Setup and Online separately in its own timing struct. Take those
// values rather than wrapping the whole call, so the split matches the spec
// instead of approximating it.
//
// Sharing choice is explicit in --variant: "yao" selects S_YAO and "gmw"
// selects S_BOOL.  The two variants are emitted as separate rows and must
// never be averaged: Yao is the constant-round competitor, while GMW exposes
// the depth-dependent round tradeoff.
// ============================================================================

#include "driver_common.h"

#include <abycore/aby/abyparty.h>
#include <abycore/circuit/booleancircuits.h>
#include <abycore/circuit/share.h>
#include <abycore/sharing/sharing.h>

#include <cstdlib>
#include <limits>

namespace bench {

ProtocolResult run_protocol(const Config& c, const Inputs& in) {
    ProtocolResult res;

    e_sharing sharing;
    const char* sharing_note;
    if (c.variant == "yao") {
        sharing = S_YAO;
        sharing_note = "aby_yao S_YAO";
    } else if (c.variant == "gmw") {
        sharing = S_BOOL;
        sharing_note = "aby_gmw S_BOOL";
    } else {
        throw std::invalid_argument(
            "ABY requires --variant yao or --variant gmw");
    }

    const e_role role = (c.party == 1) ? SERVER : CLIENT;
    const uint32_t bitlen = c.bits;
    if (c.batch > std::numeric_limits<uint32_t>::max()) {
        throw std::invalid_argument("ABY SIMD batch exceeds uint32_t");
    }
    const uint32_t nvals = static_cast<uint32_t>(c.batch);
    // This is ABY's number of OT communication channels, not an application
    // worker-thread tuning knob. Keep the upstream constructor default.
    const uint32_t nthreads = 2;

    // driver_common.h accepts exactly 80- or 128-bit security parameters.
    const seclvl sl = (c.security_param == 80) ? ST : LT;

    ABYParty* party = new ABYParty(role, c.host, c.port, sl, bitlen,
                                   nthreads, MT_OT);

    std::vector<Sharing*>& sharings = party->GetSharings();
    BooleanCircuit* circ =
        dynamic_cast<BooleanCircuit*>(sharings[sharing]->GetCircuitBuildRoutine());
    if (circ == nullptr) {
        delete party;
        throw std::runtime_error("ABY selected sharing has no BooleanCircuit");
    }

    // ABY's native SIMD representation packs the whole batch into one wire per
    // input bit. This is the same batching path used by ABY's own operation
    // tests and avoids charging the framework for t independent output gates.
    // ABY's legacy API is not const-correct; InternalPutINGate only reads these
    // arrays while packing them into SIMD wires.
    std::vector<uint64_t> alpha_plain(nvals);
    std::vector<uint64_t> beta_plain(nvals);
    for (uint32_t i = 0; i < nvals; ++i) {
        alpha_plain[i] = in.alpha[i].as_u64();
        beta_plain[i] = in.beta[i].as_u64();
    }
    share* sa = circ->PutSIMDINGate(
        nvals, alpha_plain.data(), bitlen, SERVER);
    share* sb = circ->PutSIMDINGate(
        nvals, beta_plain.data(), bitlen, CLIENT);
    share* eq = circ->PutEQGate(sa, sb);
    // One-sided output: reveal to CLIENT (the querier) only.
    share* out = circ->PutOUTGate(eq, CLIENT);

    // ABY performs Naor-Pinkas base OTs in ConnectAndBaseOTs(), before
    // ExecCircuit() starts P_TOTAL/P_SETUP recording. Invoke it explicitly and
    // include P_BASE_OT below; otherwise roughly 50 KiB per direction and its
    // RTT cost disappear from the benchmark even though every other driver
    // includes base OT in setup.
    party->ConnectAndBaseOTs();
    party->ExecCircuit();

    // ---- timing, taken from ABY's own counters --------------------------
    res.setup_ms  = party->GetTiming(P_BASE_OT) + party->GetTiming(P_SETUP);
    res.online_ms = party->GetTiming(P_ONLINE);

    res.setup_bytes_sent =
        party->GetSentData(P_BASE_OT) + party->GetSentData(P_SETUP);
    res.setup_bytes_recv =
        party->GetReceivedData(P_BASE_OT) + party->GetReceivedData(P_SETUP);
    res.online_bytes_sent = party->GetSentData(P_ONLINE);
    res.online_bytes_recv = party->GetReceivedData(P_ONLINE);
    res.bytes_sent = res.setup_bytes_sent + res.online_bytes_sent;
    res.bytes_recv = res.setup_bytes_recv + res.online_bytes_recv;
    res.n_ot = 0;                 // not exposed; leave 0 rather than guessing
    res.n_field_ops = -1;

    if (c.party == 2) {
        uint64_t* clear = nullptr;
        uint32_t out_bitlen = 0;
        uint32_t out_nvals = 0;
        out->get_clear_value_vec(&clear, &out_bitlen, &out_nvals);
        if (out_bitlen != 1 || out_nvals != nvals || clear == nullptr) {
            std::free(clear);
            throw std::runtime_error("ABY returned an unexpected SIMD output shape");
        }
        res.output.resize(nvals);
        for (uint32_t i = 0; i < nvals; ++i) {
            res.output[i] = static_cast<uint8_t>(clear[i] & 1U);
        }
        std::free(clear);
    }

    res.note = std::string(sharing_note) +
               " explicit_base_ot_in_setup independent_session_setup";
    delete party;
    return res;
}

}  // namespace bench

int main(int argc, char** argv) { return bench::driver_main(argc, argv); }
