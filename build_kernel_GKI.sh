#!/bin/bash
# ============================================================================
# b4q (Galaxy Z Flip4, SM-F7210 / chn_hkx) kernel_platform build entry
#
# Based on the ACK-merged Samsung kernel tree, with KernelSU-Next + SuSFS
# (kernel feature commits applied from the xfwdrev reference tree) and full
# vendor module set (qca/ipa/rmnet-ext/eva/video/...).
#
# Environment overrides:
#   LTO=none|thin|full            default: thin
#   ENABLE_KSU=0|1                default: 1   (CONFIG_KSU=y via ksu_defconfig)
#   ENABLE_SUSFS=0|1              default: 1   (SuSFS patch + susfs_defconfig)
#   KMI_SYMBOL_LIST_STRICT_MODE   default: 0
#   ABI_DEFINITION=               default: empty (skip ABI symbol check)
# ============================================================================

export LTO=${LTO:-thin}
# vendor blobs were written for a newer clang; keep clang 12 from turning
# pointer-type warnings into hard errors
KCFLAGS="${KCFLAGS:-} -Wno-incompatible-function-pointer-types -Wno-error"
export KCFLAGS
export TRIM_NONLISTED_KMI=${TRIM_NONLISTED_KMI:-0}
export KMI_ENFORCED=${KMI_ENFORCED:-0}
export KMI_SYMBOL_LIST_STRICT_MODE=${KMI_SYMBOL_LIST_STRICT_MODE:-0}
export ABI_DEFINITION=${ABI_DEFINITION:-}
ENABLE_KSU=${ENABLE_KSU:-1}
ENABLE_SUSFS=${ENABLE_SUSFS:-1}

# --- target config ----------------------------------------------------------
BUILD_TARGET=b4q_chn_hkx
export MODEL=$(echo $BUILD_TARGET | cut -d'_' -f1)
export PROJECT_NAME=${MODEL}
export REGION=$(echo $BUILD_TARGET | cut -d'_' -f2)
export CARRIER=$(echo $BUILD_TARGET | cut -d'_' -f3)
export TARGET_BUILD_VARIANT=user

# --- sm8450 (waipio) config -------------------------------------------------
CHIPSET_NAME=waipio
export ANDROID_BUILD_TOP=$(pwd)
export TARGET_PRODUCT=gki
export TARGET_BOARD_PLATFORM=gki
export ANDROID_PRODUCT_OUT=${ANDROID_BUILD_TOP}/out/target/product/${MODEL}
export OUT_DIR=${ANDROID_BUILD_TOP}/out/msm-${CHIPSET_NAME}-${CHIPSET_NAME}-${TARGET_PRODUCT}
export DIST_DIR=${OUT_DIR}/dist
mkdir -p "${DIST_DIR}"

# reproducible-ish version info
export KBUILD_BUILD_USER=${KBUILD_BUILD_USER:-$(whoami)}
export KBUILD_BUILD_HOST=${KBUILD_BUILD_HOST:-build-host}
export KBUILD_BUILD_TIMESTAMP=${KBUILD_BUILD_TIMESTAMP:-$(date)}
export KBUILD_BUILD_VERSION=${KBUILD_BUILD_VERSION:-1}

# --- KernelSU-Next + SuSFS --------------------------------------------------
KSU_DIR="${ANDROID_BUILD_TOP}/kernel_platform/common/KernelSU-Next"
SUSFS_PATCH="${ANDROID_BUILD_TOP}/patches/susfs.patch"
if [ "${ENABLE_SUSFS}" = "1" ]; then
    if ! grep -q 'config KSU_SUSFS' "${KSU_DIR}/kernel/Kconfig" 2>/dev/null; then
        echo ">>> applying SuSFS patch to KernelSU-Next"
        patch -d "${KSU_DIR}" -p1 -s < "${SUSFS_PATCH}" || { echo "SuSFS patch failed"; exit 1; }
    fi
fi

# --- GKI defconfig fragments (merged by POST_DEFCONFIG_CMDS) -----------------
MERGE_CONFIG="${ANDROID_BUILD_TOP}/kernel_platform/common/scripts/kconfig/merge_config.sh"
CUST_DEFCONFIG="${ANDROID_BUILD_TOP}/custom_defconfigs/b4q_defconfig"
export POST_DEFCONFIG_CMDS="check_defconfig && ${MERGE_CONFIG} -m \${OUT_DIR}/gki_kernel/common/.config ${CUST_DEFCONFIG}"
if [ "${ENABLE_KSU}" = "1" ]; then
    export POST_DEFCONFIG_CMDS="${POST_DEFCONFIG_CMDS} && ${MERGE_CONFIG} -m \${OUT_DIR}/gki_kernel/common/.config ${ANDROID_BUILD_TOP}/custom_defconfigs/ksu_defconfig"
fi
if [ "${ENABLE_SUSFS}" = "1" ]; then
    export POST_DEFCONFIG_CMDS="${POST_DEFCONFIG_CMDS} && ${MERGE_CONFIG} -m \${OUT_DIR}/gki_kernel/common/.config ${ANDROID_BUILD_TOP}/custom_defconfigs/susfs_defconfig"
fi

