#!/bin/bash
# Turn an official Torizon OS Toradex Easy Installer (Tezi) tarball into the files
# a Verdin iMX8M Plus would have after being flashed by Tezi, plus the individual
# boot artifacts for direct loading:
#
#   emmc.img          eMMC user area: MBR + one ext4 partition "otaroot" (the OTA rootfs)
#   emmc-boot0.img    eMMC boot0 hw partition: imx-boot @0, Toradex config block @end-512
#   u-boot.bin        U-Boot proper + control DTB (loaded at 0x40200000)
#   bl31.bin          TF-A BL31 (loaded at 0x970000)
#   Image, initramfs.img, <fdtfile>.dtb, bootargs.txt   kernel artifacts from the OSTree deployment
#
# Runs as root inside a container (see ../prepare-image.sh), so that file ownership,
# device nodes and hard links of the rootfs are preserved in the ext4 image.
set -euo pipefail

TEZI_TAR=$1
OUT=$2
EMMC_SIZE_MB=${EMMC_SIZE_MB:-2048}
BOOT0_SIZE=${BOOT0_SIZE:-$((8 * 1024 * 1024))}   # Renode's eMMC model default boot partition size
PART_START_SECTOR=${PART_START_SECTOR:-8192}        # 4 MiB alignment, as Tezi does
# Toradex product ID written to the config block, see U-Boot board/toradex/common/tdx-cfg-block.c:
#   0061 Quad 2GB (no Wi-Fi/BT)   0063 Quad 4GB IT (no Wi-Fi/BT)   0065 QuadLite 1GB IT (no Wi-Fi/BT)
#   0064 Quad 2GB WB IT           0058 Quad 4GB WB IT              0066/0070 Quad 8GB WB (IT)
PRODUCT_ID=${PRODUCT_ID:-61}
MODULE_VERSION=${MODULE_VERSION:-1.1A}
SERIAL=${SERIAL:-12345678}
# Optional extra kernel arguments, injected the way Torizon supports it (U-Boot env
# `torizon_bootargs_r`). Empty by default: the image's own bootargs are used as-is.
EXTRA_KARGS=${EXTRA_KARGS:-}

HERE=$(cd "$(dirname "$0")" && pwd)
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
mkdir -p "$OUT"

echo "==> Unpacking Tezi image $(basename "$TEZI_TAR")"
tar -xf "$TEZI_TAR" -C "$WORK"
TEZI=$(dirname "$(find "$WORK" -maxdepth 2 -name image.json | head -1)")

ROOTFS_TAR=$(python3 -I -c 'import json,sys; d=json.load(open(sys.argv[1])); print(next(p["content"]["filename"] for b in d["blockdevs"] if b["name"]=="emmc" for p in b["partitions"]))' "$TEZI/image.json")
LABEL=$(python3 -I -c 'import json,sys; d=json.load(open(sys.argv[1])); print(next(p["content"]["label"] for b in d["blockdevs"] if b["name"]=="emmc" for p in b["partitions"]))' "$TEZI/image.json")
BOOTLOADER=$(python3 -I -c 'import json,sys; d=json.load(open(sys.argv[1])); print(next(f["filename"] for b in d["blockdevs"] if b["name"]=="emmc-boot0" for f in b["content"]["rawfiles"]))' "$TEZI/image.json")
python3 -I -c 'import json,sys; d=json.load(open(sys.argv[1])); print("    %s %s (%s)" % (d["name"], d["version"], d["release_date"]))' "$TEZI/image.json"

echo "==> Extracting U-Boot and BL31 from $BOOTLOADER"
python3 -I "$HERE/fit_extract.py" "$TEZI/$BOOTLOADER" "$OUT" > "$OUT/imx-boot.json"
cat "$OUT/imx-boot.json"
cp "$TEZI/$BOOTLOADER" "$OUT/imx-boot"
cp "$TEZI/$(python3 -I -c 'import json,sys; print(json.load(open(sys.argv[1]))["u_boot_env"])' "$TEZI/image.json")" "$OUT/u-boot-initial-env"

