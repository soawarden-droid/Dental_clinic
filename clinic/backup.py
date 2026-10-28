"""Versioned, checksummed archives. Database snapshots use SQLite backup()."""
from pathlib import Path
import sqlite3
import json
import hashlib
import tempfile
import zipfile
import os
import shutil
from datetime import datetime
from .schema import MIGRATIONS

MAX_BYTES = 8 * 1024**3


def digest(path):
    with open(path,'rb') as f:
        return hashlib.file_digest(f,'sha256').hexdigest()


def create_backup(root, destination):
    root, destination = Path(root), Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / ('Faramarz-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'.fdbackup')
    with tempfile.TemporaryDirectory() as temp:
        stage = Path(temp)
        src = sqlite3.connect(root/'clinic.sqlite')
        out = sqlite3.connect(stage/'clinic.sqlite')
        try:
            src.backup(out)
        finally:
            out.close(); src.close()
        db = sqlite3.connect(stage/'clinic.sqlite')
        try:
            attachments = db.execute('SELECT stored,sha256 FROM attachments').fetchall()
            version = db.execute('PRAGMA user_version').fetchone()[0]
        finally:
            db.close()
        for name, expected in attachments:
            if Path(name).name!=name:
                raise ValueError('Invalid attachment path')
            dest = stage/'attachments'/name
            dest.parent.mkdir(exist_ok=True)
            shutil.copyfile(root/'attachments'/name,dest)
            if digest(dest)!=expected:
                raise ValueError('An attachment changed or is damaged')
        files = {str(p.relative_to(stage)).replace('\\','/'):digest(p) for p in stage.rglob('*') if p.is_file()}
        (stage/'manifest.json').write_text(json.dumps({'format':1,'schema':version,'created':datetime.now().isoformat(),'files':files},indent=2))
        temporary = target.with_suffix('.partial')
        try:
            with zipfile.ZipFile(temporary,'w',zipfile.ZIP_DEFLATED) as z:
                for p in stage.rglob('*'):
                    if p.is_file():
                        z.write(p,str(p.relative_to(stage)))
            os.chmod(temporary,0o600)
            os.replace(temporary,target)
        finally:
            temporary.unlink(missing_ok=True)
    return target


def validate_backup(archive, stage):
    stage = Path(stage)
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        if len(set(names))!=len(names) or sum(i.file_size for i in z.infolist())>MAX_BYTES:
            raise ValueError('Invalid or oversized backup')
        for name in names:
            p = Path(name)
            if p.is_absolute() or '..' in p.parts or '\\' in name or ':' in name:
                raise ValueError('Unsafe backup path')
        manifest = json.loads(z.read('manifest.json'))
        if manifest['format']!=1 or not 1<=manifest['schema']<=len(MIGRATIONS):
            raise ValueError('Unsupported backup version')
        if set(names) != set(manifest['files'])|{'manifest.json'}:
            raise ValueError('Backup manifest does not match contents')
        for name in manifest['files']:
            if name!='clinic.sqlite' and not (len(Path(name).parts)==2 and Path(name).parts[0]=='attachments'):
                raise ValueError('Unexpected backup file')
        z.extractall(stage)
    for name, expected in manifest['files'].items():
        if digest(stage/name)!=expected:
            raise ValueError('Backup checksum failed')
    db = sqlite3.connect(stage/'clinic.sqlite')
    try:
        if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok' or db.execute('PRAGMA foreign_key_check').fetchall():
            raise ValueError('Database integrity failed')
        if db.execute('PRAGMA user_version').fetchone()[0]!=manifest['schema']:
            raise ValueError('Schema version mismatch')
        for stored, expected in db.execute('SELECT stored,sha256 FROM attachments'):
            if manifest['files'].get('attachments/'+stored)!=expected:
                raise ValueError('Missing or damaged attachment')
    finally:
        db.close()
    return manifest


def restore_backup(store, archive):
    # Caller must hold the exclusive application lock and suspend editing.
    with tempfile.TemporaryDirectory(dir=store.root.parent) as temp:
        stage = Path(temp)
        validate_backup(archive,stage)
        safety = create_backup(store.root,store.root.parent/'FaramarzSafetyBackups')
        store.db.close()
        displaced = store.root.with_name(store.root.name+'-restore-old')
        if displaced.exists():
            raise ValueError('Previous interrupted restore needs manual recovery')
        os.replace(store.root,displaced)
        try:
            os.replace(stage,store.root)
        except Exception:
            os.replace(displaced,store.root)
            raise
        finally:
            # TemporaryDirectory accepts an already-moved directory.
            pass
        shutil.rmtree(displaced)
    return safety


def apply_retention(destination, keep):
    if not 1<=keep<=365:
        raise ValueError('Retention must be 1 to 365 backups')
    backups = sorted(Path(destination).glob('Faramarz-*.fdbackup'),reverse=True)
    for path in backups[keep:]:
        path.unlink()
