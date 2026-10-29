import importlib.util
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'overlay/target/linux/qualcommax/ipq50xx/base-files'


class ProfileTests(unittest.TestCase):
    def test_pinned_profile_preparation_keeps_explicit_build_dependencies(self):
        spec = importlib.util.spec_from_file_location('profile', ROOT / 'tools/apply-yala-profile.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary)
            tree = work / 'tree'
            recipe = tree / 'package/utils/ucode/Makefile'
            recipe.parent.mkdir(parents=True)
            recipe.write_text('old recipe')
            package = work / ('OpenClash-' + module.OPENCLASH_COMMIT) / 'luci-app-openclash'
            init = package / 'root/etc/init.d/openclash'
            init.parent.mkdir(parents=True)
            init.write_text('#!/bin/sh\nstart() {\n procd_set_param env SAFE_PATHS=/tmp\n}\n')
            (package / 'Makefile').write_text('PKG_VERSION:=0.48.002\ndefine Package/$(PKG_NAME)/config\n config demo\nendef\nDEPENDS:=+ruby +ruby-yaml +kmod-tun +unzip\n')
            archive = work / 'source.tar.gz'
            with tarfile.open(archive, 'w:gz') as output:
                output.add(package, arcname='OpenClash-' + module.OPENCLASH_COMMIT + '/luci-app-openclash')
            with patch.object(sys, 'argv', ['prepare', str(tree)]), patch.object(module.urllib.request, 'urlretrieve', side_effect=lambda url, path: shutil.copyfile(archive, path)):
                module.main()
            prepared = (tree / 'package/yala/luci-app-openclash/Makefile').read_text()
            self.assertIn('PKG_BUILD_DEPENDS:=luci-base/host', prepared)
            self.assertIn('+kmod-nft-tproxy', prepared)
            self.assertNotIn('define Package/$(PKG_NAME)/config', prepared)
            self.assertIn('GOMEMLIMIT=32MiB', (tree / 'package/yala/luci-app-openclash/root/etc/init.d/openclash').read_text())
            self.assertIn('PKG_ABI_VERSION:=20261009', recipe.read_text())
            self.assertTrue((tree / 'files/etc/rc.d/S18yala-zram').is_symlink())

    def test_vendor_abi_and_required_dependencies(self):
        text = (ROOT / 'vendor/ucode/Makefile').read_text()
        self.assertIn('PKG_ABI_VERSION:=20261009', text)
        self.assertIn('aabdeb4f5060c91c5929bf6d7af745c6aabf5ec5', text)
        config = (ROOT / 'config/rd03v2.config').read_text()
        self.assertIn('CONFIG_PACKAGE_mihomo-yala=m', config)
        self.assertIn('CONFIG_ATH11K_NSS_MEM_PROFILE_256M=y', config)

    def test_complete_world_pinning_discards_stale_abi(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            db, world = root / 'database', root / 'world'
            db.write_text('P:ucode\nV:2026.10.23-r1\n\nP:libucode20261009\nV:2026.10.23-r1\n')
            world.write_text('libucode20230711\nucode\n')
            source = (BASE / 'etc/uci-defaults/95-rd03v2-apk-pins').read_text()
            script = source.replace('/etc/apk/world', str(world)).replace('/lib/apk/db/installed', str(db))
            result = subprocess.run(['sh', '-c', script], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(world.read_text().splitlines(), ['libucode20261009=2026.10.23-r1', 'ucode=2026.10.23-r1'])
            self.assertIn('libucode20230711', (root / 'world.before-yala-profile').read_text())

    def test_zram_parameters_without_touching_real_swap(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sysfs = root / 'zram'
            sysfs.mkdir()
            (sysfs / 'disksize').write_text('0')
            swaps = root / 'swaps'
            swaps.write_text('')
            commands = root / 'commands'
            commands.mkdir()
            for name in ('modprobe', 'mkswap', 'swapon'):
                path = commands / name
                path.write_text('#!/bin/sh\nexit 0\n')
                path.chmod(0o755)
            source = (BASE / 'etc/init.d/yala-zram').read_text().replace('/sys/block/zram0', str(sysfs)).replace('/proc/swaps', str(swaps))
            script = root / 'service'
            script.write_text(source)
            import os
            env = dict(os.environ, PATH=str(commands) + ':' + os.environ['PATH'])
            result = subprocess.run(['sh', '-c', '. "$1"; start', 'fixture', str(script)], env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((sysfs / 'disksize').read_text().strip(), '67108864')
            self.assertEqual((sysfs / 'mem_limit').read_text().strip(), '25165824')
            self.assertEqual((sysfs / 'comp_algorithm').read_text().strip(), 'lzo-rle')


if __name__ == '__main__':
    unittest.main()
