#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
b4q image packaging tool.

Builds a Samsung-compatible flash set from a kernel_platform build output:

    boot.img          header v4 + stock clean GKI ramdisk + new Image
    vendor_boot.img   header v4, stock dtb/bootconfig/cmdline, vendor ramdisk
                      rebuilt from the stock one with the new module set
    vendor_dlkm.img   f2fs image with the second-stage module set

The stock images are only used as *templates* (layout, ramdisk filesystem
contents, fstab, dpolicy, metadata layout).  Module binaries always come from
the build output, so the whole set is self-consistent.

Subcommands (run in order; a shared --work dir keeps intermediate files):

  stage          collect+strip+depmod the build's modules, print a manifest
  vendor-ramdisk rebuild the vendor ramdisk (cpio + legacy lz4)
  vendor-boot    pack vendor_boot.img
  boot           pack boot.img
  vendor-dlkm    make the f2fs vendor_dlkm.img
  all            everything above

Example (b4q / SM-F7210 HK):

  scripts/b4q_images.py all \
      --dist  out/msm-waipio-waipio-gki/dist \
      --stock stock \
      --stock-dlkm-modules _ref/dlkmroot/modules \
      --krel  5.10.274-YanJiaMian-gki \
      --work  _work --out dist-images

The three produced images are meant to be flashed *together*; the kernel and
every module come from the same build, so MODVERSIONS/vermagic are consistent.
"""

import argparse
import glob
import json
import os
import re
import shutil
import struct
import subprocess
import sys

PAGE = 4096
BOOT_MAGIC = b'ANDROID!'
VENDOR_BOOT_MAGIC = b'VNDRBOOT'
BOOT_V4_HEADER_SIZE = 1584
BOOT_V4_SIGNATURE_SIZE = 4096
VENDOR_BOOT_V4_HEADER_SIZE = 2128
VENDOR_RAMDISK_TABLE_ENTRY_V4_SIZE = 108


def align(x, p=PAGE):
    return (x + p - 1) // p * p


def run(cmd, **kw):
    print('+', ' '.join(cmd) if isinstance(cmd, list) else cmd)
    return subprocess.run(cmd, check=True, **kw)


def read(path):
    with open(path, 'rb') as f:
        return f.read()


def read_text(path):
    return read(path).decode('utf-8', 'replace')


def write(path, data):
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    if isinstance(data, str):
        data = data.encode()
    with open(path, 'wb') as f:
        f.write(data)


def page_pad(data):
    return data + b'\x00' * (align(len(data)) - len(data))


# --------------------------------------------------------------------------
# stock image parsing
# --------------------------------------------------------------------------
def parse_boot(path):
    d = read(path)
    info = {
        'file': path,
        'kernel_size': struct.unpack_from('<I', d, 8)[0],
        'ramdisk_size': struct.unpack_from('<I', d, 12)[0],
        'os_version': struct.unpack_from('<I', d, 16)[0],
        'header_size': struct.unpack_from('<I', d, 20)[0],
        'header_version': struct.unpack_from('<I', d, 40)[0],
    }
    info['kernel_off'] = 4096
    info['ramdisk_off'] = align(info['kernel_off'] + info['kernel_size'])
    if info['header_version'] >= 4:
        sig_size = struct.unpack_from('<I', d, 1580)[0]
        info['signature_size'] = sig_size
        info['signature_off'] = align(info['ramdisk_off'] + info['ramdisk_size'])
    return info


def parse_vendor_boot(path):
    d = read(path)
    info = {
        'file': path,
        'header_version': struct.unpack_from('<I', d, 8)[0],
        'page_size': struct.unpack_from('<I', d, 12)[0],
        'kernel_addr': struct.unpack_from('<I', d, 16)[0],
        'ramdisk_addr': struct.unpack_from('<I', d, 20)[0],
        'vendor_ramdisk_size': struct.unpack_from('<I', d, 24)[0],
        'cmdline': d[28:28 + 2048].split(b'\x00')[0].decode('utf-8', 'replace'),
        'tags_addr': struct.unpack_from('<I', d, 2076)[0],
        'name': d[2080:2096].split(b'\x00')[0].decode('utf-8', 'replace'),
        'header_size': struct.unpack_from('<I', d, 2096)[0],
        'dtb_size': struct.unpack_from('<I', d, 2100)[0],
        'dtb_addr': struct.unpack_from('<Q', d, 2104)[0],
        'ramdisk_table_size': struct.unpack_from('<I', d, 2112)[0],
        'ramdisk_table_entry_num': struct.unpack_from('<I', d, 2116)[0],
        'ramdisk_table_entry_size': struct.unpack_from('<I', d, 2120)[0],
        'bootconfig_size': struct.unpack_from('<I', d, 2124)[0],
    }
    hs = info['header_size']
    info['ramdisk_off'] = align(hs)
    info['dtb_off'] = align(info['ramdisk_off'] + info['vendor_ramdisk_size'])
    info['table_off'] = align(info['dtb_off'] + info['dtb_size'])
    info['bootconfig_off'] = align(info['table_off'] + info['ramdisk_table_size'])
    return info


def extract_stock(stock_dir, work):
    """Extract boot/vendor_boot templates into the work dir."""
    os.makedirs(work, exist_ok=True)
    stock = {
        'boot': os.path.join(stock_dir, 'boot-stock-clean.img'),
        'vendor_boot': os.path.join(stock_dir, 'vendor_boot-stock.img'),
        'ramdisk': os.path.join(stock_dir, 'ramdisk.lz4'),
        'vendor_dlkm': os.path.join(stock_dir, 'vendor_dlkm-stock.img'),
    }
    for k, v in stock.items():
        if not os.path.exists(v):
            raise SystemExit(f'missing stock template: {v}')

    bi = parse_boot(stock['boot'])
    vi = parse_vendor_boot(stock['vendor_boot'])
    params = {'boot': bi, 'vendor_boot': vi}
    # stock boot signature (layout mimicry; device runs with vbmeta verification
    # disabled, so the payload is not actually checked)
    if bi.get('signature_size'):
        sig = read(stock['boot'])[bi['signature_off']:bi['signature_off'] + bi['signature_size']]
    else:
        sig = b''
    write(os.path.join(work, 'stock_boot_signature.bin'), sig)

    vd = read(stock['vendor_boot'])
    write(os.path.join(work, 'stock_vendor_dtb.bin'),
          vd[vi['dtb_off']:vi['dtb_off'] + vi['dtb_size']])
    write(os.path.join(work, 'stock_vendor_bootconfig.bin'),
          vd[vi['bootconfig_off']:vi['bootconfig_off'] + vi['bootconfig_size']])
    write(os.path.join(work, 'stock_vendor_ramdisk.lz4'),
          vd[vi['ramdisk_off']:vi['ramdisk_off'] + vi['vendor_ramdisk_size']])

    # unpack the stock vendor ramdisk for reuse of its files
    vbroot = os.path.join(work, 'stock_vbroot')
    shutil.rmtree(vbroot, ignore_errors=True)
    os.makedirs(vbroot)
    cpio = os.path.join(work, 'stock_vendor_ramdisk.cpio')
    with open(cpio, 'wb') as f:
        subprocess.run(['lz4', '-d', '-c', os.path.join(work, 'stock_vendor_ramdisk.lz4')],
                       stdout=f, check=True)
    with open(cpio, 'rb') as f:
        subprocess.run(['cpio', '-id', '--quiet'], cwd=vbroot, stdin=f, check=True)
    params['stock_vb_modules'] = sorted(
        os.path.basename(p) for p in glob.glob(os.path.join(vbroot, 'lib/modules/*.ko')))
    write(os.path.join(work, 'stock_params.json'), json.dumps(params, indent=2))
    print(f"stock: boot v{bi['header_version']} ramdisk={bi['ramdisk_size']}, "
          f"vendor_boot v{vi['header_version']} ramdisk={vi['vendor_ramdisk_size']}, "
          f"stock vb modules={len(params['stock_vb_modules'])}")
    return params


# --------------------------------------------------------------------------
# module staging
# --------------------------------------------------------------------------
def find_strip_tool():
    cands = [
        'kernel_platform/prebuilts-master/clang/host/linux-x86/clang-r416183b/bin/llvm-strip',
        'kernel_platform/prebuilts/clang/host/linux-x86/clang-r416183b/bin/llvm-strip',
    ]
    for c in cands:
        if os.path.exists(c):
            return os.path.abspath(c)
    return shutil.which('llvm-strip') or shutil.which('strip')


def stage_modules(dist, krel, work, strip=True):
    """Copy build .ko files into work/modroot/lib/modules/<krel>, strip, depmod."""
    modroot = os.path.join(work, 'modroot')
    kdir = os.path.join(modroot, 'lib', 'modules', krel)
    shutil.rmtree(modroot, ignore_errors=True)
    os.makedirs(kdir)
    src = sorted(glob.glob(os.path.join(dist, '*.ko')))
    if not src:
        raise SystemExit(f'no .ko files in {dist}')
    names = {}
    for p in src:
        name = os.path.basename(p)
        # Android/Samsung ship the qcacld module under a different file name
        if name == 'wlan.ko':
            name = 'qca_cld3_wlan.ko'
        if name in names:
            raise SystemExit(f'duplicate module name: {name}')
        names[name] = p
        shutil.copy2(p, os.path.join(kdir, name))
    strip_tool = find_strip_tool() if strip else None
    if strip_tool:
        for p in glob.glob(os.path.join(kdir, '*.ko')):
            subprocess.run([strip_tool, '--strip-debug', '--keep-section=.ARM.attributes', p],
                           check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    run(['depmod', '-b', modroot, krel])
    manifest = {'krel': krel, 'modules': sorted(names)}
    write(os.path.join(work, 'module_manifest.json'), json.dumps(manifest, indent=1))
    print(f'staged {len(names)} modules under {kdir}')
    return kdir, manifest


def parse_modules_dep(kdir):
    """Return depmap: module -> [modules], in the same order depmod wrote."""
    depmap = {}
    order = []
    with open(os.path.join(kdir, 'modules.dep')) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            left, _, right = line.partition(':')
            name = os.path.basename(left)
            deps = [os.path.basename(x) for x in right.split()] if right.strip() else []
            depmap[name] = deps
            order.append(name)
    return depmap, order


def closure(seeds, depmap, available):
    out = set()
    stack = [s for s in seeds if s in available]
    while stack:
        m = stack.pop()
        if m in out:
            continue
        out.add(m)
        for d in depmap.get(m, []):
            if d in available and d not in out:
                stack.append(d)
    return out


def load_list(path):
    res = []
    with open(path, errors='replace') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            res.append(line)
    return res


# --------------------------------------------------------------------------
# image writers
# --------------------------------------------------------------------------
def pack_boot(kernel, ramdisk, out, os_version, signature=b'', cmdline=b''):
    ks = read(kernel)
    rs = read(ramdisk)
    hdr = bytearray()
    hdr += BOOT_MAGIC
    hdr += struct.pack('<I', len(ks))
    hdr += struct.pack('<I', len(rs))
    hdr += struct.pack('<I', os_version)
    hdr += struct.pack('<I', BOOT_V4_HEADER_SIZE)
    hdr += struct.pack('<4I', 0, 0, 0, 0)       # reserved
    hdr += struct.pack('<I', 4)                 # header version
    hdr += cmdline.ljust(1536, b'\x00')[:1536]
    hdr += struct.pack('<I', BOOT_V4_SIGNATURE_SIZE if signature else 0)
    img = page_pad(bytes(hdr))
    img += page_pad(ks)
    img += page_pad(rs)
    if signature:
        img += page_pad(signature)
    write(out, img)
    return len(img)


def pack_vendor_boot(vendor_ramdisk, dtb, bootconfig, out, params):
    vi = params['vendor_boot']
    vr = read(vendor_ramdisk)
    dt = read(dtb)
    bc = read(bootconfig)
    hdr = bytearray()
    hdr += VENDOR_BOOT_MAGIC
    hdr += struct.pack('<I', 4)                 # header version
    hdr += struct.pack('<I', PAGE)              # page size
    hdr += struct.pack('<I', vi['kernel_addr'])
    hdr += struct.pack('<I', vi['ramdisk_addr'])
    hdr += struct.pack('<I', len(vr))
    hdr += vi['cmdline'].encode().ljust(2048, b'\x00')[:2048]
    hdr += struct.pack('<I', vi['tags_addr'])
    hdr += vi['name'].encode().ljust(16, b'\x00')[:16]
    hdr += struct.pack('<I', VENDOR_BOOT_V4_HEADER_SIZE)
    hdr += struct.pack('<I', len(dt))
    hdr += struct.pack('<Q', vi['dtb_addr'])
    hdr += struct.pack('<I', VENDOR_RAMDISK_TABLE_ENTRY_V4_SIZE)
    hdr += struct.pack('<I', 1)                 # one ramdisk entry
    hdr += struct.pack('<I', VENDOR_RAMDISK_TABLE_ENTRY_V4_SIZE)
    hdr += struct.pack('<I', len(bc))
    assert len(hdr) == VENDOR_BOOT_V4_HEADER_SIZE, len(hdr)
    # table entry: size, offset, type (platform), name, board_id
    entry = struct.pack('<III', len(vr), 0, 1) + b'\x00' * 32 + b'\x00' * 64
    assert len(entry) == VENDOR_RAMDISK_TABLE_ENTRY_V4_SIZE, len(entry)
    img = page_pad(bytes(hdr))
    img += page_pad(vr)
    img += page_pad(dt)
    img += page_pad(entry)
    img += page_pad(bc)
    write(out, img)
    return len(img)


# --------------------------------------------------------------------------
# subcommands
# --------------------------------------------------------------------------
def load_params(work):
    return json.loads(read_text(os.path.join(work, 'stock_params.json')))


def cmd_stage(args):
    stage_modules(args.dist, args.krel, args.work, strip=not args.no_strip)


def cmd_vendor_ramdisk(args):
    params = load_params(args.work)
    kdir, manifest = stage_modules(args.dist, args.krel, args.work, strip=not args.no_strip)
    depmap, order = parse_modules_dep(kdir)
    available = set(manifest['modules'])
    stock_vb = set(params['stock_vb_modules'])

    stock_dlkm = set()
    if args.stock_dlkm_modules and os.path.isdir(args.stock_dlkm_modules):
        stock_dlkm = {os.path.basename(p) for p in glob.glob(
            os.path.join(args.stock_dlkm_modules, '*.ko'))}
    print(f'stock dlkm modules listed: {len(stock_dlkm)}')

    missing = sorted(stock_vb - available)
    if missing:
        print(f'WARNING: {len(missing)} stock vendor_boot modules not built: {missing[:15]}')

    vb_set = closure([n for n in stock_vb if n in available], depmap, available)
    print(f'vendor_boot module set: {len(vb_set)}')

    # rebuild the vendor ramdisk on top of the stock one
    vbroot = os.path.join(args.work, 'vbroot')
    shutil.rmtree(vbroot, ignore_errors=True)
    shutil.copytree(os.path.join(args.work, 'stock_vbroot'), vbroot)
    moddir = os.path.join(vbroot, 'lib', 'modules')
    for p in glob.glob(os.path.join(moddir, '*')):
        if os.path.isfile(p):
            os.unlink(p)
    for name in sorted(vb_set):
        shutil.copy2(os.path.join(kdir, name), os.path.join(moddir, name))

    def rewrite_dep(paths, names, prefix):
        out = []
        for line in open(os.path.join(kdir, 'modules.dep'), errors='replace'):
            line = line.strip()
            if not line:
                continue
            left, _, right = line.partition(':')
            name = os.path.basename(left)
            if name not in names:
                continue
            deps = ['%s%s' % (prefix, os.path.basename(d)) for d in right.split()]
            out.append(('%s%s: %s' % (prefix, name, ' '.join(deps))).rstrip())
        return '\n'.join(out) + '\n'

    def filter_alias(kdir, fn, names_bare, index):
        out = []
        src = os.path.join(kdir, fn)
        if not os.path.exists(src):
            return ''
        for line in open(src, errors='replace'):
            sline = line.strip()
            if not sline or sline.startswith('#'):
                continue
            fields = sline.split()
            if len(fields) > index and fields[index] in names_bare:
                out.append(sline)
        return '\n'.join(sorted(set(out))) + '\n'

    names_bare = {n[:-3] for n in vb_set}
    write(os.path.join(moddir, 'modules.dep'), rewrite_dep(None, vb_set, '/lib/modules/'))
    write(os.path.join(moddir, 'modules.alias'),
          '# Aliases extracted from modules themselves.\n' +
          filter_alias(kdir, 'modules.alias', names_bare, 2))
    write(os.path.join(moddir, 'modules.softdep'),
          '# Soft dependencies extracted from modules themselves.\n' +
          filter_alias(kdir, 'modules.softdep', names_bare, 1))

    # keep the stock blocklist (bare names, harmless if a module is absent)
    src = os.path.join(args.work, 'stock_vbroot', 'lib/modules/modules.blocklist')
    if os.path.exists(src):
        shutil.copy2(src, os.path.join(moddir, 'modules.blocklist'))

    # load order: exactly the stock first-stage list (filtered), plus only
    # genuinely new modules that stock did not have in the vendor_boot ramdisk.
    stock_vb_names = set(params['stock_vb_modules'])
    new_mods = sorted(vb_set - stock_vb_names)
    stock_load = load_list(os.path.join(args.work, 'stock_vbroot', 'lib/modules/modules.load'))
    load = [n for n in stock_load if n in vb_set] + new_mods
    write(os.path.join(moddir, 'modules.load'), '\n'.join(load) + '\n')
    stock_load_rec = load_list(os.path.join(args.work, 'stock_vbroot', 'lib/modules/modules.load.recovery'))
    if stock_load_rec:
        load_rec = [n for n in stock_load_rec if n in vb_set] + new_mods
        write(os.path.join(moddir, 'modules.load.recovery'), '\n'.join(load_rec) + '\n')

    # fstab: our vendor_dlkm image is not AVB-signed and uses a plain f2fs
    # layout; keep it simple.  The first-stage ramdisk fstab is the one init
    # actually reads for logical partitions.
    fstab = os.path.join(vbroot, 'first_stage_ramdisk/fstab.qcom')
    if os.path.exists(fstab):
        new = []
        for line in open(fstab):
            if line.startswith('vendor_dlkm'):
                if args.strip_avb:
                    parts = line.rstrip('\n').split('\t')
                    if len(parts) >= 4:
                        parts[4] = ','.join(
                            f for f in parts[4].split(',')
                            if f not in ('avb', 'verify') and not f.startswith('avb='))
                    new.append('\t'.join(parts) + '\n')
                elif args.keep_fstab:
                    new.append(line)
                else:
                    new.append('vendor_dlkm\t/vendor_dlkm\t%s\tro\t'
                               'wait,logical,first_stage_mount,context=u:object_r:vendor_file:s0\n'
                               % args.vendor_dlkm_fs)
            else:
                new.append(line)
        open(fstab, 'w').writelines(new)

    # repack cpio + legacy lz4
    cpio = os.path.join(args.work, 'vendor_ramdisk_new.cpio')
    with open(cpio, 'wb') as f:
        subprocess.run('find . -print0 | cpio --null -o -H newc --quiet',
                       shell=True, cwd=vbroot, stdout=f, check=True)
    lz4 = os.path.join(args.work, 'vendor_ramdisk_new.lz4')
    with open(lz4, 'wb') as f:
        subprocess.run(['lz4', '-l', '-9', '-c', cpio], stdout=f, check=True)
    print(f'vendor ramdisk rebuilt: {len(vb_set)} modules, {os.path.getsize(lz4)} bytes (lz4 legacy)')
    json.dump({'vendor_boot_modules': sorted(vb_set),
               'stock_dlkm_modules': sorted(stock_dlkm)},
              open(os.path.join(args.work, 'vb_selection.json'), 'w'), indent=1)


def cmd_vendor_boot(args):
    params = load_params(args.work)
    vr = os.path.join(args.work, 'vendor_ramdisk_new.lz4')
    dtb = args.vendor_dtb or os.path.join(args.work, 'stock_vendor_dtb.bin')
    bc = os.path.join(args.work, 'stock_vendor_bootconfig.bin')
    for p in (vr, bc):
        if not os.path.exists(p):
            raise SystemExit(f'missing {p} (run vendor-ramdisk first)')
    if not os.path.exists(dtb):
        raise SystemExit(f'missing dtb {dtb}')
    out = os.path.join(args.out, 'vendor_boot.img')
    size = pack_vendor_boot(vr, dtb, bc, out, params)
    print(f'vendor_boot.img: {size} bytes -> {out}')


def cmd_boot(args):
    params = load_params(args.work)
    kernel = os.path.join(args.dist, 'Image')
    if not os.path.exists(kernel):
        raise SystemExit(f'missing {kernel}')
    sig = read(os.path.join(args.work, 'stock_boot_signature.bin'))
    out = os.path.join(args.out, 'boot.img')
    size = pack_boot(kernel, args.stock_ramdisk, out,
                     params['boot']['os_version'], signature=sig)
    print(f'boot.img: {size} bytes -> {out}')


def cmd_vendor_dlkm(args):
    params = load_params(args.work)
    kdir, manifest = stage_modules(args.dist, args.krel, args.work, strip=not args.no_strip)
    depmap, order = parse_modules_dep(kdir)
    available = set(manifest['modules'])
    sel = json.load(open(os.path.join(args.work, 'vb_selection.json')))
    vb_set = set(sel['vendor_boot_modules'])
    stock_dlkm = set()
    if args.stock_dlkm_modules and os.path.isdir(args.stock_dlkm_modules):
        stock_dlkm = {os.path.basename(p) for p in glob.glob(
            os.path.join(args.stock_dlkm_modules, '*.ko'))}
        missing = sorted(stock_dlkm - available)
        if missing:
            print(f'WARNING: {len(missing)} stock vendor_dlkm modules not built: {missing[:15]}')
    dlkm_set = closure([n for n in stock_dlkm if n in available], depmap, available)
    # anything we built that is not in the first-stage set must live somewhere
    dlkm_set |= (available - vb_set)
    if args.dlkm_exclude_first_stage:
        load_path = os.path.join(args.work, 'vbroot', 'lib', 'modules', 'modules.load')
        if os.path.exists(load_path):
            first = set(load_list(load_path))
            removed = dlkm_set & first
            dlkm_set -= first
            print(f'vendor_dlkm: moved {len(removed)} first-stage modules out of dlkm')
    if args.dedupe_dlkm:
        dup = dlkm_set & vb_set
        dlkm_set -= vb_set
        print(f'vendor_dlkm: deduped {len(dup)} modules already in vendor_boot')
    print(f'vendor_dlkm module set: {len(dlkm_set)}')

    root = os.path.join(args.work, 'dlkm_root')
    shutil.rmtree(root, ignore_errors=True)
    moddir = os.path.join(root, 'lib', 'modules')
    os.makedirs(moddir)
    for name in sorted(dlkm_set):
        shutil.copy2(os.path.join(kdir, name), os.path.join(moddir, name))

    prefix = '/vendor/lib/modules/'
    dep_lines = []
    for line in open(os.path.join(kdir, 'modules.dep'), errors='replace'):
        line = line.strip()
        if not line:
            continue
        left, _, right = line.partition(':')
        name = os.path.basename(left)
        if name not in dlkm_set:
            continue
        deps = ['%s%s' % (prefix, os.path.basename(d)) for d in right.split()]
        dep_lines.append(('%s%s: %s' % (prefix, name, ' '.join(deps))).rstrip())
    write(os.path.join(moddir, 'modules.dep'), '\n'.join(dep_lines) + '\n')

    # alias/softdep reference bare module names, same as stock
    dlkm_bare = {n[:-3] for n in dlkm_set}
    for fn, index in (('modules.alias', 2), ('modules.softdep', 1)):
        src = os.path.join(kdir, fn)
        if not os.path.exists(src):
            continue
        out = []
        for line in open(src, errors='replace'):
            sline = line.strip()
            if not sline or sline.startswith('#'):
                continue
            fields = sline.split()
            if len(fields) > index and fields[index] in dlkm_bare:
                out.append(sline)
        write(os.path.join(moddir, fn), '\n'.join(sorted(set(out))) + '\n')
    if os.path.exists(os.path.join(args.stock_dlkm_modules, 'modules.blocklist')):
        shutil.copy2(os.path.join(args.stock_dlkm_modules, 'modules.blocklist'),
                     os.path.join(moddir, 'modules.blocklist'))

    stock_load = load_list(os.path.join(args.stock_dlkm_modules, 'modules.load'))
    load = [n for n in stock_load if n in dlkm_set]
    load += sorted(dlkm_set - set(load))
    write(os.path.join(moddir, 'modules.load'), '\n'.join(load) + '\n')

    # make the f2fs image (same size as the stock logical partition)
    os.makedirs(args.out, exist_ok=True)
    img = os.path.join(args.out, 'vendor_dlkm.img')
    sectors = args.vendor_dlkm_sectors
    if os.path.exists(img):
        os.unlink(img)
    size = sectors * 512
    if args.vendor_dlkm_fs == 'ext4':
        blocks = size // 4096
        run(['mke2fs', '-q', '-F', '-t', 'ext4', '-b', '4096', '-I', '256',
             '-L', 'vendor_dlkm', '-O', '^has_journal,^resize_inode,^metadata_csum',
             '-d', root, img, str(blocks)])
    else:
        with open(img, 'wb') as f:
            f.truncate(size)
        run(['mkfs.f2fs', '-f', '-l', 'vendor_dlkm',
             '-O', 'extra_attr,compression', img, str(sectors)])
        run(['sload.f2fs', '-c', '-f', root, '-t', '/', img])
    print(f'vendor_dlkm.img ({args.vendor_dlkm_fs}): {os.path.getsize(img)} bytes -> {img}')


def cmd_all(args):
    cmd_stage(args)
    cmd_vendor_ramdisk(args)
    cmd_vendor_boot(args)
    cmd_boot(args)
    cmd_vendor_dlkm(args)
    print('\nALL IMAGES BUILT:')
    for f in ('boot.img', 'vendor_boot.img', 'vendor_dlkm.img'):
        p = os.path.join(args.out, f)
        print(f'  {f:18s} {os.path.getsize(p):>12,d} bytes  {p}')


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('cmd', choices=['stage', 'vendor-ramdisk', 'vendor-boot',
                                    'boot', 'vendor-dlkm', 'all'])
    ap.add_argument('--dist', default='out/msm-waipio-waipio-gki/dist',
                    help='kernel_platform build dist dir (Image + *.ko)')
    ap.add_argument('--stock', default='stock', help='stock template dir')
    ap.add_argument('--stock-dlkm-modules', default='_ref/dlkmroot/modules',
                    help='stock vendor_dlkm modules dir (extracted from device/firmware)')
    ap.add_argument('--stock-ramdisk', default='stock/ramdisk.lz4',
                    help='clean stock GKI ramdisk (from stock boot.img)')
    ap.add_argument('--krel', required=False, default=None,
                    help='kernel release (e.g. 5.10.274-YanJiaMian-gki)')
    ap.add_argument('--work', default='_work')
    ap.add_argument('--out', default='dist-images')
    ap.add_argument('--vendor-dlkm-sectors', type=lambda x: int(x, 0),
                    default=68272128 // 512)  # stock b4q vendor_dlkm partition size
    ap.add_argument('--vendor-dlkm-fs', choices=['ext4', 'f2fs'], default='ext4',
                    help='filesystem for the rebuilt vendor_dlkm image '
                         '(ext4 is used by the packaged vendor_boot fstab)')
    ap.add_argument('--vendor-dtb', default=None,
                    help='override the vendor_boot dtb image (default: stock dtb)')
    ap.add_argument('--dlkm-exclude-first-stage', action='store_true',
                    help='exclude modules listed in the vendor_boot first-stage '
                         'modules.load from vendor_dlkm (stock partition semantics)')
    ap.add_argument('--strip-avb', action='store_true',
                    help='keep the stock fstab type but drop avb/verify flags on vendor_dlkm')
    ap.add_argument('--keep-fstab', action='store_true',
                    help='do not rewrite the vendor_dlkm fstab entry (keep stock fs type)')
    ap.add_argument('--dedupe-dlkm', action='store_true',
                    help='skip modules already present in the vendor_boot first-stage '
                         'set when building vendor_dlkm (saves space)')
    ap.add_argument('--no-strip', action='store_true')
    args = ap.parse_args()

    os.makedirs(args.work, exist_ok=True)
    os.makedirs(args.out, exist_ok=True)
    if not args.krel:
        for c in ('out/msm-waipio-waipio-gki/gki_kernel/common/include/config/kernel.release',
                  'kernel_platform/out/msm-waipio-waipio-gki/gki_kernel/common/include/config/kernel.release'):
            if os.path.exists(c):
                args.krel = read(c).decode().strip()
                break
        if not args.krel:
            raise SystemExit('cannot determine kernel release, pass --krel')

    # stock params are needed by every command
    if not os.path.exists(os.path.join(args.work, 'stock_params.json')):
        extract_stock(args.stock, args.work)

    if args.cmd == 'stage':
        cmd_stage(args)
    elif args.cmd == 'vendor-ramdisk':
        cmd_vendor_ramdisk(args)
    elif args.cmd == 'vendor-boot':
        cmd_vendor_boot(args)
    elif args.cmd == 'boot':
        cmd_boot(args)
    elif args.cmd == 'vendor-dlkm':
        cmd_vendor_dlkm(args)
    else:
        cmd_all(args)


if __name__ == '__main__':
    main()
