// ============================================================================
// csv_row.h -- shared by every baseline driver and by APEQ itself.
//
// One row per party per execution, in the exact field order of
// spec/measurement-framework.md section 1. Nothing else in the codebase writes
// to results.csv. If a driver needs a field this header does not expose, add it
// here and to the spec together -- never emit an ad-hoc column.
// ============================================================================
#pragma once

#include <chrono>
#include <cstdint>
#include <cstdio>
#include <string>
#include <sys/resource.h>

namespace bench {

struct Row {
    std::string run_id;          // UUIDv4, IDENTICAL on both parties
    std::string timestamp_utc;
    std::string git_commit;
    std::string hostname;

    std::string protocol;        // apeq | emp_eq | aby_eq | cryptflow2_eq | volepsi_eq
    std::string backend = "n/a"; // ips_ole | ferret_vole | n/a
    std::string variant = "n/a"; // ole | vole_hash | n/a

    uint64_t batch_size = 0;
    uint32_t input_bits = 0;
    uint32_t field_bits = 0;
    uint32_t security_param = 128;   // MANDATORY. See spec section 1.

    std::string network;         // lan | wan
    double rtt_ms = 0;           // the CONFIGURED tc value
    double bandwidth_mbps = 0;

    uint32_t rep = 0;
    uint64_t seed = 0;

    char party = 'B';            // 'A' holder, 'B' querier

    double setup_ms = -1;
    double online_ms = -1;

    uint64_t setup_bytes_sent = 0;
    uint64_t setup_bytes_recv = 0;
    uint64_t online_bytes_sent = 0;
    uint64_t online_bytes_recv = 0;
    uint64_t bytes_sent = 0;
    uint64_t bytes_recv = 0;

    uint64_t n_ot = 0;
    int64_t  n_field_ops = -1;

    bool correct = false;
    int64_t n_false_pos = -1;    // party A always writes -1
    int64_t n_false_neg = -1;

    std::string status = "ok";   // ok | timeout | oom | crash | skipped
    std::string note;            // MUST NOT contain a comma
};

inline uint64_t peak_rss_kb() {
    struct rusage ru{};
    getrusage(RUSAGE_SELF, &ru);
    return static_cast<uint64_t>(ru.ru_maxrss);   // KiB on Linux
}

inline std::string sanitise(std::string s) {
    for (char& c : s) {
        if (c == ',' || c == '\n' || c == '\r') c = ' ';
    }
    return s;
}

inline void write_header(std::FILE* f) {
    std::fprintf(f,
        "run_id,timestamp_utc,git_commit,hostname,"
        "protocol,backend,variant,"
        "batch_size,input_bits,field_bits,security_param,"
        "network,rtt_ms,bandwidth_mbps,"
        "rep,seed,"
        "party,"
        "setup_ms,online_ms,total_ms,"
        "setup_bytes_sent,setup_bytes_recv,"
        "online_bytes_sent,online_bytes_recv,"
        "bytes_sent,bytes_recv,"
        "peak_rss_kb,"
        "n_ot,n_field_ops,"
        "correct,n_false_pos,n_false_neg,"
        "status,note\n");
}

inline void write_row(std::FILE* f, const Row& r) {
    const bool ok = (r.status == "ok");
    // Non-ok runs leave timing and byte fields EMPTY. Never substitute a value:
    // validate.py treats a populated timing field on a non-ok row as an error,
    // and a figure that averages over substituted values is misleading.
    char setup[32] = "", online[32] = "", total[32] = "";
    char setup_sent[32] = "", setup_recv[32] = "";
    char online_sent[32] = "", online_recv[32] = "";
    char sent[32] = "", recv[32] = "";
    if (ok) {
        std::snprintf(setup,  sizeof setup,  "%.3f", r.setup_ms);
        std::snprintf(online, sizeof online, "%.3f", r.online_ms);
        std::snprintf(total,  sizeof total,  "%.3f", r.setup_ms + r.online_ms);
        std::snprintf(setup_sent, sizeof setup_sent, "%llu",
                      (unsigned long long)r.setup_bytes_sent);
        std::snprintf(setup_recv, sizeof setup_recv, "%llu",
                      (unsigned long long)r.setup_bytes_recv);
        std::snprintf(online_sent, sizeof online_sent, "%llu",
                      (unsigned long long)r.online_bytes_sent);
        std::snprintf(online_recv, sizeof online_recv, "%llu",
                      (unsigned long long)r.online_bytes_recv);
        std::snprintf(sent,   sizeof sent,   "%llu", (unsigned long long)r.bytes_sent);
        std::snprintf(recv,   sizeof recv,   "%llu", (unsigned long long)r.bytes_recv);
    }

    std::fprintf(f,
        "%s,%s,%s,%s,"
        "%s,%s,%s,"
        "%llu,%u,%u,%u,"
        "%s,%.3f,%.3f,"
        "%u,%llu,"
        "%c,"
        "%s,%s,%s,"
        "%s,%s,%s,%s,"
        "%s,%s,"
        "%llu,"
        "%llu,%lld,"
        "%s,%lld,%lld,"
        "%s,%s\n",
        r.run_id.c_str(), r.timestamp_utc.c_str(), r.git_commit.c_str(),
        r.hostname.c_str(),
        r.protocol.c_str(), r.backend.c_str(), r.variant.c_str(),
        (unsigned long long)r.batch_size, r.input_bits, r.field_bits,
        r.security_param,
        r.network.c_str(), r.rtt_ms, r.bandwidth_mbps,
        r.rep, (unsigned long long)r.seed,
        r.party,
        setup, online, total,
        setup_sent, setup_recv, online_sent, online_recv,
        sent, recv,
        (unsigned long long)peak_rss_kb(),
        (unsigned long long)r.n_ot, (long long)r.n_field_ops,
        ok ? (r.correct ? "true" : "false") : "",
        (long long)r.n_false_pos, (long long)r.n_false_neg,
        r.status.c_str(), sanitise(r.note).c_str());
    std::fflush(f);   // flush per row: a crashed run must not lose its predecessors
}

// ---------------------------------------------------------------------------
// Timing. Both parties time themselves; never use the shell's `time`, and never
// time only one side. Take timestamps inside the party object so that process
// startup and argument parsing are excluded.
// ---------------------------------------------------------------------------
class Timer {
public:
    void start() { t0_ = clock::now(); }
    double stop_ms() {
        auto dt = clock::now() - t0_;
        return std::chrono::duration<double, std::milli>(dt).count();
    }
private:
    using clock = std::chrono::steady_clock;   // NOT system_clock: not monotonic
    clock::time_point t0_{};
};

}  // namespace bench
