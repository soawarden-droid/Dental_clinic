# Native, replaceable shared libraries. Omit unused GPL-only Qt plugins/modules.
import sys
from PyInstaller.utils.hooks import collect_submodules

a = Analysis(
    ['main.py'], pathex=['.'], binaries=[],
    datas=[('assets','assets'),('docs/USER_GUIDE.md','docs'),('docs/USER_GUIDE.fa_AF.md','docs'),('docs/ATTRIBUTION.md','docs'),('LICENSE','.')],
    hiddenimports=collect_submodules('jdatetime'),
    excludes=['PySide6.QtPdf','PySide6.QtVirtualKeyboard','PySide6.QtQuick','PySide6.QtQml','PySide6.QtWebEngineCore'],
)
blocked=('qt6pdf','qt6virtualkeyboard','qt6qml','qt6quick','qtvirtualkeyboardplugin','qpdf.','qvnc.')
a.binaries=[entry for entry in a.binaries if not any(word in entry[0].lower() for word in blocked)]
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='faramarz-dental',debug=False,bootloader_ignore_signals=False,strip=False,upx=False,console=False,icon='assets/clinic.ico' if sys.platform=='win32' else None)
coll=COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='faramarz-dental')
