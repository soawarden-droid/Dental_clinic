# Assets and dependency notices

The clinic icon and interface were created in this repository and are covered by the project MIT license. No doctor photographs, credentials, or patient records are supplied. Demonstration records are fictional and isolated from the normal profile.

Apexo's manual was read only as workflow inspiration: https://github.com/elselawi/apexo/blob/main/manual.md. No Apexo source code, assets, database, or license-covered implementation was copied. The older sibling project was left untouched.

Bundled fonts:

- Noto Sans and Noto Sans Arabic, Google/Noto contributors, SIL Open Font License 1.1. Full distribution notices: `assets/Noto-LICENSE.txt`.
- DejaVu Sans, DejaVu contributors / Bitstream, permissive font license. Full notices: `assets/DejaVu-LICENSE.txt`.

Runtime:

- CPython 3.12, Python Software Foundation license; SQLite public domain. https://www.python.org/psf/license/ and https://www.sqlite.org/copyright.html
- Qt and PySide6 6.8.3: LGPLv3/GPL/commercial licensing, used as dynamically loaded shared libraries. This project elects the LGPLv3 option for the included LGPL modules. Qt libraries remain replaceable in the `_internal/PySide6` directory. No static linking. User modification and reverse engineering for debugging modifications to these libraries is permitted. Qt/PySide source for this exact release is available at https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.8.3-src/ and https://download.qt.io/archive/qt/6.8/6.8.3/submodules/ . LGPL text: `assets/licenses/LGPL-3.0.txt`. PySide wheel notices are also included under `_internal/PySide6` where supplied by its packaging.
- jdatetime 5.2.0 and jalali-core 1.0.0: PSF license. https://github.com/slashmili/python-jdatetime and https://github.com/jalali/jalali-core
- PyInstaller 6.12.0 bootloader: GPLv2 with bootloader exception permitting distribution of bundled applications. https://pyinstaller.org/en/v6.12.0/license.html

Build and test dependency versions, including transitive dependencies, are recorded in `requirements.lock`. This is an offline runtime; downloads are needed only for developer dependency installation and builds on a new machine. Packaging bundles the interpreter, Qt shared libraries and platform plugins, both calendars, fonts and application assets.

The release companion directory `dist/third-party-sources/` supplies complete unmodified Qt Base, Qt SVG, Qt Image Formats, Qt Wayland and PySide 6.8.3 source archives, with SHA-256 checksums and replacement instructions. Keep these alongside binary redistribution. `scripts/fetch_qt_sources.py` reproduces the source bundle. Full license/copyright texts extracted from those exact sources, Python package distributions, ICU 73.2, and available system-library notices are included in `assets/licenses/`. The runtime needs no source downloads or online license checks.
