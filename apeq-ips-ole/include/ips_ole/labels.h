#pragma once

#include <string_view>

namespace apeq::ips_ole::labels {

inline constexpr std::string_view kPublicSession = "APEQ-v1-public-session";
inline constexpr std::string_view kReceiverSession = "APEQ-v1-receiver-session";
inline constexpr std::string_view kSenderSession = "APEQ-v1-sender-session";
inline constexpr std::string_view kPoints = "APEQ-v1-points";
inline constexpr std::string_view kNoise = "APEQ-v1-noise";
inline constexpr std::string_view kUVec = "APEQ-v1-uvec";
inline constexpr std::string_view kVVec = "APEQ-v1-vvec";
inline constexpr std::string_view kPolyAB = "APEQ-v1-polyAB";
inline constexpr std::string_view kEqualityA = "APEQ-v1-equality-a";
inline constexpr std::string_view kHkdfSalt = "APEQ-v1-HKDF-SHA256";

}  // namespace apeq::ips_ole::labels
