import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent

def now():
    return datetime.now(timezone.utc).isoformat()

def data_dir():
    return Path(os.getenv('DATA_DIR', 'data')).resolve()

@contextmanager
def connect():
    data_dir().mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(data_dir() / 'news.db', timeout=10)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

def init_db():
    with connect() as db:
        db.executescript((ROOT / 'migrations/001_initial.sql').read_text())

def dumps(value):
    return json.dumps(value, ensure_ascii=False)

if __name__ == '__main__':
    init_db()
