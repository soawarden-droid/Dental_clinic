"""Collect release copyright/license texts without changing binaries."""
from pathlib import Path
import tarfile
import subprocess
import shutil
import urllib.request
root=Path('assets/licenses')
for archive in Path('dist/third-party-sources').glob('*.tar.xz'):
    module=archive.name.split('-everywhere')[0].replace('pyside-setup','pyside')
    with tarfile.open(archive) as tar:
        for member in tar:
            name=Path(member.name)
            if not member.isfile() or member.size>500000:continue
            if '/LICENSES/' not in member.name and not any(term in name.name.upper() for term in ('LICENSE','COPYING','COPYRIGHT')):continue
            relative=Path(*name.parts[1:])
            if '..' in relative.parts:continue
            dest=root/'qt-source-notices'/module/relative
            dest.parent.mkdir(parents=True,exist_ok=True)
            with tar.extractfile(member) as f:dest.write_bytes(f.read())
for name in ['python3.12','libpython3.12-stdlib','libpython3.12']:
    source=Path('/usr/share/doc')/name/'copyright'
    if source.exists():shutil.copyfile(source,root/(name+'-copyright.txt'))
system=root/'system-libraries';system.mkdir(exist_ok=True)
for binary in Path('dist/faramarz-dental/_internal').glob('*.so*'):
    library=Path('/lib/x86_64-linux-gnu')/binary.name
    if not library.exists():continue
    result=subprocess.run(['dpkg-query','-S',str(library.resolve())],capture_output=True,text=True)
    if result.returncode:continue
    package=result.stdout.split(': /')[0].split(':')[0]
    source=Path('/usr/share/doc')/package/'copyright'
    if source.exists():shutil.copyfile(source,system/(package+'.txt'))
url='https://raw.githubusercontent.com/unicode-org/icu/release-73-2/icu4c/LICENSE'
try:(root/'ICU-73.2-LICENSE.txt').write_bytes(urllib.request.urlopen(url,timeout=30).read())
except Exception:
    url='https://raw.githubusercontent.com/unicode-org/icu/release-73-2/LICENSE'
    (root/'ICU-73.2-LICENSE.txt').write_bytes(urllib.request.urlopen(url,timeout=30).read())
print('Collected',len(list(root.rglob('*'))),'notice entries')
