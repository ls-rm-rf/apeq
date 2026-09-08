#include "driver_common.h"
#include <cassert>
#include <iostream>

int main() {
    using namespace bench;
    assert(parse_application_value(" \t00042 \r") == 42);
    assert(parse_application_value("0") == 0);
    assert(parse_application_value("18446744073709551615") == UINT64_MAX);
    unsigned rejected = 0;
    for (const char* s : {"", " \t", "-1", "+1", "1.0", "1e3", "0x10", "1,2",
                          "18446744073709551616", "12x"}) {
        try { parse_application_value(s); }
        catch (const std::exception&) { ++rejected; }
    }
    assert(rejected == 10);
    char directory[] = "/tmp/v5-input-test-XXXXXX";
    if (!mkdtemp(directory)) return 2;
    const std::string base(directory);
    auto put = [&](const std::string& name, const std::string& body) {
        std::ofstream f(base+"/"+name); f << body;
    };
    put("pairs.csv", "pair_id\np0\np1\np2\n");
    put("values.csv", "pair_id,value\np0, 00042 \np1,18446744073709551615\np2,42\n");
    Config c;
    c.batch = 3;
    c.private_input = base+"/values.csv";
    c.pair_manifest = base+"/pairs.csv";
    for (int role : {1, 2}) {
        c.party = role;
        std::vector<std::string> ids;
        const auto in = read_application_inputs(c, ids);
        const auto& own = role == 1 ? in.alpha : in.beta;
        const auto& peer = role == 1 ? in.beta : in.alpha;
        assert(in.expected.empty());
        assert(own[0].low == 42 && own[1].low == UINT64_MAX && own[2].low == 42);
        for (auto v : peer) assert(v.low == 0 && v.high == 0);
    }
    auto must_fail = [&]() {
        std::vector<std::string> ids;
        try { read_application_inputs(c, ids); }
        catch (const std::exception&) { ++rejected; return; }
        throw std::runtime_error("invalid private input unexpectedly accepted");
    };
    put("values.csv", "pair_id,value\np1,1\np0,2\np2,3\n"); must_fail();
    put("values.csv", "pair_id,value\np0,1\np1,2\n"); must_fail();
    put("values.csv", "pair_id,value\np0,1\np1,2\np2,3\np3,4\n"); must_fail();
    put("values.csv", "pair_id,value\np0,1\np1,2\np2,3\n");
    put("pairs.csv", "pair_id\np0\np0\np2\n"); must_fail();
    c.private_input = base+"/missing.csv"; must_fail();
    std::remove((base+"/values.csv").c_str());
    std::remove((base+"/pairs.csv").c_str());
    rmdir(base.c_str());
    std::cout << "PASS: uint64 boundaries; 15 invalid-input cases; both roles contain only local inputs; no truth vector\n";
}
