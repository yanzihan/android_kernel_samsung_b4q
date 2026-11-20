# Samsung Galaxy Z Flip4 (b4q / SM-F7210, chn_hkx) kernel

Superproject for the SM8475 (waipio) kernel platform of the Galaxy Z Flip4.
The kernel sources live in two branches of
[android_kernel_samsung_sm8475](https://github.com/yanzihan/android_kernel_samsung_sm8475):

| branch | content |
| --- | --- |
| `seventeen-common` | GKI `kernel_platform/common` tree (Linux 5.10 + ACK `android12-5.10-lts` 5.10.274) |
| `msm-kernel` | `kernel_platform/msm-kernel` vendor tree (5.10.252, SM-F7210 OSRC) |

## Features

- ACK `android12-5.10-lts` (5.10.274) grafted on the Samsung SM-F7210 tree, KMI preserved
- KernelSU-Next as built-in root (branch pinned at `aa235b99`), manager UAPI 6
- SuSFS v2.4.0 (official `simonpunk/susfs4ksu` patch set for `gki-android12-5.10`)
- KNOX / DEFEX / DSMS / FIVE / RKP / KDP / UH / PROCA / NGKSM / SEC LMKD removed
- Boots official OneUI8 with the stock `vendor_boot` / `vendor_dlkm` images

## Layout

```
build_kernel_b4q.sh        # full build entry (Image + all .ko)
build_kernel_GKI.sh        # GKI build entry used by build_kernel_b4q.sh
custom_defconfigs/         # b4q / ksu / susfs / recovery fragments
patches/                   # SuSFS patches (KernelSU-Next side + kernel side)
stock/                     # stock firmware templates used for packaging
vendor/                    # Qualcomm opensource vendor modules (SM-F7210 OSRC)
kernel_platform/           # Samsung GKI 2.0 build system
external/AnyKernel3        # flashable zip template (submodule)
```

## Build requirements

- Samsung `clang-r416183b` (or compatible clang 12.0.5) under
  `kernel_platform/prebuilts-master/clang/host/linux-x86/clang-r416183b`
- LineageOS host tools (prebuilt dtc/mkdtboimg/mkbootimg/fcvt) available
- `python3` for `scripts/b4q_images.py`

## Build

```bash
# device tree + submodules
git submodule update --init --recursive

# Image + all modules
bash build_kernel_b4q.sh

# package boot/vendor_boot/vendor_dlkm
python3 scripts/b4q_images.py all --dist <dist-out> --stock stock
```

## KernelSU manager

The kernel reports manager UAPI 6, so the manager APK must be built from
KernelSU-Next `dev` with UAPI 6 (e.g. the CI build `v3.4.2-97-gcefb048b`,
versionCode `33452-6`). The official v3.4.2 release (UAPI 5) is too old.

## Notes

- `vendor/` and `stock/` images are imported from the Samsung OSRC release for
  SM-F7210 (chn_hkx), they are only needed for packaging/flashing.
- The upstream Linux/ACK history is not included; this repository keeps the
  kernel trees as squashed baselines plus the feature commits.
