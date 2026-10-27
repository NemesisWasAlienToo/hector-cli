#!/usr/bin/env python3
"""A tiny check executed *inside* the shell-test container, against the bind-mounted
project. Reads generated/values.txt (produced by the prepare step), sums the numeric
lines, and fails (non-zero exit) unless they total $EXPECTED_SUM (set by the test's
docker-flags) — proving the prepare step's output is visible to the test."""
import os
import sys


def main():
    nums = []
    with open("generated/values.txt") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            nums.append(int(line))

    expected = int(os.environ["EXPECTED_SUM"])
    total = sum(nums)
    print(f"read {len(nums)} values, sum = {total}")
    if total != expected:
        print(f"FAIL: expected sum {expected}, got {total}", file=sys.stderr)
        sys.exit(1)
    print("PASS")


if __name__ == "__main__":
    main()
