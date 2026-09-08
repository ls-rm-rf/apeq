#include "ips_ole/core.h"
#include "in_memory_retriever.h"

#include <cstdint>
#include <iostream>
#include <string>
#include <vector>

namespace {

using apeq::ips_ole::Fp;

void emit_vector(const std::string& name, const std::vector<Fp>& values) {
  for (std::size_t i = 0; i < values.size(); ++i) {
    std::cout << name << '\t' << i << '\t' << values[i].to_hex() << '\n';
  }
}

}  // namespace

int main() {
  using namespace apeq::ips_ole;
  const auto params = OleParams::defaults();
  const auto public_seed = deterministic_test_seed();
  auto receiver_private_seed = public_seed;
  auto sender_private_seed = public_seed;
  for (auto& byte : receiver_private_seed) {
    byte = static_cast<std::uint8_t>(byte ^ 0x5aU);
  }
  for (auto& byte : sender_private_seed) {
    byte = static_cast<std::uint8_t>(byte ^ 0xa5U);
  }
  constexpr std::uint64_t session_id = 0x0102030405060708ULL;
  OleReceiver receiver(params, public_seed, receiver_private_seed, session_id);
  OleSender sender(params, public_seed, sender_private_seed, session_id);

  std::vector<Fp> x;
  std::vector<Fp> a;
  std::vector<Fp> b;
  for (std::size_t i = 0; i < params.t; ++i) {
    x.push_back(Fp::from_u64(1000 + i));
    a.push_back(Fp::from_u64(2000 + 3 * i));
    b.push_back(Fp::from_u64(3000 + 5 * i));
  }
  const auto encoding = receiver.encode(x);
  const auto offered = sender.respond(encoding, a, b);
  testing::InMemoryRetriever retriever(offered);
  const auto retrieved = receiver.retrieve(retriever);
  const auto y = receiver.reconstruct(retrieved);

  std::cout << "meta\tsession_id\t0102030405060708\n";
  std::cout << "meta\tbatch_counter\t" << encoding.batch_counter << '\n';
  emit_vector("input_points", receiver.public_points().input_points());
  emit_vector("codeword_points", receiver.public_points().codeword_points());
  emit_vector("x", x);
  emit_vector("a", a);
  emit_vector("b", b);
  emit_vector("v", encoding.values);
  emit_vector("w", offered);
  emit_vector("y", y);
  return 0;
}
