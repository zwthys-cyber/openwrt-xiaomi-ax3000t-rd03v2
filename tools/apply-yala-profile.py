#!/usr/bin/env python3
"""Prepare the coherent ABI and pinned proxy packages before feeds/defconfig."""
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request

REPO = Path(__file__).resolve().parents[1]
OPENCLASH_COMMIT = 'e553e82e01c697aefbe1555261a503f425e00ccd'


def main():
    tree = Path(sys.argv[1]).resolve()
    package = tree / 'package/utils/ucode'
    if not (package / 'Makefile').is_file():
        raise ValueError('ucode recipe missing')
    shutil.rmtree(package)
    shutil.copytree(REPO / 'vendor/ucode', package)
    startup = tree / 'files/etc/rc.d/S18yala-zram'
    startup.parent.mkdir(parents=True, exist_ok=True)
    startup.symlink_to('../init.d/yala-zram')
    target = tree / 'package/yala/luci-app-openclash'
    if target.exists():
        raise ValueError('refusing to overwrite an existing OpenClash package')
    with tempfile.TemporaryDirectory() as temporary:
        archive = Path(temporary) / 'source.tar.gz'
        url = f'https://github.com/vernesong/OpenClash/archive/{OPENCLASH_COMMIT}.tar.gz'
        urllib.request.urlretrieve(url, archive)
        print('OpenClash pinned source archive sha256:', hashlib.sha256(archive.read_bytes()).hexdigest())
        with tarfile.open(archive) as tar:
            prefix = f'OpenClash-{OPENCLASH_COMMIT}/luci-app-openclash/'
            for member in tar.getmembers():
                if member.name.startswith(prefix):
                    tar.extract(member, temporary, filter='data')
        shutil.copytree(Path(temporary) / prefix, target)
    init = target / 'root/etc/init.d/openclash'
    text = init.read_text()
    marker = 'procd_set_param env SAFE_PATHS='
    lines = text.splitlines(keepends=True)
    matches = [i for i, line in enumerate(lines) if marker in line]
    if len(matches) != 1:
        raise ValueError('OpenClash environment anchor changed')
    lines.insert(matches[0] + 1, '   procd_append_param env GOGC=50 GOMEMLIMIT=32MiB\n')
    init.write_text(''.join(lines))
    makefile = target / 'Makefile'
    text = makefile.read_text()
    if text.count('PKG_VERSION:=0.48.002\n') != 1:
        raise ValueError('OpenClash version changed')
    makefile.write_text(text.replace('PKG_VERSION:=0.48.002\n', 'PKG_VERSION:=0.48.002\nPKG_RELEASE:=101\n'))
    subprocess.run(['sh', '-n', str(init)], check=True)


if __name__ == '__main__':
    main()
