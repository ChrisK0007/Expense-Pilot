"""Parse untrusted receipts in a resource-bounded Linux child, never a web thread."""
import json
import subprocess
import sys
from pathlib import Path
from threading import BoundedSemaphore

_slots = BoundedSemaphore(2)


def inspect_pdf(data, extract=False):
    if not data or len(data) > 12 * 1024 * 1024:
        raise ValueError('Use a PDF no larger than 12 MB.')
    if not _slots.acquire(blocking=False):
        raise ValueError('Receipt processing is busy. Please retry shortly.')
    try:
        result = subprocess.run([sys.executable, str(Path(__file__).resolve()), 'text' if extract else 'pages'],
                                input=data, capture_output=True, timeout=15, check=True)
        return json.loads(result.stdout)
    except (subprocess.SubprocessError, ValueError, OSError):
        raise ValueError('This PDF could not be processed safely. Use an unencrypted PDF of 1–8 pages or upload a receipt photo.') from None
    finally:
        _slots.release()


if __name__ == '__main__':
    import io
    import resource
    resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_CPU, (8, 8))
    from pypdf import PdfReader
    data = sys.stdin.buffer.read(12 * 1024 * 1024 + 1)
    if len(data) > 12 * 1024 * 1024: raise ValueError('size')
    pdf = PdfReader(io.BytesIO(data))
    if pdf.is_encrypted: raise ValueError('encrypted')
    count = len(pdf.pages)
    if not 1 <= count <= 8: raise ValueError('pages')
    text = ''
    if sys.argv[1] == 'text':
        for page in pdf.pages:
            text += (page.extract_text() or '')[:24000-len(text)] + '\n'
            if len(text) >= 24000: break
    print(json.dumps(dict(pages=count, text=text[:24000])))
