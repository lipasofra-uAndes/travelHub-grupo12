from dataclasses import dataclass, asdict
from datetime import datetime


@dataclass
class PingEchoLog:
    """Modelo de log de Ping/Echo almacenado en SQLite"""

    id: int  # auto-increment PK
    service: str  # worker
    request_id: str  # ID del ping
    status: str  # UP, UNHEALTHY
    timestamp: str  # ISO8601 de cuando ocurrió

    def to_dict(self):
        """Convierte a diccionario para serialización"""
        return asdict(self)

    @staticmethod
    def from_row(row: tuple):
        """Construye desde fila de SQLite (id, service, request_id, status, timestamp)"""
        return PingEchoLog(
            id=row[0],
            service=row[1],
            request_id=row[2],
            status=row[3],
            timestamp=row[4],
        )

    @staticmethod
    def echo_up(service: str, request_id: str) -> "PingEchoLog":
        """Crea un log de echo exitoso (UP)"""
        return PingEchoLog(
            id=0,  # auto-filled por DB
            service=service,
            request_id=request_id,
            status="UP",
            timestamp=datetime.utcnow().isoformat() + "Z",
        )
