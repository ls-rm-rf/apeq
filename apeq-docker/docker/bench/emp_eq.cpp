// ============================================================================
// emp_eq.cpp -- equality baseline on EMP-toolkit (semi-honest, Yao).
//
// Built against the exact EMP 0.3 revisions pinned in Dockerfile.emp. The
// receive counter is supplied by the audited patch in docker/patches/.
//
// Reports EMP's *equality* circuit, not a comparison circuit. The pinned EMP
// Integer::equal path is bitwise XOR followed by an AND reduction; substituting
// an ordering comparator would overstate EMP's cost and make our numbers look
// better than they are.
// ============================================================================

#include "driver_common.h"
#include "counting_io.h"

#include <emp-tool/emp-tool.h>
#include <emp-sh2pc/emp-sh2pc.h>

#include <limits>
#include <memory>

using namespace emp;

namespace bench {

ProtocolResult run_protocol(const Config& c, const Inputs& in) {
    ProtocolResult res;
    Timer t;

    // Establish the transport before timing. NetIO's constructor blocks on A
    // until B's container is launched; including that host scheduling delay
    // would inflate only A's setup and would not measure protocol work.
    NetIO* raw = new NetIO(c.party == 1 ? nullptr : c.host.c_str(), c.port);

    // EMP's NetIO already tracks payload in `counter`. Prefer it over a
    // wrapper so we are counting exactly what EMP itself sends.
    raw->counter = 0;
    raw->recv_counter = 0;  // added by patches/emp-tool-0.3.0-recv-counter.patch

    // ---- setup: base OTs + OT extension ---------------------------------
    t.start();
    setup_semi_honest(raw, c.party);   // base OTs + OT extension happen here

    raw->flush();
    res.setup_bytes_sent = raw->counter;
    res.setup_bytes_recv = raw->recv_counter;
    res.setup_ms = t.stop_ms();

    // ---- online: garble and evaluate the equality circuit ---------------
    t.start();

    const int L = static_cast<int>(c.bits);
    if (c.batch > static_cast<uint64_t>(std::numeric_limits<int>::max()) ||
        c.batch > static_cast<uint64_t>(std::numeric_limits<int>::max()) /
                      static_cast<uint64_t>(L)) {
        die("EMP's batched feed/reveal API is limited to INT_MAX wires");
    }

    // Feeding and revealing one equality at a time serializes the two traffic
    // directions: B sends one input, then A sends one garbled circuit/output,
    // so a batch of n comparisons appears to take n network rounds.  EMP's
    // protocol API accepts many wires at once.  Flatten all inputs, feed each
    // owner exactly once, build every circuit, and reveal every output in one
    // call.  This is the same collection of independent equality circuits,
    // but it exposes Yao's constant-round execution instead of a driver loop.
    const int wire_count = static_cast<int>(c.batch * static_cast<uint64_t>(L));
    std::unique_ptr<bool[]> alpha_plain(new bool[wire_count]);
    std::unique_ptr<bool[]> beta_plain(new bool[wire_count]);
    std::vector<Bit> alpha_wires(static_cast<size_t>(wire_count));
    std::vector<Bit> beta_wires(static_cast<size_t>(wire_count));

    for (uint64_t i = 0; i < c.batch; ++i) {
        const size_t base = static_cast<size_t>(i) * static_cast<size_t>(L);
        const uint64_t alpha = in.alpha[i].as_u64();
        const uint64_t beta = in.beta[i].as_u64();
        for (int j = 0; j < L; ++j) {
            alpha_plain[base + static_cast<size_t>(j)] =
                ((alpha >> j) & 1ULL) != 0;
            beta_plain[base + static_cast<size_t>(j)] =
                ((beta >> j) & 1ULL) != 0;
        }
    }

    ProtocolExecution::prot_exec->feed(
        reinterpret_cast<block*>(alpha_wires.data()), ALICE,
        alpha_plain.get(), wire_count);
    ProtocolExecution::prot_exec->feed(
        reinterpret_cast<block*>(beta_wires.data()), BOB,
        beta_plain.get(), wire_count);

    std::vector<block> equality_labels(static_cast<size_t>(c.batch));
    for (uint64_t i = 0; i < c.batch; ++i) {
        const size_t base = static_cast<size_t>(i) * static_cast<size_t>(L);
        Bit eq(true, PUBLIC);
        for (int j = 0; j < L; ++j) {
            const size_t k = base + static_cast<size_t>(j);
            eq = eq & (alpha_wires[k] == beta_wires[k]);
        }
        equality_labels[static_cast<size_t>(i)] = eq.bit;
    }

    std::unique_ptr<bool[]> revealed(new bool[static_cast<size_t>(c.batch)]());
    ProtocolExecution::prot_exec->reveal(
        revealed.get(), BOB, equality_labels.data(), static_cast<int>(c.batch));

    raw->flush();
    res.online_ms = t.stop_ms();

    // ---- accounting ------------------------------------------------------
    // NetIO tracks only what this party sent. The peer's row supplies the other
    // direction, and validate.py cross-checks the two.
    res.bytes_sent = raw->counter;
    res.bytes_recv = raw->recv_counter;
    res.online_bytes_sent = res.bytes_sent - res.setup_bytes_sent;
    res.online_bytes_recv = res.bytes_recv - res.setup_bytes_recv;
    res.n_ot = 0;                   // ADJUST: OT count is not exposed directly;
                                    // leave 0 rather than guessing.
    res.n_field_ops = -1;           // not meaningful for a Boolean circuit

    if (c.party == 2) {
        res.output.resize(static_cast<size_t>(c.batch));
        for (uint64_t i = 0; i < c.batch; ++i)
            res.output[static_cast<size_t>(i)] = revealed[i] ? 1 : 0;
    }

    res.note = "emp_yao batched_feed_and_reveal independent_session_setup";

    // The generator can finish writing before the evaluator has consumed the
    // final garbled gates on a delayed link.  Keep both endpoints alive until
    // both measured online phases are complete.  Counters and timers above are
    // intentionally sampled first.  NetIO::sync uses its internal I/O methods,
    // so its one-byte-each-way lifecycle barrier is not reported as protocol
    // work; it also uses the server/client ordering required by this stdio-based
    // channel instead of making both endpoints switch direction at once.
    raw->sync();

    finalize_semi_honest();
    delete raw;
    return res;
}

}  // namespace bench

int main(int argc, char** argv) { return bench::driver_main(argc, argv); }
