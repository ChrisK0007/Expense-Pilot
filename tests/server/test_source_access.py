import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from app import app, VERSION


class SourceAccessTests(unittest.TestCase):
    def test_public_build_source_and_notices(self):
        client = app.test_client()
        self.assertEqual(client.get('/about').status_code, 200)
        response = client.get('/source')
        self.assertEqual(response.status_code, 200)
        self.assertIn(VERSION, response.headers['Content-Disposition'])
        manifest = client.get('/legal/manifest').json
        self.assertEqual(manifest['version'], VERSION)
        self.assertEqual(hashlib.sha256(response.data).hexdigest(), manifest['archive_sha256'])
        with zipfile.ZipFile(io.BytesIO(response.data)) as archive:
            self.assertEqual(archive.read('server/VERSION').decode().strip(), VERSION)
            self.assertEqual(archive.read('server/app.py'), Path('/app/app.py').read_bytes())
            self.assertNotIn('.git/config', archive.namelist())
            self.assertNotIn('rounded.sqlite', archive.namelist())
        for document in ('licence', 'copyright', 'third-party', 'inventory', 'dependencies'):
            self.assertEqual(client.get('/legal/' + document).status_code, 200, document)
        inventory = client.get('/legal/inventory').json
        self.assertTrue(inventory['debian'])
        self.assertTrue(inventory['notices'])
        self.assertIn('flask', [d['name'].lower() for d in inventory['python']])
        with zipfile.ZipFile(io.BytesIO(client.get('/legal/dependencies').data)) as archive:
            for name, digest in inventory['notices'].items():
                self.assertEqual(hashlib.sha256(archive.read(name)).hexdigest(), digest)

    def test_missing_or_wrong_bundle_never_reads_live_workspace(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(app.config, SOURCE_BUNDLE_DIR=tmp):
            client = app.test_client()
            self.assertEqual(client.get('/source').status_code, 503)
            self.assertIn(b'unavailable', client.get('/about').data)
            (Path(tmp) / 'source-manifest.json').write_text(json.dumps({'version': '0.0.0'}))
            self.assertEqual(client.get('/legal/licence').status_code, 503)
            self.assertEqual(client.get('/legal/unknown').status_code, 404)
            self.assertEqual(client.get('/legal/../../data/rounded.sqlite').status_code, 404)

    def test_help_uses_build_revision_or_matching_channel(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(app.config, SOURCE_BUNDLE_DIR=tmp):
            client = app.test_client()
            channel = 'beta' if '-beta.' in VERSION else 'main'
            self.assertIn('/blob/' + channel + '/', client.get('/help').location)
            (Path(tmp) / 'source-manifest.json').write_text(json.dumps({'version': VERSION, 'revision': 'b' * 40}))
            self.assertIn('/blob/' + 'b' * 40 + '/', client.get('/help').location)
