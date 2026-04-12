"""SQLite через aiosqlite — полная реализация."""

import json
from pathlib import Path
from typing import Any

import aiosqlite

from backend.config import settings

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    mode TEXT NOT NULL,
    variant TEXT NOT NULL DEFAULT 'A',
    status TEXT NOT NULL DEFAULT 'pending',
    input_file TEXT,
    target_positions TEXT,
    total_urls INTEGER DEFAULT 0,
    processed_urls INTEGER DEFAULT 0,
    found_contacts INTEGER DEFAULT 0,
    errors_count INTEGER DEFAULT 0,
    output_file TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    completed_at DATETIME
);

CREATE TABLE IF NOT EXISTS processed_sites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL REFERENCES tasks(id),
    url TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    error_code TEXT,
    error_message TEXT,
    pages_visited INTEGER DEFAULT 0,
    contacts_found INTEGER DEFAULT 0,
    extraction_method TEXT DEFAULT 'regex',
    processing_time_ms INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ps_task_status
    ON processed_sites(task_id, status);

CREATE TABLE IF NOT EXISTS contacts_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL REFERENCES tasks(id),
    site_url TEXT NOT NULL,
    page_url TEXT NOT NULL,
    company_name TEXT,
    company_email TEXT,
    company_phone TEXT,
    person_name TEXT,
    position_raw TEXT,
    position_norm TEXT,
    role_category TEXT,
    person_email TEXT,
    person_phone TEXT,
    inn TEXT,
    kpp TEXT,
    social_links TEXT,
    page_language TEXT,
    extraction_method TEXT DEFAULT 'regex',
    status TEXT DEFAULT 'ok',
    comment TEXT,
    scan_date DATE DEFAULT CURRENT_DATE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS blacklist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_type TEXT NOT NULL,
    entry_value TEXT NOT NULL UNIQUE,
    added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    source TEXT DEFAULT 'user'
);

CREATE INDEX IF NOT EXISTS idx_bl_value ON blacklist(entry_value);
"""


class Database:
    def __init__(self) -> None:
        self.db_path = settings.SQLITE_DB_PATH
        self._db: aiosqlite.Connection | None = None

    async def initialize(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self.db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.executescript(SCHEMA_SQL)
        await self._db.commit()

    async def close(self) -> None:
        if self._db:
            await self._db.close()

    # ── Tasks ──

    async def create_task(
        self,
        task_id: str,
        mode: str,
        total_urls: int,
        target_positions: list[str] | None = None,
        input_file: str | None = None,
    ) -> None:
        pos_json = json.dumps(target_positions, ensure_ascii=False) if target_positions else None
        await self._db.execute(
            """INSERT INTO tasks (id, mode, variant, status, input_file,
               target_positions, total_urls)
               VALUES (?, ?, ?, 'pending', ?, ?, ?)""",
            (task_id, mode, settings.VARIANT, input_file, pos_json, total_urls),
        )
        await self._db.commit()

    async def get_task(self, task_id: str) -> dict | None:
        async with self._db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None

    async def list_tasks(self, limit: int = 50, offset: int = 0) -> list[dict]:
        async with self._db.execute(
            "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    async def update_task(self, task_id: str, **kwargs: Any) -> None:
        sets = ", ".join(f"{k} = ?" for k in kwargs)
        vals = list(kwargs.values()) + [task_id]
        await self._db.execute(
            f"UPDATE tasks SET {sets}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            vals,
        )
        await self._db.commit()

    # ── Processed Sites ──

    async def add_site(self, task_id: str, url: str) -> int:
        cur = await self._db.execute(
            "INSERT INTO processed_sites (task_id, url) VALUES (?, ?)",
            (task_id, url),
        )
        await self._db.commit()
        return cur.lastrowid

    async def update_site(self, site_id: int, **kwargs: Any) -> None:
        sets = ", ".join(f"{k} = ?" for k in kwargs)
        vals = list(kwargs.values()) + [site_id]
        await self._db.execute(
            f"UPDATE processed_sites SET {sets}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            vals,
        )
        await self._db.commit()

    async def get_pending_sites(self, task_id: str) -> list[dict]:
        async with self._db.execute(
            "SELECT * FROM processed_sites WHERE task_id = ? AND status = 'pending' ORDER BY id",
            (task_id,),
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    async def get_task_sites(self, task_id: str) -> list[dict]:
        async with self._db.execute(
            "SELECT * FROM processed_sites WHERE task_id = ? ORDER BY id",
            (task_id,),
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    # ── Contacts ──

    async def save_contact(self, **kwargs: Any) -> int:
        cols = ", ".join(kwargs.keys())
        placeholders = ", ".join("?" for _ in kwargs)
        cur = await self._db.execute(
            f"INSERT INTO contacts_cache ({cols}) VALUES ({placeholders})",
            list(kwargs.values()),
        )
        await self._db.commit()
        return cur.lastrowid

    async def get_task_contacts(self, task_id: str) -> list[dict]:
        async with self._db.execute(
            "SELECT * FROM contacts_cache WHERE task_id = ? ORDER BY id",
            (task_id,),
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    # ── Blacklist ──

    async def add_blacklist_entry(self, entry_type: str, entry_value: str) -> bool:
        try:
            await self._db.execute(
                "INSERT OR IGNORE INTO blacklist (entry_type, entry_value) VALUES (?, ?)",
                (entry_type, entry_value.lower().strip()),
            )
            await self._db.commit()
            return True
        except Exception:
            return False

    async def get_blacklist(self) -> list[dict]:
        async with self._db.execute("SELECT * FROM blacklist ORDER BY id") as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    async def is_blacklisted(self, value: str) -> bool:
        v = value.lower().strip()
        async with self._db.execute(
            "SELECT COUNT(*) as cnt FROM blacklist WHERE entry_value = ?", (v,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row)["cnt"] > 0

    async def is_domain_blacklisted(self, domain: str) -> bool:
        d = domain.lower().strip()
        async with self._db.execute(
            "SELECT COUNT(*) as cnt FROM blacklist WHERE entry_type = 'domain' AND entry_value = ?",
            (d,),
        ) as cur:
            row = await cur.fetchone()
            return dict(row)["cnt"] > 0

    async def delete_blacklist_entry(self, entry_id: int) -> None:
        await self._db.execute("DELETE FROM blacklist WHERE id = ?", (entry_id,))
        await self._db.commit()

    async def clear_blacklist(self) -> None:
        await self._db.execute("DELETE FROM blacklist")
        await self._db.commit()

    async def count_blacklist(self) -> int:
        async with self._db.execute("SELECT COUNT(*) as cnt FROM blacklist") as cur:
            row = await cur.fetchone()
            return dict(row)["cnt"]
