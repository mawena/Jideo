"""Accès SQLite. Une seule connexion partagée, protégée par un verrou."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any

import numpy as np

SCHEMA = """
CREATE TABLE IF NOT EXISTS media (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    original_name TEXT NOT NULL,
    path TEXT NOT NULL,
    thumbnail_path TEXT,
    width INTEGER,
    height INTEGER,
    duration REAL,
    fps REAL,
    has_audio INTEGER,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS faces (
    id TEXT PRIMARY KEY,
    media_id TEXT NOT NULL REFERENCES media(id) ON DELETE CASCADE,
    idx INTEGER NOT NULL,
    t REAL NOT NULL,
    bbox TEXT NOT NULL,
    score REAL NOT NULL,
    embedding BLOB NOT NULL,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    status TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 0,
    params TEXT NOT NULL,
    progress REAL NOT NULL DEFAULT 0,
    message TEXT,
    result_path TEXT,
    stats TEXT,
    created_at REAL NOT NULL,
    started_at REAL,
    finished_at REAL
);
CREATE INDEX IF NOT EXISTS jobs_queue ON jobs(status, priority DESC, created_at);
"""

JOB_FIELDS = {"status", "progress", "message", "result_path", "stats", "started_at", "finished_at"}


def new_id() -> str:
    return uuid.uuid4().hex


class Database:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._lock:
            self._conn.execute("PRAGMA foreign_keys = ON")
            self._conn.execute("PRAGMA journal_mode = WAL")
            self._conn.executescript(SCHEMA)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def _exec(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            return self._conn.execute(sql, params)

    def _one(self, sql: str, params: tuple = ()) -> dict | None:
        with self._lock:
            row = self._conn.execute(sql, params).fetchone()
        return dict(row) if row else None

    def _all(self, sql: str, params: tuple = ()) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    # --- media -------------------------------------------------------------

    def insert_media(
        self, *, kind: str, original_name: str, path: Path | str, width: int, height: int,
        duration: float | None = None, fps: float | None = None, has_audio: bool | None = None,
        thumbnail_path: Path | str | None = None, media_id: str | None = None,
    ) -> dict:
        media_id = media_id or new_id()
        self._exec(
            "INSERT INTO media (id, kind, original_name, path, thumbnail_path, width, height,"
            " duration, fps, has_audio, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (media_id, kind, original_name, str(path), str(thumbnail_path) if thumbnail_path else None,
             width, height, duration, fps, None if has_audio is None else int(has_audio), time.time()),
        )
        return self.get_media(media_id)

    def get_media(self, media_id: str) -> dict | None:
        return self._one("SELECT * FROM media WHERE id = ?", (media_id,))

    def delete_media(self, media_id: str) -> None:
        self._exec("DELETE FROM media WHERE id = ?", (media_id,))

    # --- faces -------------------------------------------------------------

    def insert_face(
        self, *, media_id: str, index: int, t: float, bbox: tuple | list, score: float, embedding: np.ndarray,
    ) -> dict:
        face_id = new_id()
        self._exec(
            "INSERT INTO faces (id, media_id, idx, t, bbox, score, embedding, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (face_id, media_id, index, t, json.dumps([float(v) for v in bbox]), float(score),
             np.asarray(embedding, dtype=np.float32).tobytes(), time.time()),
        )
        return self.get_face(face_id)

    def get_face(self, face_id: str) -> dict | None:
        row = self._one("SELECT * FROM faces WHERE id = ?", (face_id,))
        if row:
            row["bbox"] = json.loads(row["bbox"])
            row["embedding"] = np.frombuffer(row["embedding"], dtype=np.float32).copy()
        return row

    # --- jobs --------------------------------------------------------------

    def insert_job(self, *, type: str, params: dict[str, Any], priority: int = 0) -> dict:
        job_id = new_id()
        self._exec(
            "INSERT INTO jobs (id, type, status, priority, params, created_at) VALUES (?, ?, 'queued', ?, ?, ?)",
            (job_id, type, priority, json.dumps(params), time.time()),
        )
        return self.get_job(job_id)

    @staticmethod
    def _job(row: dict | None) -> dict | None:
        if row:
            row["params"] = json.loads(row["params"])
            row["stats"] = json.loads(row["stats"]) if row["stats"] else None
        return row

    def get_job(self, job_id: str) -> dict | None:
        return self._job(self._one("SELECT * FROM jobs WHERE id = ?", (job_id,)))

    def list_jobs(self, limit: int = 50, offset: int = 0) -> list[dict]:
        rows = self._all(
            "SELECT * FROM jobs ORDER BY created_at DESC, rowid DESC LIMIT ? OFFSET ?", (limit, offset)
        )
        return [self._job(r) for r in rows]

    def claim_next_job(self) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT id FROM jobs WHERE status = 'queued' ORDER BY priority DESC, created_at, rowid LIMIT 1"
            ).fetchone()
            if row is None:
                return None
            self._conn.execute(
                "UPDATE jobs SET status = 'running', started_at = ?, progress = 0 WHERE id = ?",
                (time.time(), row["id"]),
            )
        return self.get_job(row["id"])

    def update_job(self, job_id: str, **fields: Any) -> None:
        unknown = set(fields) - JOB_FIELDS
        if unknown:
            raise ValueError(f"champs inconnus : {unknown}")
        if "stats" in fields:
            fields["stats"] = json.dumps(fields["stats"]) if fields["stats"] is not None else None
        if fields.get("result_path") is not None:
            fields["result_path"] = str(fields["result_path"])
        assignments = ", ".join(f"{name} = ?" for name in fields)
        self._exec(f"UPDATE jobs SET {assignments} WHERE id = ?", (*fields.values(), job_id))

    def cancel_queued_job(self, job_id: str) -> bool:
        cursor = self._exec(
            "UPDATE jobs SET status = 'cancelled', finished_at = ? WHERE id = ? AND status = 'queued'",
            (time.time(), job_id),
        )
        return cursor.rowcount == 1

    def delete_job(self, job_id: str) -> None:
        self._exec("DELETE FROM jobs WHERE id = ?", (job_id,))

    def mark_interrupted_jobs(self) -> int:
        cursor = self._exec(
            "UPDATE jobs SET status = 'failed', message = 'Interrompue par un redémarrage du serveur',"
            " finished_at = ? WHERE status = 'running'",
            (time.time(),),
        )
        return cursor.rowcount
