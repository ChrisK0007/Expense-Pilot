"""Bounded local previews and text extraction. Never execute document content."""
import base64
import io
import json
from pathlib import Path
import subprocess
import sys
from threading import BoundedSemaphore

MAX_FILE = 10 * 1024 * 1024
MAX_TEXT = 100000
_slots = BoundedSemaphore(2)


def process(raw, extension, mode='info', page=1):
    if not raw or len(raw) > MAX_FILE:
        raise ValueError('Choose a non-empty document no larger than 10 MB.')
    if not _slots.acquire(timeout=5):
        raise ValueError('Document processing is busy. Please retry shortly.')
    try:
        result = subprocess.run([sys.executable, str(Path(__file__).resolve()), extension, mode, str(page)],
                                input=raw, capture_output=True, timeout=25, check=True)
        value = json.loads(result.stdout)
        if 'error' in value:
            raise ValueError(value['error'])
        return value
    except (subprocess.SubprocessError, OSError, json.JSONDecodeError):
        raise ValueError('This document could not be processed within the preview limits. The original is still available to download.') from None
    finally:
        _slots.release()


def office_preview(raw, extension):
    import posixpath
    import re
    import zipfile
    from xml.etree import ElementTree as ET
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        remaining = 12 * 1024 * 1024
        def xml(name):
            nonlocal remaining
            info = z.getinfo(name)
            if info.file_size > 4 * 1024 * 1024 or info.file_size > remaining:
                raise ValueError('This Office file is too complex for an in-page preview. Download the original.')
            remaining -= info.file_size
            data = z.read(name)
            if b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():
                raise ValueError('This Office file cannot be previewed.')
            return ET.fromstring(data)
        def local(tag): return tag.rsplit('}', 1)[-1]
        if extension == '.docx':
            root = xml('word/document.xml')
            paragraphs = [''.join(n.text or '' for n in p.iter() if local(n.tag) == 't')
                          for p in root.iter() if local(p.tag) == 'p']
            text = '\n'.join(paragraphs)
            return dict(kind='text', text=text[:MAX_TEXT], truncated=len(text) > MAX_TEXT,
                        notice='Text preview. Original formatting, images and page layout are available in the download.')
        shared = []
        if 'xl/sharedStrings.xml' in z.namelist():
            shared = [''.join(n.text or '' for n in item.iter() if local(n.tag) == 't')
                      for item in xml('xl/sharedStrings.xml')]
        relations = {r.attrib.get('Id'): r.attrib.get('Target', '') for r in xml('xl/_rels/workbook.xml.rels')
                     if r.attrib.get('TargetMode') != 'External'}
        sheets, truncated = [], False
        characters, total_cells = 0, 0
        for sheet in xml('xl/workbook.xml').iter():
            if local(sheet.tag) != 'sheet': continue
            if len(sheets) >= 10:
                truncated = True; break
            rid = next((v for k, v in sheet.attrib.items() if k.endswith('}id')), '')
            target = relations.get(rid, '')
            name = posixpath.normpath(target.lstrip('/') if target.startswith('/') else 'xl/' + target)
            if not name.startswith('xl/worksheets/') or not name.endswith('.xml'):
                continue
            data, cells = [], 0
            for row in xml(name).iter():
                if local(row.tag) != 'row': continue
                if len(data) >= 500 or total_cells >= 10000 or characters >= MAX_TEXT:
                    truncated = True; break
                values = []
                for cell in row:
                    if local(cell.tag) != 'c': continue
                    if total_cells >= 10000 or characters >= MAX_TEXT:
                        truncated=True;break
                    match = re.match(r'([A-Z]+)', cell.attrib.get('r', ''))
                    col = 0
                    for char in match[1] if match else '': col = col * 26 + ord(char) - 64
                    if not 1 <= col <= 50:
                        truncated = True; continue
                    while len(values) < col: values.append('')
                    nodes = {local(n.tag): n for n in cell}
                    value = nodes['v'].text or '' if 'v' in nodes else ''
                    kind = cell.attrib.get('t')
                    if kind == 's': value = shared[int(value)] if value.isdigit() and int(value) < len(shared) else ''
                    elif kind == 'inlineStr': value = ''.join(n.text or '' for n in cell.iter() if local(n.tag) == 't')
                    elif 'f' in nodes and 'v' not in nodes: value = 'Formula (not calculated): ' + (nodes['f'].text or '')
                    if len(value) > 1000: truncated = True
                    limited=value[:min(1000, MAX_TEXT-characters)]
                    if len(limited)<len(value): truncated=True
                    values[col - 1] = limited; cells += 1; total_cells += 1; characters += len(limited)
                data.append(values)
            sheets.append(dict(name=sheet.attrib.get('name', 'Sheet'), rows=data))
        return dict(kind='sheets', sheets=sheets, truncated=truncated,
                    notice='Cell-value preview. Formatting, charts and images are omitted; formula results are the values saved in the file. Dates may appear as their stored Excel numbers.')


