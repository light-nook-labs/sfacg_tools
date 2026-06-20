import sqlite3
import re
from pathlib import Path
from datetime import datetime
from loguru import logger
from .config import PACKAGE_DIR

DB_PATH = PACKAGE_DIR / 'progress.db'


def _extract_id(url: str) -> str:
    match = re.search(r'/(\d+)/?$', url.rstrip('/'))
    return match.group(1) if match else url


def _connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path or DB_PATH))
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            title TEXT NOT NULL,
            output_dir TEXT NOT NULL,
            format TEXT DEFAULT '',
            total INTEGER DEFAULT 0,
            completed INTEGER DEFAULT 0,
            status TEXT DEFAULT 'pending',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS chapters (
            task_id TEXT NOT NULL,
            cid TEXT NOT NULL,
            title TEXT DEFAULT '',
            status TEXT DEFAULT 'pending',
            file_path TEXT DEFAULT '',
            error TEXT DEFAULT '',
            PRIMARY KEY (task_id, cid),
            FOREIGN KEY (task_id) REFERENCES tasks(id)
        )
    ''')
    conn.commit()
    return conn


class ProgressTracker:

    def __init__(self, db_path: str | Path | None = None):
        self.db_path = db_path or DB_PATH
        self.conn = _connect(self.db_path)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def create_task(
        self,
        task_type: str,
        title: str,
        content_id: str | int,
        output_dir: str | Path,
        format: str = '',
        chapters: list[dict[str, str]] | None = None,
    ) -> str:
        task_id = f'{task_type}_{content_id}'
        now = datetime.now().isoformat()

        existing = self.conn.execute('SELECT id, status, completed FROM tasks WHERE id=?', (task_id,)).fetchone()

        if existing:
            if existing[1] == 'done':
                logger.bind(force=True).info(f'任务已完成: {title}')
                return task_id
            logger.bind(force=True).info(f'恢复任务: {title} (已完成 {existing[2]})')
            self.conn.execute(
                'UPDATE tasks SET status=?, updated_at=? WHERE id=?',
                ('running', now, task_id),
            )
        else:
            self.conn.execute(
                'INSERT INTO tasks (id, type, title, output_dir, format, total, status, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)',
                (task_id, task_type, title, str(output_dir), format, len(chapters or []), 'running', now, now),
            )
            if chapters:
                self.conn.executemany(
                    'INSERT OR IGNORE INTO chapters (task_id, cid, title) VALUES (?,?,?)',
                    [(task_id, _extract_id(ch['url']), ch.get('title', '')) for ch in chapters],
                )
        self.conn.commit()
        return task_id

    def mark_done(self, task_id: str, chapter_url: str, file_path: str = ''):
        cid = _extract_id(chapter_url)
        now = datetime.now().isoformat()
        self.conn.execute(
            'UPDATE chapters SET status=?, file_path=? WHERE task_id=? AND cid=?',
            ('done', file_path, task_id, cid),
        )
        self.conn.execute(
            'UPDATE tasks SET completed=completed+1, updated_at=? WHERE id=?',
            (now, task_id),
        )
        self.conn.commit()

    def mark_failed(self, task_id: str, chapter_url: str, error: str = ''):
        cid = _extract_id(chapter_url)
        self.conn.execute(
            'UPDATE chapters SET status=?, error=? WHERE task_id=? AND cid=?',
            ('failed', error[:500], task_id, cid),
        )
        self.conn.commit()

    def mark_task_done(self, task_id: str):
        now = datetime.now().isoformat()
        self.conn.execute(
            'UPDATE tasks SET status=?, updated_at=? WHERE id=?',
            ('done', now, task_id),
        )
        self.conn.commit()

    def delete_task(self, task_id: str):
        self.conn.execute('DELETE FROM chapters WHERE task_id=?', (task_id,))
        self.conn.execute('DELETE FROM tasks WHERE id=?', (task_id,))
        self.conn.commit()

    def get_pending(self, task_id: str) -> list[dict[str, str]]:
        rows = self.conn.execute(
            'SELECT cid, title FROM chapters WHERE task_id=? AND status!=?',
            (task_id, 'done'),
        ).fetchall()
        return [{'cid': r[0], 'title': r[1]} for r in rows]

    def get_done_count(self, task_id: str) -> int:
        row = self.conn.execute(
            'SELECT COUNT(*) FROM chapters WHERE task_id=? AND status=?',
            (task_id, 'done'),
        ).fetchone()
        return row[0] if row else 0

    def get_total(self, task_id: str) -> int:
        row = self.conn.execute(
            'SELECT COUNT(*) FROM chapters WHERE task_id=?',
            (task_id,),
        ).fetchone()
        return row[0] if row else 0

    def summary(self, task_id: str) -> dict:
        task = self.conn.execute('SELECT * FROM tasks WHERE id=?', (task_id,)).fetchone()
        if not task:
            return {}
        total = self.get_total(task_id)
        done = self.get_done_count(task_id)
        return {
            'id': task[0],
            'type': task[1],
            'title': task[2],
            'total': total,
            'done': done,
            'pending': total - done,
            'status': task[7],
        }

    def list_tasks(self) -> list[dict]:
        rows = self.conn.execute('SELECT id, type, title, status, completed, total FROM tasks ORDER BY updated_at DESC').fetchall()
        return [
            {'id': r[0], 'type': r[1], 'title': r[2], 'status': r[3], 'done': r[4], 'total': r[5]}
            for r in rows
        ]

    def cleanup_done(self):
        done_tasks = self.conn.execute("SELECT id FROM tasks WHERE status='done'").fetchall()
        for (task_id,) in done_tasks:
            self.conn.execute('DELETE FROM chapters WHERE task_id=?', (task_id,))
            self.conn.execute('DELETE FROM tasks WHERE id=?', (task_id,))
        self.conn.commit()
        return len(done_tasks)

    def close(self):
        self.conn.close()
