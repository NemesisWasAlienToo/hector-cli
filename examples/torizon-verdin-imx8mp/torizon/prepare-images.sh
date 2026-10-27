#!/bin/bash
# Official Torizon OS Tezi image -> what the eMMC of a flashed Verdin iMX8M Plus holds, plus the
# U-Boot / BL31 binaries that SPL would leave in memory (images/). Downloads the Tezi tarball
# into downloads/ if needed; does nothing if the images are newer than the tarball and scripts.
#
#   torizon/prepare-images.sh [output-dir]      (default: images/ next to this folder)
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(dirname "$HERE")
TORIZON_VERSION=${TORIZON_VERSION:-7.8.0+build.60}
TORIZON_URL=${TORIZON_URL:-https://artifacts.toradex.com/artifactory/torizoncore-oe-prod-frankfurt/scarthgap-7.x.y/release/${TORIZON_VERSION##*.}/verdin-imx8mp/torizon/torizon-docker/oedeploy/torizon-docker-verdin-imx8mp-Tezi_${TORIZON_VERSION}.tar}
TEZI_TAR=$ROOT/downloads/torizon-docker-verdin-imx8mp-Tezi_${TORIZON_VERSION}.tar
OUT=${1:-$ROOT/images}

if [ ! -f "$TEZI_TAR" ]; then
    mkdir -p "$(dirname "$TEZI_TAR")"
    echo "==> Downloading ${TORIZON_URL}"
    curl -fL --progress-bar -o "$TEZI_TAR.part" "${TORIZON_URL//+/%2B}"
    mv "$TEZI_TAR.part" "$TEZI_TAR"
fi

up_to_date=true
for f in emmc.img emmc-boot0.img u-boot.bin bl31.bin; do
    for src in "$TEZI_TAR" "$HERE"/*; do
        [ "$OUT/$f" -nt "$src" ] || up_to_date=false
    done
done
if $up_to_date; then
    echo "==> Images in $OUT are up to date"
    exit 0
fi

mkdir -p "$OUT"
OUT=$(cd "$OUT" && pwd)
docker build -q -t torizon-image-tools "$HERE" > /dev/null
docker run --rm \
    -e HOST_UID="$(id -u)" -e HOST_GID="$(id -g)" \
    -e EMMC_SIZE_MB -e PRODUCT_ID -e MODULE_VERSION -e SERIAL -e EXTRA_KARGS \
    -v "$HERE:/scripts:ro" \
    -v "$TEZI_TAR:/in/tezi.tar:ro" \
    -v "$OUT:/out" \
    torizon-image-tools /scripts/build-image.sh /in/tezi.tar /out
