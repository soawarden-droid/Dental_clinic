import os
import sqlite3
from pathlib import Path


def data_path():
    base = Path(os.environ.get('LOCALAPPDATA' if os.name=='nt' else 'XDG_DATA_HOME', Path.home() / '.local/share'))
    return Path(os.environ.get('FARAMARZ_PROFILE', base / 'FaramarzDental'))


class Store:
    def __init__(self, root=None):
        self.root = Path(root or data_path())
        recovery=self.root.with_name(self.root.name+'-restore-old')
        if recovery.exists() and not self.root.exists():
            os.replace(recovery,self.root)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.db = sqlite3.connect(self.root / 'clinic.sqlite')
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL)')
        self.db.commit()

    def setting(self, key, default=''):
        r = self.db.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
        return r[0] if r else default

    def set_setting(self, key, value):
        with self.db:
            self.db.execute('INSERT INTO settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (key, str(value)))

    def rows(self, sql, args=()):
        return [dict(r) for r in self.db.execute(sql, args).fetchall()]

    def one(self, sql, args=()):
        r = self.db.execute(sql, args).fetchone()
        return dict(r) if r else None

    def migrate(self):
        from .schema import MIGRATIONS
        version = self.db.execute('PRAGMA user_version').fetchone()[0]
        if version > len(MIGRATIONS):
            raise ValueError('Database belongs to a newer application version')
        for i in range(version, len(MIGRATIONS)):
            try:
                self.db.executescript('BEGIN IMMEDIATE;\n' + MIGRATIONS[i] + f'\nPRAGMA user_version={i+1};\nCOMMIT;')
            except Exception:
                self.db.rollback()
                raise
        if not self.rows('SELECT id FROM catalogue'):
            with self.db:
                self.db.executemany('INSERT INTO catalogue(name,price) VALUES(?,?)', [(x, 0) for x in ['Consultation','Scaling','Filling','Extraction','Root canal','Crown','Bridge','Denture','Orthodontic visit']])
