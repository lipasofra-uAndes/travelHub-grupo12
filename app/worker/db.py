import json
import os
import sqlite3
from contextlib import closing
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.models.operation import Operation
from app.models.monitoring import HealthCheck, Incident

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
        
        # Nueva tabla health_checks (reemplaza ping_echo_log)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS health_checks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                service TEXT NOT NULL,
                request_id TEXT NOT NULL,
                status TEXT NOT NULL,
                latency_ms REAL,
                http_code INTEGER,
                timestamp TEXT NOT NULL,
                is_timeout INTEGER DEFAULT 0
            )
            """
        )
        
        # Índice para consultas por servicio y timestamp
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_health_checks_service_ts 
            ON health_checks(service, timestamp DESC)
            """
        )
        
        # Tabla de incidentes para tracking MTTD/MTTR
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS incidents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                service TEXT NOT NULL,
                started_at TEXT NOT NULL,
                detected_at TEXT,
                resolved_at TEXT,
                severity TEXT NOT NULL DEFAULT 'CRITICAL',
                consecutive_failures INTEGER NOT NULL,
                resolution_action TEXT,
                mttd_seconds REAL,
                mttr_seconds REAL
            )
            """
        )
        
        # Índice para incidentes activos
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_incidents_service_active 
            ON incidents(service, resolved_at)
            """
        )
        
        # Mantener tabla legacy para compatibilidad
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


def log_echo(service: str, request_id: str, status: str, ts: str, latency_ms: float = None) -> None:
    """Registra un echo recibido (compatible con legacy + nuevo formato)"""
    # Guardar en tabla legacy para compatibilidad
    with closing(sqlite3.connect(DB_PATH)) as conn:
        conn.execute(
            "INSERT INTO ping_echo_log(service, request_id, status, ts) VALUES(?, ?, ?, ?)",
            (service, request_id, status, ts),
        )
        conn.commit()
    
    # También guardar en nueva tabla health_checks
    check = HealthCheck(
        id=0,
        service=service,
        request_id=request_id,
        status=status,
        latency_ms=latency_ms,
        http_code=200 if status == "UP" else None,
        timestamp=ts,
        is_timeout=False,
    )
    save_health_check(check)


def get_last_echo(service: str) -> Optional[HealthCheck]:
    """Obtiene el último eco registrado para un servicio"""
    checks = get_recent_health_checks(service, limit=1)
    return checks[0] if checks else None


def get_recent_echoes(service: str, limit: int = 10) -> List[HealthCheck]:
    """Obtiene los últimos N ecos de un servicio"""
    with closing(sqlite3.connect(DB_PATH)) as conn:
        rows = conn.execute(
            "SELECT id, service, request_id, status, ts FROM ping_echo_log WHERE service = ? ORDER BY id DESC LIMIT ?",
            (service, limit),
        ).fetchall()

    return [HealthCheck.from_row(row) for row in rows]


# ==================== HEALTH CHECKS ====================

