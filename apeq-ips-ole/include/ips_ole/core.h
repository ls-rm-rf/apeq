#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <memory>
#include <string>
#include <vector>

namespace apeq::ips_ole {

using MasterSeed = std::array<std::uint8_t, 32>;

class Fp {
 public:
  Fp() = delete;

  static Fp zero();
  static Fp one();
  static Fp from_u64(std::uint64_t value);
  static Fp from_hex(const std::string& canonical_hex);

  [[nodiscard]] std::string to_hex() const;
  [[nodiscard]] bool is_zero() const;
  [[nodiscard]] Fp inv() const;
  [[nodiscard]] Fp pow(std::uint64_t exponent) const;

  friend Fp operator+(const Fp& lhs, const Fp& rhs);
  friend Fp operator-(const Fp& lhs, const Fp& rhs);
  friend Fp operator*(const Fp& lhs, const Fp& rhs);
  friend bool operator==(const Fp& lhs, const Fp& rhs) = default;

 private:
  using Limb = unsigned __int128;

  explicit Fp(Limb montgomery_value);
  static Fp from_canonical(Limb value);
  [[nodiscard]] Limb canonical() const;
  static void check(Limb value);

  Limb value_;
};

using Polynomial = std::vector<Fp>;  // coefficients in ascending degree order

[[nodiscard]] Fp evaluate(const Polynomial& polynomial, const Fp& x);
[[nodiscard]] Polynomial interpolate(const std::vector<Fp>& x,
                                     const std::vector<Fp>& y);
[[nodiscard]] Polynomial multiply(const Polynomial& lhs,
                                  const Polynomial& rhs);
[[nodiscard]] std::size_t degree(const Polynomial& polynomial);

class Prng {
 public:
  explicit Prng(const MasterSeed& seed);
  Prng(const Prng&) = delete;
  Prng& operator=(const Prng&) = delete;
  Prng(Prng&&) noexcept;
  Prng& operator=(Prng&&) noexcept;
  ~Prng();

  [[nodiscard]] std::uint64_t next_u64();
  [[nodiscard]] std::uint64_t uniform_below(std::uint64_t bound);
  [[nodiscard]] Fp random_fp();

 private:
  struct State;
  std::unique_ptr<State> state_;
};

[[nodiscard]] MasterSeed derive_key(const MasterSeed& parent,
                                    const std::string& label,
                                    const std::vector<std::uint8_t>& suffix = {});
[[nodiscard]] std::vector<std::size_t> sample_fixed_weight(
    std::size_t n, std::size_t weight, Prng& prng);

struct OleParams {
  std::size_t n;
  std::size_t rho;
  std::size_t ell;
  std::size_t k;
  std::size_t t;

  static OleParams defaults();
  void validate() const;
  [[nodiscard]] std::size_t degree_p() const;
  [[nodiscard]] std::size_t degree_a() const;
  [[nodiscard]] std::size_t degree_b() const;
};

class PublicPoints {
 public:
  // Legacy public-seed constructor retained for reproducing frozen experiments.
  PublicPoints(const OleParams& params, const MasterSeed& public_session_key);
  PublicPoints(const OleParams& params, std::vector<Fp> input_points,
               std::vector<Fp> codeword_points);
  // Keep the sampler seed private; publish only the sampled points.
  [[nodiscard]] static PublicPoints random(const OleParams& params);

  [[nodiscard]] const std::vector<Fp>& input_points() const;
  [[nodiscard]] const std::vector<Fp>& codeword_points() const;

 private:
  std::vector<Fp> input_points_;
  std::vector<Fp> codeword_points_;
};

struct Encoding {
  std::uint64_t batch_counter;
  std::vector<Fp> values;
};

class Retriever {
 public:
  virtual ~Retriever() = default;
  virtual std::vector<Fp> retrieve(
      std::size_t universe_size,
      const std::vector<std::size_t>& private_choices) = 0;
};

class OleReceiver {
 public:
  OleReceiver(OleParams params, MasterSeed public_seed,
              MasterSeed receiver_private_seed, std::uint64_t session_id);
  OleReceiver(OleParams params, PublicPoints points,
              MasterSeed receiver_private_seed, std::uint64_t session_id);

  Encoding encode(const std::vector<Fp>& x);
  std::vector<Encoding> encode_many(
      const std::vector<std::vector<Fp>>& batches);
  std::vector<Fp> retrieve(Retriever& retriever) const;
  std::vector<std::vector<Fp>> retrieve_many(Retriever& retriever) const;
  std::vector<Fp> reconstruct(const std::vector<Fp>& retrieved);
  std::vector<std::vector<Fp>> reconstruct_many(
      const std::vector<std::vector<Fp>>& retrieved);

  [[nodiscard]] const PublicPoints& public_points() const;

 private:
  OleParams params_;
  MasterSeed private_session_key_;
  PublicPoints points_;
  std::uint64_t batch_counter_ = 0;
  std::uint64_t active_batch_ = 0;
  bool has_active_batch_ = false;
  std::vector<std::size_t> choices_;
  std::vector<std::vector<std::size_t>> batched_choices_;

  Encoding encode_with_choices(const std::vector<Fp>& x,
                               std::vector<std::size_t>& choices);
  std::vector<Fp> reconstruct_with_choices(
      const std::vector<Fp>& retrieved,
      const std::vector<std::size_t>& choices) const;
};

class OleSender {
 public:
  OleSender(OleParams params, MasterSeed public_seed,
            MasterSeed sender_private_seed, std::uint64_t session_id);
  OleSender(OleParams params, PublicPoints points,
            MasterSeed sender_private_seed, std::uint64_t session_id);

  std::vector<Fp> respond(const Encoding& encoding,
                          const std::vector<Fp>& a,
                          const std::vector<Fp>& b);

  [[nodiscard]] const PublicPoints& public_points() const;

 private:
  OleParams params_;
  MasterSeed private_session_key_;
  PublicPoints points_;
  std::uint64_t batch_counter_ = 0;
};

[[nodiscard]] Polynomial sample_constrained_polynomial(
    const std::vector<Fp>& points, const std::vector<Fp>& values,
    std::size_t target_degree, Prng& prng);

[[nodiscard]] MasterSeed deterministic_test_seed();
[[nodiscard]] MasterSeed random_master_seed();

}  // namespace apeq::ips_ole