def worker(raw, extension, mode, page):
    import tempfile
    if extension == '.pdf':
        from pypdf import PdfReader
        pdf = PdfReader(io.BytesIO(raw))
        if pdf.is_encrypted:
            raise ValueError('This PDF is password-protected. Download it to view it, or upload an unencrypted copy for preview or import.')
        count = len(pdf.pages)
        if not 1 <= count <= 500:
            raise ValueError('PDF previews and imports support 1–500 pages. Download the original for larger files.')
        if mode == 'info': return dict(kind='pdf', pages=count)
        with tempfile.TemporaryDirectory(prefix='expense-pilot-document-') as directory:
            source = Path(directory) / 'document.pdf'; source.write_bytes(raw)
            if mode == 'evidence':
                from xml.etree import ElementTree as ET
                output=Path(directory)/'words.html'
                subprocess.run(['pdftotext','-f','1','-l','20','-bbox','-enc','UTF-8',str(source),str(output)],check=True,timeout=15,capture_output=True)
                if output.stat().st_size>4*1024*1024: raise ValueError('This text layer is too large to highlight.')
                root=ET.fromstring(output.read_bytes());pages=[];count=0
                for page in root.iter():
                    if page.tag.rsplit('}',1)[-1]!='page': continue
                    words=[]
                    for word in page.iter():
                        if word.tag.rsplit('}',1)[-1]!='word': continue
                        count+=1
                        if count>20000: break
                        words.append(dict(text=word.text or '',x=float(word.attrib['xMin']),y=float(word.attrib['yMin']),right=float(word.attrib['xMax']),bottom=float(word.attrib['yMax'])))
                    pages.append(dict(width=float(page.attrib['width']),height=float(page.attrib['height']),words=words))
                return dict(pages=pages)
            if mode == 'extract':
                output = Path(directory) / 'document.txt'
                subprocess.run(['pdftotext', '-layout', '-enc', 'UTF-8', str(source), str(output)],
                               check=True, timeout=15, capture_output=True)
                if output.stat().st_size > 2 * 1024 * 1024:
                    raise ValueError('The report contains too much text to import.')
                return dict(text=output.read_text(), pages=count)
            if mode != 'page' or not 1 <= page <= count: raise ValueError('Choose a page within this document.')
            output = Path(directory) / 'page'
            subprocess.run(['pdftoppm', '-f', str(page), '-l', str(page), '-singlefile', '-scale-to', '1600',
                            '-png', str(source), str(output)], check=True, timeout=18, capture_output=True)
            return dict(image=base64.b64encode(output.with_suffix('.png').read_bytes()).decode())
    if extension in ('.png', '.jpg', '.jpeg', '.webp'):
        from PIL import Image, ImageOps
        Image.MAX_IMAGE_PIXELS = 25000000
        with Image.open(io.BytesIO(raw)) as image:
            if image.width * image.height > 25000000: raise ValueError('This image is too large to preview. Download the original.')
            if mode == 'info': return dict(kind='image', pages=1)
            if mode != 'page' or page != 1: raise ValueError('Choose page 1 for an image.')
            image = ImageOps.exif_transpose(image).convert('RGB'); image.thumbnail((1600,1600))
            output = io.BytesIO(); image.save(output, 'PNG')
            return dict(image=base64.b64encode(output.getvalue()).decode())
    if mode != 'info': raise ValueError('This document has no image pages.')
    if extension in ('.docx', '.xlsx'): return office_preview(raw, extension)
    text = raw.decode('utf-8-sig')
    if extension == '.csv':
        import csv
        try: dialect = csv.Sniffer().sniff(text[:8192], delimiters=',;\t')
        except csv.Error: dialect = csv.excel
        rows, truncated = [], False
        characters=0
        for row in csv.reader(io.StringIO(text), dialect):
            if len(rows) >= 500 or characters >= MAX_TEXT:
                truncated = True; break
            if len(row) > 50 or any(len(v) > 1000 for v in row): truncated = True
            limited=[]
            for value in row[:50]:
                part=value[:min(1000, MAX_TEXT-characters)]
                if len(part)<len(value): truncated=True
                limited.append(part);characters+=len(part)
            rows.append(limited)
        return dict(kind='sheets', sheets=[dict(name='CSV', rows=rows)], truncated=truncated, notice='CSV values; formulas are displayed as text.')
    if extension != '.txt': raise ValueError('This file type cannot be previewed.')
    return dict(kind='text', text=text[:MAX_TEXT], truncated=len(text) > MAX_TEXT, notice='')


if __name__ == '__main__':
    import resource
    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_CPU, (15, 15))
    resource.setrlimit(resource.RLIMIT_FSIZE, (16 * 1024 * 1024, 16 * 1024 * 1024))
    try:
        raw = sys.stdin.buffer.read(MAX_FILE + 1)
        if not raw or len(raw) > MAX_FILE: raise ValueError('Choose a document no larger than 10 MB.')
        result = worker(raw, sys.argv[1], sys.argv[2], int(sys.argv[3]))
        print(json.dumps(result))
    except ValueError as exc:
        print(json.dumps(dict(error=str(exc))))
    except Exception:
        print(json.dumps(dict(error='This document could not be previewed or imported. The original is still available to download.')))
