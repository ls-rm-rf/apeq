# Current manuscript to source map

| Paper result or interface | Source entry |
|---|---|
| Independent bit-OT equality | `apeq-docker/docker/bench/apeq_ot_eq.cpp` |
| Packed OLE and public points | `apeq-ips-ole/`, `apeq-docker/docker/bench/apeq_eq.cpp` |
| Session-bound VOLE | `apeq-docker/docker/bench/apeq_vole_eq.cpp`, `apeq_vole_digest.h` |
| Persistent transport, fresh request cryptography | `apeq-docker/docker/bench/request_socket.h`, bit-OT and VOLE drivers |
| Private inputs and single-sided output | `apeq-docker/docker/bench/driver_common.h`, `reproduction/tools/check_application_io_v5.cpp` |
| E1, Fig. 7 and application tables | `reproduction/tools/run_application_v5.py`, `analyse_application_v5.py`, `make_v5_results.py` |
| E2 private-field leakage | Paper's ratio argument; `analysis/check_packed_ole_recovery.cpp` and exact-field checks |
| E3, Fig. 8 and sequence tables | `reproduction/tools/run_sequence_v5.py`, `analyse_sequence_v5.py`, `make_v5_results.py` |
| Arbitrary mask-degree affine-target recovery | `reproduction/tools/check_bivariate_family_v5.py`; proof remains in paper |
| Target rank and reduced-view controls | `reproduction/tools/check_bivariate_rank_v4.py` |
| Stripped-reply linearisation table | `analysis/reproduce_attack_table.py` |
| Packed all-reply R1 | `analysis/check_packed_ole_recovery.cpp` |
| Earlier bivariate repair diagnostic | `analysis/check_bivariate_repair_attack.py` |
| Candidate-message decoding cost | `analysis/estimate_rs.py`, `check_candidate_attack.py`, `compare_ole_parameters.py` |
| V4 and paired R2 | `reproduction/tools/prepare_v4.py`, `prepare_r2.py` and summary scripts |
| Historical batch/width/RTT figures | `apeq-pipeline/scripts/`, `experiments/` |
| Figs. 1 and 5 | PowerPoint authoring assets, excluded from source package |

Measured campaigns and proof diagnostics are distinct. Passing a correctness or
rank check is not a security proof. This package introduces no new measurements.
