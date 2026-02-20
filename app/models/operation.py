from typing import Any, Dict, Optional
from dataclasses import dataclass, asdict
from datetime import datetime


@dataclass
class Operation:
    """Modelo de operación almacenada en SQLite"""

    id: str
    type: str
    payload: Dict[str, Any]
    status: str
    error: Optional[str]
    created_at: str
    updated_at: str

    def to_dict(self):
        """Convierte a diccionario para serialización"""
        data = asdict(self)
        return data

    @staticmethod
    def from_row(row: tuple):
        """Construye desde fila de SQLite (id, type, payload, status, error, created_at, updated_at)"""
        import json

        return Operation(
            id=row[0],
            type=row[1],
            payload=json.loads(row[2]) if row[2] else {},
            status=row[3],
            error=row[4],
            created_at=row[5],
            updated_at=row[6],
        )

    @staticmethod
    def pending(operation_id: str, type: str, payload: Dict[str, Any]) -> "Operation":
        """Crea una operación nueva en estado PENDING"""
        now = datetime.utcnow().isoformat() + "Z"
        return Operation(
            id=operation_id,
            type=type,
            payload=payload,
            status="PENDING",
            error=None,
            created_at=now,
            updated_at=now,
        )

    def mark_processing(self) -> "Operation":
        """Marca operación como en procesamiento"""
        return Operation(
            id=self.id,
            type=self.type,
            payload=self.payload,
            status="PROCESSING",
            error=self.error,
            created_at=self.created_at,
            updated_at=datetime.utcnow().isoformat() + "Z",
        )

    def mark_processed(self) -> "Operation":
        """Marca como exitosamente procesada"""
        return Operation(
            id=self.id,
            type=self.type,
            payload=self.payload,
            status="PROCESSED",
            error=None,
            created_at=self.created_at,
            updated_at=datetime.utcnow().isoformat() + "Z",
        )

    def mark_failed(self, error_msg: str) -> "Operation":
        """Marca como fallida"""
        return Operation(
            id=self.id,
            type=self.type,
            payload=self.payload,
            status="FAILED",
            error=error_msg,
            created_at=self.created_at,
            updated_at=datetime.utcnow().isoformat() + "Z",
        )
