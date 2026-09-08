#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
docker run --rm --network none \
  --mount "type=bind,src=$ROOT/apeq-docker/docker/bench,dst=/bench,readonly" \
  --mount "type=bind,src=$ROOT/reproduction/tools,dst=/tests,readonly" \
  --entrypoint /bin/sh apeq/apeq-ot \
  -c 'g++ -std=c++17 -O2 -I/bench /tests/check_application_io_v5.cpp -o /tmp/check-input && /tmp/check-input'
