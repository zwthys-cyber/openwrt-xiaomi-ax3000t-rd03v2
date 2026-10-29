#!/usr/bin/env python3
"""Verify the actual arm64 rootfs and module ABI on the GitHub runner."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

REPO = Path(__file__).resolve().parents[1]


def require(value, message):
    if not value:
        raise ValueError(message)
    print('PASS', message)


def main():
    tree, release = map(lambda p: Path(p).resolve(), sys.argv[1:])
    spec = importlib.util.spec_from_file_location('artifact_verifier', REPO / 'tools/verify-artifacts.py')
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    prefix = verifier.PREFIX
    with tempfile.TemporaryDirectory(prefix='yala-image-') as temporary:
        work = Path(temporary)
        root = verifier.unpack_root(release / (prefix + '-squashfs-sysupgrade.bin'), work)
        installed = verifier.manifest((root / 'lib/apk/db/installed').read_text())
        require('libucode20261009' in installed and 'libucode20230711' not in installed, 'one coherent ucode ABI')
        require(installed['ucode'].startswith('2026.10.23~aabdeb4f'), 'pinned interpreter in actual image')
        require('mihomo-yala' not in installed and not (root / 'etc/openclash/core/clash_meta').exists(), 'large core excluded from RAM installer package profile')
        require('luci-app-openclash' in installed and 'kmod-zram' in installed, 'proxy UI and compressed swap installed')
        require('GOMEMLIMIT=32MiB' in (root / 'etc/init.d/openclash').read_text(), 'persistent core memory environment')
        require((root / 'etc/rc.d/S18yala-zram').is_symlink(), 'early zram startup enabled')
        require((root / 'etc/rc.d/S17yala-cpu-limit').is_symlink(), 'rated CPU ceiling enabled at boot')
        require('1008000' in (root / 'etc/init.d/yala-cpu-limit').read_text(), 'rated 1008 MHz CPU ceiling retained')
        old = list(root.glob('usr/lib/libucode.so.20230711*'))
        require(not old, 'no legacy libucode fallback retained')
        env = dict(os.environ, GOGC='50', GOMEMLIMIT='24MiB')
        common = ['qemu-aarch64', '-L', str(root), '-E', f'LD_LIBRARY_PATH={root}/lib:{root}/usr/lib']
        program = "import * as fs from 'fs'; import * as uci from 'uci'; import * as ubus from 'ubus'; import * as uloop from 'uloop'; import * as nl80211 from 'nl80211'; import * as rtnl from 'rtnl'; import {sha256} from 'digest'; print('YALA_ABI_OK ',sha256('abc'));"
        output = subprocess.check_output(common + [str(root / 'usr/bin/ucode'), '-L', str(root / 'usr/lib/ucode/*.so'), '-e', program], text=True, stderr=subprocess.STDOUT, env=env, timeout=45)
        require('YALA_ABI_OK ba7816bf' in output, 'arm64 interpreter imports all wireless/RPC modules under QEMU')
        loaded = []
        # rpcd has no help flag. Its pinned main.c rejects -t 0 before
        # touching UCI or connecting to ubus, and returns -1 (status 255).
        probes = [
            ('usr/sbin/hostapd', ['-v'], (0, 1), 'hostapd'),
            ('sbin/netifd', ['-h'], (0, 1), 'usage'),
            ('sbin/rpcd', ['-t', '0'], (255,), 'Invalid execution timeout specified'),
        ]
        for name, arguments, expected_codes, marker in probes:
            binary = root / name
            if not binary.exists():
                continue
            process = subprocess.run(common + [str(binary)] + arguments, text=True, capture_output=True, env=env, timeout=30)
            text = process.stdout + process.stderr
            require(process.returncode in expected_codes, f'binary expected exit: {name}, status={process.returncode}, output={text[:800]!r}')
            require('symbol not found' not in text.lower() and 'error loading shared library' not in text.lower(), 'arm64 ELF runtime dependencies: ' + name)
            require(marker.lower() in text.lower(), 'binary responds with expected version/usage/validation message: ' + name)
            loaded.append(name)
        require('usr/sbin/hostapd' in loaded and 'sbin/netifd' in loaded, 'wireless consumer binaries exercised')
        # C modules resolve ucode symbols from their host; QEMU imports above
        # validate those bindings. Only executable consumers require a NEEDED entry.
        for name in ('usr/sbin/wpad', 'sbin/netifd', 'usr/bin/ucode'):
            text = subprocess.check_output(['readelf','-d',str(root / name)],text=True)
            require('libucode.so.20261009' in text and 'libucode.so.20230711' not in text, 'linked ABI: ' + name)
        apk = tree / 'staging_dir/host/bin/apk'
        package_index = tree / 'bin/targets/qualcommax/ipq50xx/packages/packages.adb'
        available = json.loads(subprocess.check_output([str(apk),'adbdump','--format','json',str(package_index)]))['packages']
        names = {item['name'] for item in available}
        require(set(installed) <= names, 'every installed package is available in the matching signed bundle')
        require('mihomo-yala' in names, 'matching official-core package available separately')
        report = {'source_commit':os.environ.get('GITHUB_SHA'), 'run_url':f"https://github.com/{os.environ.get('GITHUB_REPOSITORY')}/actions/runs/{os.environ.get('GITHUB_RUN_ID')}", 'board':'xiaomi,mi-router-ax3000t-v2', 'ucode_abi':'20261009', 'zram_logical_mib':64, 'zram_physical_cap_mib':24, 'core_in_installer':False, 'installed_packages':len(installed), 'signed_feed_packages':len(names), 'hardware_validation':'not performed', 'flashing':'not performed or authorized', 'feed_publication':'not performed; draft artifacts only', 'public_key_sha256':hashlib.sha256((REPO / 'keys/public-key.pem').read_bytes()).hexdigest()}
        report.update(upstream_release='v2.1.0', cpu_max_khz=1008000)
        (release / 'yala-verification.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report,indent=2))


if __name__ == '__main__':
    main()
