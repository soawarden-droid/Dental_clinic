"""Install a built Linux bundle per user, overriding stale system shortcuts.

Does not open or migrate clinic records. Close the app and reopen afterward.
"""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


def install(bundle,base=None):
    bundle=Path(bundle).resolve();home=Path(base or Path.home())
    binary=bundle/'faramarz-dental'
    if not binary.is_file():raise ValueError('Build the Ubuntu application bundle first')
    result=subprocess.run([str(binary),'--version'],capture_output=True,text=True,check=True)
    version=result.stdout.strip().split()[-1]
    if not version or any(c not in '0123456789.' for c in version):raise ValueError('Invalid application version')
    parent=home/'.local/opt/faramarz-dental';parent.mkdir(parents=True,exist_ok=True)
    target=parent/version
    if not target.exists():
        with tempfile.TemporaryDirectory(dir=parent,prefix='install-') as temp:
            stage=Path(temp)/version;shutil.copytree(bundle,stage,symlinks=True);stage.rename(target)
    # A running older version keeps its files; switch future launches atomically.
    temporary=parent/'current-next';temporary.unlink(missing_ok=True);temporary.symlink_to(version,target_is_directory=True);os.replace(temporary,parent/'current')
    current=parent/'current';applications=home/'.local/share/applications';applications.mkdir(parents=True,exist_ok=True)
    desktop=applications/'faramarz-dental.desktop'
    desktop.write_text('[Desktop Entry]\nType=Application\nName=Faramarz Dental Clinic\nName[fa_AF]=کلینیک دندان فرامرز\nComment=Offline dental clinic records\nExec="'+str(current/'faramarz-dental')+'"\nTryExec='+str(current/'faramarz-dental')+'\nIcon='+str(current/'_internal/assets/clinic.svg')+'\nCategories=Office;Science;MedicalSoftware;\nTerminal=false\n',encoding='utf-8');desktop.chmod(0o755)
    bins=home/'.local/bin';bins.mkdir(parents=True,exist_ok=True);shortcut=bins/'faramarz-dental'
    if shortcut.is_symlink() or not shortcut.exists():shortcut.unlink(missing_ok=True);shortcut.symlink_to(current/'faramarz-dental')
    if shutil.which('update-desktop-database'):subprocess.run(['update-desktop-database',str(applications)],check=True)
    print('Installed',version,'at',target)
    print('Close any open clinic window, then use Faramarz Dental Clinic in Applications.')
    return target


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('bundle',nargs='?',default='dist/faramarz-dental');args=parser.parse_args();install(args.bundle)
