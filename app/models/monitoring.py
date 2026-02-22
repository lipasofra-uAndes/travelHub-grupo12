from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Optional


@dataclass
class HealthCheck:
    """Modelo de health check almacenado en SQLite - Extiende PingEchoLog con latencia"""

    id: int  # auto-increment PK
    service: str  # api-gateway, reserves, payments, search, worker, redis
    request_id: str  # ID del ping
    status: str  # UP, DOWN, TIMEOUT, DEGRADED, UNHEALTHY
    latency_ms: Optional[float]  # Tiempo de respuesta en ms
    http_code: Optional[int]  # Código HTTP si aplica
    timestamp: str  # ISO8601 de cuando ocurrió
    is_timeout: bool = False  # True si fue timeout
    error_message: Optional[str] = None  # Mensaje de error si falló

    def to_dict(self):
        """Convierte a diccionario para serialización"""
        return asdict(self)

    @staticmethod
    def from_row(row: tuple) -> "HealthCheck":
        """Construye desde fila de SQLite"""
        return HealthCheck(
            id=row[0],
            service=row[1],
            request_id=row[2],
            status=row[3],
            latency_ms=row[4],
            http_code=row[5],
            timestamp=row[6],
            is_timeout=bool(row[7]) if row[7] is not None else False,
        )

    @staticmethod
    def up(service: str, request_id: str, latency_ms: float, http_code: int = 200) -> "HealthCheck":
        """Crea un health check exitoso (UP)"""
        return HealthCheck(
            id=0,
            service=service,
            request_id=request_id,
            status="UP",
            latency_ms=latency_ms,
            http_code=http_code,
            timestamp=datetime.utcnow().isoformat() + "Z",
            is_timeout=False,
        )

    @staticmethod
    def down(service: str, request_id: str) -> "HealthCheck":
        """Crea un health check de servicio caído (DOWN)"""
        return HealthCheck(
            id=0,
            service=service,
            request_id=request_id,
            status="DOWN",
            latency_ms=None,
            http_code=None,
            timestamp=datetime.utcnow().isoformat() + "Z",
            is_timeout=False,
        )

    @staticmethod
    def timeout(service: str, request_id: str, timeout_ms: float) -> "HealthCheck":
        """Crea un health check de timeout"""
        return HealthCheck(
            id=0,
            service=service,
            request_id=request_id,
            status="TIMEOUT",
            latency_ms=timeout_ms,
            http_code=None,
            timestamp=datetime.utcnow().isoformat() + "Z",
            is_timeout=True,
        )

    def is_failure(self) -> bool:
        """Retorna True si este check representa una falla"""
        return self.status in ("DOWN", "TIMEOUT", "UNHEALTHY")


@dataclass
class Incident:
    """Modelo de incidente para tracking de MTTD/MTTR"""

    id: int  # auto-increment PK
    service: str  # Servicio afectado
    started_at: str  # ISO8601 - Primera falla detectada
    detected_at: Optional[str]  # ISO8601 - Cuando se detectó (N fallas consecutivas)
    resolved_at: Optional[str]  # ISO8601 - Cuando se recuperó
    severity: str  # WARNING, CRITICAL
    consecutive_failures: int  # Cuántas fallas dispararon el incidente
    resolution_action: Optional[str]  # auto-recovery, restart, manual
    mttd_seconds: Optional[float]  # Mean Time To Detect (detected_at - started_at)
    mttr_seconds: Optional[float]  # Mean Time To Recover (resolved_at - detected_at)

    def to_dict(self):
        """Convierte a diccionario para serialización"""
        return asdict(self)

    @staticmethod
    def from_row(row: tuple) -> "Incident":
        """Construye desde fila de SQLite"""
        return Incident(
            id=row[0],
            service=row[1],
            started_at=row[2],
            detected_at=row[3],
            resolved_at=row[4],
            severity=row[5],
            consecutive_failures=row[6],
            resolution_action=row[7],
            mttd_seconds=row[8],
            mttr_seconds=row[9],
        )

    @staticmethod
    def create(
        service: str,
        first_failure_time: str,
        consecutive_failures: int,
        severity: str = "CRITICAL"
    ) -> "Incident":
        """Crea un nuevo incidente cuando se detectan N fallas consecutivas"""
        now = datetime.utcnow().isoformat() + "Z"
        
        # Calcular MTTD
        first_dt = datetime.fromisoformat(first_failure_time.replace("Z", "+00:00"))
        detected_dt = datetime.utcnow()
        mttd = (detected_dt - first_dt.replace(tzinfo=None)).total_seconds()
        
        return Incident(
            id=0,
            service=service,
            started_at=first_failure_time,
            detected_at=now,
            resolved_at=None,
            severity=severity,
            consecutive_failures=consecutive_failures,
            resolution_action=None,
            mttd_seconds=mttd,
            mttr_seconds=None,
        )

    def resolve(self, action: str = "auto-recovery") -> None:
        """Marca el incidente como resuelto y calcula MTTR"""
        now = datetime.utcnow()
        self.resolved_at = now.isoformat() + "Z"
        self.resolution_action = action
        
        if self.detected_at:
            detected_dt = datetime.fromisoformat(self.detected_at.replace("Z", "+00:00"))
            self.mttr_seconds = (now - detected_dt.replace(tzinfo=None)).total_seconds()

    def is_active(self) -> bool:
        """Retorna True si el incidente sigue activo"""
        return self.resolved_at is None


# Alias para compatibilidad con código existente
PingEchoLog = HealthCheck
