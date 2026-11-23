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
