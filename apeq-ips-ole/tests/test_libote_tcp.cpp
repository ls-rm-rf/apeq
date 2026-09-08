#include "ips_ole/core.h"
#include "libote_retriever.h"

#include <coproto/Socket/AsioSocket.h>
#include <cryptoTools/Crypto/PRNG.h>
#include <macoro/sync_wait.h>

#include <cstddef>
#include <exception>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

int main(int argc, char** argv) {
  using namespace apeq::ips_ole;
  try {
    if (argc != 3) {
      throw std::invalid_argument(
          "usage: ips_ole_libote_tcp {sender|receiver} host:port");
    }
    const std::string role = argv[1];
    if (role != "sender" && role != "receiver") {
      throw std::invalid_argument("role must be sender or receiver");
    }
    auto socket = coproto::asioConnect(argv[2], role == "sender");
    osuCrypto::PRNG libote_prng(osuCrypto::sysRandomSeed());
    Prng value_prng(deterministic_test_seed());
    std::uint64_t base_ots = 0;
    std::uint64_t extended_ots = 0;

    if (role == "sender") {
      LibOteSenderRetriever retriever(socket, libote_prng);
      retriever.setup();
      for (std::size_t round = 0; round < 3; ++round) {
        std::vector<Fp> offered(512, Fp::zero());
        for (auto& value : offered) {
          value = value_prng.random_fp();
        }
        retriever.send(offered);
      }
      base_ots = retriever.base_ots_consumed();
      extended_ots = retriever.extended_ots_consumed();
    } else {
      LibOteReceiverRetriever retriever(socket, libote_prng);
      retriever.setup();
      for (std::size_t round = 0; round < 3; ++round) {
        std::vector<Fp> expected(512, Fp::zero());
        for (auto& value : expected) {
          value = value_prng.random_fp();
        }
        std::vector<std::size_t> choices;
        for (std::size_t i = round; i < expected.size(); i += 3 + round) {
          choices.push_back(i);
        }
        const auto selected = retriever.retrieve(expected.size(), choices);
        if (selected.size() != choices.size()) {
          throw std::runtime_error("TCP Retriever returned wrong value count");
        }
        for (std::size_t i = 0; i < choices.size(); ++i) {
          if (!(selected[i] == expected[choices[i]])) {
            throw std::runtime_error("TCP Retriever value mismatch");
          }
        }
      }
      base_ots = retriever.base_ots_consumed();
      extended_ots = retriever.extended_ots_consumed();
    }
    if (base_ots == 0 || extended_ots != 3 * 512) {
      throw std::runtime_error("TCP Retriever reported a wrong OT count");
    }
    macoro::sync_wait(socket.flush());
    std::cout << "IPS-OLE libOTe TCP " << role << " passed sent="
              << socket.bytesSent() << " recv=" << socket.bytesReceived()
              << " base_ot=" << base_ots << " extended_ot=" << extended_ots
              << " n_ot=" << base_ots + extended_ots << '\n';
    return 0;
  } catch (const std::exception& error) {
    std::cerr << "IPS-OLE libOTe TCP failure: " << error.what() << '\n';
    return 1;
  }
}
