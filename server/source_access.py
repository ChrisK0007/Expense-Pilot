"""Public access to immutable build-time source and notices; never archive /data."""
import json
from pathlib import Path
import re
from flask import abort, redirect, render_template, send_file

FILES = {
    'source': ('application-source.zip', 'application/zip'),
    'manifest': ('source-manifest.json', 'application/json'),
    'licence': ('LICENSE', 'text/plain'),
    'copyright': ('COPYRIGHT', 'text/plain'),
    'third-party': ('THIRD_PARTY_NOTICES.md', 'text/plain'),
    'dependencies': ('dependency-notices.zip', 'application/zip'),
    'inventory': ('dependency-inventory.json', 'application/json'),
}


def register(app, version):
    app.config.setdefault('SOURCE_BUNDLE_DIR', str(Path(__file__).parent / 'legal'))

    def directory():
        return Path(app.config['SOURCE_BUNDLE_DIR'])

    def manifest():
        try:
            result = json.loads((directory() / 'source-manifest.json').read_text())
            return result if result.get('version') == version else {}
        except (OSError, ValueError):
            return {}

    @app.get('/about')
    def source_about():
        return render_template('source.html', version=version,
                               available=bool(manifest()) and (directory() / FILES['source'][0]).is_file())

    @app.get('/source')
    def source_download():
        return legal_download('source')

    @app.get('/legal/<document>')
    def legal_download(document):
        if document not in FILES:
            abort(404)
        if not manifest():
            abort(503, description='Source and licence downloads are unavailable for this build.')
        filename, mime = FILES[document]
        path = directory() / filename
        if not path.is_file() or path.is_symlink():
            abort(503, description='This build does not contain the requested document.')
        return send_file(path, mimetype=mime, as_attachment=document in ('source', 'dependencies'),
                         download_name=f'expense-pilot-{version}-{filename}', conditional=True)

    @app.get('/help')
    def installation_help():
        revision = manifest().get('revision', '')
        ref = revision if re.fullmatch(r'[0-9a-f]{40}', revision) else ('beta' if '-beta.' in version else 'main')
        return redirect(f'https://github.com/ChrisK0007/Expense-Pilot/blob/{ref}/docs/public-release.md')
