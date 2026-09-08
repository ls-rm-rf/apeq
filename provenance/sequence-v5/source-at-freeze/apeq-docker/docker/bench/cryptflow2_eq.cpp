// ============================================================================
// cryptflow2_eq.cpp -- equality baseline on CrypTFlow2 / SCI (semi-honest, OT).
//
// SCI offers both OT-based and HE-based protocols. This driver uses the
// OT-based millionaire/equality primitive. The paper MUST state which one the
// CrypTFlow2 row refers to; the previous version of this work conflated them.
// ============================================================================

#include "driver_common.h"

#include "Millionaire/equality.h"
#include "utils/emp-tool.h"
#include "OT/emp-ot.h"

#include <limits>
#include <memory>

namespace bench {

ProtocolResult run_protocol(const Config& c, const Inputs& in) {
    ProtocolResult res;
    const int party = c.party;    // SCI uses 1 = ALICE, 2 = BOB, same as ours
    if (c.batch > static_cast<uint64_t>(std::numeric_limits<int>::max())) {
        throw std::invalid_argument("SCI equality batch exceeds int");
    }
    const int batch = static_cast<int>(c.batch);

    // ---- setup: IO + OT extension ---------------------------------------
    // Establishing the three SCI TCP channels is transport initialization,
    // not cryptographic setup, and is excluded just as in the EMP driver.
    std::unique_ptr<sci::IOPack> iopack(
        new sci::IOPack(party, c.port, c.host));
    Timer t;
    t.start();
    std::unique_ptr<sci::OTPack> otpack(new sci::OTPack(iopack.get(), party));

    // SCI's base OT and OT-extension setup happens in the OTPack constructor.
    iopack->io->flush();
    const uint64_t setup_sent = iopack->get_comm();
    const uint64_t setup_recv = iopack->get_recv_comm();
    res.setup_bytes_sent = setup_sent;
    res.setup_bytes_recv = setup_recv;
    res.setup_ms = t.stop_ms();

    // ---- online ----------------------------------------------------------
    t.start();

    std::unique_ptr<Equality> eq(
        new Equality(party, iopack.get(), otpack.get(), c.bits,
                     /*radix_base=*/4));

    std::vector<uint8_t> shares(c.batch, 0);
    std::vector<uint64_t> mine(c.batch);
    for (uint64_t i = 0; i < c.batch; ++i)
        mine[i] = (party == 1) ? in.alpha[i].as_u64()
                               : in.beta[i].as_u64();

    // Batched call: one invocation for the whole batch, not a loop. SCI
    // amortises its OT usage across the batch, and calling it per comparison
    // would misrepresent the protocol.
    eq->check_equality(shares.data(), mine.data(), batch, c.bits,
                       /*radix_base=*/4);

    // ---- output reconstruction -------------------------------------------
    // IMPORTANT: SCI returns a *secret share* of the equality bit, whereas APEQ
    // hands the querier a plaintext bit. Reconstruction below costs one extra
    // message, which is included in the byte counts. This functionality
    // difference must be stated in the evaluation section -- it is not a
    // like-for-like comparison and pretending otherwise is exactly the kind of
    // thing a reviewer will catch.
    if (party == 1) {
        iopack->io->send_data(shares.data(), batch);
    } else {
        std::vector<uint8_t> other(c.batch);
        iopack->io->recv_data(other.data(), batch);
        res.output.resize(c.batch);
        for (uint64_t i = 0; i < c.batch; ++i)
            res.output[i] = static_cast<uint8_t>((shares[i] ^ other[i]) & 1);
    }
    iopack->io->flush();
    res.online_ms = t.stop_ms();

    res.bytes_sent = iopack->get_comm();
    res.bytes_recv = iopack->get_recv_comm();
    res.online_bytes_sent = res.bytes_sent - res.setup_bytes_sent;
    res.online_bytes_recv = res.bytes_recv - res.setup_bytes_recv;
    res.n_ot = 0;
    res.n_field_ops = -1;

    char buf[192];
    std::snprintf(buf, sizeof buf,
                  "sci_ot radix=4 setup_sent=%llu setup_recv=%llu "
                  "shared_output_reconstructed independent_session_setup",
                  (unsigned long long)setup_sent,
                  (unsigned long long)setup_recv);
    res.note = buf;
    return res;
}

}  // namespace bench

int main(int argc, char** argv) { return bench::driver_main(argc, argv); }
