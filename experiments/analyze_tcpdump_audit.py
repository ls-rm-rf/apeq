#!/usr/bin/env python3
"""Compare unique TCP payload bytes with in-process benchmark counters."""

import csv
import argparse
import os
import re
from collections import defaultdict


ENDPOINT = re.compile(
    r"^(?P<time>\d+\.\d+) IP "
    r"(?P<src>\d+\.\d+\.\d+\.\d+)\.(?P<sport>\d+) > "
    r"(?P<dst>\d+\.\d+\.\d+\.\d+)\.(?P<dport>\d+): (?P<rest>.*)$"
)
SEQ = re.compile(r"\bseq (?P<start>\d+):(?P<end>\d+)")
LENGTH = re.compile(r"\blength (?P<length>\d+)\s*$")


def union_size(intervals):
    total = 0
    current_start = current_end = None
    for start, end in sorted(intervals):
        if current_start is None:
            current_start, current_end = start, end
        elif start <= current_end:
            current_end = max(current_end, end)
        else:
            total += current_end - current_start
            current_start, current_end = start, end
    if current_start is not None:
        total += current_end - current_start
    return total


def parse_capture(path, a_ip, b_ip):
    intervals = defaultdict(list)
    raw_bytes = defaultdict(int)
    packets = defaultdict(int)
    events = []
    unparsed_payload = []
    with open(path, encoding="utf-8", errors="replace") as handle:
        for line_number, line in enumerate(handle, 1):
            match = ENDPOINT.match(line.rstrip())
            if not match:
                continue
            length_match = LENGTH.search(match.group("rest"))
            if not length_match or int(length_match.group("length")) == 0:
                continue
            length = int(length_match.group("length"))
            seq_match = SEQ.search(match.group("rest"))
            if not seq_match:
                unparsed_payload.append((line_number, line.rstrip()))
                continue
            src, dst = match.group("src"), match.group("dst")
            if src == a_ip and dst == b_ip:
                direction = "A_to_B"
            elif src == b_ip and dst == a_ip:
                direction = "B_to_A"
            else:
                continue
            key = (direction, match.group("sport"), match.group("dport"))
            start, end = int(seq_match.group("start")), int(seq_match.group("end"))
            intervals[key].append((start, end))
            raw_bytes[direction] += length
            packets[direction] += 1
            events.append((float(match.group("time")), direction, length))

    if unparsed_payload:
        raise RuntimeError(f"{path}: {len(unparsed_payload)} payload packet(s) lack sequence ranges")

    unique = defaultdict(int)
    for key, ranges in intervals.items():
        unique[key[0]] += union_size(ranges)

    # Collapse consecutive data packets in the same direction. These are TCP
    # payload bursts, not automatically protocol rounds, but they expose every
    # direction switch for the EMP audit.
    bursts = []
    for timestamp, direction, length in sorted(events):
        if not bursts or bursts[-1][1] != direction:
            bursts.append([timestamp, direction, length, 1])
        else:
            bursts[-1][2] += length
            bursts[-1][3] += 1
    return unique, raw_bytes, packets, bursts


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--audit-dir",
        default=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "tcpdump-audit-8251"),
    )
    args = parser.parse_args()
    audit = os.path.realpath(os.path.abspath(args.audit_dir))
    input_csv = os.path.join(audit, "results-normalized.csv")
    metadata_path = os.path.join(audit, "captures.tsv")
    output_path = os.path.join(audit, "tcp-payload-audit.csv")
    bursts_path = os.path.join(audit, "payload-bursts.csv")
    report_path = os.path.join(audit, "TCPDUMP_AUDIT.md")

    with open(input_csv, newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    parties = defaultdict(dict)
    for row in rows:
        parties[row["run_id"]][row["party"]] = row

    with open(metadata_path, newline="", encoding="utf-8") as handle:
        metadata = list(csv.DictReader(handle, delimiter="\t"))

    output = []
    burst_rows = []
    for item in metadata:
        run_id = item["run_id"]
        pair = parties[run_id]
        if set(pair) != {"A", "B"}:
            raise RuntimeError(f"{run_id}: missing A/B result rows")
        unique, raw, packets, bursts = parse_capture(
            os.path.join(audit, item["packets"]), item["a_ip"], item["b_ip"]
        )
        internal_a_to_b = int(pair["A"]["bytes_sent"])
        internal_b_to_a = int(pair["B"]["bytes_sent"])
        values = {
            "run_id": run_id,
            "protocol": item["protocol"],
            "backend": item["backend"],
            "variant": item["variant"],
            "a_to_b_internal": internal_a_to_b,
            "a_to_b_tcp_unique": unique["A_to_B"],
            "a_to_b_difference": unique["A_to_B"] - internal_a_to_b,
            "b_to_a_internal": internal_b_to_a,
            "b_to_a_tcp_unique": unique["B_to_A"],
            "b_to_a_difference": unique["B_to_A"] - internal_b_to_a,
            "a_to_b_tcp_raw": raw["A_to_B"],
            "b_to_a_tcp_raw": raw["B_to_A"],
            "a_to_b_retransmitted": raw["A_to_B"] - unique["A_to_B"],
            "b_to_a_retransmitted": raw["B_to_A"] - unique["B_to_A"],
            "a_to_b_payload_packets": packets["A_to_B"],
            "b_to_a_payload_packets": packets["B_to_A"],
            "payload_bursts": len(bursts),
        }
        output.append(values)
        origin = bursts[0][0] if bursts else 0.0
        for index, (timestamp, direction, length, count) in enumerate(bursts, 1):
            burst_rows.append({
                "run_id": run_id,
                "protocol": item["protocol"],
                "variant": item["variant"],
                "burst": index,
                "offset_ms": (timestamp - origin) * 1000.0,
                "direction": direction,
                "payload_bytes": length,
                "packets": count,
            })

    with open(output_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(output[0]))
        writer.writeheader()
        writer.writerows(output)
    with open(bursts_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(burst_rows[0]))
        writer.writeheader()
        writer.writerows(burst_rows)

    with open(report_path, "w", encoding="utf-8") as handle:
        handle.write("# E3/E4 TCP payload audit\n\n")
        handle.write("Each row is one independent 64-bit, batch-100, RTT-20 ms execution. ")
        handle.write("TCP values are unique sequence-space payload bytes, excluding Ethernet/IP/TCP headers and retransmissions.\n\n")
        handle.write("| Protocol | Variant | A→B internal | A→B TCP | Δ | B→A internal | B→A TCP | Δ | Retransmitted | Bursts |\n")
        handle.write("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|\n")
        for row in output:
            retransmitted = row["a_to_b_retransmitted"] + row["b_to_a_retransmitted"]
            handle.write(
                f"| {row['protocol']} | {row['variant']} | "
                f"{row['a_to_b_internal']} | {row['a_to_b_tcp_unique']} | {row['a_to_b_difference']} | "
                f"{row['b_to_a_internal']} | {row['b_to_a_tcp_unique']} | {row['b_to_a_difference']} | "
                f"{retransmitted} | {row['payload_bursts']} |\n"
            )
    print(f"wrote {output_path}")
    print(f"wrote {bursts_path}")
    print(f"wrote {report_path}")


if __name__ == "__main__":
    main()
