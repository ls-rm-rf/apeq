#include "ips_ole/core.h"

#include "ips_ole/labels.h"

#include <openssl/evp.h>
#include <openssl/rand.h>

#include <algorithm>
#include <array>
#include <cassert>
#include <cstring>
#include <limits>
#include <numeric>
#include <stdexcept>
#include <unordered_set>
#include <utility>

#include <boost/multiprecision/cpp_int.hpp>

namespace apeq::ips_ole {
namespace {

using Wide = boost::multiprecision::uint256_t;
using Limb = unsigned __int128;

constexpr Limb kModulus = (Limb{1} << 127U) - Limb{1};

std::vector<std::uint8_t> as_bytes(const std::string& value) {
  return {value.begin(), value.end()};
}

std::array<std::uint8_t, 32> sha256(
    const std::vector<std::uint8_t>& input) {
  std::array<std::uint8_t, 32> output{};
  auto* context = EVP_MD_CTX_new();
  if (context == nullptr) {
    throw std::runtime_error("EVP_MD_CTX_new failed");
  }
  unsigned int output_size = 0;
  const bool ok = EVP_DigestInit_ex(context, EVP_sha256(), nullptr) == 1 &&
                  EVP_DigestUpdate(context, input.data(), input.size()) == 1 &&
                  EVP_DigestFinal_ex(context, output.data(), &output_size) == 1;
  EVP_MD_CTX_free(context);
  if (!ok || output_size != output.size()) {
    throw std::runtime_error("SHA-256 failed");
  }
  return output;
}

std::array<std::uint8_t, 32> hmac_sha256(
    const std::vector<std::uint8_t>& key,
    const std::vector<std::uint8_t>& message) {
  constexpr std::size_t kBlockSize = 64;
  std::array<std::uint8_t, kBlockSize> normalized{};
  if (key.size() > kBlockSize) {
    const auto digest = sha256(key);
    std::copy(digest.begin(), digest.end(), normalized.begin());
  } else {
    std::copy(key.begin(), key.end(), normalized.begin());
  }

  std::vector<std::uint8_t> inner(kBlockSize + message.size());
  std::vector<std::uint8_t> outer(kBlockSize + 32);
  for (std::size_t i = 0; i < kBlockSize; ++i) {
    inner[i] = static_cast<std::uint8_t>(normalized[i] ^ 0x36U);
    outer[i] = static_cast<std::uint8_t>(normalized[i] ^ 0x5cU);
  }
  std::copy(message.begin(), message.end(), inner.begin() + kBlockSize);
  const auto inner_digest = sha256(inner);
  std::copy(inner_digest.begin(), inner_digest.end(), outer.begin() + kBlockSize);
  return sha256(outer);
}

std::vector<std::uint8_t> be64(std::uint64_t value) {
  std::vector<std::uint8_t> result(8);
  for (std::size_t i = 0; i < result.size(); ++i) {
    result[result.size() - 1 - i] = static_cast<std::uint8_t>(value & 0xffU);
    value >>= 8U;
  }
  return result;
}

MasterSeed derive_session_key(const MasterSeed& seed, std::string_view label,
                              std::uint64_t session_id) {
  return derive_key(seed, std::string(label), be64(session_id));
}

Limb wide_to_limb(const Wide& value) {
  constexpr std::uint64_t kMask = std::numeric_limits<std::uint64_t>::max();
  const auto low = (value & kMask).convert_to<std::uint64_t>();
  const auto high = (value >> 64U).convert_to<std::uint64_t>();
  return (Limb{high} << 64U) | Limb{low};
}

Polynomial add_polynomials(const Polynomial& lhs, const Polynomial& rhs) {
  const auto size = std::max(lhs.size(), rhs.size());
  Polynomial result(size, Fp::zero());
  for (std::size_t i = 0; i < lhs.size(); ++i) {
    result[i] = result[i] + lhs[i];
  }
  for (std::size_t i = 0; i < rhs.size(); ++i) {
    result[i] = result[i] + rhs[i];
  }
  return result;
}

void require_size(const std::vector<Fp>& values, std::size_t expected,
                  const char* name) {
  if (values.size() != expected) {
    throw std::invalid_argument(std::string(name) + " has wrong size");
  }
}

}  // namespace

Fp::Fp(Limb montgomery_value) : value_(montgomery_value) { check(value_); }

Fp Fp::zero() { return Fp(Limb{0}); }

Fp Fp::one() { return from_canonical(Limb{1}); }

Fp Fp::from_u64(std::uint64_t value) {
  return from_canonical(Limb{value});
}

Fp Fp::from_canonical(Limb value) {
  if (value >= kModulus) {
    throw std::out_of_range("Fp canonical value is not in [0,p)");
  }
  Limb montgomery = value << 1U;
  if (montgomery >= kModulus) {
    montgomery -= kModulus;
  }
  return Fp(montgomery);
}

Fp Fp::from_hex(const std::string& canonical_hex) {
  if (canonical_hex.empty() || canonical_hex.size() > 32) {
    throw std::invalid_argument("invalid Fp hexadecimal length");
  }
  Limb value = 0;
  for (const char ch : canonical_hex) {
    unsigned digit = 0;
    if (ch >= '0' && ch <= '9') {
      digit = static_cast<unsigned>(ch - '0');
    } else if (ch >= 'a' && ch <= 'f') {
      digit = static_cast<unsigned>(ch - 'a' + 10);
    } else if (ch >= 'A' && ch <= 'F') {
      digit = static_cast<unsigned>(ch - 'A' + 10);
    } else {
      throw std::invalid_argument("invalid Fp hexadecimal digit");
    }
    value = (value << 4U) | Limb{digit};
  }
  return from_canonical(value);
}

Fp::Limb Fp::canonical() const {
  check(value_);
  if ((value_ & Limb{1}) == 0) {
    return value_ >> 1U;
  }
  return (value_ + kModulus) >> 1U;
}

std::string Fp::to_hex() const {
  static constexpr char kDigits[] = "0123456789abcdef";
  Limb value = canonical();
  std::string result(32, '0');
  for (std::size_t i = 0; i < result.size(); ++i) {
    const auto position = result.size() - 1 - i;
    result[position] = kDigits[static_cast<unsigned>(value & Limb{0xf})];
    value >>= 4U;
  }
  return result;
}

bool Fp::is_zero() const { return value_ == 0; }

Fp Fp::pow(std::uint64_t exponent) const {
  Fp base = *this;
  Fp result = one();
  while (exponent != 0) {
    if ((exponent & 1U) != 0) {
      result = result * base;
    }
    exponent >>= 1U;
    if (exponent != 0) {
      base = base * base;
    }
  }
  return result;
}

Fp Fp::inv() const {
  if (is_zero()) {
    throw std::domain_error("zero has no field inverse");
  }
  Limb exponent = kModulus - Limb{2};
  Fp base = *this;
  Fp result = one();
  while (exponent != 0) {
    if ((exponent & Limb{1}) != 0) {
      result = result * base;
    }
    exponent >>= 1U;
    if (exponent != 0) {
      base = base * base;
    }
  }
  return result;
}

void Fp::check(Limb value) {
#ifdef FP_CHECKED
  if (value >= kModulus) {
    throw std::logic_error("Fp Montgomery invariant violated");
  }
#else
  (void)value;
#endif
}

Fp operator+(const Fp& lhs, const Fp& rhs) {
  Fp::check(lhs.value_);
  Fp::check(rhs.value_);
  Limb sum = lhs.value_ + rhs.value_;
  if (sum >= kModulus) {
    sum -= kModulus;
  }
  return Fp(sum);
}

Fp operator-(const Fp& lhs, const Fp& rhs) {
  Fp::check(lhs.value_);
  Fp::check(rhs.value_);
  const Limb difference = lhs.value_ >= rhs.value_
                              ? lhs.value_ - rhs.value_
                              : kModulus - (rhs.value_ - lhs.value_);
  return Fp(difference);
}

Fp operator*(const Fp& lhs, const Fp& rhs) {
  Fp::check(lhs.value_);
  Fp::check(rhs.value_);
  const Wide product = Wide(lhs.value_) * Wide(rhs.value_);
  const Wide modulus = Wide(kModulus);
  Limb reduced = wide_to_limb(product % modulus);
  // R = 2^128 mod p = 2. Dividing the raw product by R keeps the
  // result in Montgomery form. Division by two modulo odd p is exact here.
  reduced = (reduced & Limb{1}) == 0
                ? reduced >> 1U
                : (reduced + kModulus) >> 1U;
  return Fp(reduced);
}

Fp evaluate(const Polynomial& polynomial, const Fp& x) {
  Fp result = Fp::zero();
  for (auto it = polynomial.rbegin(); it != polynomial.rend(); ++it) {
    result = result * x + *it;
  }
  return result;
}

Polynomial multiply(const Polynomial& lhs, const Polynomial& rhs) {
  if (lhs.empty() || rhs.empty()) {
    return {Fp::zero()};
  }
  Polynomial result(lhs.size() + rhs.size() - 1, Fp::zero());
  for (std::size_t i = 0; i < lhs.size(); ++i) {
    for (std::size_t j = 0; j < rhs.size(); ++j) {
      result[i + j] = result[i + j] + lhs[i] * rhs[j];
    }
  }
  return result;
}

std::size_t degree(const Polynomial& polynomial) {
  if (polynomial.empty()) {
    return 0;
  }
  for (std::size_t i = polynomial.size(); i > 0; --i) {
    if (!polynomial[i - 1].is_zero()) {
      return i - 1;
    }
  }
  return 0;
}

Polynomial interpolate(const std::vector<Fp>& x,
                       const std::vector<Fp>& y) {
  if (x.empty() || x.size() != y.size()) {
    throw std::invalid_argument("interpolation vectors must have equal nonzero size");
  }
  std::unordered_set<std::string> distinct;
  for (const auto& point : x) {
    if (!distinct.insert(point.to_hex()).second) {
      throw std::invalid_argument("interpolation points must be distinct");
    }
  }

  Polynomial product{Fp::one()};
  for (const auto& point : x) {
    product = multiply(product, {Fp::zero() - point, Fp::one()});
  }

  Polynomial derivative(product.size() - 1, Fp::zero());
  for (std::size_t i = 1; i < product.size(); ++i) {
    derivative[i - 1] = product[i] * Fp::from_u64(i);
  }

  // Batch inversion turns n expensive exponentiations into one inversion and
  // 3n multiplications. Distinct interpolation points make every denominator
  // nonzero.
  std::vector<Fp> denominators;
  denominators.reserve(x.size());
  for (const auto& point : x) {
    denominators.push_back(evaluate(derivative, point));
  }
  std::vector<Fp> prefixes(x.size(), Fp::one());
  Fp accumulator = Fp::one();
  for (std::size_t i = 0; i < denominators.size(); ++i) {
    prefixes[i] = accumulator;
    accumulator = accumulator * denominators[i];
  }
  accumulator = accumulator.inv();
  std::vector<Fp> inverse_denominators(x.size(), Fp::zero());
  for (std::size_t i = denominators.size(); i > 0; --i) {
    inverse_denominators[i - 1] = accumulator * prefixes[i - 1];
    accumulator = accumulator * denominators[i - 1];
  }

  Polynomial result(x.size(), Fp::zero());
  for (std::size_t i = 0; i < x.size(); ++i) {
    const Fp scale = y[i] * inverse_denominators[i];
    Polynomial quotient(x.size(), Fp::zero());
    quotient.back() = product.back();
    for (std::size_t j = x.size() - 1; j > 0; --j) {
      quotient[j - 1] = product[j] + x[i] * quotient[j];
    }
#ifdef FP_CHECKED
    if (!(product.front() + x[i] * quotient.front()).is_zero()) {
      throw std::logic_error("synthetic division remainder is nonzero");
    }
#endif
    for (std::size_t j = 0; j < result.size(); ++j) {
      result[j] = result[j] + quotient[j] * scale;
    }
  }
  return result;
}

struct Prng::State {
  explicit State(const MasterSeed& input_seed) : seed(input_seed) {}

