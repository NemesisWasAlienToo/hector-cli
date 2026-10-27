#!/usr/bin/env python3
"""Generate a Toradex module config block (as written to eMMC boot0 at the factory).

Layout follows U-Boot's board/toradex/common/tdx-cfg-block.c: a sequence of 32-bit
little-endian tags {len:14 (payload in words), flags:2, id:16}, each followed by
its payload, terminated by an all-ones TAG_INVALID word.
"""
import argparse
import struct

TAG_VALID = 0xCF01
TAG_MAC = 0x0000
TAG_HW = 0x0008
TAG_INVALID = 0xFFFF
TAG_FLAG_VALID = 0x1

TORADEX_OUI = bytes((0x00, 0x14, 0x2D))
CFG_BLOCK_SIZE = 512


def tag(tag_id, payload=b""):
    payload += b"\0" * (-len(payload) % 4)
    word = (len(payload) // 4) | (TAG_FLAG_VALID << 14) | (tag_id << 16)
    return struct.pack("<I", word) + payload


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("output")
    ap.add_argument("--product-id", type=int, default=61,
                    help="Toradex product ID (default: 0061, Verdin iMX8M Plus Quad 2GB, no Wi-Fi/BT)")
    ap.add_argument("--version", default="1.1A", help="module revision, e.g. 1.1A")
    ap.add_argument("--serial", type=int, default=12345678,
                    help="serial number; also the NIC part of the MAC address")
    args = ap.parse_args()

    major, minor, assembly = int(args.version[0]), int(args.version[2]), ord(args.version[3]) - ord("A")
    hw = struct.pack("<HHHH", major, minor, assembly, args.product_id)
    mac = TORADEX_OUI + args.serial.to_bytes(3, "big")

    block = tag(TAG_VALID) + tag(TAG_HW, hw) + tag(TAG_MAC, mac)
    block += b"\xff" * (CFG_BLOCK_SIZE - len(block))
    with open(args.output, "wb") as f:
        f.write(block)


if __name__ == "__main__":
    main()
