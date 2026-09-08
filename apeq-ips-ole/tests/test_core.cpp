#include "ips_ole/core.h"
#include "in_memory_retriever.h"

#include <algorithm>
#include <atomic>
#include <cmath>
#include <cstdlib>
#include <exception>
#include <iostream>
#include <mutex>
#include <memory>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

#include <boost/multiprecision/cpp_int.hpp>

namespace {

using apeq::ips_ole::Fp;
using apeq::ips_ole::MasterSeed;
using apeq::ips_ole::OleParams;
using apeq::ips_ole::OleReceiver;
using apeq::ips_ole::OleSender;
using apeq::ips_ole::Polynomial;
using apeq::ips_ole::Prng;
using boost::multiprecision::cpp_int;

constexpr char kModulusHex[] = "7fffffffffffffffffffffffffffffff";

void require(bool condition, const std::string& message) {
  if (!condition) {
    throw std::runtime_error(message);
  }
}

cpp_int parse_hex(const std::string& value) {
  cpp_int result = 0;
  for (const char ch : value) {
    const unsigned digit = ch <= '9' ? static_cast<unsigned>(ch - '0')
                                     : static_cast<unsigned>(ch - 'a' + 10);
    result = (result << 4) + digit;
  }
  return result;
}

std::string to_hex(cpp_int value) {
  static constexpr char kDigits[] = "0123456789abcdef";
  std::string result(32, '0');
  for (std::size_t i = 0; i < result.size(); ++i) {
    result[result.size() - 1 - i] =
        kDigits[static_cast<unsigned>((value & 15).convert_to<unsigned>())];
    value >>= 4;
  }
  return result;
}

MasterSeed seed_with_offset(std::uint8_t offset) {
  auto seed = apeq::ips_ole::deterministic_test_seed();
  for (auto& byte : seed) {
    byte = static_cast<std::uint8_t>(byte + offset);
  }
  return seed;
}

std::size_t env_count(const char* name, std::size_t fallback) {
  const char* value = std::getenv(name);
  return value == nullptr ? fallback : std::stoull(value);
}

void test_field() {
  const cpp_int modulus = parse_hex(kModulusHex);
  Prng prng(seed_with_offset(1));
  const auto pairs = env_count("IPS_OLE_FIELD_PAIRS", 20000);
  const auto inverses = env_count("IPS_OLE_FIELD_INVERSES", 256);
  for (std::size_t i = 0; i < pairs; ++i) {
    const auto a = prng.random_fp();
    const auto b = prng.random_fp();
    const auto ai = parse_hex(a.to_hex());
    const auto bi = parse_hex(b.to_hex());
    require((a + b).to_hex() == to_hex((ai + bi) % modulus),
            "field addition mismatch");
    require((a - b).to_hex() == to_hex((ai - bi + modulus) % modulus),
            "field subtraction mismatch");
    require((a * b).to_hex() == to_hex((ai * bi) % modulus),
            "field multiplication mismatch");
    require(Fp::from_hex(a.to_hex()) == a, "field I/O round trip failed");
    if (i < inverses && !a.is_zero()) {
      const auto expected_inverse = boost::multiprecision::powm(ai, modulus - 2,
                                                                modulus);
      require(a.inv().to_hex() == to_hex(expected_inverse),
              "field inverse mismatch");
    }
  }
  bool rejected_modulus = false;
  try {
    (void)Fp::from_hex(kModulusHex);
  } catch (const std::out_of_range&) {
    rejected_modulus = true;
  }
  require(rejected_modulus, "Fp accepted the modulus as a field element");
  require(apeq::ips_ole::random_master_seed() !=
              apeq::ips_ole::random_master_seed(),
          "OS CSPRNG repeated a 256-bit master seed");
}

void test_polynomials() {
  std::vector<Fp> x{Fp::from_u64(1), Fp::from_u64(2), Fp::from_u64(4),
                    Fp::from_u64(8)};
  Polynomial original{Fp::from_u64(9), Fp::from_u64(7), Fp::from_u64(5),
                      Fp::from_u64(3)};
  std::vector<Fp> y;
  for (const auto& point : x) {
    y.push_back(apeq::ips_ole::evaluate(original, point));
  }
  const auto recovered = apeq::ips_ole::interpolate(x, y);
  require(recovered == original, "polynomial interpolation mismatch");

  Prng prng(seed_with_offset(2));
  const auto constrained = apeq::ips_ole::sample_constrained_polynomial(
      {x[0], x[1]}, {y[0], y[1]}, 7, prng);
  require(apeq::ips_ole::degree(constrained) <= 7,
          "constrained polynomial exceeds its degree bound");
  require(apeq::ips_ole::evaluate(constrained, x[0]) == y[0] &&
              apeq::ips_ole::evaluate(constrained, x[1]) == y[1],
          "constrained polynomial lost a constraint");

  Prng unique_prng(seed_with_offset(4));
  const auto unique = apeq::ips_ole::sample_constrained_polynomial(
      {x[0], x[1]}, {Fp::from_u64(5), Fp::from_u64(5)}, 1, unique_prng);
  require(apeq::ips_ole::degree(unique) == 0,
          "bounded-degree sampler forced an unnecessary leading coefficient");
}

void test_noise() {
  constexpr std::size_t n = 1024;
  constexpr std::size_t weight = 255;
  const auto samples = env_count("IPS_OLE_NOISE_SAMPLES", 20000);
  Prng prng(seed_with_offset(3));
  std::vector<std::size_t> marginal(n, 0);
  std::vector<std::pair<std::size_t, std::size_t>> pair_indices;
  std::vector<std::size_t> pair_counts(200, 0);
  for (std::size_t sample = 0; sample < pair_counts.size(); ++sample) {
    std::size_t i = (sample * 137 + 3) % n;
    std::size_t j = (sample * 293 + 11) % n;
    if (i == j) {
      j = (j + 1) % n;
    }
    pair_indices.emplace_back(i, j);
  }
  std::set<std::vector<std::size_t>> first_sets;
  for (std::size_t trial = 0; trial < samples; ++trial) {
    auto selected = apeq::ips_ole::sample_fixed_weight(n, weight, prng);
    require(selected.size() == weight, "fixed-weight sampler changed weight");
    std::sort(selected.begin(), selected.end());
    require(std::adjacent_find(selected.begin(), selected.end()) == selected.end(),
            "fixed-weight sampler returned a duplicate");
    if (trial < 64) {
      first_sets.insert(selected);
    }
    for (const auto i : selected) {
      ++marginal[i];
    }
    std::vector<bool> included(n, false);
    for (const auto i : selected) {
      included[i] = true;
    }
    for (std::size_t i = 0; i < pair_indices.size(); ++i) {
      if (included[pair_indices[i].first] && included[pair_indices[i].second]) {
        ++pair_counts[i];
      }
    }
  }
  require(first_sets.size() == 64, "consecutive fixed-weight samples repeated");

  const double p = static_cast<double>(weight) / n;
  const double marginal_sigma = std::sqrt(samples * p * (1.0 - p));
  double chi_square = 0.0;
  for (const auto count : marginal) {
    const double delta = static_cast<double>(count) - samples * p;
    require(std::abs(delta) <= 5.0 * marginal_sigma,
            "fixed-weight marginal exceeded five sigma");
    chi_square += delta * delta / (samples * p);
  }
  require(std::isfinite(chi_square), "noise chi-square is not finite");
  std::cout << "noise chi-square=" << chi_square << " samples=" << samples << '\n';

  const double pair_p = static_cast<double>(weight * (weight - 1)) /
                        static_cast<double>(n * (n - 1));
  const double pair_sigma = std::sqrt(samples * pair_p * (1.0 - pair_p));
  for (std::size_t sample = 0; sample < pair_counts.size(); ++sample) {
    const double delta = static_cast<double>(pair_counts[sample]) - samples * pair_p;
    require(std::abs(delta) <= 5.0 * pair_sigma,
            "fixed-weight pair frequency exceeded five sigma");
  }
}

std::vector<std::size_t> run_protocol_trial(const OleParams& params,
                                             const MasterSeed& seed,
                                             std::uint64_t session_id) {
  auto receiver_private_seed = seed;
  auto sender_private_seed = seed;
  for (auto& byte : receiver_private_seed) {
    byte = static_cast<std::uint8_t>(byte ^ 0x5aU);
  }
  for (auto& byte : sender_private_seed) {
    byte = static_cast<std::uint8_t>(byte ^ 0xa5U);
  }
  require(receiver_private_seed != sender_private_seed &&
              receiver_private_seed != seed && sender_private_seed != seed,
          "test seeds are not domain-separated");
  OleReceiver receiver(params, seed, receiver_private_seed, session_id);
  OleSender sender(params, seed, sender_private_seed, session_id);
  require(receiver.public_points().input_points() ==
              sender.public_points().input_points() &&
              receiver.public_points().codeword_points() ==
              sender.public_points().codeword_points(),
          "parties derived different public points");

  Prng input_prng(seed_with_offset(static_cast<std::uint8_t>(session_id)));
  std::vector<Fp> x(params.t, Fp::zero());
  std::vector<Fp> a(params.t, Fp::zero());
  std::vector<Fp> b(params.t, Fp::zero());
  for (std::size_t i = 0; i < params.t; ++i) {
    x[i] = input_prng.random_fp();
    a[i] = input_prng.random_fp();
    b[i] = input_prng.random_fp();
  }
  const auto encoding = receiver.encode(x);
  const auto offered = sender.respond(encoding, a, b);
  apeq::ips_ole::testing::InMemoryRetriever retriever(offered);
  const auto retrieved = receiver.retrieve(retriever);
  const auto first_choices = retriever.choices_seen_for_test();
  const auto y = receiver.reconstruct(retrieved);
  for (std::size_t i = 0; i < params.t; ++i) {
    require(y[i] == a[i] * x[i] + b[i], "IPS-OLE algebraic identity failed");
  }

  bool sender_rejected_reuse = false;
  try {
    (void)sender.respond(encoding, a, b);
  } catch (const std::logic_error&) {
    sender_rejected_reuse = true;
  }
  require(sender_rejected_reuse, "sender accepted a repeated batch counter");

  const auto second_encoding = receiver.encode(x);
  const auto second_offered = sender.respond(second_encoding, a, b);
  apeq::ips_ole::testing::InMemoryRetriever second_retriever(second_offered);
  const auto second_retrieved = receiver.retrieve(second_retriever);
  const auto second_y = receiver.reconstruct(second_retrieved);
  require(second_y == y, "consecutive batch changed the algebraic output");
  require(second_retriever.choices_seen_for_test() != first_choices,
          "consecutive batches reused the private fixed-weight set");
  return first_choices;
}

void test_batched_retrieval() {
  const OleParams params{48, 33, 15, 8, 3};
  const auto public_seed = seed_with_offset(101);
  const auto receiver_seed = seed_with_offset(102);
  const auto sender_seed = seed_with_offset(103);
  constexpr std::size_t groups = 3;

  OleReceiver receiver(params, public_seed, receiver_seed, 1);
  OleSender sender(params, public_seed, sender_seed, 1);
  std::vector<std::vector<Fp>> expected(groups);
  std::vector<std::vector<Fp>> inputs(groups);
  std::vector<std::vector<Fp>> coefficients_a(groups);
  std::vector<std::vector<Fp>> coefficients_b(groups);
  std::vector<Fp> all_offered;
  for (std::size_t group = 0; group < groups; ++group) {
    Prng prng(seed_with_offset(static_cast<std::uint8_t>(110 + group)));
    auto& x = inputs[group];
    auto& a = coefficients_a[group];
    auto& b = coefficients_b[group];
    x = std::vector<Fp>(params.t, Fp::zero());
    a = std::vector<Fp>(params.t, Fp::zero());
    b = std::vector<Fp>(params.t, Fp::zero());
    expected[group] = std::vector<Fp>(params.t, Fp::zero());
    for (std::size_t i = 0; i < params.t; ++i) {
      x[i] = prng.random_fp();
      a[i] = prng.random_fp();
      b[i] = prng.random_fp();
      expected[group][i] = a[i] * x[i] + b[i];
    }
  }
  const auto encodings = receiver.encode_many(inputs);
  for (std::size_t group = 0; group < groups; ++group) {
    const auto offered = sender.respond(
        encodings[group], coefficients_a[group], coefficients_b[group]);
    all_offered.insert(all_offered.end(), offered.begin(), offered.end());
  }

  apeq::ips_ole::testing::InMemoryRetriever retriever(
      std::move(all_offered));
  const auto retrieved = receiver.retrieve_many(retriever);
  require(retrieved.size() == groups,
          "batched retrieval returned the wrong group count");
  require(retriever.choices_seen_for_test().size() == groups * params.ell,
          "batched retrieval did not combine every private choice");
  const auto outputs = receiver.reconstruct_many(retrieved);
  for (std::size_t group = 0; group < groups; ++group) {
    require(outputs[group] == expected[group],
            "batched IPS-OLE algebraic identity failed");
  }
}

void test_secret_logging() {
  std::ostringstream captured_out;
  std::ostringstream captured_err;
  auto* old_out = std::cout.rdbuf(captured_out.rdbuf());
  auto* old_err = std::cerr.rdbuf(captured_err.rdbuf());
  try {
    (void)run_protocol_trial(OleParams{48, 33, 15, 8, 3}, seed_with_offset(91),
                             0x5151ULL);
  } catch (...) {
    std::cout.rdbuf(old_out);
    std::cerr.rdbuf(old_err);
    throw;
  }
  std::cout.rdbuf(old_out);
  std::cerr.rdbuf(old_err);
  require(captured_out.str().empty() && captured_err.str().empty(),
          "S1 failed: IPS-OLE protocol core wrote data to stdout/stderr");
}

void test_protocol() {
  const auto defaults = OleParams::defaults();
  require(defaults.n == 1024 && defaults.rho == 769 &&
              defaults.ell == 255 && defaults.k == 128 &&
              defaults.degree_p() == 127 &&
              defaults.degree_a() == 127 && defaults.degree_b() == 254,
          "default IPS-OLE degree parameters changed");
  const OleParams small{48, 33, 15, 8, 3};
  small.validate();
  test_batched_retrieval();
  const auto trials = env_count("IPS_OLE_PROTOCOL_TRIALS", 100);
  for (std::size_t trial = 0; trial < trials; ++trial) {
    run_protocol_trial(small, seed_with_offset(static_cast<std::uint8_t>(trial)),
                       trial + 1);
  }
  const auto default_trials = env_count("IPS_OLE_DEFAULT_PROTOCOL_TRIALS", 1);
  const auto trial_offset = env_count("IPS_OLE_DEFAULT_TRIAL_OFFSET", 0);
  for (std::size_t trial = 0; trial < default_trials; ++trial) {
    run_protocol_trial(OleParams::defaults(), seed_with_offset(19),
                       0x12345678ULL + trial_offset + trial);
  }

  bool invalid_rejected = false;
  try {
    OleParams{1024, 769, 255, 127, 48}.validate();
  } catch (const std::invalid_argument&) {
    invalid_rejected = true;
  }
  require(invalid_rejected, "undefined/wrong k was not rejected");

  bool c4_rejected = false;
  try {
    OleParams{32, 17, 15, 8, 3}.validate();
  } catch (const std::invalid_argument&) {
    c4_rejected = true;
  }
  require(c4_rejected, "c=4 security profile was not rejected");
}

void test_explicit_public_points() {
  using apeq::ips_ole::PublicPoints;
  const OleParams params{48, 33, 15, 8, 3};
  auto points = PublicPoints::random(params);
  auto input = points.input_points();
  auto codeword = points.codeword_points();
  // Force zero into the domain to exercise the distribution's boundary case.
  input[0] = Fp::zero();
  points = PublicPoints(params, input, codeword);
  OleReceiver receiver(params, points, seed_with_offset(31), 1);
  OleSender sender(params, points, seed_with_offset(41), 1);
  const std::vector<Fp> x{Fp::zero(), Fp::one(), Fp::from_u64(65535)};
  const std::vector<Fp> a{Fp::one(), Fp::from_u64(3), Fp::from_u64(7)};
  const std::vector<Fp> b{Fp::from_u64(5), Fp::zero(), Fp::from_u64(9)};
  const auto offered = sender.respond(receiver.encode(x), a, b);
  apeq::ips_ole::testing::InMemoryRetriever retriever(offered);
  const auto result = receiver.reconstruct(receiver.retrieve(retriever));
  for (std::size_t i = 0; i < x.size(); ++i)
    require(result[i] == a[i] * x[i] + b[i], "explicit-point OLE failed");
  auto rejected = [&](const std::vector<Fp>& xs, const std::vector<Fp>& ys) {
    try { PublicPoints invalid(params, xs, ys); }
    catch (const std::invalid_argument&) { return true; }
    return false;
  };
  codeword[0] = input[0];
  require(rejected(input, codeword), "cross-set duplicate accepted");
  codeword = points.codeword_points();
  input[1] = input[0];
  require(rejected(input, codeword), "within-set duplicate accepted");
  input = points.input_points();
  input.pop_back();
  require(rejected(input, codeword), "wrong point count accepted");
}

void test_concurrency() {
  const OleParams small{48, 33, 15, 8, 3};
  const auto sessions = env_count("IPS_OLE_CONCURRENT_SESSIONS", 64);
  std::atomic<std::size_t> failures{0};
  std::mutex choices_mutex;
  std::set<std::vector<std::size_t>> session_choices;
  std::vector<std::thread> workers;
  workers.reserve(sessions);
  for (std::size_t i = 0; i < sessions; ++i) {
    workers.emplace_back([&, i] {
      try {
        auto choices = run_protocol_trial(small, seed_with_offset(77), i + 1000);
        std::sort(choices.begin(), choices.end());
        std::lock_guard<std::mutex> lock(choices_mutex);
        session_choices.insert(std::move(choices));
      } catch (...) {
        ++failures;
      }
    });
  }
  for (auto& worker : workers) {
    worker.join();
  }
  require(failures == 0, "a concurrent IPS-OLE session failed");
  require(session_choices.size() == sessions,
          "concurrent sessions reused a private fixed-weight set");
}

}  // namespace

int main() {
  try {
    test_field();
    test_polynomials();
    test_noise();
    test_secret_logging();
    test_protocol();
    test_explicit_public_points();
    test_concurrency();
    std::cout << "IPS-OLE core tests passed\n";
    return 0;
  } catch (const std::exception& error) {
    std::cerr << "IPS-OLE core test failure: " << error.what() << '\n';
    return 1;
  }
}
