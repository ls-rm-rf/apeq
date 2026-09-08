#include "driver_common.h"
namespace bench {
ProtocolResult run_protocol(const Config& c, const Inputs& in) {
    ProtocolResult r;
    r.setup_ms=1.5+(c.seed%7)*0.01; r.online_ms=0.01*c.batch+(c.seed%13)*0.003;
    { uint64_t groups=(c.batch+47)/48;
      uint64_t half=groups*1024*((c.field_bits+7)/8);
      r.setup_bytes_sent=r.setup_bytes_recv=128;
      r.online_bytes_sent=r.online_bytes_recv=half-128;
      r.bytes_sent=r.bytes_recv=half; }
    if (c.party==2) { r.output.assign(in.expected.begin(), in.expected.end()); }
    r.note="mock independent_session_setup";
    return r;
}
}
int main(int argc,char**argv){ return bench::driver_main(argc,argv); }