def save_health_check(check: HealthCheck) -> int:
    """Guarda un health check y retorna el ID"""
    with closing(sqlite3.connect(DB_PATH)) as conn:
        cursor = conn.execute(
            """
            INSERT INTO health_checks(service, request_id, status, latency_ms, http_code, timestamp, is_timeout)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                check.service,
                check.request_id,
                check.status,
                check.latency_ms,
                check.http_code,
                check.timestamp,
                1 if check.is_timeout else 0,
            ),
        )
        conn.commit()
        return cursor.lastrowid


def get_recent_health_checks(service: str, limit: int = 10) -> List[HealthCheck]:
    """Obtiene los últimos N health checks de un servicio"""
    with closing(sqlite3.connect(DB_PATH)) as conn:
        rows = conn.execute(
            """
            SELECT id, service, request_id, status, latency_ms, http_code, timestamp, is_timeout 
            FROM health_checks 
            WHERE service = ? 
            ORDER BY id DESC 
            LIMIT ?
            """,
            (service, limit),
        ).fetchall()

    return [HealthCheck.from_row(row) for row in rows]


def get_all_recent_health_checks(limit: int = 50) -> List[HealthCheck]:
    """Obtiene los últimos N health checks de TODOS los servicios"""
    with closing(sqlite3.connect(DB_PATH)) as conn:
        rows = conn.execute(
            """
            SELECT id, service, request_id, status, latency_ms, http_code, timestamp, is_timeout 
            FROM health_checks 
            ORDER BY id DESC 
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [HealthCheck.from_row(row) for row in rows]


def get_last_n_health_checks(service: str, n: int) -> List[HealthCheck]:
    """Obtiene los últimos N health checks (ordenados del más reciente al más antiguo)"""
    return get_recent_health_checks(service, limit=n)


def count_consecutive_failures(service: str, threshold: int) -> tuple[int, Optional[str]]:
    """
    Cuenta fallas consecutivas recientes para un servicio.
    Retorna (cantidad_fallas, timestamp_primera_falla)
    """
    checks = get_last_n_health_checks(service, threshold + 5)  # Obtener un poco más para contexto
    
    consecutive = 0
    first_failure_ts = None
    
    for check in checks:
        if check.is_failure():
            consecutive += 1
            first_failure_ts = check.timestamp  # Se actualiza hasta la más antigua consecutiva
        else:
            break  # Se rompe la racha de fallas
    
    return consecutive, first_failure_ts


# ==================== INCIDENTS ====================

def save_incident(incident: Incident) -> int:
    """Guarda un incidente y retorna el ID"""
    with closing(sqlite3.connect(DB_PATH)) as conn:
        cursor = conn.execute(
            """
            INSERT INTO incidents(
                service, started_at, detected_at, resolved_at, severity, 
                consecutive_failures, resolution_action, mttd_seconds, mttr_seconds
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                incident.service,
                incident.started_at,
                incident.detected_at,
                incident.resolved_at,
                incident.severity,
                incident.consecutive_failures,
                incident.resolution_action,
                incident.mttd_seconds,
                incident.mttr_seconds,
            ),
        )
        conn.commit()
        return cursor.lastrowid


def get_active_incident(service: str) -> Optional[Incident]:
    """Obtiene el incidente activo (no resuelto) para un servicio"""
    with closing(sqlite3.connect(DB_PATH)) as conn:
        row = conn.execute(
            """
            SELECT id, service, started_at, detected_at, resolved_at, severity,
                   consecutive_failures, resolution_action, mttd_seconds, mttr_seconds
            FROM incidents 
            WHERE service = ? AND resolved_at IS NULL 
            ORDER BY id DESC 
            LIMIT 1
            """,
            (service,),
        ).fetchone()

    if not row:
        return None

    return Incident.from_row(row)


def update_incident(incident: Incident) -> None:
    """Actualiza un incidente existente"""
    with closing(sqlite3.connect(DB_PATH)) as conn:
        conn.execute(
            """
            UPDATE incidents
            SET resolved_at = ?, resolution_action = ?, mttr_seconds = ?
            WHERE id = ?
            """,
            (
                incident.resolved_at,
                incident.resolution_action,
                incident.mttr_seconds,
                incident.id,
            ),
        )
        conn.commit()


def get_incidents_by_service(service: str, limit: int = 50) -> List[Incident]:
    """Obtiene los últimos N incidentes de un servicio"""
    with closing(sqlite3.connect(DB_PATH)) as conn:
        rows = conn.execute(
            """
            SELECT id, service, started_at, detected_at, resolved_at, severity,
                   consecutive_failures, resolution_action, mttd_seconds, mttr_seconds
            FROM incidents 
            WHERE service = ? 
            ORDER BY id DESC 
            LIMIT ?
            """,
            (service, limit),
        ).fetchall()

    return [Incident.from_row(row) for row in rows]


def get_all_incidents(limit: int = 100) -> List[Incident]:
    """Obtiene todos los incidentes recientes"""
    with closing(sqlite3.connect(DB_PATH)) as conn:
        rows = conn.execute(
            """
            SELECT id, service, started_at, detected_at, resolved_at, severity,
                   consecutive_failures, resolution_action, mttd_seconds, mttr_seconds
            FROM incidents 
            ORDER BY id DESC 
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [Incident.from_row(row) for row in rows]



