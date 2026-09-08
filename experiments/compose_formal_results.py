#!/usr/bin/env python3
"""Replace stale ABY rows with the corrected revision while preserving provenance."""

import argparse
import csv
from pathlib import Path


def read_csv(path):
    with Path(path).open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return reader.fieldnames, list(reader)


def write_csv(path, header, rows):
    with Path(path).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=header, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def compose(base_path, correction_rows, network, output_path):
    header, base_rows = read_csv(base_path)
    replacements = [
        row for row in correction_rows
        if row["protocol"] == "aby_eq" and row["network"] == network
    ]
    kept = [row for row in base_rows if row["protocol"] != "aby_eq"]
    if not replacements:
        raise SystemExit(f"no corrected ABY rows found for network={network}")
    if any(row["network"] != network for row in base_rows):
        raise SystemExit(f"base file {base_path} contains another network")
    if set(header) != set(replacements[0]):
        raise SystemExit("base/correction CSV headers differ")
    rows = kept + replacements
    rows.sort(key=lambda row: (
        row["protocol"], row["variant"], int(row["input_bits"]),
        int(row["batch_size"]), int(row["rep"]), row["party"], row["run_id"]
    ))
    write_csv(output_path, header, rows)
    print(
        f"wrote {output_path}: kept={len(kept)} corrected_aby={len(replacements)} "
        f"total={len(rows)}"
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-lan", required=True)
    parser.add_argument("--base-wan", required=True)
    parser.add_argument("--base-round", required=True)
    parser.add_argument("--corrected-main", required=True)
    parser.add_argument("--corrected-round", required=True)
    parser.add_argument("--out-lan", required=True)
    parser.add_argument("--out-wan", required=True)
    parser.add_argument("--out-round", required=True)
    args = parser.parse_args()

    main_header, main_corrections = read_csv(args.corrected_main)
    round_header, round_corrections = read_csv(args.corrected_round)
    if main_header != round_header:
        raise SystemExit("corrected main/round CSV headers differ")

    compose(args.base_lan, main_corrections, "lan", args.out_lan)
    compose(args.base_wan, main_corrections, "wan", args.out_wan)
    compose(args.base_round, round_corrections, "round_sweep", args.out_round)


if __name__ == "__main__":
    main()
