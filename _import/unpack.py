#!/usr/bin/env python3
import base64,hashlib,json,io,zipfile,pathlib,shutil,sys
root=pathlib.Path(__file__).resolve().parents[1]
imp=root/'_import'
meta=json.loads((imp/'MANIFEST.json').read_text())
b64=''.join((imp/f'part_{i:03d}.txt').read_text().strip() for i in range(meta['n_parts']))
assert len(b64)==meta['b64_len'], (len(b64), meta['b64_len'])
raw=base64.b64decode(b64)
assert hashlib.sha256(raw).hexdigest()==meta['zip_sha256']
with zipfile.ZipFile(io.BytesIO(raw)) as zf:
    zf.extractall(root)
print('unpacked', meta['zip_bytes'], 'ok')
