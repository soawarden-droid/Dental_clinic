$ErrorActionPreference = 'Stop'
python -m pip install -r requirements.lock
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
python -m pip check
if ($LASTEXITCODE -ne 0) { throw 'Dependency graph failed' }
python -m pytest -q
if ($LASTEXITCODE -ne 0) { throw 'Tests failed' }
python -m PyInstaller --noconfirm --clean faramarz.spec
if ($LASTEXITCODE -ne 0) { throw 'Application build failed' }
& "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" scripts/windows.iss
if ($LASTEXITCODE -ne 0) { throw 'Installer compilation failed' }
