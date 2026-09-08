#include "ips_ole/core.h"
#include "libote_retriever.h"

#include <coproto/Socket/LocalAsyncSock.h>
#include <cryptoTools/Crypto/PRNG.h>

#include <algorithm>
#include <exception>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <thread>
#include <vector>

namespace {

void require(bool condition, const char* message) {
  if (!condition) {
    throw std::runtime_error(message);
  }
}

class StreamCapture {
 public:
  StreamCapture()
      : old_out_(std::cout.rdbuf(out_.rdbuf())),
        old_err_(std::cerr.rdbuf(err_.rdbuf())) {}

  ~StreamCapture() { restore(); }

  void restore() {
    if (!restored_) {
      std::cout.rdbuf(old_out_);
      std::cerr.rdbuf(old_err_);
      restored_ = true;
    }
  }

  [[nodiscard]] bool empty() const {
    return out_.str().empty() && err_.str().empty();
  }

 private:
  std::ostringstream out_;
  std::ostringstream err_;
  std::streambuf* old_out_;
  std::streambuf* old_err_;
  bool restored_ = false;
};

}  // namespace

int main() {
  using namespace apeq::ips_ole;
  try {
    StreamCapture protocol_logs;
    auto sockets = coproto::LocalAsyncSocket::makePair();
    osuCrypto::PRNG receiver_prng(osuCrypto::sysRandomSeed());
    osuCrypto::PRNG sender_prng(osuCrypto::sysRandomSeed());
    LibOteReceiverRetriever receiver(sockets[0], receiver_prng);
    LibOteSenderRetriever sender(sockets[1], sender_prng);

    std::exception_ptr receiver_error;
    std::exception_ptr sender_error;
    std::thread receiver_setup([&] {
      try {
        receiver.setup();
      } catch (...) {
        receiver_error = std::current_exception();
      }
    });
    std::thread sender_setup([&] {
      try {
        sender.setup();
      } catch (...) {
        sender_error = std::current_exception();
      }
    });
    receiver_setup.join();
    sender_setup.join();
    if (receiver_error) {
      std::rethrow_exception(receiver_error);
    }
    if (sender_error) {
      std::rethrow_exception(sender_error);
    }
    require(receiver.base_ots_consumed() > 0,
            "receiver did not count real base OTs");
    require(receiver.base_ots_consumed() == sender.base_ots_consumed(),
            "sender and receiver disagree on base OT count");
    require(receiver.extended_ots_consumed() == 0 &&
                sender.extended_ots_consumed() == 0,
            "OT extension count was nonzero before retrieval");

    bool duplicate_rejected = false;
    try {
      (void)receiver.retrieve(4, {1, 1});
    } catch (const std::invalid_argument&) {
      duplicate_rejected = true;
    }
    require(duplicate_rejected,
            "libOTe Retriever accepted duplicate private choices");

    Prng value_prng(deterministic_test_seed());
    for (std::size_t round = 0; round < 3; ++round) {
      std::vector<Fp> offered(512, Fp::zero());
      for (auto& value : offered) {
        value = value_prng.random_fp();
      }
      std::vector<std::size_t> choices;
      for (std::size_t i = round; i < offered.size(); i += 3 + round) {
        choices.push_back(i);
      }

      std::vector<Fp> selected;
      receiver_error = nullptr;
      sender_error = nullptr;
      std::thread receiver_round([&] {
        try {
          selected = receiver.retrieve(offered.size(), choices);
        } catch (...) {
          receiver_error = std::current_exception();
        }
      });
      std::thread sender_round([&] {
        try {
          sender.send(offered);
        } catch (...) {
          sender_error = std::current_exception();
        }
      });
      receiver_round.join();
      sender_round.join();
      if (receiver_error) {
        std::rethrow_exception(receiver_error);
      }
      if (sender_error) {
        std::rethrow_exception(sender_error);
      }

      require(selected.size() == choices.size(),
              "libOTe returned the wrong number of selected values");
      for (std::size_t i = 0; i < choices.size(); ++i) {
        require(selected[i] == offered[choices[i]],
                "libOTe chosen-message retrieval mismatch");
      }
      const auto expected_extended = (round + 1) * offered.size();
      require(receiver.extended_ots_consumed() == expected_extended &&
                  sender.extended_ots_consumed() == expected_extended,
              "chosen-message OT extension count is wrong");
    }

    const auto params = OleParams::defaults();
    const auto public_seed = deterministic_test_seed();
    auto receiver_private_seed = public_seed;
    auto sender_private_seed = public_seed;
    receiver_private_seed[0] ^= 0x5aU;
    sender_private_seed[0] ^= 0xa5U;
    OleReceiver ole_receiver(params, public_seed, receiver_private_seed,
                             0x9988776655443322ULL);
    OleSender ole_sender(params, public_seed, sender_private_seed,
                         0x9988776655443322ULL);
    for (std::size_t round = 0; round < 10; ++round) {
      std::vector<Fp> x(params.t, Fp::zero());
      std::vector<Fp> a(params.t, Fp::zero());
      std::vector<Fp> b(params.t, Fp::zero());
      for (std::size_t i = 0; i < params.t; ++i) {
        x[i] = value_prng.random_fp();
        a[i] = value_prng.random_fp();
        b[i] = value_prng.random_fp();
      }
      const auto encoding = ole_receiver.encode(x);
      const auto offered = ole_sender.respond(encoding, a, b);

      std::vector<Fp> retrieved;
      receiver_error = nullptr;
      sender_error = nullptr;
      std::thread receiver_round([&] {
        try {
          retrieved = ole_receiver.retrieve(receiver);
        } catch (...) {
          receiver_error = std::current_exception();
        }
      });
      std::thread sender_round([&] {
        try {
          sender.send(offered);
        } catch (...) {
          sender_error = std::current_exception();
        }
      });
      receiver_round.join();
      sender_round.join();
      if (receiver_error) {
        std::rethrow_exception(receiver_error);
      }
      if (sender_error) {
        std::rethrow_exception(sender_error);
      }

      const auto y = ole_receiver.reconstruct(retrieved);
      for (std::size_t i = 0; i < params.t; ++i) {
        require(y[i] == a[i] * x[i] + b[i],
                "end-to-end IPS-OLE over libOTe failed");
      }
    }
    const std::uint64_t expected_extended = 3 * 512 + 10 * params.n;
    require(receiver.extended_ots_consumed() == expected_extended &&
                sender.extended_ots_consumed() == expected_extended,
            "full IPS-OLE OT extension count is wrong");
    require(receiver.ots_consumed() ==
                receiver.base_ots_consumed() + expected_extended &&
                sender.ots_consumed() ==
                sender.base_ots_consumed() + expected_extended,
            "total OT count is wrong");
    protocol_logs.restore();
    require(protocol_logs.empty(),
            "S1 failed: IPS-OLE-over-libOTe wrote data to stdout/stderr");
    std::cout << "IPS-OLE libOTe Retriever tests passed\n";
    return 0;
  } catch (const std::exception& error) {
    std::cerr << "IPS-OLE libOTe test failure: " << error.what() << '\n';
    return 1;
  }
}