# --- external DLKM symbol exports / module list (full set) -------------------
export KBUILD_EXTRA_SYMBOLS="${ANDROID_BUILD_TOP}/out/vendor/qcom/opensource/mmrm-driver/Module.symvers \
  ${ANDROID_BUILD_TOP}/out/vendor/qcom/opensource/datarmnet/core/Module.symvers \
  ${ANDROID_BUILD_TOP}/out/vendor/qcom/opensource/wlan/qcacld-3.0/Module.symvers \
  ${ANDROID_BUILD_TOP}/out/vendor/qcom/opensource/camera-kernel/Module.symvers \
  ${ANDROID_BUILD_TOP}/out/vendor/qcom/opensource/eva-kernel/Module.symvers \
  ${ANDROID_BUILD_TOP}/out/vendor/qcom/opensource/video-driver/Module.symvers \
  ${ANDROID_BUILD_TOP}/out/vendor/qcom/opensource/display-drivers/msm/Module.symvers \
  ${ANDROID_BUILD_TOP}/out/vendor/qcom/opensource/datarmnet-ext/aps/Module.symvers \
  ${ANDROID_BUILD_TOP}/out/vendor/qcom/opensource/datarmnet-ext/wlan/Module.symvers \
  ${ANDROID_BUILD_TOP}/out/vendor/qcom/opensource/datarmnet-ext/shs/Module.symvers \
  ${ANDROID_BUILD_TOP}/out/vendor/qcom/opensource/datarmnet-ext/perf_tether/Module.symvers \
  ${ANDROID_BUILD_TOP}/out/vendor/qcom/opensource/datarmnet-ext/perf/Module.symvers \
  ${ANDROID_BUILD_TOP}/out/vendor/qcom/opensource/datarmnet-ext/sch/Module.symvers \
  ${ANDROID_BUILD_TOP}/out/vendor/qcom/opensource/datarmnet-ext/offload/Module.symvers \
  ${ANDROID_BUILD_TOP}/out/vendor/qcom/opensource/dataipa/drivers/platform/msm/Module.symvers \
  ${ANDROID_BUILD_TOP}/out/vendor/qcom/opensource/audio-kernel/Module.symvers"

export MODNAME=audio_dlkm
export RMNET_CORE_INC_DIR="${ANDROID_BUILD_TOP}/vendor/qcom/opensource/datarmnet/core"
export DATARMNET_CORE_PATH="datarmnet/core"

export KBUILD_EXT_MODULES="../vendor/qcom/opensource/wlan/qcacld-3.0 \
    ../vendor/qcom/opensource/dataipa/drivers/platform/msm \
    ../vendor/qcom/opensource/datarmnet/core \
    ../vendor/qcom/opensource/datarmnet-ext/aps \
    ../vendor/qcom/opensource/datarmnet-ext/offload \
    ../vendor/qcom/opensource/datarmnet-ext/shs \
    ../vendor/qcom/opensource/datarmnet-ext/sch \
    ../vendor/qcom/opensource/datarmnet-ext/perf \
    ../vendor/qcom/opensource/datarmnet-ext/perf_tether \
    ../vendor/qcom/opensource/datarmnet-ext/wlan \
    ../vendor/qcom/opensource/mmrm-driver \
    ../vendor/qcom/opensource/audio-kernel \
    ../vendor/qcom/opensource/camera-kernel \
    ../vendor/qcom/opensource/display-drivers/msm \
    ../vendor/qcom/opensource/eva-kernel \
    ../vendor/qcom/opensource/video-driver"

# --- merge custom defconfig fragments into the GKI defconfig -----------------
export KCFLAGS="${KCFLAGS} -Wno-error -Wno-strict-prototypes -Wno-macro-redefined"
export LOCALVERSION=
GKI_DEFCONFIG="${ANDROID_BUILD_TOP}/kernel_platform/common/arch/arm64/configs/gki_defconfig"
cp -f "${GKI_DEFCONFIG}" "${GKI_DEFCONFIG}.build-backup"
trap 'mv -f "${GKI_DEFCONFIG}.build-backup" "${GKI_DEFCONFIG}"' EXIT
for frag in "${ANDROID_BUILD_TOP}/custom_defconfigs/b4q_defconfig"; do
    echo "" >> "${GKI_DEFCONFIG}"
    echo "# --- merged from $(basename ${frag}) ---" >> "${GKI_DEFCONFIG}"
    cat "${frag}" >> "${GKI_DEFCONFIG}"
done
if [ "${ENABLE_KSU}" = "1" ]; then
    echo "" >> "${GKI_DEFCONFIG}"; cat "${ANDROID_BUILD_TOP}/custom_defconfigs/ksu_defconfig" >> "${GKI_DEFCONFIG}"
fi
if [ "${ENABLE_SUSFS}" = "1" ]; then
    echo "" >> "${GKI_DEFCONFIG}"; cat "${ANDROID_BUILD_TOP}/custom_defconfigs/susfs_defconfig" >> "${GKI_DEFCONFIG}"
fi
echo ">>> gki_defconfig fragments merged"

# --- go ---------------------------------------------------------------------
RECOMPILE_KERNEL=1 ./kernel_platform/build/android/prepare_vendor.sh sec ${TARGET_PRODUCT}
