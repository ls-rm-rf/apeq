FROM ubuntu:24.04

ARG DEBIAN_FRONTEND=noninteractive

RUN apt-get -o Acquire::Retries=5 update \
    && apt-get -o Acquire::Retries=5 install -y --no-install-recommends \
      bash \
      build-essential \
      ca-certificates \
      cmake \
      libboost-dev \
      libssl-dev \
      ninja-build \
      python3 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/ips-ole
COPY . .

RUN cmake -S . -B build -G Ninja \
      -DCMAKE_BUILD_TYPE=Release \
      -DFP_CHECKED=ON \
    && cmake --build build --parallel 4 \
    && ctest --test-dir build --output-on-failure \
    && bash tests/lint.sh \
    && build/ips_ole_vectors > /tmp/ips-ole-vector.tsv \
    && python3 reference/apeq_ole.py /tmp/ips-ole-vector.tsv

ARG IPS_OLE_REVISION=unknown
LABEL org.opencontainers.image.title="APEQ IPS-OLE core verification"
LABEL org.opencontainers.image.revision="${IPS_OLE_REVISION}"

CMD ["ctest", "--test-dir", "build", "--output-on-failure"]
