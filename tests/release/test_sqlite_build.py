import hashlib
from pathlib import Path
import runpy
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
build_module = runpy.run_path(str(ROOT / 'scripts/build_sqlite.py'))
retain = runpy.run_path(str(ROOT / 'scripts/package_dependency_sources.py'))['retain_sqlite']


class SQLiteBuildTests(unittest.TestCase):
    def test_corrupt_download_is_rejected_before_compilation(self):
        with tempfile.TemporaryDirectory() as folder:
            archive = Path(folder) / 'source.zip'
            archive.write_bytes(b'untrusted download')
            with patch('subprocess.run') as compiler:
                with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
                    build_module['build'](Path(folder) / 'out', archive)
                compiler.assert_not_called()

    def test_retained_source_matches_inventory_and_rejects_tampering(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            share = root / 'share'; share.mkdir()
            payload = b'synthetic source archive'
            (share / 'source.zip').write_bytes(payload)
            (share / 'NOTICE.txt').write_text('notice')
            (share / 'sqlite-runtime.json').write_text('{}')
            package = dict(name='sqlite', version='test', source_archive='source.zip',
                           source_url='https://www.sqlite.org/test',
                           archive_sha3_256=hashlib.sha3_256(payload).hexdigest())
            manifest = {'additional': []}
            retain({'native': [package]}, root / 'sources', manifest, share)
            self.assertEqual((root / 'sources/native/sqlite/source.zip').read_bytes(), payload)
            self.assertEqual(manifest['additional'][0]['version'], 'test')
            (share / 'source.zip').write_bytes(b'modified')
            with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
                retain({'native': [package]}, root / 'bad', {'additional': []}, share)
