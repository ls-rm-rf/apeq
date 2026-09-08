// ============================================================================
// driver_common.h -- shared scaffolding for every benchmark driver.
//
// Each baseline supplies only a `run_protocol` implementation; everything else
// (argument parsing, seeding, timing discipline, correctness checking, CSV
// emission) lives here so that all protocols are measured identically.
//
// Protocol-specific bodies still need per-library build verification. Keep
// argument parsing, input generation and CSV emission common to every driver.
// ============================================================================
#pragma once

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <ctime>
#include <fstream>
#include <iomanip>
#include <limits>
#include <random>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>
#include <unistd.h>

#include "csv_row.h"

namespace bench {

// ---------------------------------------------------------------------------
// Configuration, populated from argv. Every driver accepts the same flags so
// run_all.sh does not need per-protocol special cases.
// ---------------------------------------------------------------------------
struct Config {
    std::string protocol;
    std::string variant = "n/a";
    std::string backend = "n/a";
    uint64_t    batch = 1;
    uint32_t    bits = 32;
    uint32_t    field_bits = 128;
    uint32_t    security_param = 128;
    uint32_t    ole_n = 1024;
    uint32_t    ole_rho = 769;
    uint32_t    ole_ell = 255;
    uint32_t    ole_k = 128;
    uint32_t    ole_t = 48;
    std::string network = "lan";
    uint32_t    rep = 0;
    uint64_t    seed = 0;          // 0 => derive deterministically, see below
    int         party = 1;         // 1 = holder (A), 2 = querier (B)
    std::string host = "127.0.0.1";
    int         port = 12345;
    std::string run_id;
    std::string out = "results.csv";
    std::string note;
    std::string private_input;     // application mode: only this party's file
    std::string pair_manifest;     // public ordered pair identifiers; no values
    std::string equality_output;   // application mode: B only
    double      rtt_ms = 0;
    double      bandwidth_mbps = 0;
};

inline void die(const std::string& msg) { throw std::runtime_error(msg); }

inline Config parse_args(int argc, char** argv) {
    Config c;
    auto need = [&](int i) { if (i + 1 >= argc) die(std::string("missing value for ") + argv[i]); };
    for (int i = 1; i < argc; ++i) {
        std::string a = argv[i];
        if      (a == "--protocol") { need(i); c.protocol = argv[++i]; }
        else if (a == "--variant")  { need(i); c.variant  = argv[++i]; }
        else if (a == "--backend")  { need(i); c.backend  = argv[++i]; }
        else if (a == "--batch")    { need(i); c.batch    = std::stoull(argv[++i]); }
        else if (a == "--bits")     { need(i); c.bits     = std::stoul(argv[++i]); }
        else if (a == "--field-bits"){need(i); c.field_bits = std::stoul(argv[++i]); }
        else if (a == "--kappa")    { need(i); c.security_param = std::stoul(argv[++i]); }
        else if (a == "--ole-n")     { need(i); c.ole_n   = std::stoul(argv[++i]); }
        else if (a == "--ole-rho")   { need(i); c.ole_rho = std::stoul(argv[++i]); }
        else if (a == "--ole-ell")   { need(i); c.ole_ell = std::stoul(argv[++i]); }
        else if (a == "--ole-k")     { need(i); c.ole_k   = std::stoul(argv[++i]); }
        else if (a == "--ole-t")     { need(i); c.ole_t   = std::stoul(argv[++i]); }
        else if (a == "--network")  { need(i); c.network  = argv[++i]; }
        else if (a == "--rep")      { need(i); c.rep      = std::stoul(argv[++i]); }
        else if (a == "--seed")     { need(i); c.seed     = std::stoull(argv[++i]); }
        else if (a == "--party")    { need(i); c.party    = std::stoi(argv[++i]); }
        else if (a == "--host")     { need(i); c.host     = argv[++i]; }
        else if (a == "--port")     { need(i); c.port     = std::stoi(argv[++i]); }
        else if (a == "--run-id")   { need(i); c.run_id   = argv[++i]; }
        else if (a == "--out")      { need(i); c.out      = argv[++i]; }
        else if (a == "--note")     { need(i); c.note     = argv[++i]; }
        else if (a == "--private-input") { need(i); c.private_input = argv[++i]; }
        else if (a == "--pair-manifest") { need(i); c.pair_manifest = argv[++i]; }
        else if (a == "--equality-output") { need(i); c.equality_output = argv[++i]; }
        else if (a == "--rtt")      { need(i); c.rtt_ms   = std::stod(argv[++i]); }
        else if (a == "--bandwidth"){ need(i); c.bandwidth_mbps = std::stod(argv[++i]); }
        else die("unknown argument: " + a);
    }
    if (c.protocol.empty()) die("--protocol is required");
    if (c.run_id.empty())   die("--run-id is required and must match on both parties");
    if (c.party != 1 && c.party != 2)
        die("--party must be 1 (holder/A) or 2 (querier/B)");
    if (c.batch == 0)
        die("--batch must be positive");
    const uint32_t max_input_bits = c.protocol == "apeq" ? 126U : 64U;
    if (c.bits == 0 || c.bits > max_input_bits) {
        die("--bits must be in 1.." + std::to_string(max_input_bits) +
            (c.protocol == "apeq"
                 ? "; APEQ uses an injective two-limb encoding below 2^126"
                 : "; this baseline is restricted to its uint64_t adapter"));
    }
    if (c.security_param != 80 && c.security_param != 128)
        die("--kappa must be 80 or 128; the field is mandatory in every row");
    if (!c.private_input.empty() || !c.pair_manifest.empty() || !c.equality_output.empty()) {
        if (c.private_input.empty() || c.pair_manifest.empty() || c.bits != 64)
            die("application mode requires private input, manifest and exactly 64 input bits");
        if ((c.party == 2) != !c.equality_output.empty())
            die("application equality output is required for B and forbidden for A");
    }

    // Both parties must generate the SAME inputs, so the seed is derived from
    // the run identity rather than from the clock. Passing --seed overrides.
    if (c.seed == 0) {
        std::hash<std::string> h;
        c.seed = h(c.run_id + "|" + std::to_string(c.batch) + "|" +
                   std::to_string(c.bits) + "|" + std::to_string(c.rep));
        if (c.seed == 0) c.seed = 1;
    }
    return c;
}

// ---------------------------------------------------------------------------
// Inputs. Both parties derive the full plaintext pair from the shared seed;
// each then uses only its own half. This lets either party check the output
// against a reference without an extra protocol message.
//
// Roughly half the coordinates are made equal on purpose: a batch of uniformly
// random pairs would almost never exercise the equal branch, and a false
// negative there would go unnoticed.
// ---------------------------------------------------------------------------
struct InputValue {
    uint64_t low = 0;
    uint64_t high = 0;

