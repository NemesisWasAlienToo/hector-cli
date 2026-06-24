#!/usr/bin/env python3
"""A tiny check executed *inside* the shell-test container, against the bind-mounted
project. Reads generated/values.txt (produced by the build step), sums the numeric
lines, and fails (non-zero exit) unless they total 42 — proving the build step's
output is visible to the test."""
import sys


def main():
    nums = []
    with open("generated/values.txt") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            nums.append(int(line))

    total = sum(nums)
    print(f"read {len(nums)} values, sum = {total}")
    if total != 42:
        print(f"FAIL: expected sum 42, got {total}", file=sys.stderr)
        sys.exit(1)
    print("PASS")


if __name__ == "__main__":
    main()
