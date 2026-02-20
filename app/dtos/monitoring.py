from typing import Optional
from pydantic import BaseModel, Field
from datetime import datetime


class EchoResponseDTO(BaseModel):
    """DTO para respuesta Echo del worker cuando responde a Ping"""

    service: str = Field(..., description="Servicio que responde (worker)")
    request_id: str = Field(..., description="ID del ping original")
    status: str = Field(..., description="Estado: UP, UNHEALTHY")
    ts: str = Field(..., description="Timestamp de respuesta (ISO8601)")

    class Config:
        json_schema_extra = {
            "example": {
                "service": "worker",
                "request_id": "ping-001",
                "status": "UP",
                "ts": "2026-02-19T21:00:01Z",
            }
        }
