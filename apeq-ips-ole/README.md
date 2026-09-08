# IPS-OLE core

这是 `apeq` 的 IPS noisy-encoding OLE 核心（半诚实模型），对应
`apeq-pipeline/spec/ips-ole-backend.md` 的构建顺序 1–6。当前实现包括：

- `p = 2^127-1` 上封装的 Montgomery-domain `Fp`；
- 多项式求值、插值和带约束的有界次数均匀采样；
- 默认参数显式固定 `n=1024`、`rho=769`、`k=128`，并在
  `FP_CHECKED` 下检查 `deg(A)<=127`、`deg(B)<=254`；
- HKDF-SHA256 域分离、严格递增 batch counter；
- 无偏 partial Fisher–Yates 固定重量噪声；
- `encode/respond/reconstruct` 和仅用于测试的内存 Retriever；
- 独立 Python 整数参考实现及逐元素 transcript 交叉验证。
- 基于真实 McRosRoy base OT 和 IKNP OT extension 的 libOTe Retriever。
- Retriever 的真实 base/extended/total OT 计数器，以及完整运行无秘密日志的
  S1 回归测试。
- 公共点 seed、receiver 私有 seed、sender 私有 seed 三层严格分离；私有 seed
  来自 OS CSPRNG，绝不写入 CSV 或日志，避免 sender 从公共 benchmark seed
  推导 receiver 的噪声与掩码。

本目录仍只是 IPS-OLE 后端：`InMemoryRetriever` 只存在于 `tests/`，真实后端在
`adapters/libote_retriever.*`。端到端 equality 组合与统一 benchmark driver
位于 `apeq-docker/docker/bench/apeq_eq.cpp`；后端单元测试不能替代该 driver 的
端到端正确性和性能矩阵。

具体安全与组合边界见 [SECURITY.md](../SECURITY.md)：名义 128 参数不等于认证
128 位安全；功能测试不构成 libOTe 软件组合的端到端 UC 证明。最新 RS 攻击
成本与小域诊断源码见 [analysis/README.md](../analysis/README.md)。

## Docker 验证

从 `apeq-docker/docker` 目录运行：

```bash
bash ./build_image.sh ips-ole-core
docker run --rm apeq/ips-ole-core
```

构建过程会在镜像内开启 `FP_CHECKED`，运行 C++ 测试、源码 lint、生成固定测试
向量，再由 `reference/apeq_ole.py` 独立重算并逐元素比较。这个镜像不是 benchmark
driver 镜像，所以没有 `ENTRYPOINT /opt/bench/driver`，也不需要复制
`driver_common.h`；所有实际 baseline driver 镜像仍然必须复制该头文件。

真实 OT 镜像复用已经固定依赖版本的 `apeq/volepsi` 镜像，因此先构建 VolePSI：

```bash
bash ./build_image.sh volepsi
bash ./build_image.sh ips-ole-libote
docker run --rm apeq/ips-ole-libote
```

`ips-ole-libote` 在构建时验证真实 base OT、3 轮 chosen-message OT extension、
10 个默认参数的完整 `encode/respond/OT/reconstruct` batch。另有
`ips_ole_libote_tcp` 用于两个容器间的真实 TCP 检查。两个 IPS-OLE 镜像都是
验证镜像，不是 benchmark driver，因此都不复制 `driver_common.h`。

默认一次 Retriever 调用消耗 1024 个 extension OT。端到端 APEQ driver
对请求 batch `b` 执行 `ceil(b/48)` 个完整组，并把
`1024 * ceil(b/48)` 个 extension OT（以及 session setup 的 base OT）写入
CSV；补齐的 dummy 项所产生的时间和通信也必须计入。所有组在一次执行中
合并为一条 encoding 消息和一次 IKNP extension，不能按组顺序发起网络子协议，
否则实测轮数会错误地随 `ceil(b/48)` 增长。

默认测试用于每次构建的快速回归。扩大统计/代数测试可设置：

```bash
docker run --rm \
  -e IPS_OLE_FIELD_PAIRS=1000000 \
  -e IPS_OLE_FIELD_INVERSES=1000000 \
  -e IPS_OLE_NOISE_SAMPLES=1000000 \
  -e IPS_OLE_PROTOCOL_TRIALS=10000 \
  -e IPS_OLE_DEFAULT_PROTOCOL_TRIALS=5000 \
  apeq/ips-ole-core ./build/ips_ole_tests
```

每个 protocol trial 会验证两个连续 batch，因此 5000 个默认参数 trial 对应
P1 的 10000 个 batch。2026-08-28 已实际完成 F1 的 1,000,000 组运算、N1–N3 的
1,000,000 次默认参数固定重量抽样以及 P1 的 10,000 个默认参数 batch，均为零失败。
以后修改核心源码后必须重跑，不能沿用旧结果。
