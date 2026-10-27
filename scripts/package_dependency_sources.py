"""Retain exact dependency sources at build time, independently of upstream retention.

Run in a disposable build stage derived from the runtime dependency stage.
Never run against a workspace data directory. Missing sources fail the build.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sysconfig
import tempfile
import time
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen
import zipfile


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def download(url, path, expected=None):
    if urlparse(url).scheme != 'https':
        raise ValueError('Source downloads require HTTPS')
    path.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(3):
        try:
            with urlopen(Request(url, headers={'User-Agent': 'Expense-Pilot-source-packager'}), timeout=120) as source, path.open('wb') as target:
                while block := source.read(1024 * 1024):
                    target.write(block)
            break
        except OSError:
            if attempt == 2:
                raise
            time.sleep(2 * (attempt + 1))
    if not path.stat().st_size or expected and digest(path) != expected:
        raise ValueError(f'Source checksum mismatch: {path.name}')


def enable_debian_sources():
    enabled = False
    for path in Path('/etc/apt/sources.list.d').glob('*.sources'):
        content = path.read_text()
        content, count = re.subn(r'^Types: deb$', 'Types: deb deb-src', content, flags=re.M)
        if count:
            path.write_text(content)
            enabled = True
    if not enabled:
        raise RuntimeError('Expected Debian deb822 binary sources; update the source collector for this base image')
    subprocess.run(['apt-get', 'update'], check=True)


def verify_archive(archive_path, manifest):
    """Stream verification; the source archive can be larger than available RAM."""
    with zipfile.ZipFile(archive_path) as archive:
        expected = set(manifest['files']) | {'dependency-sources-manifest.json'}
        if set(archive.namelist()) != expected:
            raise ValueError('Dependency source archive inventory mismatch')
        for name, checksum in manifest['files'].items():
            with archive.open(name) as stream:
                if hashlib.file_digest(stream, 'sha256').hexdigest() != checksum:
                    raise ValueError(f'Dependency source archive checksum mismatch: {name}')


def retain_sqlite(inventory, root, manifest, share=Path('/opt/sqlite/share')):
    for package in inventory.get('native', []):
        if package['name'] != 'sqlite':
            raise RuntimeError('Unknown native dependency requires source collection support')
        filename = package['source_archive']
        if Path(filename).name != filename:
            raise ValueError('Invalid SQLite source filename')
        source = share / filename
        with source.open('rb') as stream:
            checksum = hashlib.file_digest(stream, 'sha3_256').hexdigest()
        if checksum != package['archive_sha3_256']:
            raise ValueError('SQLite retained source checksum mismatch')
        folder = root / 'native' / 'sqlite'
        folder.mkdir(parents=True)
        for filename in (filename, 'NOTICE.txt', 'sqlite-runtime.json'):
            shutil.copyfile(share / filename, folder / filename)
        manifest['additional'].append(dict(name='sqlite', version=package['version'],
                                          url=package['source_url'], directory='native/sqlite'))


def collect(inventory_path, output):
    inventory = json.loads(inventory_path.read_text())
    manifest = {'format': 1, 'debian': [], 'python': [], 'additional': [], 'files': {}}
    output.mkdir(parents=True, exist_ok=True)
    enable_debian_sources()
    with tempfile.TemporaryDirectory(prefix='dependency-sources-') as temp:
        root = Path(temp)
        retain_sqlite(inventory, root, manifest)
        # Each .dsc plus its upstream tarball and Debian patches is retained.
        # apt authenticates source indexes and verifies the downloaded hashes.
        sources = sorted({(p['source'], p['source_version']) for p in inventory['debian']})
        for name, version in sources:
            folder = root / 'debian' / name
            folder.mkdir(parents=True)
            subprocess.run(['apt-get', 'source', '--download-only', '--only-source',
                            '-o', 'APT::Sandbox::User=root', f'{name}={version}'], cwd=folder, check=True)
            if not list(folder.glob('*.dsc')) or len(list(folder.iterdir())) < 2:
                raise RuntimeError(f'Incomplete Debian source: {name} {version}')
            manifest['debian'].append({'name': name, 'version': version,
                                       'directory': str(folder.relative_to(root))})

        for package in inventory['python']:
            name, version = package['name'], package['version']
            metadata_path = root / 'python' / name / 'pypi.json'
            download(f'https://pypi.org/pypi/{quote(name)}/{quote(version)}/json', metadata_path)
            info = json.loads(metadata_path.read_text())
            sdists = [entry for entry in info['urls'] if entry['packagetype'] == 'sdist']
            if len(sdists) != 1:
                raise RuntimeError(f'Expected one source distribution for {name} {version}')
            source = sdists[0]
            filename = source['filename']
            if Path(filename).name != filename:
                raise ValueError('Invalid upstream filename')
            download(source['url'], metadata_path.parent / filename, source['digests']['sha256'])
            manifest['python'].append({'name': name, 'version': version,
                                       'file': str((metadata_path.parent / filename).relative_to(root))})

        python_version = os.environ['PYTHON_VERSION']
        if python_version != inventory['python_version']:
            raise RuntimeError('CPython source does not match the installed runtime')
        python_file = f'Python-{python_version}.tar.xz'
        download(f'https://www.python.org/ftp/python/{python_version}/{python_file}',
                 root / 'cpython' / python_file, os.environ['PYTHON_SHA256'])
        (root / 'cpython' / 'configure-arguments.txt').write_text(str(sysconfig.get_config_var('CONFIG_ARGS')) + '\n')

        # Pillow wheels can contain an LGPL FriBiDi library outside dpkg's inventory.
        # Identify the actual loaded library rather than assuming a wheel version.
        from PIL import features
        pillow_features = {name: features.version(name) for name in features.get_supported()}
        manifest['pillow_features'] = pillow_features
        if features.check_feature('libimagequant'):
            raise RuntimeError('A new GPL libimagequant wheel requires a source review before publication')
        if features.check_feature('fribidi'):
            version = features.version_feature('fribidi')
            if not version or not re.fullmatch(r'\d+\.\d+\.\d+', version):
                raise RuntimeError('Cannot identify the exact FriBiDi version')
            url = f'https://github.com/fribidi/fribidi/releases/download/v{version}/fribidi-{version}.tar.xz'
            download(url, root / 'native' / f'fribidi-{version}.tar.xz')
            manifest['additional'].append({'name': 'fribidi', 'version': version, 'url': url})

        (root / 'README.txt').write_text('''Dependency sources for the accompanying Expense Pilot image.

debian/: exact source packages for every installed Debian binary package.
Run dpkg-source -x package.dsc, then follow debian/rules and debian/control
inside the extracted source. The upstream source, Debian patches and packaging
build instructions are retained together. Build dependencies are listed there.

python/: exact PyPI source distributions, including their build configuration.
Install in a compatible Python environment with pip install <source archive>.
Original wheel notices, including permissively licensed bundled libraries, are
in dependency-notices.zip. cryptography's optional native OpenSSL components
retain their upstream Apache/OpenSSL notices. No project patches are applied.

cpython/: matching CPython source and the runtime's configure arguments.
Follow its README build instructions. The application Dockerfile is in the
separate application-source.zip; it records installation and startup commands.

native/sqlite/: the checksum-verified SQLite amalgamation used by Python,
plus its version, source ID and exact compiler command in sqlite-runtime.json.
scripts/build_sqlite.py in application-source.zip reproduces this build.

native/: matching upstream FriBiDi source when Pillow loads this LGPL library.
Follow its README/INSTALL. Pillow source contains its Raqm integration and
build configuration. You may rebuild the image with modified dependencies;
there are no signature or licence-key restrictions on running modified images.

This archive is build-time software material only. It contains no user data.
Keep it with the exact image and accompanying manifests when redistributing.
''')
        for path in sorted(root.rglob('*')):
            if path.is_file():
                manifest['files'][str(path.relative_to(root))] = digest(path)
        archive_path = output / 'dependency-sources.zip'
        # Upstream tarballs are already compressed. Storing avoids expensive recompression.
        with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_STORED, allowZip64=True) as archive:
            for name in manifest['files']:
                archive.write(root / name, name)
            archive.writestr('dependency-sources-manifest.json', json.dumps(manifest, indent=2) + '\n')
        verify_archive(archive_path, manifest)
    manifest['archive_sha256'] = digest(archive_path)
    manifest['archive_bytes'] = archive_path.stat().st_size
    (output / 'dependency-sources-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(f"Retained {len(sources)} Debian and {len(inventory['python'])} Python source packages; {archive_path.stat().st_size} bytes")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('inventory', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    collect(args.inventory, args.output)
