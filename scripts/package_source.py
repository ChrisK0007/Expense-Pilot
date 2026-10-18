"""Bundle build inputs, never Git history or live workspace data."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import zipfile

ROOT_FILES = {'Dockerfile', '.dockerignore', '.env.example', 'LICENSE', 'COPYRIGHT',
              'THIRD_PARTY_NOTICES.md', 'README.md', 'CONTRIBUTING.md', 'SUPPORT.md',
              'SECURITY.md', 'prepare.sh', 'backup.sh', 'compose.yaml',
              'compose.public.yaml', 'compose.registry.yaml', 'ca_profile.xml'}
DIRECTORIES = {'server', 'scripts', 'tests', 'docs', 'deploy', '.github'}
PRIVATE_PARTS = {'.git', '.env', '__pycache__', 'data', 'uploads', 'receipts', 'backups', 'node_modules'}
PRIVATE_SUFFIXES = {'.pyc', '.db', '.sqlite', '.sqlite3', '.pem', '.key', '.log', '.zip'}


def source_files(root):
    for path in sorted(root.rglob('*')):
        relative = path.relative_to(root)
        if any(part in PRIVATE_PARTS or part.startswith('.env.') and part != '.env.example'
               for part in relative.parts) or path.suffix.lower() in PRIVATE_SUFFIXES:
            continue
        if len(relative.parts) == 1:
            allowed = relative.name in ROOT_FILES
        else:
            allowed = relative.parts[0] in DIRECTORIES
        if not allowed:
            continue
        if path.is_symlink():
            raise ValueError(f'Symlinks are not allowed in the source bundle: {relative}')
        if path.is_file():
            yield relative.as_posix(), path


def package(root, output, revision='unknown'):
    if revision != 'unknown' and not re.fullmatch(r'[0-9a-f]{40}', revision):
        raise ValueError('SOURCE_REVISION must be a full Git commit SHA or unknown')
    version = (root / 'server/VERSION').read_text().strip()
    if not re.fullmatch(r'\d+\.\d+\.\d+(?:-beta\.\d+)?', version):
        raise ValueError('Invalid application version')
    output.mkdir(parents=True, exist_ok=True)
    manifest = {'version': version, 'revision': revision, 'files': {}}
    with zipfile.ZipFile(output / 'application-source.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, path in source_files(root):
            content = path.read_bytes()
            manifest['files'][name] = hashlib.sha256(content).hexdigest()
            info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            info.external_attr = (0o100755 if path.stat().st_mode & 0o111 else 0o100644) << 16
            archive.writestr(info, content, compress_type=zipfile.ZIP_DEFLATED)
        archive.writestr('SOURCE_MANIFEST.json', json.dumps(manifest, indent=2) + '\n')
    manifest['archive_sha256'] = hashlib.sha256((output / 'application-source.zip').read_bytes()).hexdigest()
    (output / 'source-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--revision', default='unknown')
    args = parser.parse_args()
    package(args.root.resolve(), args.output.resolve(), args.revision)
