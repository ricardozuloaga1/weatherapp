"""Small private SQLite store. Single local process only; no API credentials stored."""
import json
import os
from pathlib import Path
import secrets
import sqlite3


class PilotStore:
    def __init__(self, path):
        if str(path) != ':memory:':
            path = Path(path)
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            self.db = sqlite3.connect(path, check_same_thread=False)
            os.chmod(path, 0o600)
        else:
            self.db = sqlite3.connect(':memory:', check_same_thread=False)
        self.db.executescript('''
            PRAGMA secure_delete=ON;
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE IF NOT EXISTS records (owner TEXT PRIMARY KEY, photo BLOB, body TEXT);
            CREATE TABLE IF NOT EXISTS images (id TEXT PRIMARY KEY, owner TEXT, image BLOB);
        ''')
        self.db.execute('INSERT OR IGNORE INTO settings VALUES (?, ?)', ('secret', secrets.token_hex(32)))
        self.db.execute('INSERT OR IGNORE INTO settings VALUES (?, ?)', ('submitted', '0'))
        self.db.commit()

    def setting(self, key):
        return self.db.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()[0]

    def count(self):
        return int(self.setting('submitted'))

    def load(self):
        records = {}
        for owner, photo, body in self.db.execute('SELECT owner, photo, body FROM records'):
            record = json.loads(body)
            record['photo'] = photo
            images = dict(self.db.execute('SELECT id, image FROM images WHERE owner=?', (owner,)))
            for job in record['jobs']:
                if job['id'] in images:
                    job['image'] = images[job['id']]
                if job['status'] in {'queued', 'generating'}:
                    job.update(status='interrupted', error='Server stopped before completion was recorded. Billing may have occurred. No automatic retry.')
            records[owner] = record
        for owner, record in records.items():
            self.save(owner, record)
        return records

    def save(self, owner, record, submitted=None):
        body = {k: v for k, v in record.items() if k != 'photo'}
        body['jobs'] = [{k: v for k, v in j.items() if k != 'image'} for j in record['jobs']]
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO records VALUES (?, ?, ?)', (owner, record['photo'], json.dumps(body)))
            for job in record['jobs']:
                if 'image' in job:
                    self.db.execute('INSERT OR IGNORE INTO images VALUES (?, ?, ?)', (job['id'], owner, job['image']))
            if submitted is not None:
                self.db.execute('UPDATE settings SET value=? WHERE key=?', (str(submitted), 'submitted'))

    def delete(self, owner):
        with self.db:
            self.db.execute('DELETE FROM records WHERE owner=?', (owner,))
            self.db.execute('DELETE FROM images WHERE owner=?', (owner,))