echo "==> Building eMMC boot0 ($((BOOT0_SIZE / 1024)) KiB)"
python3 -I "$HERE/tdx_cfgblock.py" "$WORK/cfgblock.bin" --product-id "$PRODUCT_ID" --version "$MODULE_VERSION" --serial "$SERIAL"
truncate -s 0 "$OUT/emmc-boot0.img"
truncate -s "$BOOT0_SIZE" "$OUT/emmc-boot0.img"
dd if="$TEZI/$BOOTLOADER" of="$OUT/emmc-boot0.img" conv=notrunc status=none
# CONFIG_TDX_CFG_BLOCK_PART=1, CONFIG_TDX_CFG_BLOCK_OFFSET=-512
dd if="$WORK/cfgblock.bin" of="$OUT/emmc-boot0.img" bs=512 seek=$((BOOT0_SIZE / 512 - 1)) conv=notrunc status=none
if [ -n "$EXTRA_KARGS" ]; then
    echo "    adding torizon_bootargs_r=\"$EXTRA_KARGS\" to the U-Boot environment"
    { grep -v '^torizon_bootargs_r=' "$OUT/u-boot-initial-env"; echo "torizon_bootargs_r=$EXTRA_KARGS"; } > "$WORK/env.txt"
    # CONFIG_SYS_MMC_ENV_PART=1, CONFIG_ENV_OFFSET=-0x2200, CONFIG_ENV_SIZE=0x2000
    mkenvimage -s 0x2000 -o "$WORK/env.bin" "$WORK/env.txt"
    dd if="$WORK/env.bin" of="$OUT/emmc-boot0.img" bs=512 seek=$(((BOOT0_SIZE - 0x2200) / 512)) conv=notrunc status=none
fi

echo "==> Unpacking rootfs $ROOTFS_TAR"
mkdir "$WORK/rootfs"
zstd -dc "$TEZI/$ROOTFS_TAR" | tar --numeric-owner --xattrs --xattrs-include='*' -xpf - -C "$WORK/rootfs"

echo "==> Collecting kernel artifacts from the OSTree deployment"
UENV="$WORK/rootfs/boot/loader/uEnv.txt"
uenv() { sed -n "s/^$1=//p" "$UENV" | head -1; }
KERNEL=$(uenv kernel_image); INITRD=$(uenv ramdisk_image); FDTDIR=$(uenv fdtdir)
FDTFILE=$(sed -n 's/^fdtfile=//p' "$OUT/u-boot-initial-env")
if [ -z "$FDTFILE" ]; then
    # preboot: fdtfile=imx8mp-verdin-${variant}-${fdt_board}.dtb; U-Boot sets variant=wifi for "WB" modules
    case $((10#$PRODUCT_ID)) in 61|63|65) VARIANT=nonwifi ;; *) VARIANT=wifi ;; esac
    FDTFILE=$(sed -n 's/^fdt_board=//p' "$OUT/u-boot-initial-env")
    FDTFILE="imx8mp-verdin-${VARIANT}-${FDTFILE}.dtb"
fi
gzip -dc "$WORK/rootfs$KERNEL" > "$OUT/Image"
cp "$WORK/rootfs$INITRD" "$OUT/initramfs.img"
cp "$WORK/rootfs/boot$FDTDIR/$FDTFILE" "$OUT/$FDTFILE"
# Same composition as uEnv.txt's set_bootargs (defargs/tdxargs are empty by default)
echo "root=LABEL=$LABEL rootfstype=ext4 $(uenv bootargs) $EXTRA_KARGS" | sed 's/ *$//' > "$OUT/bootargs.txt"
echo "    kernel:  $KERNEL"
echo "    fdtfile: $FDTFILE"
echo "    args:    $(cat "$OUT/bootargs.txt")"

echo "==> Building eMMC user area (${EMMC_SIZE_MB} MiB)"
PART_SECTORS=$((EMMC_SIZE_MB * 2048 - PART_START_SECTOR))
mkfs.ext4 -q -F -L "$LABEL" -E nodiscard -d "$WORK/rootfs" "$WORK/part.img" "$((PART_SECTORS / 2))k"
rm -f "$OUT/emmc.img"
truncate -s "${EMMC_SIZE_MB}M" "$OUT/emmc.img"
echo "start=$PART_START_SECTOR, size=$PART_SECTORS, type=83" | sfdisk -q --label dos "$OUT/emmc.img"
dd if="$WORK/part.img" of="$OUT/emmc.img" bs=1M seek=$((PART_START_SECTOR / 2048)) conv=notrunc,sparse status=none

chown -R "${HOST_UID:-0}:${HOST_GID:-0}" "$OUT"
echo "==> Done: $OUT"
ls -la "$OUT"
