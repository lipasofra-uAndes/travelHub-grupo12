import json
import os
import sqlite3
from contextlib import closing
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.models.operation import Operation
from app.models.monitoring import PingEchoLog

DB_PATH = os.getenv("SQLITE_DB_PATH", "/data/operations.db")


def _utc_now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def init_db() -> None:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with closing(sqlite3.connect(DB_PATH)) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS operations (
                id TEXT PRIMARY KEY,
                type TEXT,
                payload TEXT,
                status TEXT NOT NULL,
                error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ping_echo_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                service TEXT NOT NULL,
                request_id TEXT NOT NULL,
                status TEXT NOT NULL,
                ts TEXT NOT NULL
            )
            """
        )

        conn.commit()


def get_operation(operation_id: str) -> Optional[Operation]:
    with closing(sqlite3.connect(DB_PATH)) as conn:
        row = conn.execute(
            "SELECT id, type, payload, status, error, created_at, updated_at FROM operations WHERE id = ?",
            (operation_id,),
        ).fetchone()

    if not row:
        return None

    return Operation.from_row(row)


def save_operation(operation: Operation) -> None:
    """Guarda o actualiza una operación"""
    with closing(sqlite3.connect(DB_PATH)) as conn:
        payload_json = json.dumps(operation.payload) if operation.payload else None
        conn.execute(
            """
            INSERT OR REPLACE INTO operations(id, type, payload, status, error, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                operation.id,
                operation.type,
                payload_json,
                operation.status,
                operation.error,
                operation.created_at,
                operation.updated_at,
            ),
        )
        conn.commit()


def update_operation_status(operation_id: str, status: str, error: Optional[str] = None) -> None:
    now = _utc_now_iso()
    with closing(sqlite3.connect(DB_PATH)) as conn:
        conn.execute(
            """
            UPDATE operations
            SET status = ?, error = ?, updated_at = ?
            WHERE id = ?
            """,
            (status, error, now, operation_id),
        )
        conn.commit()


def log_echo(service: str, request_id: str, status: str, ts: str) -> None:
    """Registra un echo recibido"""
    log = PingEchoLog(id=0, service=service, request_id=request_id, status=status, timestamp=ts)
    with closing(sqlite3.connect(DB_PATH)) as conn:
        conn.execute(
            "INSERT INTO ping_echo_log(service, request_id, status, ts) VALUES(?, ?, ?, ?)",
            (log.service, log.request_id, log.status, log.timestamp),
        )
        conn.commit()


def get_last_echo(service: str) -> Optional[PingEchoLog]:
    """Obtiene el último eco registrado para un servicio"""
    with closing(sqlite3.connect(DB_PATH)) as conn:
        row = conn.execute(
            "SELECT id, service, request_id, status, ts FROM ping_echo_log WHERE service = ? ORDER BY id DESC LIMIT 1",
            (service,),
        ).fetchone()

    if not row:
        return None

    return PingEchoLog.from_row(row)


def get_recent_echoes(service: str, limit: int = 10) -> List[PingEchoLog]:
    """Obtiene los últimos N ecos de un servicio"""
    with closing(sqlite3.connect(DB_PATH)) as conn:
        rows = conn.execute(
            "SELECT id, service, request_id, status, ts FROM ping_echo_log WHERE service = ? ORDER BY id DESC LIMIT ?",
            (service, limit),
        ).fetchall()

    return [PingEchoLog.from_row(row) for row in rows]



