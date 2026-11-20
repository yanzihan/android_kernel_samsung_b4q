#!/bin/bash
# ============================================================
# b4q (Galaxy Z Flip4 chn_hkx, SM8475) GKI kernel build script
#
# Output: dist/{Image, *.ko, dtbo.img, boot.img, vendor_boot.img,
#               vendor_dlkm.img, System.map, vmlinux}
#
# Requirements:
#   - clang-r416183b toolchain
#       CLANG_DIR=/path/to/clang-r416183b   (default: kernel_platform/prebuilts-master/...)
#   - AOSP/Lineage host prebuilts (build-tools, kernel-build-tools)
#       HOST_PREBUILTS=/path/to/prebuilts   (default: kernel_platform/prebuilts)
#   - vendor/qcom/opensource/* (external DLKMs), imported from the OSRC drop
#
# Optional: boot/base.img - if present, magiskboot is used to repack the
#           kernel into that boot image layout instead of the default one.
# ============================================================

set -e

TOPDIR=$(cd "$(dirname "$0")" && pwd -P)
cd "${TOPDIR}"

# --- 0. environment ----------------------------------------------------------
export HERMETIC_TOOLCHAIN=0

KP=${TOPDIR}/kernel_platform
CLANG_DIR=${CLANG_DIR:-${KP}/prebuilts-master/clang/host/linux-x86/clang-r416183b}
HOST_PREBUILTS=${HOST_PREBUILTS:-${KP}/prebuilts}

echo "=== 1. toolchain check ==="
if [ ! -x "${CLANG_DIR}/bin/clang" ]; then
    echo "ERROR: clang-r416183b not found at ${CLANG_DIR}"
    echo "       install it there or set CLANG_DIR"
    exit 1
fi
"${CLANG_DIR}/bin/clang" --version | head -1

if [ ! -e "${KP}/prebuilts/build-tools" ]; then
    if [ -d "${HOST_PREBUILTS}/build-tools" ] && [ -d "${HOST_PREBUILTS}/kernel-build-tools" ]; then
        mkdir -p "${KP}/prebuilts/gas/linux-x86"
        ln -sfn "${HOST_PREBUILTS}/build-tools"        "${KP}/prebuilts/build-tools"
        ln -sfn "${HOST_PREBUILTS}/kernel-build-tools" "${KP}/prebuilts/kernel-build-tools"
        if [ -x "${HOST_PREBUILTS}/kernel-build-tools/linux-x86/bin/mkdtboimg" ]; then
            ln -sf "${HOST_PREBUILTS}/kernel-build-tools/linux-x86/bin/mkdtboimg" \
                   "${KP}/prebuilts/gas/linux-x86/mkdtboimg.py"
        fi
        echo "  linked host prebuilts from ${HOST_PREBUILTS}"
    else
        echo "ERROR: host prebuilts not found at ${HOST_PREBUILTS}"
        echo "       install build-tools/kernel-build-tools there or set HOST_PREBUILTS"
        exit 1
    fi
fi

# Samsung build flow may leave read-only host directories; make them writable
find "${TOPDIR}/out" \( -type d -o -type f \) -perm 555 -exec chmod u+w {} + 2>/dev/null || true

# --- 2. build (Samsung GKI flow) --------------------------------------------
echo "=== 2. build kernel + modules (LTO, takes a while) ==="
bash ./build_kernel_GKI.sh

DIST=${TOPDIR}/out/msm-waipio-waipio-gki/dist
[ -f "${DIST}/Image" ] || { echo "ERROR: build failed, no ${DIST}/Image"; exit 1; }

# --- 3. collect artifacts ----------------------------------------------------
mkdir -p "${TOPDIR}/dist"
echo "=== 3. collect artifacts into dist/ ==="
for f in boot.img vendor_boot.img super.img vendor_dlkm.img dtbo.img \
         Image Image.lz4 System.map vmlinux; do
    if [ -f "${DIST}/${f}" ]; then cp -f "${DIST}/${f}" "${TOPDIR}/dist/"; fi
done
cp -f "${DIST}"/*.ko "${TOPDIR}/dist/" 2>/dev/null || true

# --- 4. optional boot repack from a reference image --------------------------
MAGISKBOOT=$(command -v magiskboot 2>/dev/null)
[ -z "$MAGISKBOOT" ] && [ -x "${TOPDIR}/tools/magiskboot" ] && MAGISKBOOT="${TOPDIR}/tools/magiskboot"
if [ -f "${TOPDIR}/boot/base.img" ]; then
    if [ -z "$MAGISKBOOT" ]; then
        echo "WARN: boot/base.img present but magiskboot not found, skipping repack"
    else
        echo "=== 4. repack boot.img from boot/base.img ==="
        WORK=${TOPDIR}/boot/work
        rm -rf "${WORK}" && mkdir -p "${WORK}"
        cp "${TOPDIR}/boot/base.img" "${WORK}/boot.img"
        (cd "${WORK}" && "${MAGISKBOOT}" unpack boot.img >/dev/null)
        cp -f "${DIST}/Image" "${WORK}/kernel"
        (cd "${WORK}" && "${MAGISKBOOT}" repack boot.img "${TOPDIR}/dist/boot.img" >/dev/null)
        rm -rf "${WORK}"
        echo "  repacked dist/boot.img"
    fi
fi

# --- 5. summary --------------------------------------------------------------
echo
echo "build complete:"
for f in boot.img vendor_boot.img dtbo.img Image Image.lz4 super.img vendor_dlkm.img; do
    if [ -f "${TOPDIR}/dist/${f}" ]; then printf "  %-18s %s\n" "${f}" "$(du -h "${TOPDIR}/dist/${f}" | cut -f1)"; fi
done
echo "  modules            $(ls "${TOPDIR}/dist"/*.ko 2>/dev/null | wc -l)"
echo "  kernel version: $(strings "${TOPDIR}/dist/Image" | grep -m1 -oE 'Linux version [^ ]+' | cut -d' ' -f3)"
