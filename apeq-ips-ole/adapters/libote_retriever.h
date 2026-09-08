#pragma once

#include "ips_ole/core.h"

#include <coproto/Socket/Socket.h>
#include <cryptoTools/Crypto/PRNG.h>
#include <libOTe/TwoChooseOne/Iknp/IknpOtExtReceiver.h>
#include <libOTe/TwoChooseOne/Iknp/IknpOtExtSender.h>

#include <cstddef>
#include <vector>

namespace apeq::ips_ole {

// Receiver side of the semi-honest IKNP chosen-message OT adapter. setup()
// performs real base OTs and must run concurrently with the sender's setup().
class LibOteReceiverRetriever final : public Retriever {
 public:
  LibOteReceiverRetriever(coproto::Socket& socket, osuCrypto::PRNG& prng);

  void setup();
  std::vector<Fp> retrieve(
      std::size_t universe_size,
      const std::vector<std::size_t>& private_choices) override;
  [[nodiscard]] std::uint64_t base_ots_consumed() const;
  [[nodiscard]] std::uint64_t extended_ots_consumed() const;
  [[nodiscard]] std::uint64_t ots_consumed() const;

 private:
  coproto::Socket& socket_;
  osuCrypto::PRNG& prng_;
  osuCrypto::IknpOtExtReceiver receiver_;
  bool setup_complete_ = false;
  std::uint64_t base_ots_consumed_ = 0;
  std::uint64_t extended_ots_consumed_ = 0;
};

// Sender-side peer. Only the receiver class implements the core Retriever
// interface because private choices exist solely on that side.
class LibOteSenderRetriever {
 public:
  LibOteSenderRetriever(coproto::Socket& socket, osuCrypto::PRNG& prng);

  void setup();
  void send(const std::vector<Fp>& offered);
  [[nodiscard]] std::uint64_t base_ots_consumed() const;
  [[nodiscard]] std::uint64_t extended_ots_consumed() const;
  [[nodiscard]] std::uint64_t ots_consumed() const;

 private:
  coproto::Socket& socket_;
  osuCrypto::PRNG& prng_;
  osuCrypto::IknpOtExtSender sender_;
  bool setup_complete_ = false;
  std::uint64_t base_ots_consumed_ = 0;
  std::uint64_t extended_ots_consumed_ = 0;
};

}  // namespace apeq::ips_ole
