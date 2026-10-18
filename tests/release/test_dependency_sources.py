import hashlib
import json
from pathlib import Path
import runpy
import tempfile
import unittest
import zipfile

VERIFY = runpy.run_path(str(Path(__file__).resolve().parents[2] / 'scripts/package_dependency_sources.py'))['verify_archive']


class DependencyArchiveTests(unittest.TestCase):
    def test_archive_rejects_missing_extra_and_corrupt_source(self):
        payload = b'upstream source and patches'
        manifest = {'files': {'debian/example/source.tar.xz': hashlib.sha256(payload).hexdigest()}}
        for kind in ('valid', 'missing', 'extra', 'corrupt'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / 'sources.zip'
                with zipfile.ZipFile(path, 'w') as archive:
                    archive.writestr('dependency-sources-manifest.json', json.dumps(manifest))
                    if kind != 'missing':
                        archive.writestr('debian/example/source.tar.xz', b'wrong' if kind == 'corrupt' else payload)
                    if kind == 'extra':
                        archive.writestr('unexpected', b'private')
                if kind == 'valid':
                    VERIFY(path, manifest)
                else:
                    with self.assertRaises(ValueError):
                        VERIFY(path, manifest)
