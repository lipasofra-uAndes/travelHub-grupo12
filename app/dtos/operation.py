from typing import Any, Dict, Optional
from pydantic import BaseModel, Field
from datetime import datetime


class OperationDTO(BaseModel):
    """DTO para operaciones de negocio que viajan por Celery"""

    id: str = Field(..., description="ID único de la operación")
    type: str = Field(..., description="Tipo de operación: pay, reserve, search")
    payload: Dict[str, Any] = Field(default_factory=dict, description="Datos de negocio")
    status: str = Field(..., description="Estado: PENDING, PROCESSING, PROCESSED, FAILED")
    error: Optional[str] = Field(None, description="Mensaje de error si falló")
    created_at: str = Field(..., description="Timestamp de creación (ISO8601)")
    updated_at: str = Field(..., description="Timestamp de última actualización (ISO8601)")

    class Config:
        json_schema_extra = {
            "example": {
                "id": "op-001",
                "type": "pay",
                "payload": {"amount": 100, "currency": "ARS"},
                "status": "PENDING",
                "error": None,
                "created_at": "2026-02-19T21:00:00Z",
                "updated_at": "2026-02-19T21:00:00Z",
            }
        }


class ProcessOperationTaskDTO(BaseModel):
    """DTO para el task de procesamiento enviado a Celery"""

    operation_id: str = Field(..., description="ID de la operación a procesar")
    retry_count: int = Field(0, description="Contador interno de reintentos")

    class Config:
        json_schema_extra = {
            "example": {
                "operation_id": "op-001",
                "retry_count": 0,
            }
        }


class OperationResponseDTO(BaseModel):
    """DTO para la respuesta tras procesar una operación"""

    operation_id: str
    status: str
    processed_at: str = Field(..., description="Timestamp de procesamiento (ISO8601)")
    result: Optional[Dict[str, Any]] = Field(None, description="Resultado del procesamiento")
    error: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "operation_id": "op-001",
                "status": "PROCESSED",
                "processed_at": "2026-02-19T21:00:05Z",
                "result": {"transaction_id": "tx-001"},
                "error": None,
            }
        }
