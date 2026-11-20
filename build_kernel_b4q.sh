#!/bin/bash
# ============================================================
# b4q (Galaxy Z Flip4 chn_hkx, SM8475) GKI 内核一键构建脚本
# 产物: dist/boot.img + dist/vendor_boot.img + dist/dtbo.img
#       + dist/Image + dist/Image.lz4 + dist/super.img + 全部 .ko
#
# 依赖:
#   kernel_platform/prebuilts-master/clang/.../clang-r416183b   编译工具链
#       (脚本会自动从 p3q 树软链接, 也可自己放好)
#   lineage-23.2/prebuilts/{build-tools,kernel-build-tools}      宿主工具
#       (脚本会自动软链接)
#   vendor/qcom/opensource/*                                    外部 DLKM
#
# 说明:
#   - 必须从真实路径 (/mnt/build2/...) 运行, prepare_vendor.sh
#     会校验 kernel_platform 的相对位置
#   - HERMETIC_TOOLCHAIN=0: 三星的封闭 PATH 缺宿主工具
#   - boot/ 目录约定 (可选):
#       boot/base.img    放入原版 boot.img 则用 magiskboot 重打包
#                        (仅替换内核, 保留底包头格式/ramdisk)
#       不放则直接使用 Samsung 流程产出的 dist/boot.img
# ============================================================

set -e

TOPDIR=$(cd "$(dirname "$0")" && pwd -P)
cd "${TOPDIR}"

# --- 0. 基本环境 ------------------------------------------------------------
export HERMETIC_TOOLCHAIN=0

KP=${TOPDIR}/kernel_platform
CLANG_LINK=${KP}/prebuilts-master/clang/host/linux-x86/clang-r416183b
P3Q=/mnt/build2/android_kernel_samsung_sm8350-p3q
LINEAGE_PREBUILTS=/mnt/build2/lineage-23.2/prebuilts

echo "=== 1. 检查/准备工具链 ==="
if [ ! -x "${CLANG_LINK}/bin/clang" ]; then
    if [ -x "${P3Q}/toolchains/clang/clang-r416183b/bin/clang" ]; then
        mkdir -p "$(dirname "${CLANG_LINK}")"
        ln -sfn "${P3Q}/toolchains/clang/clang-r416183b" "${CLANG_LINK}"
        echo "  已链接 clang-r416183b <- p3q toolchains"
    else
        echo "❌ 找不到 clang-r416183b (p3q 树或 ${CLANG_LINK})"
        exit 1
    fi
fi
"${CLANG_LINK}/bin/clang" --version | head -1

if [ ! -e "${KP}/prebuilts/build-tools" ]; then
    if [ -d "${LINEAGE_PREBUILTS}/build-tools" ]; then
        mkdir -p "${KP}/prebuilts/gas/linux-x86"
        ln -sfn "${LINEAGE_PREBUILTS}/build-tools"        "${KP}/prebuilts/build-tools"
        ln -sfn "${LINEAGE_PREBUILTS}/kernel-build-tools" "${KP}/prebuilts/kernel-build-tools"
        for f in "${P3Q}/toolchains/gcc64/bin"/*; do
            ln -sf "$f" "${KP}/prebuilts/gas/linux-x86/$(basename "$f")"
        done
        ln -sf "${LINEAGE_PREBUILTS}/kernel-build-tools/linux-x86/bin/mkdtboimg" \
               "${KP}/prebuilts/gas/linux-x86/mkdtboimg.py"
        echo "  已链接 AOSP 宿主 prebuilts <- lineage-23.2"
    else
        echo "❌ 找不到 ${LINEAGE_PREBUILTS} (宿主工具)"
        exit 1
    fi
fi

# 三星流程会把旧的 host 目录写成只读, 影响重复构建
find "${TOPDIR}/out" \( -type d -o -type f \) -perm 555 -exec chmod u+w {} + 2>/dev/null || true

# --- 2. 构建 (Samsung GKI 流程) ----------------------------------------------
echo "=== 2. 编译内核 + 模块 (时间较长, 含 LTO) ==="
bash ./build_kernel_GKI.sh

DIST=${TOPDIR}/out/msm-waipio-waipio-gki/dist
[ -f "${DIST}/Image" ] || { echo "❌ 构建失败, 未找到 ${DIST}/Image"; exit 1; }

# --- 3. 收集产物 ------------------------------------------------------------
mkdir -p "${TOPDIR}/dist"
echo "=== 3. 收集产物到 dist/ ==="
for f in boot.img vendor_boot.img super.img vendor_dlkm.img dtbo.img \
         Image Image.lz4 System.map vmlinux; do
    if [ -f "${DIST}/${f}" ]; then cp -f "${DIST}/${f}" "${TOPDIR}/dist/"; fi
done
cp -f "${DIST}"/*.ko "${TOPDIR}/dist/" 2>/dev/null || true

# --- 4. 可选: 用底包重打包 boot.img ------------------------------------------
MAGISKBOOT=$(command -v magiskboot 2>/dev/null)
[ -z "$MAGISKBOOT" ] && [ -x "${TOPDIR}/tools/magiskboot" ] && MAGISKBOOT="${TOPDIR}/tools/magiskboot"
if [ -f "${TOPDIR}/boot/base.img" ]; then
    if [ -z "$MAGISKBOOT" ]; then
        echo "⚠️  boot/base.img 存在但找不到 magiskboot, 跳过重打包"
    else
        echo "=== 4. 用底包重打包 boot.img ==="
        WORK=${TOPDIR}/boot/work
        rm -rf "${WORK}" && mkdir -p "${WORK}"
        cp "${TOPDIR}/boot/base.img" "${WORK}/boot.img"
        (cd "${WORK}" && "${MAGISKBOOT}" unpack boot.img >/dev/null)
        cp -f "${DIST}/Image" "${WORK}/kernel"
        (cd "${WORK}" && "${MAGISKBOOT}" repack boot.img "${TOPDIR}/dist/boot.img" >/dev/null)
        rm -rf "${WORK}"
        echo "  已用底包重打包 dist/boot.img"
    fi
fi

# --- 5. 结果 -----------------------------------------------------------------
echo
echo "✅ 构建完成:"
for f in boot.img vendor_boot.img dtbo.img Image Image.lz4 super.img vendor_dlkm.img; do
    if [ -f "${TOPDIR}/dist/${f}" ]; then printf "  %-18s %s\n" "${f}" "$(du -h "${TOPDIR}/dist/${f}" | cut -f1)"; fi
done
echo "  ko 模块          $(ls "${TOPDIR}/dist"/*.ko 2>/dev/null | wc -l) 个"
echo "  内核版本: $(strings "${TOPDIR}/dist/Image" | grep -m1 -oE 'Linux version [^ ]+' | cut -d' ' -f3)"
