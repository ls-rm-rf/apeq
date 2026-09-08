#!/usr/bin/env python3
"""Independent, deterministic reference for the IPS-OLE core test vector.

This intentionally uses Python integers instead of sharing C++ field or polynomial
code. It consumes only public transcript fields from ips_ole_vectors; secret L/u/A/B
values are derived locally and are never written to the vector file.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
from pathlib import Path

P = (1 << 127) - 1
N, RHO, ELL, K, T = 1024, 769, 255, 128, 48
DEG_A, DEG_B = 127, 254
HKDF_SALT = b"APEQ-v1-HKDF-SHA256"


def hmac256(key: bytes, message: bytes) -> bytes:
    return hmac.new(key, message, hashlib.sha256).digest()


def derive_key(parent: bytes, label: bytes, suffix: bytes = b"") -> bytes:
    extracted = hmac256(HKDF_SALT, parent)
    return hmac256(extracted, label + suffix + b"\x01")


class Prng:
    def __init__(self, seed: bytes):
        self.seed = seed
        self.counter = 0
        self.block = b""
        self.position = 0

    def _bytes(self, size: int) -> bytes:
        output = bytearray()
        while len(output) < size:
            if self.position == len(self.block):
                self.block = hmac256(self.seed, self.counter.to_bytes(8, "big"))
                self.counter += 1
                self.position = 0
            take = min(size - len(output), len(self.block) - self.position)
            output.extend(self.block[self.position : self.position + take])
            self.position += take
        return bytes(output)

    def next_u64(self) -> int:
        return int.from_bytes(self._bytes(8), "big")

    def uniform_below(self, bound: int) -> int:
        if bound <= 0:
            raise ValueError("bound must be positive")
        threshold = ((1 << 64) - bound) % bound
        while True:
            value = self.next_u64()
            if value >= threshold:
                return value % bound

    def fp(self) -> int:
        while True:
            high = self.next_u64() & ((1 << 63) - 1)
            low = self.next_u64()
            value = (high << 64) | low
            if value < P:
                return value


def add_poly(left: list[int], right: list[int]) -> list[int]:
    result = [0] * max(len(left), len(right))
    for i, value in enumerate(left):
        result[i] = (result[i] + value) % P
    for i, value in enumerate(right):
        result[i] = (result[i] + value) % P
    return result


def mul_poly(left: list[int], right: list[int]) -> list[int]:
    result = [0] * (len(left) + len(right) - 1)
    for i, a in enumerate(left):
        for j, b in enumerate(right):
            result[i + j] = (result[i + j] + a * b) % P
    return result


def evaluate(poly: list[int], point: int) -> int:
    result = 0
    for coefficient in reversed(poly):
        result = (result * point + coefficient) % P
    return result


def interpolate(points: list[int], values: list[int]) -> list[int]:
    if not points or len(points) != len(values) or len(set(points)) != len(points):
        raise ValueError("invalid interpolation input")
    product = [1]
    for point in points:
        product = mul_poly(product, [(-point) % P, 1])
    derivative = [(i * product[i]) % P for i in range(1, len(product))]
    result = [0] * len(points)
    for point, value in zip(points, values):
        scale = value * pow(evaluate(derivative, point), P - 2, P) % P
        quotient = [0] * len(points)
        quotient[-1] = product[-1]
        for j in range(len(points) - 1, 0, -1):
            quotient[j - 1] = (product[j] + point * quotient[j]) % P
        if (product[0] + point * quotient[0]) % P:
            raise AssertionError("nonzero synthetic-division remainder")
        for j, coefficient in enumerate(quotient):
            result[j] = (result[j] + coefficient * scale) % P
    return result


def constrained(points: list[int], values: list[int], degree: int, prng: Prng) -> list[int]:
    base = interpolate(points, values)
    vanishing = [1]
    for point in points:
        vanishing = mul_poly(vanishing, [(-point) % P, 1])
    q_degree = degree - len(points)
    quotient = [prng.fp() for _ in range(q_degree + 1)]
    result = add_poly(base, mul_poly(vanishing, quotient))
    return result


def sample_l(prng: Prng) -> list[int]:
    indices = list(range(N))
    for i in range(ELL):
        j = i + prng.uniform_below(N - i)
        indices[i], indices[j] = indices[j], indices[i]
    return indices[:ELL]


def generate() -> dict[str, list[int]]:
    public_seed = bytes(range(32))
    receiver_private_seed = bytes(value ^ 0x5A for value in public_seed)
    sender_private_seed = bytes(value ^ 0xA5 for value in public_seed)
    session_id = 0x0102030405060708
    suffix_session = session_id.to_bytes(8, "big")
    public_session = derive_key(
        public_seed, b"APEQ-v1-public-session", suffix_session
    )
    receiver_session = derive_key(
        receiver_private_seed, b"APEQ-v1-receiver-session", suffix_session
    )
    sender_session = derive_key(
        sender_private_seed, b"APEQ-v1-sender-session", suffix_session
    )

    point_prng = Prng(derive_key(public_session, b"APEQ-v1-points"))
    seen: set[int] = set()

    def points(count: int) -> list[int]:
        result: list[int] = []
        while len(result) < count:
            candidate = point_prng.fp()
            if candidate and candidate not in seen:
                seen.add(candidate)
                result.append(candidate)
        return result

    input_points = points(K)
    codeword_points = points(N)
    counter = 1
    suffix = counter.to_bytes(8, "big")
    noise_prng = Prng(derive_key(receiver_session, b"APEQ-v1-noise", suffix))
    u_prng = Prng(derive_key(receiver_session, b"APEQ-v1-uvec", suffix))
    v_prng = Prng(derive_key(receiver_session, b"APEQ-v1-vvec", suffix))
    ab_prng = Prng(derive_key(sender_session, b"APEQ-v1-polyAB", suffix))

    x = [1000 + i for i in range(T)]
    a = [2000 + 3 * i for i in range(T)]
    b = [3000 + 5 * i for i in range(T)]
    selected = sample_l(noise_prng)
    u = [u_prng.fp() for _ in range(K)]
    u[:T] = x
    poly_p = interpolate(input_points, u)
    v = [v_prng.fp() for _ in range(N)]
    for choice in selected:
        v[choice] = evaluate(poly_p, codeword_points[choice])

    poly_a = constrained(input_points[:T], a, DEG_A, ab_prng)
    poly_b = constrained(input_points[:T], b, DEG_B, ab_prng)
    w = [
        (evaluate(poly_a, point) * value + evaluate(poly_b, point)) % P
        for point, value in zip(codeword_points, v)
    ]
    poly_y = interpolate(
        [codeword_points[i] for i in selected], [w[i] for i in selected]
    )
    y = [evaluate(poly_y, input_points[i]) for i in range(T)]
    return {
        "input_points": input_points,
        "codeword_points": codeword_points,
        "x": x,
        "a": a,
        "b": b,
        "v": v,
        "w": w,
        "y": y,
    }


def read_vector(path: Path) -> dict[str, list[int]]:
    values: dict[str, list[int]] = {}
    for line in path.read_text(encoding="ascii").splitlines():
        name, index, value = line.split("\t")
        if name == "meta":
            continue
        bucket = values.setdefault(name, [])
        if int(index) != len(bucket):
            raise ValueError(f"non-contiguous {name} index")
        bucket.append(int(value, 16))
    return values


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("vector", type=Path)
    args = parser.parse_args()
    expected = generate()
    actual = read_vector(args.vector)
    for name, expected_values in expected.items():
        if actual.get(name) != expected_values:
            for i, (left, right) in enumerate(zip(actual.get(name, []), expected_values)):
                if left != right:
                    raise SystemExit(f"P2 mismatch: {name}[{i}]")
            raise SystemExit(f"P2 mismatch: {name} length")
    print("IPS-OLE Python cross-validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