    uint64_t as_u64() const {
        if (high != 0)
            die("wide input reached a uint64_t-only baseline adapter");
        return low;
    }

    bool operator==(const InputValue& other) const {
        return low == other.low && high == other.high;
    }

    bool operator!=(const InputValue& other) const { return !(*this == other); }
};

inline InputValue mask_input(InputValue value, uint32_t bits) {
    if (bits <= 64) {
        value.high = 0;
        if (bits < 64) value.low &= (uint64_t{1} << bits) - 1U;
    } else {
        const uint32_t high_bits = bits - 64;
        value.high &= (uint64_t{1} << high_bits) - 1U;
    }
    return value;
}

inline InputValue random_input(std::mt19937_64& rng, uint32_t bits) {
    // Preserve the exact historical PRNG draw count for every 1..64-bit
    // workload. Wide APEQ inputs consume a second word for the high limb.
    InputValue value;
    value.low = rng();
    if (bits > 64) value.high = rng();
    return mask_input(value, bits);
}

struct Inputs {
    std::vector<InputValue> alpha;   // holder
    std::vector<InputValue> beta;    // querier
    std::vector<uint8_t>  expected;
};

inline Inputs make_inputs(const Config& c) {
    Inputs in;
    in.alpha.resize(c.batch);
    in.beta.resize(c.batch);
    in.expected.resize(c.batch);

    std::mt19937_64 rng(c.seed);
    for (uint64_t i = 0; i < c.batch; ++i) {
        InputValue a = random_input(rng, c.bits);
        bool equal = (rng() & 1) != 0;
        InputValue b = equal ? a : random_input(rng, c.bits);
        if (!equal && b == a) b.low ^= 1ULL;   // keep the label honest
        in.alpha[i] = a;
        in.beta[i]  = b;
        in.expected[i] = (a == b) ? 1 : 0;
    }
    return in;
}

// ---------------------------------------------------------------------------
// Result returned by each protocol implementation.
// ---------------------------------------------------------------------------
struct ProtocolResult {
    double   setup_ms = 0;
    double   online_ms = 0;
    uint64_t setup_bytes_sent = 0;
    uint64_t setup_bytes_recv = 0;
    uint64_t online_bytes_sent = 0;
    uint64_t online_bytes_recv = 0;
    uint64_t bytes_sent = 0;
    uint64_t bytes_recv = 0;
    uint64_t n_ot = 0;
    int64_t  n_field_ops = -1;
    std::vector<uint8_t> output;   // querier only; empty for the holder
    std::string note;
};

// Supplied by each baseline.
ProtocolResult run_protocol(const Config& c, const Inputs& in);

// ---------------------------------------------------------------------------
// Correctness. Only the querier holds an output; the holder writes -1, per the
// spec's reporting convention.
// ---------------------------------------------------------------------------
struct Correctness {
    bool ok = false;
    int64_t false_pos = -1;
    int64_t false_neg = -1;
};

inline Correctness check(const Config& c, const Inputs& in,
                         const ProtocolResult& r) {
    Correctness out;
    if (c.party != 2) return out;   // holder: leaves -1/-1, ok stays false below

    if (r.output.size() != c.batch) {
        out.ok = false;
        out.false_pos = out.false_neg = -1;
        return out;
    }
    int64_t fp = 0, fn = 0;
    for (uint64_t i = 0; i < c.batch; ++i) {
        if (r.output[i] && !in.expected[i]) ++fp;
        if (!r.output[i] && in.expected[i]) ++fn;
    }
    out.false_pos = fp;
    out.false_neg = fn;
    out.ok = (fp == 0 && fn == 0);
    return out;
}

// ---------------------------------------------------------------------------
// Environment metadata.
// ---------------------------------------------------------------------------
inline std::string iso_now() {
    std::time_t t = std::time(nullptr);
    char buf[32];
    std::strftime(buf, sizeof buf, "%Y-%m-%dT%H:%M:%SZ", std::gmtime(&t));
    return buf;
}

inline std::string hostname() {
    char buf[256] = {0};
    if (gethostname(buf, sizeof buf - 1) != 0) return "unknown";
    return buf;
}

// GIT_COMMIT is injected at build time:
//   add_definitions(-DGIT_COMMIT="$(git rev-parse --short HEAD)$(dirty)")
// validate.py rejects a dataset spanning multiple commits and warns on -dirty.
#ifndef GIT_COMMIT
#define GIT_COMMIT "unknown"
#endif

inline void emit(const Config& c, const ProtocolResult& r,
                 const Correctness& k, const std::string& status,
                 const std::string& extra_note) {
    Row row;
    row.run_id = c.run_id;
    row.timestamp_utc = iso_now();
    row.git_commit = GIT_COMMIT;
    row.hostname = hostname();
    row.protocol = c.protocol;
    row.backend = c.backend;
    row.variant = c.variant;
    row.batch_size = c.batch;
    row.input_bits = c.bits;
    row.field_bits = c.field_bits;
    row.security_param = c.security_param;
    row.network = c.network;
    row.rtt_ms = c.rtt_ms;
    row.bandwidth_mbps = c.bandwidth_mbps;
    row.rep = c.rep;
    row.seed = c.seed;
    row.party = (c.party == 1) ? 'A' : 'B';
    row.setup_ms = r.setup_ms;
    row.online_ms = r.online_ms;
    row.setup_bytes_sent = r.setup_bytes_sent;
    row.setup_bytes_recv = r.setup_bytes_recv;
    row.online_bytes_sent = r.online_bytes_sent;
    row.online_bytes_recv = r.online_bytes_recv;
    row.bytes_sent = r.bytes_sent;
    row.bytes_recv = r.bytes_recv;
    row.n_ot = r.n_ot;
    row.n_field_ops = r.n_field_ops;
    row.correct = (c.party == 2) ? k.ok : true;
    row.n_false_pos = k.false_pos;
    row.n_false_neg = k.false_neg;
    row.status = status;
    row.note = r.note.empty() ? extra_note
                              : (r.note + " " + extra_note);

    bool need_header = (access(c.out.c_str(), F_OK) != 0);
    std::FILE* f = std::fopen(c.out.c_str(), "a");
    if (!f) { std::fprintf(stderr, "cannot open %s\n", c.out.c_str()); return; }
    if (need_header) write_header(f);
    write_row(f, row);
    std::fclose(f);
}

// ---------------------------------------------------------------------------
// Entry point shared by every driver. A failing run still emits a row: a
// silently missing row would break validate.py's pairing check, which is
// exactly the signal we want.
// ---------------------------------------------------------------------------
// The application mode never calls make_inputs or receives an expected vector.
// Its output is checked by a separate host-side verifier after both parties exit.
inline std::string trim_decimal(const std::string& s) {
    const auto first = s.find_first_not_of(" \t\r");
    if (first == std::string::npos) return "";
    return s.substr(first, s.find_last_not_of(" \t\r") - first + 1);
}

inline uint64_t parse_application_value(const std::string& raw) {
    const auto value = trim_decimal(raw);
    if (value.empty()) die("application field is missing");
    uint64_t out = 0;
    for (char ch : value) {
        if (ch < '0' || ch > '9') die("application field must be an unsigned decimal integer");
        const uint64_t digit = static_cast<uint64_t>(ch - '0');
        if (out > (std::numeric_limits<uint64_t>::max() - digit) / 10)
            die("application field exceeds uint64");
        out = out * 10 + digit;
    }
    return out;
}

inline Inputs read_application_inputs(const Config& c, std::vector<std::string>& ids) {
    std::ifstream manifest(c.pair_manifest), local(c.private_input);
    if (!manifest || !local) die("cannot open application input or manifest");
    std::string line;
    if (!std::getline(manifest, line) || trim_decimal(line) != "pair_id")
        die("invalid public manifest header");
    std::set<std::string> seen;
    while (std::getline(manifest, line)) {
        if (!line.empty() && line.back() == '\r') line.pop_back();
        if (line.empty() || line.find_first_not_of("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-") != std::string::npos
            || !seen.insert(line).second)
            die("invalid or duplicate public pair identifier");
        ids.push_back(line);
    }
    if (ids.size() != c.batch) die("public manifest batch mismatch");
    if (!std::getline(local, line) || trim_decimal(line) != "pair_id,value")
        die("invalid private input header");
    Inputs in;
    // ABY's API takes both buffers but reads each input only at its owner.
    // The other buffer contains zero placeholders, never the other party's data.
    in.alpha.resize(c.batch);
    in.beta.resize(c.batch);
    auto& own = c.party == 1 ? in.alpha : in.beta;
    for (std::size_t i = 0; i < ids.size(); ++i) {
        if (!std::getline(local, line)) die("private input has missing records");
        const auto comma = line.find(',');
        if (comma == std::string::npos || line.substr(0, comma) != ids[i])
            die("private record order does not match public manifest");
        own[i].low = parse_application_value(line.substr(comma + 1));
    }
    if (std::getline(local, line)) die("private input has extra records");
    if (manifest.bad() || local.bad()) die("application input read failed");
    return in;
}

inline std::string json_string(const std::string& s) {
    std::string out = "\"";
    for (unsigned char c : s) {
        if (c == '\\' || c == '\"') { out += '\\'; out += c; }
        else if (c < 32) out += ' ';
        else out += c;
    }
    return out + "\"";
}

inline int application_main(const Config& c) {
    Timer total, phase;
    total.start();
    phase.start();
    std::vector<std::string> ids;
    const Inputs in = read_application_inputs(c, ids);
    const double input_ms = phase.stop_ms();
    phase.start();
    const ProtocolResult r = run_protocol(c, in);
    const double protocol_call_ms = phase.stop_ms();
    phase.start();
    uint64_t equal_count = 0;
    if (c.party == 2) {
        if (r.output.size() != c.batch) die("application output batch mismatch");
        std::ofstream output(c.equality_output);
        if (!output) die("cannot open equality output");
        output << "pair_id,equal\n";
        for (std::size_t i = 0; i < ids.size(); ++i) {
            if (r.output[i] > 1) die("application output is not a bit");
            output << ids[i] << ',' << unsigned(r.output[i]) << '\n';
            equal_count += r.output[i];
        }
        output.close();
        if (!output) die("cannot write equality output");
    } else if (!r.output.empty()) die("holder must not receive equality output");
    const double output_ms = phase.stop_ms();
    const double application_ms = total.stop_ms();
    std::ofstream metrics(c.out);
    if (!metrics) die("cannot open application metrics");
    metrics << std::setprecision(17)
        << "{\n\"schema\":\"apeq-application-v5\",\n"
        << "\"run_id\":" << json_string(c.run_id) << ",\n"
        << "\"source_revision\":" << json_string(GIT_COMMIT) << ",\n"
        << "\"party\":" << c.party << ",\n"
        << "\"protocol\":" << json_string(c.protocol) << ",\n"
        << "\"backend\":" << json_string(c.backend) << ",\n"
        << "\"variant\":" << json_string(c.variant) << ",\n"
        << "\"batch\":" << c.batch << ",\n"
        << "\"input_bits\":" << c.bits << ",\n"
        << "\"field_bits\":" << c.field_bits << ",\n"
        << "\"nominal_kappa\":" << c.security_param << ",\n"
        << "\"network\":" << json_string(c.network) << ",\n"
        << "\"rep\":" << c.rep << ",\n"
        << "\"input_ms\":" << input_ms << ",\n"
        << "\"protocol_call_ms\":" << protocol_call_ms << ",\n"
        << "\"output_ms\":" << output_ms << ",\n"
        << "\"application_ms\":" << application_ms << ",\n"
        << "\"setup_ms\":" << r.setup_ms << ",\n"
        << "\"online_ms\":" << r.online_ms << ",\n"
        << "\"setup_bytes_sent\":" << r.setup_bytes_sent << ",\n"
        << "\"setup_bytes_recv\":" << r.setup_bytes_recv << ",\n"
        << "\"online_bytes_sent\":" << r.online_bytes_sent << ",\n"
        << "\"online_bytes_recv\":" << r.online_bytes_recv << ",\n"
        << "\"bytes_sent\":" << r.bytes_sent << ",\n"
        << "\"bytes_recv\":" << r.bytes_recv << ",\n"
        << "\"peak_rss_kb\":" << peak_rss_kb() << ",\n"
        << "\"n_ot\":" << r.n_ot << ",\n"
        << "\"equal_count\":" << (c.party == 2 ? std::to_string(equal_count) : "null") << ",\n"
        << "\"correct\":null,\n\"status\":\"completed_unverified\",\n"
        << "\"note\":" << json_string(r.note) << "\n}\n";
    metrics.close();
    if (!metrics) die("cannot write application metrics");
    return 0;
}

inline int driver_main(int argc, char** argv) {
    Config c;
    try {
        c = parse_args(argc, argv);
    } catch (const std::exception& e) {
        std::fprintf(stderr, "argument error: %s\n", e.what());
        return 2;
    }

    if (!c.private_input.empty()) {
        try { return application_main(c); }
        catch (const std::exception& e) {
            // Errors contain no private values. Failed runs are preserved by
            // the application harness and never converted to successful rows.
            std::fprintf(stderr, "application error: %s\n", e.what());
            return 4;
        }
    }

    Inputs in = make_inputs(c);

    try {
        ProtocolResult r = run_protocol(c, in);
        Correctness k = check(c, in, r);
        emit(c, r, k, "ok", c.note);
        if (c.party == 2 && !k.ok) {
            std::fprintf(stderr,
                "CORRECTNESS FAILURE: fp=%lld fn=%lld (%s/%s, batch %llu, %u bits)\n",
                (long long)k.false_pos, (long long)k.false_neg,
                c.protocol.c_str(), c.variant.c_str(),
                (unsigned long long)c.batch, c.bits);
            return 1;
        }
        return 0;
    } catch (const std::bad_alloc&) {
        ProtocolResult r; Correctness k;
        emit(c, r, k, "oom", c.note);
        return 3;
    } catch (const std::exception& e) {
        ProtocolResult r; Correctness k;
        emit(c, r, k, "crash", c.note + " " + e.what());
        return 4;
    }
}

}  // namespace bench
