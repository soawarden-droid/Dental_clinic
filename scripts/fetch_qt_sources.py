"""Fetch exact unmodified LGPL library sources for companion distribution."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import urllib.request
import hashlib
root=Path('dist/third-party-sources');root.mkdir(parents=True,exist_ok=True)
urls=[f'https://download.qt.io/archive/qt/6.8/6.8.3/submodules/{module}-everywhere-src-6.8.3.tar.xz' for module in ('qtbase','qtimageformats','qtsvg','qtwayland')]
urls+=['https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.8.3-src/pyside-setup-everywhere-src-6.8.3.tar.xz']
def fetch(url):
    target=root/url.rsplit('/',1)[1]
    if not target.exists():urllib.request.urlretrieve(url,target)
    with target.open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
    return f'{digest}  {target.name}'
with ThreadPoolExecutor(max_workers=3) as pool:results=list(pool.map(fetch,urls))
(root/'SHA256SUMS').write_text('\n'.join(results)+'\n')
(root/'README.txt').write_text('Unmodified corresponding Qt/PySide 6.8.3 source for the replaceable shared libraries included with Faramarz Dental Clinic.\n'+ '\n'.join(urls)+'\n\nExtract and follow the included Qt/PySide build documentation. Use matching Python 3.12 and the same operating system/architecture. Replace matching shared libraries in the application _internal/PySide6 directory; no application signature or online activation prevents replacement. Keep the original installation as a recovery copy. The complete application source and build specification are delivered separately.\n')
print('\n'.join(results))
