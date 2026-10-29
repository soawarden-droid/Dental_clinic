#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
.venv/bin/python -m PyInstaller --noconfirm --clean faramarz.spec
stage=build/deb
rm -rf "$stage"
mkdir -p "$stage/opt/faramarz-dental" "$stage/usr/bin" "$stage/usr/share/applications" "$stage/usr/share/icons/hicolor/scalable/apps" "$stage/DEBIAN"
cp -a dist/faramarz-dental/. "$stage/opt/faramarz-dental/"
ln -s /opt/faramarz-dental/faramarz-dental "$stage/usr/bin/faramarz-dental"
cp assets/clinic.svg "$stage/usr/share/icons/hicolor/scalable/apps/faramarz-dental.svg"
cat > "$stage/usr/share/applications/faramarz-dental.desktop" <<'DESKTOP'
[Desktop Entry]
Type=Application
Name=Faramarz Dental Clinic
Name[fa_AF]=کلینیک دندان فرامرز
Comment=Offline dental clinic records
Exec=/opt/faramarz-dental/faramarz-dental
Icon=faramarz-dental
Categories=Office;MedicalSoftware;
Terminal=false
DESKTOP
cat > "$stage/DEBIAN/control" <<'CONTROL'
Package: faramarz-dental
Version: 0.2.0
Architecture: amd64
Maintainer: Faramarz Dental Clinic
Depends: libc6 (>= 2.39), libgl1, libegl1, libxkbcommon0, libxkbcommon-x11-0, libxcb-cursor0, libxcb-icccm4, libxcb-keysyms1, libxcb-shape0, libxcb-xinerama0, libxcb-randr0, libxcb-render-util0, libxcb-image0, libfontconfig1, libdbus-1-3
Description: Offline dental records, appointments and billing
 Native desktop application with embedded SQLite and local backups.
CONTROL
chmod -R go-w "$stage"
dpkg-deb --root-owner-group -Zxz -z3 --threads-max=2 --build "$stage" dist/faramarz-dental_0.2.0_amd64.deb
