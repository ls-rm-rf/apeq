#pragma once

#include "ips_ole/core.h"

#include <cstddef>
#include <stdexcept>
#include <utility>
#include <vector>

namespace apeq::ips_ole::testing {

// Test-only stand-in. Production code must provide an OT-backed receiver-side
// Retriever whose network transcript does not reveal private_choices.
class InMemoryRetriever final : public Retriever {
 public:
  explicit InMemoryRetriever(std::vector<Fp> offered)
      : offered_(std::move(offered)) {}

  std::vector<Fp> retrieve(
      std::size_t universe_size,
      const std::vector<std::size_t>& private_choices) override {
    if (universe_size != offered_.size()) {
      throw std::invalid_argument("retrieval universe size mismatch");
    }
    choices_seen_for_test_ = private_choices;
    std::vector<Fp> selected;
    selected.reserve(private_choices.size());
    for (const auto choice : private_choices) {
      if (choice >= offered_.size()) {
        throw std::out_of_range("retrieval choice exceeds offered values");
      }
      selected.push_back(offered_[choice]);
    }
    return selected;
  }

  [[nodiscard]] const std::vector<std::size_t>& choices_seen_for_test() const {
    return choices_seen_for_test_;
  }

 private:
  std::vector<Fp> offered_;
  std::vector<std::size_t> choices_seen_for_test_;
};

}  // namespace apeq::ips_ole::testing
