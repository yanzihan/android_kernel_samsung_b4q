# Kernel-only release (verified on official OneUI8)

## What ships

`boot.img` only. The vendor side stays stock:

| partition | source |
| --- | --- |
| boot | this project (5.10.274-YanJiaMian-gki) |
| vendor_boot | stock / OEM |
| vendor_dlkm | stock / OEM |
| dtbo | **stock / OEM** |

Kernel features: KernelSU-Next (built-in), SuSFS v2.4.0, Samsung
KNOX/RKP/KDP/UH/DEFEX/DSMS/FIVE/NGKSM trimmed.

Verified on SM-F7210 (b4q, chn_hkx) with
`BP2A.250605.031.A3.F7210ZSSAIZH2`: boot, SIM, sound, WiFi, display,
490 vendor modules loaded, KernelSU + SuSFS active.

## Why kernel-only

The vendor module tree (`msm-kernel`) and the GKI kernel tree (`common`)
must have byte-identical headers/Kconfig for a mixed build. In this
project the common tree is Samsung-OSRC + a self-made ACK 5.10.274
graft + security trims + KernelSU/SuSFS patches, while the vendor tree
is the plain Samsung vendor tree. Their headers differ, so self-built
vendor modules are rejected/crash the kernel when loaded:

- mixed build (common kernel + vendor modules) -> module ABI mismatch,
  boot loops at the first screen
- standalone kernel from the vendor tree -> that tree's core kernel
  files are incomplete (only vendor modules are ever compiled there)

So the supported, verified deliverable is the kernel image on top of
the stock vendor images.

## dtbo

Do not ship a recompiled dtbo: the OSRC-generated overlay does not
match the device's audio amp/codec device-tree nodes and the sound card
fails to register (`/proc/asound` empty, `audio amp: No callback
registered`). Stock dtbo works with this kernel.

## Flash

```
# TWRP / sky adb
adb push boot-padded.img /tmp/boot.img
adb shell 'dd if=/tmp/boot.img of=/dev/block/by-name/boot bs=1M conv=fsync'
adb shell sync
adb reboot
```

## KernelSU manager

Requires a manager APK with UAPI 6 (KernelSU-Next CI build, e.g.
`KernelSU_Next_v3.4.2-97-gcefb048b_33452` or newer).

## KernelSU manager version

The kernel is built from KernelSU-Next `aa235b99` and reports KSU version
code **33554** (tag `v3.4.2`). The manager APK shipped with the ROM must be
the matching CI build:

    KernelSU_Next_v3.4.2-199-gaa235b99_33554-release.apk

Older managers (e.g. the 33452 build) still work but the manager shows a
"kernel version too old" notice. If the kernel source moves to another
KernelSU-Next commit, regenerate the guess version and ship the manager
build of the same commit.

## How the KernelSU version is derived (verified 2026-11-24)

KernelSU-Next is tracked as a git submodule (`kernel_platform/common/KernelSU-Next`,
commit `aa235b99`, describe `v3.4.2-199-gaa235b99`). Its `kernel/Kbuild`
computes the version from git:

    KSU_VERSION = 30000 + $(git rev-list --count HEAD)   # 30000 + 3554 = 33554
    KSU_VERSION_TAG = $(git describe --tags --abbrev=0)  # v3.4.2

If the directory has no `.git` (e.g. a vendored copy or a tree where the
submodule was never initialised), Kbuild falls back to `1` / `v0.0.1`, and
managers that require a recent kernel version (Zygisk Next 1.5.3+,
NeoZygisk v2.4) refuse to install. Two ways to keep it correct:

* keep the submodule initialised (`git submodule update --init KernelSU-Next`)
  - preferred, version and tag stay authentic; or
* if the tree is shipped without the submodule history, set the fallbacks in
  `KernelSU-Next/kernel/Kbuild`:

      KSU_VERSION_FALLBACK := 33554
      KSU_VERSION_TAG_FALLBACK := v3.4.2-199-gaa235b99

The SuSFS patch (`patches/susfs.patch`) is re-applied to the submodule by
`scripts/build_image_only_ksu.sh` when it is missing.

Verified on the ported OneUI 9 ROM (b4q hardware, F7410 system):
the manager shows `v3.4.2 (33554-6)` (kernel) / `v3.4.2-199-gaa235b99
(33554-6)` (manager), SuSFS v2.4.0 active, NeoZygisk v2.4 injected, and the
official Zygisk Next 1.5.3 installer accepts the kernel (>= 10940).