  MasterSeed seed;
  std::uint64_t counter = 0;
  MasterSeed block{};
  std::size_t position = block.size();
};

Prng::Prng(const MasterSeed& seed) : state_(std::make_unique<State>(seed)) {}
Prng::Prng(Prng&&) noexcept = default;
Prng& Prng::operator=(Prng&&) noexcept = default;
Prng::~Prng() = default;

std::uint64_t Prng::next_u64() {
  std::array<std::uint8_t, 8> bytes{};
  for (auto& byte : bytes) {
    if (state_->position == state_->block.size()) {
      if (state_->counter == std::numeric_limits<std::uint64_t>::max()) {
        throw std::overflow_error("PRNG counter exhausted");
      }
      const auto message = be64(state_->counter++);
      state_->block = hmac_sha256(
          {state_->seed.begin(), state_->seed.end()}, message);
      state_->position = 0;
    }
    byte = state_->block[state_->position++];
  }
  std::uint64_t result = 0;
  for (const auto byte : bytes) {
    result = (result << 8U) | byte;
  }
  return result;
}

std::uint64_t Prng::uniform_below(std::uint64_t bound) {
  if (bound == 0) {
    throw std::invalid_argument("uniform_below bound must be positive");
  }
  const std::uint64_t threshold = (std::uint64_t{0} - bound) % bound;
  while (true) {
    const auto sample = next_u64();
    if (sample >= threshold) {
      return sample % bound;
    }
  }
}

Fp Prng::random_fp() {
  while (true) {
    const auto high = next_u64() & 0x7fffffffffffffffULL;
    const auto low = next_u64();
    const Limb candidate = (Limb{high} << 64U) | Limb{low};
    if (candidate < kModulus) {
      return Fp::from_hex([&] {
        static constexpr char kDigits[] = "0123456789abcdef";
        Limb value = candidate;
        std::string result(32, '0');
        for (std::size_t i = 0; i < result.size(); ++i) {
          result[result.size() - 1 - i] =
              kDigits[static_cast<unsigned>(value & Limb{0xf})];
          value >>= 4U;
        }
        return result;
      }());
    }
  }
}

MasterSeed derive_key(const MasterSeed& parent, const std::string& label,
                      const std::vector<std::uint8_t>& suffix) {
  const auto salt = as_bytes(std::string(labels::kHkdfSalt));
  const auto extracted = hmac_sha256(
      salt, {parent.begin(), parent.end()});
  auto info = as_bytes(label);
  info.insert(info.end(), suffix.begin(), suffix.end());
  info.push_back(1);  // first and only HKDF-Expand block
  return hmac_sha256({extracted.begin(), extracted.end()}, info);
}

std::vector<std::size_t> sample_fixed_weight(std::size_t n,
                                             std::size_t weight,
                                             Prng& prng) {
  if (weight > n) {
    throw std::invalid_argument("fixed weight exceeds population");
  }
  std::vector<std::size_t> indices(n);
  std::iota(indices.begin(), indices.end(), 0);
  for (std::size_t i = 0; i < weight; ++i) {
    const auto offset = prng.uniform_below(n - i);
    const auto j = i + static_cast<std::size_t>(offset);
    std::swap(indices[i], indices[j]);
  }
  indices.resize(weight);
  return indices;
}

OleParams OleParams::defaults() { return {1024, 769, 255, 128, 48}; }

void OleParams::validate() const {
  if (n == 0 || ell == 0 || k == 0 || t == 0) {
    throw std::invalid_argument("IPS-OLE parameters must be nonzero");
  }
  if (n != rho + ell) {
    throw std::invalid_argument("IPS-OLE requires n = rho + ell");
  }
  if (n % k != 0 || n / k <= 4) {
    throw std::invalid_argument("IPS-OLE requires n = c*k with integer c > 4");
  }
  if ((ell & 1U) == 0) {
    throw std::invalid_argument("IPS-OLE requires odd ell");
  }
  if (k != (ell + 1) / 2) {
    throw std::invalid_argument("IPS-OLE requires k = (ell+1)/2");
  }
  if (t > k || t > ell / 4) {
    throw std::invalid_argument("IPS-OLE batch size exceeds the proven bound");
  }
  if (degree_a() + degree_p() != degree_b()) {
    throw std::invalid_argument("IPS-OLE polynomial degree identity failed");
  }
}

std::size_t OleParams::degree_p() const { return k - 1; }
std::size_t OleParams::degree_a() const { return (ell - 1) / 2; }
std::size_t OleParams::degree_b() const { return ell - 1; }

PublicPoints::PublicPoints(const OleParams& params,
                            const MasterSeed& public_session_key) {
  params.validate();
  Prng prng(derive_key(public_session_key, std::string(labels::kPoints)));
  std::unordered_set<std::string> seen;
  auto append_distinct = [&](std::vector<Fp>& destination,
                             std::size_t count) {
    while (destination.size() < count) {
      auto candidate = prng.random_fp();
      if (!candidate.is_zero() && seen.insert(candidate.to_hex()).second) {
        destination.push_back(candidate);
      }
    }
  };
  append_distinct(input_points_, params.k);
  append_distinct(codeword_points_, params.n);
}

PublicPoints::PublicPoints(const OleParams& params, std::vector<Fp> input_points,
                           std::vector<Fp> codeword_points)
    : input_points_(std::move(input_points)),
      codeword_points_(std::move(codeword_points)) {
  params.validate();
  require_size(input_points_, params.k, "public input points");
  require_size(codeword_points_, params.n, "public codeword points");
  std::unordered_set<std::string> seen;
  for (const auto* points : {&input_points_, &codeword_points_}) {
    for (const auto& point : *points) {
      if (!seen.insert(point.to_hex()).second) {
        throw std::invalid_argument("public points must be pairwise distinct");
      }
    }
  }
}

PublicPoints PublicPoints::random(const OleParams& params) {
  params.validate();
  Prng prng(random_master_seed());
  std::unordered_set<std::string> seen;
  std::vector<Fp> input, codeword;
  auto sample = [&](std::vector<Fp>& out, std::size_t count) {
    while (out.size() < count) {
      const auto point = prng.random_fp();
      // Zero is allowed: the reference distribution is over the whole field.
      if (seen.insert(point.to_hex()).second) out.push_back(point);
    }
  };
  sample(input, params.k);
  sample(codeword, params.n);
  return PublicPoints(params, std::move(input), std::move(codeword));
}

const std::vector<Fp>& PublicPoints::input_points() const {
  return input_points_;
}

const std::vector<Fp>& PublicPoints::codeword_points() const {
  return codeword_points_;
}

Polynomial sample_constrained_polynomial(
    const std::vector<Fp>& points, const std::vector<Fp>& values,
    std::size_t target_degree, Prng& prng) {
  if (points.empty() || points.size() != values.size()) {
    throw std::invalid_argument("polynomial constraints have wrong size");
  }
  if (target_degree + 1 < points.size()) {
    throw std::invalid_argument("target degree cannot satisfy all constraints");
  }

  const Polynomial base = interpolate(points, values);
  if (target_degree + 1 == points.size()) {
    if (degree(base) > target_degree) {
      throw std::logic_error("constrained polynomial exceeds degree bound");
    }
    return base;
  }
  Polynomial vanishing{Fp::one()};
  for (const auto& point : points) {
    vanishing = multiply(vanishing, {Fp::zero() - point, Fp::one()});
  }

  const std::size_t quotient_degree = target_degree - points.size();
  Polynomial random_quotient(quotient_degree + 1, Fp::zero());
  for (auto& coefficient : random_quotient) {
    coefficient = prng.random_fp();
  }
  auto result = add_polynomials(base, multiply(vanishing, random_quotient));
  if (degree(result) > target_degree) {
    throw std::logic_error("constrained polynomial exceeds degree bound");
  }
  return result;
}

OleReceiver::OleReceiver(OleParams params, MasterSeed public_seed,
                         MasterSeed receiver_private_seed,
                         std::uint64_t session_id)
    : params_(params),
      private_session_key_(derive_session_key(
          receiver_private_seed, labels::kReceiverSession, session_id)),
      points_(params_, derive_session_key(public_seed, labels::kPublicSession,
                                          session_id)) {
  params_.validate();
}

OleReceiver::OleReceiver(OleParams params, PublicPoints points,
                         MasterSeed receiver_private_seed,
                         std::uint64_t session_id)
    : params_(params),
      private_session_key_(derive_session_key(
          receiver_private_seed, labels::kReceiverSession, session_id)),
      points_(params_, points.input_points(), points.codeword_points()) {}

Encoding OleReceiver::encode(const std::vector<Fp>& x) {
  if (has_active_batch_ || !batched_choices_.empty()) {
    throw std::logic_error("previous IPS-OLE batch has not been reconstructed");
  }
  auto encoding = encode_with_choices(x, choices_);
  active_batch_ = encoding.batch_counter;
  has_active_batch_ = true;
  return encoding;
}

Encoding OleReceiver::encode_with_choices(
    const std::vector<Fp>& x, std::vector<std::size_t>& choices) {
  require_size(x, params_.t, "x");
  if (batch_counter_ == std::numeric_limits<std::uint64_t>::max()) {
    throw std::overflow_error("IPS-OLE batch counter exhausted");
  }
  ++batch_counter_;  // increment before deriving any per-batch secret

  const auto suffix = be64(batch_counter_);
  Prng noise_prng(
      derive_key(private_session_key_, std::string(labels::kNoise), suffix));
  Prng u_prng(
      derive_key(private_session_key_, std::string(labels::kUVec), suffix));
  Prng v_prng(
      derive_key(private_session_key_, std::string(labels::kVVec), suffix));

  choices = sample_fixed_weight(params_.n, params_.ell, noise_prng);
  std::vector<Fp> u(params_.k, Fp::zero());
  for (auto& value : u) {
    value = u_prng.random_fp();
  }
  std::copy(x.begin(), x.end(), u.begin());
  const auto polynomial = interpolate(points_.input_points(), u);

  std::vector<Fp> v(params_.n, Fp::zero());
  for (auto& value : v) {
    value = v_prng.random_fp();
  }
  for (const auto choice : choices) {
    v[choice] = evaluate(polynomial, points_.codeword_points()[choice]);
  }
  return {batch_counter_, std::move(v)};
}

std::vector<Encoding> OleReceiver::encode_many(
    const std::vector<std::vector<Fp>>& batches) {
  if (batches.empty()) {
    throw std::invalid_argument("batched IPS-OLE input is empty");
  }
  if (has_active_batch_ || !batched_choices_.empty()) {
    throw std::logic_error("previous IPS-OLE batch has not been reconstructed");
  }
  std::vector<Encoding> encodings;
  encodings.reserve(batches.size());
  batched_choices_.reserve(batches.size());
  for (const auto& x : batches) {
    batched_choices_.emplace_back();
    encodings.push_back(encode_with_choices(x, batched_choices_.back()));
  }
  return encodings;
}

std::vector<Fp> OleReceiver::retrieve(Retriever& retriever) const {
  if (!has_active_batch_) {
    throw std::logic_error("no active IPS-OLE batch");
  }
  return retriever.retrieve(params_.n, choices_);
}

std::vector<std::vector<Fp>> OleReceiver::retrieve_many(
    Retriever& retriever) const {
  if (batched_choices_.empty()) {
    throw std::logic_error("no active batched IPS-OLE request");
  }

  std::size_t selected_size = 0;
  std::vector<std::size_t> flattened_choices;
  std::size_t universe_size = 0;
  for (const auto& choices : batched_choices_) {
    if (universe_size > std::numeric_limits<std::size_t>::max() - params_.n) {
      throw std::overflow_error("batched retrieval universe overflow");
    }
    if (selected_size > std::numeric_limits<std::size_t>::max() -
                            choices.size()) {
      throw std::overflow_error("batched retrieval selection overflow");
    }
    const auto offset = universe_size;
    universe_size += params_.n;
    selected_size += choices.size();
    flattened_choices.reserve(selected_size);
    for (const auto choice : choices) {
      flattened_choices.push_back(offset + choice);
    }
  }

  const auto flattened = retriever.retrieve(universe_size, flattened_choices);
  if (flattened.size() != selected_size) {
    throw std::invalid_argument("batched retriever returned the wrong size");
  }

  std::vector<std::vector<Fp>> result;
  result.reserve(batched_choices_.size());
  std::size_t offset = 0;
  for (const auto& choices : batched_choices_) {
    const auto count = choices.size();
    result.emplace_back(flattened.begin() + offset,
                        flattened.begin() + offset + count);
    offset += count;
  }
  return result;
}

std::vector<Fp> OleReceiver::reconstruct(
    const std::vector<Fp>& retrieved) {
  if (!has_active_batch_) {
    throw std::logic_error("no active IPS-OLE batch");
  }
  auto result = reconstruct_with_choices(retrieved, choices_);
  std::fill(choices_.begin(), choices_.end(), 0);
  choices_.clear();
  has_active_batch_ = false;
  active_batch_ = 0;
  return result;
}

std::vector<Fp> OleReceiver::reconstruct_with_choices(
    const std::vector<Fp>& retrieved,
    const std::vector<std::size_t>& choices) const {
  require_size(retrieved, params_.ell, "retrieved");
  std::vector<Fp> selected_points;
  selected_points.reserve(params_.ell);
  for (const auto choice : choices) {
    selected_points.push_back(points_.codeword_points()[choice]);
  }
  const auto y_polynomial = interpolate(selected_points, retrieved);
#ifdef FP_CHECKED
  if (degree(y_polynomial) > params_.degree_b()) {
    throw std::logic_error("reconstructed polynomial exceeds ell-1");
  }
#endif
  std::vector<Fp> result;
  result.reserve(params_.t);
  for (std::size_t i = 0; i < params_.t; ++i) {
    result.push_back(evaluate(y_polynomial, points_.input_points()[i]));
  }
  return result;
}

std::vector<std::vector<Fp>> OleReceiver::reconstruct_many(
    const std::vector<std::vector<Fp>>& retrieved) {
  if (batched_choices_.empty()) {
    throw std::logic_error("no active batched IPS-OLE request");
  }
  if (retrieved.size() != batched_choices_.size()) {
    throw std::invalid_argument("batched retrieved group count mismatch");
  }
  std::vector<std::vector<Fp>> result;
  result.reserve(retrieved.size());
  for (std::size_t i = 0; i < retrieved.size(); ++i) {
    result.push_back(
        reconstruct_with_choices(retrieved[i], batched_choices_[i]));
  }
  for (auto& choices : batched_choices_) {
    std::fill(choices.begin(), choices.end(), 0);
  }
  batched_choices_.clear();
  return result;
}

const PublicPoints& OleReceiver::public_points() const { return points_; }

OleSender::OleSender(OleParams params, MasterSeed public_seed,
                     MasterSeed sender_private_seed,
                     std::uint64_t session_id)
    : params_(params),
      private_session_key_(derive_session_key(
          sender_private_seed, labels::kSenderSession, session_id)),
      points_(params_, derive_session_key(public_seed, labels::kPublicSession,
                                          session_id)) {
  params_.validate();
}

OleSender::OleSender(OleParams params, PublicPoints points,
                     MasterSeed sender_private_seed,
                     std::uint64_t session_id)
    : params_(params),
      private_session_key_(derive_session_key(
          sender_private_seed, labels::kSenderSession, session_id)),
      points_(params_, points.input_points(), points.codeword_points()) {}

std::vector<Fp> OleSender::respond(const Encoding& encoding,
                                   const std::vector<Fp>& a,
                                   const std::vector<Fp>& b) {
  require_size(encoding.values, params_.n, "encoding");
  require_size(a, params_.t, "a");
  require_size(b, params_.t, "b");
  if (batch_counter_ == std::numeric_limits<std::uint64_t>::max() ||
      encoding.batch_counter != batch_counter_ + 1) {
    throw std::logic_error("sender observed a repeated or regressed batch counter");
  }
  batch_counter_ = encoding.batch_counter;

  const auto suffix = be64(batch_counter_);
  Prng prng(
      derive_key(private_session_key_, std::string(labels::kPolyAB), suffix));
  const std::vector<Fp> constraint_points(points_.input_points().begin(),
                                          points_.input_points().begin() + params_.t);
  const auto polynomial_a = sample_constrained_polynomial(
      constraint_points, a, params_.degree_a(), prng);
  const auto polynomial_b = sample_constrained_polynomial(
      constraint_points, b, params_.degree_b(), prng);
#ifdef FP_CHECKED
  if (degree(polynomial_a) > params_.degree_a() ||
      degree(polynomial_b) > params_.degree_b()) {
    throw std::logic_error("sender polynomial degree hygiene failed");
  }
#endif

  std::vector<Fp> offered(params_.n, Fp::zero());
  for (std::size_t i = 0; i < params_.n; ++i) {
    offered[i] = evaluate(polynomial_a, points_.codeword_points()[i]) *
                     encoding.values[i] +
                 evaluate(polynomial_b, points_.codeword_points()[i]);
  }
  return offered;
}

const PublicPoints& OleSender::public_points() const { return points_; }

MasterSeed deterministic_test_seed() {
  MasterSeed seed{};
  for (std::size_t i = 0; i < seed.size(); ++i) {
    seed[i] = static_cast<std::uint8_t>(i);
  }
  return seed;
}

MasterSeed random_master_seed() {
  MasterSeed seed{};
  if (RAND_bytes(seed.data(), static_cast<int>(seed.size())) != 1) {
    throw std::runtime_error("operating-system CSPRNG failed");
  }
  return seed;
}

}  // namespace apeq::ips_ole
