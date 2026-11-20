#!/bin/bash
# ============================================================================
# b4q test-flash helper  (run from the host, device must be booted in TWRP
# with working adb, like the old "twrp_b4q" recovery).
#
#   scripts/flash_b4q.sh check                 - show device + sizes
#   scripts/flash_b4q.sh backup [dir]          - dd current boot/vendor_boot/
#                                                vendor_dlkm to host (dir)
#   scripts/flash_b4q.sh flash  [dir]          - flash dist-images/{boot,
#                                                vendor_boot,vendor_dlkm}.img
#   scripts/flash_b4q.sh restore [dir]         - flash back the backed-up
#                                                images (or stock/ templates)
#
# vendor_dlkm is a *logical* partition (inside super), so it is written to
# /dev/block/mapper/vendor_dlkm after unmounting it in TWRP.  boot and
# vendor_boot are normal partitions.
# ============================================================================
set -e

TOPDIR=$(cd "$(dirname "$0")/.." && pwd -P)
IMG_DIR=${TOPDIR}/dist-images
STOCK_DIR=${TOPDIR}/stock
SERIAL=${ANDROID_SERIAL:-}

adb_() {
    if [ -n "$SERIAL" ]; then adb -s "$SERIAL" "$@"; else adb "$@"; fi
}

require_twrp() {
    local dev
    dev=$(adb_ devices | awk 'NR==2 {print $2}')
    [ -n "$dev" ] || { echo "ERROR: no adb device"; exit 1; }
    local state
    state=$(adb_ get-state 2>/dev/null || true)
    [ "$state" = "recovery" ] || { echo "ERROR: device is not in recovery (state=$state)"; exit 1; }
    echo "device: $(adb_ devices | awk 'NR==2 {print $1, $2, $4}')"
}

md5_host() { md5sum "$1" | awk '{print $1}'; }

flash_raw() {
    local host_img=$1 remote=$2 label=$3
    local size host_md5 dev_md5
    [ -f "$host_img" ] || { echo "ERROR: $host_img missing"; exit 1; }
    size=$(stat -c %s "$host_img")
    host_md5=$(md5_host "$host_img")
    echo ">>> $label: $size bytes  md5=$host_md5"
    adb_ push "$host_img" "/tmp/b4q-flash-$label.img" >/dev/null
    adb_ shell "dd if=/tmp/b4q-flash-$label.img of=$remote bs=1M conv=fsync 2>&1 | tail -1"
    adb_ shell "sync; blockdev --flushbufs $remote 2>/dev/null || true"
    dev_md5=$(adb_ shell "dd if=$remote bs=1M count=$(( (size + 1048575) / 1048576 )) 2>/dev/null | md5sum" | awk '{print $1}')
    echo "    device md5 (first $(( (size + 1048575) / 1048576 )) MiB) = $dev_md5"
    adb_ shell "rm -f /tmp/b4q-flash-$label.img"
}

cmd_check() {
    require_twrp
    echo "--- partition sizes ---"
    adb_ shell 'for p in boot vendor_boot; do echo -n "$p: "; blockdev --getsize64 /dev/block/by-name/$p; done; echo -n "vendor_dlkm: "; blockdev --getsize64 /dev/block/mapper/vendor_dlkm'
    echo "--- current images ---"
    for f in "$IMG_DIR/boot.img" "$IMG_DIR/vendor_boot.img" "$IMG_DIR/vendor_dlkm.img"; do
        [ -f "$f" ] && echo "$(stat -c %s "$f")  $f" || echo "MISSING $f"
    done
}

cmd_backup() {
    require_twrp
    local out=${1:-$TOPDIR/backup-$(date +%Y%m%d-%H%M%S)}
    mkdir -p "$out"
    echo ">>> backing up to $out"
    adb_ shell 'dd if=/dev/block/by-name/boot of=/tmp/b4q-boot-bak.img bs=1M 2>/dev/null
                dd if=/dev/block/by-name/vendor_boot of=/tmp/b4q-vb-bak.img bs=1M 2>/dev/null
                dd if=/dev/block/mapper/vendor_dlkm of=/tmp/b4q-dlkm-bak.img bs=1M 2>/dev/null'
    adb_ pull /tmp/b4q-boot-bak.img "$out/boot.img" >/dev/null
    adb_ pull /tmp/b4q-vb-bak.img "$out/vendor_boot.img" >/dev/null
    adb_ pull /tmp/b4q-dlkm-bak.img "$out/vendor_dlkm.img" >/dev/null
    adb_ shell 'rm -f /tmp/b4q-*-bak.img'
    ls -la "$out"
}

cmd_flash() {
    require_twrp
    local imgdir=${1:-$IMG_DIR}
    echo '>>> unmounting /vendor_dlkm'
    adb_ shell 'umount /vendor_dlkm 2>/dev/null || true; umount /vendor 2>/dev/null || true'
    flash_raw "$imgdir/vendor_dlkm.img" /dev/block/mapper/vendor_dlkm vendor_dlkm
    flash_raw "$imgdir/vendor_boot.img" /dev/block/by-name/vendor_boot vendor_boot
    flash_raw "$imgdir/boot.img" /dev/block/by-name/boot boot
    echo '>>> done; rebooting to system'
    adb_ shell 'reboot' || true
}

cmd_restore() {
    require_twrp
    local dir=${1:-$TOPDIR/stock}
    local boot_img="$dir/boot-stock-magisk.img"
    [ -f "$boot_img" ] || boot_img="$dir/boot-stock-clean.img"
    echo '>>> unmounting /vendor_dlkm'
    adb_ shell 'umount /vendor_dlkm 2>/dev/null || true'
    flash_raw "$dir/vendor_dlkm-stock.img" /dev/block/mapper/vendor_dlkm vendor_dlkm
    flash_raw "$dir/vendor_boot-stock.img" /dev/block/by-name/vendor_boot vendor_boot
    flash_raw "$boot_img" /dev/block/by-name/boot boot
    echo '>>> stock images restored; rebooting'
    adb_ shell 'reboot' || true
}

case "${1:-}" in
    check)   cmd_check ;;
    backup)  cmd_backup "${2:-}" ;;
    flash)   cmd_flash "${2:-}" ;;
    restore) cmd_restore "${2:-}" ;;
    *) sed -n '2,20p' "$0"; exit 1 ;;
esac
