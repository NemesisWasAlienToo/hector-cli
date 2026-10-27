#!/usr/bin/env python3
"""Extract U-Boot proper, TF-A BL31 and U-Boot's control DTB from an i.MX8M `imx-boot`.

imx-boot (flash.bin) is: IVT + SPL + DDR training firmware, followed by a FIT image
with external data ("Configuration to load ATF before U-Boot"). The FIT is a plain
flattened device tree; each image node carries `data-position`/`data-size` relative
to the start of the FIT, plus `load`/`entry` addresses.
"""
import argparse
import json
import os
import struct
import sys

FDT_MAGIC = 0xD00DFEED
FDT_BEGIN_NODE, FDT_END_NODE, FDT_PROP, FDT_NOP, FDT_END = 1, 2, 3, 4, 9


def parse_fdt(blob):
    """Return a nested dict {name: {"props": {...}, "nodes": {...}}} for an FDT blob."""
    magic, totalsize, off_struct, off_strings = struct.unpack_from(">IIII", blob, 0)
    if magic != FDT_MAGIC:
        raise ValueError("not an FDT")

    def string_at(off):
        end = blob.index(b"\0", off_strings + off)
        return blob[off_strings + off:end].decode()

    root = {"props": {}, "nodes": {}}
    stack = []
    pos = off_struct
    while True:
        (token,) = struct.unpack_from(">I", blob, pos)
        pos += 4
        if token == FDT_BEGIN_NODE:
            end = blob.index(b"\0", pos)
            name = blob[pos:end].decode()
            pos = (end + 4) & ~3
            node = {"props": {}, "nodes": {}}
            if stack:
                stack[-1]["nodes"][name] = node
            else:
                node = root
            stack.append(node)
        elif token == FDT_END_NODE:
            stack.pop()
        elif token == FDT_PROP:
            length, nameoff = struct.unpack_from(">II", blob, pos)
            pos += 8
            stack[-1]["props"][string_at(nameoff)] = blob[pos:pos + length]
            pos = (pos + length + 3) & ~3
        elif token == FDT_NOP:
            continue
        elif token == FDT_END:
            return root, totalsize
        else:
            raise ValueError("bad FDT token 0x%x at 0x%x" % (token, pos - 4))


def cells(value):
    """Decode a big-endian 1- or 2-cell integer property."""
    if len(value) == 4:
        return struct.unpack(">I", value)[0]
    if len(value) == 8:
        hi, lo = struct.unpack(">II", value)
        return (hi << 32) | lo
    raise ValueError("unexpected cell size %d" % len(value))


def find_fit(blob):
    """Find the U-Boot FIT: an FDT that has /images and /configurations nodes."""
    off = 0
    while True:
        off = blob.find(struct.pack(">I", FDT_MAGIC), off)
        if off < 0:
            raise ValueError("no FIT image found")
        try:
            tree, size = parse_fdt(blob[off:])
            if "images" in tree["nodes"] and "configurations" in tree["nodes"]:
                return off, tree
        except (ValueError, IndexError, struct.error):
            pass
        off += 4


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("imx_boot")
    ap.add_argument("outdir")
    args = ap.parse_args()

    blob = open(args.imx_boot, "rb").read()
    fit_off, fit = find_fit(blob)
    images = fit["nodes"]["images"]["nodes"]
    configs = fit["nodes"]["configurations"]
    default = configs["props"]["default"].rstrip(b"\0").decode()
    config = configs["nodes"][default]["props"]

    def image(name):
        props = images[name]["props"]
        pos = cells(props["data-position"])
        size = cells(props["data-size"])
        return props, blob[fit_off + pos:fit_off + pos + size]

    def prop_name(key):
        return config[key].split(b"\0")[0].decode()

    uboot_props, uboot = image(prop_name("firmware"))
    atf_props, atf = image(prop_name("loadables"))
    dtb_props, dtb = image(prop_name("fdt"))

    os.makedirs(args.outdir, exist_ok=True)
    out = {
        "fit_offset": fit_off,
        "uboot_load": cells(uboot_props["load"]),
        "bl31_load": cells(atf_props["load"]),
        "bl31_entry": cells(atf_props["entry"]),
        "uboot_dtb": dtb_props["description"].rstrip(b"\0").decode(),
    }
    for name, data in (("u-boot-nodtb.bin", uboot), ("bl31.bin", atf), ("u-boot.dtb", dtb),
                       # CONFIG_OF_SEPARATE: U-Boot expects its control DTB right after the image (_end)
                       ("u-boot.bin", uboot + dtb)):
        with open(os.path.join(args.outdir, name), "wb") as f:
            f.write(data)
    json.dump(out, sys.stdout, indent=2)
    print()


if __name__ == "__main__":
    main()
