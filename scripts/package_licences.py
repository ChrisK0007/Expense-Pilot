"""Capture the actual image's dependency versions and bundled licence notices."""
import hashlib
from importlib import metadata
import json
from pathlib import Path
import platform
import subprocess
import sys
import sysconfig
from urllib.parse import quote
import zipfile


def collect(output):
    output.mkdir(parents=True, exist_ok=True)
    inventory = {'python_version': platform.python_version(), 'python': [], 'debian': [], 'notices': {}}
    with zipfile.ZipFile(output / 'dependency-notices.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
        def notice(name, path):
            if not path.is_file():
                return
            data = path.read_bytes()
            archive.writestr(name, data)
            inventory['notices'][name] = hashlib.sha256(data).hexdigest()

        for dist in sorted(metadata.distributions(), key=lambda d: d.metadata['Name'].lower()):
            name, version = dist.metadata['Name'], dist.version
            entry = {'name': name, 'version': version,
                     'licence': dist.metadata.get('License-Expression') or dist.metadata.get('License') or 'See bundled notices',
                     'upstream': f'https://pypi.org/project/{quote(name)}/{quote(version)}/', 'notices': []}
            for file in dist.files or []:
                # Includes vendored library/font notices, not just .dist-info metadata.
                if any(word in file.name.lower() for word in ('license', 'licence', 'copyright', 'notice')):
                    dest = f'python/{name}/{str(file).replace("../", "").lstrip("/")}'
                    notice(dest, Path(dist.locate_file(file)))
                    if dest in inventory['notices']:
                        entry['notices'].append(dest)
            inventory['python'].append(entry)
        fields = '${binary:Package}\t${Version}\t${source:Package}\t${source:Version}\n'
        for line in subprocess.check_output(['dpkg-query', '-W', '-f=' + fields], text=True).splitlines():
            name, version, source, source_version = line.split('\t')
            source, source_version = source or name.split(':')[0], source_version or version
            dest = f'debian/{name}/copyright'
            notice(dest, Path('/usr/share/doc') / name.split(':')[0] / 'copyright')
            inventory['debian'].append({'name': name, 'version': version, 'source': source,
                'source_version': source_version, 'notice': dest if dest in inventory['notices'] else None,
                'source_lookup': f'https://snapshot.debian.org/package/{quote(source)}/{quote(source_version, safe="")}/'})
        for path in sorted(Path('/usr/share/common-licenses').glob('*')):
            notice('debian/common-licenses/' + path.name, path)
        notice('python/stdlib/LICENSE.txt', Path(sysconfig.get_path('stdlib')) / 'LICENSE.txt')
        archive.writestr('dependency-inventory.json', json.dumps(inventory, indent=2) + '\n')
    (output / 'dependency-inventory.json').write_text(json.dumps(inventory, indent=2) + '\n')


if __name__ == '__main__':
    collect(Path(sys.argv[1]))
