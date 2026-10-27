"""Build the pinned SQLite shared library; never touch application data.

Checksums: https://www.sqlite.org/download.html and releaselog/3_54_1.html.
The source archive, notices and exact compiler arguments accompany the image.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import time
from urllib.request import urlopen
import zipfile

VERSION = '3.54.1'
SOURCE_ID = '2026-10-16 14:45:20 555e07ef33f69a0957d24d8e555b702464a131d6f1607f4c3c1e4551e8e6ca76'
ARCHIVE = 'sqlite-amalgamation-3540100.zip'
URL = 'https://www.sqlite.org/2026/' + ARCHIVE
ARCHIVE_SHA3 = '92281c86e2957f9b9305890f9ac04204caa7b677cc868dc326d942689df28e30'
SOURCE_SHA3 = 'e2b869d3003b33c942b7dd7063604fbc53553e1b66609570df39b9b7b558ee81'
OPTIONS = ['SQLITE_THREADSAFE=1', 'SQLITE_ENABLE_COLUMN_METADATA',
           'SQLITE_ENABLE_FTS5', 'SQLITE_ENABLE_RTREE', 'SQLITE_ENABLE_MATH_FUNCTIONS',
           'SQLITE_ENABLE_DBSTAT_VTAB', 'SQLITE_ENABLE_UNLOCK_NOTIFY',
           'SQLITE_SECURE_DELETE', 'SQLITE_USE_URI=1']


def verified_source(payload):
    if hashlib.sha3_256(payload).hexdigest() != ARCHIVE_SHA3:
        raise ValueError('SQLite source archive checksum mismatch')
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        # Read named members, never extract paths supplied by an archive.
        source = archive.read('sqlite-amalgamation-3540100/sqlite3.c')
    if hashlib.sha3_256(source).hexdigest() != SOURCE_SHA3:
        raise ValueError('SQLite C source checksum mismatch')
    return source


def build(output, archive_path=None):
    if archive_path:
        payload = archive_path.read_bytes()
    else:
        for attempt in range(3):
            try:
                with urlopen(URL, timeout=60) as response:
                    payload = response.read(8 * 1024 * 1024)
                break
            except OSError:
                if attempt == 2:
                    raise
                time.sleep(attempt + 1)
    source = verified_source(payload)
    library = output / 'lib' / 'libsqlite3.so.0'
    share = output / 'share'
    library.parent.mkdir(parents=True, exist_ok=True)
    share.mkdir(parents=True, exist_ok=True)
    command = ['cc', '-O2', '-fPIC', '-shared', '-Wl,-soname,libsqlite3.so.0',
               *['-D' + option for option in OPTIONS],
               '-o', str(library.resolve()), 'sqlite3.c', '-lm', '-ldl', '-pthread']
    with tempfile.TemporaryDirectory(prefix='sqlite-build-') as folder:
        (Path(folder) / 'sqlite3.c').write_bytes(source)
        subprocess.run(command, cwd=folder, check=True)
    manifest = dict(name='sqlite', version=VERSION, source_id=SOURCE_ID,
                    source_url=URL, source_archive=ARCHIVE,
                    source_sha3_256=SOURCE_SHA3, archive_sha3_256=ARCHIVE_SHA3,
                    library_sha256=hashlib.sha256(library.read_bytes()).hexdigest(),
                    compiler=subprocess.check_output(['cc', '--version'], text=True).splitlines()[0],
                    build_command=command, licence='Public domain')
    (share / ARCHIVE).write_bytes(payload)
    (share / 'sqlite-runtime.json').write_text(json.dumps(manifest, indent=2) + '\n')
    (share / 'NOTICE.txt').write_text('SQLite ' + VERSION + '\nPublic domain.\n'
                                    'https://www.sqlite.org/copyright.html\n' + URL + '\n')
    print('Built SQLite', VERSION)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--archive', type=Path)
    args = parser.parse_args()
    build(args.output, args.archive)
