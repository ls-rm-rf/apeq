#include "libote_retriever.h"

#include <macoro/sync_wait.h>

#include <array>
#include <cstdint>
#include <iomanip>
#include <sstream>
#include <stdexcept>
#include <string>

namespace apeq::ips_ole {
namespace {

osuCrypto::block fp_to_block(const Fp& value) {
  const std::string hex = value.to_hex();
  const auto high = std::stoull(hex.substr(0, 16), nullptr, 16);
  const auto low = std::stoull(hex.substr(16, 16), nullptr, 16);
  return osuCrypto::block(high, low);
}

Fp block_to_fp(const osuCrypto::block& value) {
  const auto words = value.get<std::uint64_t>();
  std::ostringstream encoded;
  encoded << std::hex << std::setfill('0') << std::setw(16) << words[1]
          << std::setw(16) << words[0];
  return Fp::from_hex(encoded.str());
}

}  // namespace

LibOteReceiverRetriever::LibOteReceiverRetriever(coproto::Socket& socket,
                                                 osuCrypto::PRNG& prng)
    : socket_(socket), prng_(prng) {}

void LibOteReceiverRetriever::setup() {
  if (setup_complete_) {
    throw std::logic_error("libOTe receiver setup called more than once");
  }
  macoro::sync_wait(receiver_.genBaseOts(prng_, socket_));
  base_ots_consumed_ = receiver_.baseOtCount();
  setup_complete_ = true;
}

std::vector<Fp> LibOteReceiverRetriever::retrieve(
    std::size_t universe_size,
    const std::vector<std::size_t>& private_choices) {
  if (!setup_complete_) {
    throw std::logic_error("libOTe receiver used before setup");
  }
  if (universe_size == 0) {
    throw std::invalid_argument("libOTe retrieval universe is empty");
  }
  osuCrypto::BitVector choices(universe_size);
  std::vector<bool> seen(universe_size, false);
  for (const auto choice : private_choices) {
    if (choice >= universe_size) {
      throw std::out_of_range("private retrieval choice exceeds universe");
    }
    if (seen[choice]) {
      throw std::invalid_argument("private retrieval choices contain a duplicate");
    }
    seen[choice] = true;
    choices[choice] = 1;
  }

  osuCrypto::AlignedUnVector<osuCrypto::block> received(universe_size);
  macoro::sync_wait(receiver_.receiveChosen(choices, received, prng_, socket_));
  extended_ots_consumed_ += universe_size;

  std::vector<Fp> selected;
  selected.reserve(private_choices.size());
  for (const auto choice : private_choices) {
    selected.push_back(block_to_fp(received[choice]));
  }
  return selected;
}

std::uint64_t LibOteReceiverRetriever::base_ots_consumed() const {
  return base_ots_consumed_;
}

std::uint64_t LibOteReceiverRetriever::extended_ots_consumed() const {
  return extended_ots_consumed_;
}

std::uint64_t LibOteReceiverRetriever::ots_consumed() const {
  return base_ots_consumed_ + extended_ots_consumed_;
}

LibOteSenderRetriever::LibOteSenderRetriever(coproto::Socket& socket,
                                             osuCrypto::PRNG& prng)
    : socket_(socket), prng_(prng) {}

void LibOteSenderRetriever::setup() {
  if (setup_complete_) {
    throw std::logic_error("libOTe sender setup called more than once");
  }
  macoro::sync_wait(sender_.genBaseOts(prng_, socket_));
  base_ots_consumed_ = sender_.baseOtCount();
  setup_complete_ = true;
}

void LibOteSenderRetriever::send(const std::vector<Fp>& offered) {
  if (!setup_complete_) {
    throw std::logic_error("libOTe sender used before setup");
  }
  if (offered.empty()) {
    throw std::invalid_argument("libOTe offered vector is empty");
  }
  osuCrypto::AlignedUnVector<std::array<osuCrypto::block, 2>> messages(
      offered.size());
  for (std::size_t i = 0; i < offered.size(); ++i) {
    messages[i][0] = osuCrypto::ZeroBlock;
    messages[i][1] = fp_to_block(offered[i]);
  }
  macoro::sync_wait(sender_.sendChosen(messages, prng_, socket_));
  extended_ots_consumed_ += offered.size();
}

std::uint64_t LibOteSenderRetriever::base_ots_consumed() const {
  return base_ots_consumed_;
}

std::uint64_t LibOteSenderRetriever::extended_ots_consumed() const {
  return extended_ots_consumed_;
}

std::uint64_t LibOteSenderRetriever::ots_consumed() const {
  return base_ots_consumed_ + extended_ots_consumed_;
}

}  // namespace apeq::ips_ole
