import hashlib
import json
from pathlib import Path
import runpy
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[2]
package = runpy.run_path(str(ROOT / 'scripts/package_source.py'))['package']


class SourceBundleTests(unittest.TestCase):
    def test_build_inputs_and_checksums_without_private_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, output = Path(tmp) / 'repo', Path(tmp) / 'out'
            files = {'server/VERSION': '1.0.4-beta.2', 'server/app.py': 'print(1)',
                     'Dockerfile': 'FROM python:3.12-slim', 'LICENSE': 'licence',
                     'scripts/prepare.sh': 'true', '.env.example': 'SETUP_TOKEN=',
                     '.github/workflows/docker.yml': 'name: Build',
                     '.git/config': 'private', '.env': 'secret', 'server/.env.local': 'secret',
                     'server/rounded.sqlite': 'records', 'server/data/record.txt': 'records',
                     'server/uploads/receipt.pdf': 'receipt', 'server/backups/old.zip': 'backup',
                     'outside.txt': 'private'}
            for name, content in files.items():
                path = root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(content)
            package(root, output, 'a' * 40)
            manifest = json.loads((output / 'source-manifest.json').read_text())
            with zipfile.ZipFile(output / 'application-source.zip') as archive:
                self.assertEqual(set(archive.namelist()), set(list(files)[:7]) | {'SOURCE_MANIFEST.json'})
                for name, digest in manifest['files'].items():
                    self.assertEqual(hashlib.sha256(archive.read(name)).hexdigest(), digest)
                self.assertEqual(json.loads(archive.read('SOURCE_MANIFEST.json'))['revision'], 'a' * 40)
            self.assertEqual(manifest['archive_sha256'], hashlib.sha256((output / 'application-source.zip').read_bytes()).hexdigest())

    def test_symlink_and_invalid_revision_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, output = Path(tmp) / 'repo', Path(tmp) / 'out'
            (root / 'server').mkdir(parents=True)
            (root / 'server/VERSION').write_text('1.0.4-beta.2')
            (root / 'server/leak.txt').symlink_to('/etc/passwd')
            with self.assertRaises(ValueError): package(root, output)
            with self.assertRaises(ValueError): package(root, output, '../../private')

    def test_repository_source_covers_runtime_and_build_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            package(ROOT, Path(tmp))
            with zipfile.ZipFile(Path(tmp) / 'application-source.zip') as archive:
                for name in ['server/app.py', 'server/VERSION', 'Dockerfile', '.dockerignore',
                             'server/requirements.txt', 'LICENSE', 'COPYRIGHT',
                             'scripts/package_source.py', 'scripts/package_licences.py',
                             'server/datasets/LICENSE-au-suburbs.txt', '.github/workflows/docker.yml']:
                    self.assertIn(name, archive.namelist())
