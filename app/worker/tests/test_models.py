"""Tests para modelos de negocio"""

from datetime import datetime

import pytest

from app.models.operation import Operation
from app.models.monitoring import PingEchoLog


class TestOperationModel:
    """Tests para modelo Operation"""

    def test_pending_creation(self):
        """Crea operación en estado PENDING"""
        op = Operation.pending("op-001", "pay", {"amount": 100})

        assert op.id == "op-001"
        assert op.type == "pay"
        assert op.status == "PENDING"
        assert op.error is None
        assert op.payload == {"amount": 100}
        assert op.created_at == op.updated_at

    def test_mark_processing(self):
        """Transición PENDING -> PROCESSING"""
        op = Operation.pending("op-001", "pay", {"amount": 100})
        processing = op.mark_processing()

        assert processing.status == "PROCESSING"
        assert processing.updated_at > op.updated_at
        assert processing.created_at == op.created_at

    def test_mark_processed(self):
        """Transición PROCESSING -> PROCESSED"""
        op = Operation.pending("op-001", "pay", {"amount": 100})
        processed = op.mark_processed()

        assert processed.status == "PROCESSED"
        assert processed.error is None
        assert processed.updated_at >= op.updated_at

    def test_mark_failed(self):
        """Transición -> FAILED con mensaje"""
        op = Operation.pending("op-001", "pay", {"amount": 100})
        failed = op.mark_failed("payment gateway timeout")

        assert failed.status == "FAILED"
        assert failed.error == "payment gateway timeout"
        assert failed.updated_at > op.updated_at

    def test_to_dict(self):
        """Convierte modelo a diccionario"""
        op = Operation.pending("op-001", "pay", {"amount": 100})
        data = op.to_dict()

        assert isinstance(data, dict)
        assert data["id"] == "op-001"
        assert data["type"] == "pay"
        assert data["status"] == "PENDING"
        assert data["payload"] == {"amount": 100}

    def test_from_row(self):
        """Construye desde tupla de SQLite"""
        now = datetime.utcnow().isoformat() + "Z"
        row = (
            "op-001",
            "reserve",
            '{"hotel_id": 123}',
            "PROCESSED",
            None,
            now,
            now,
        )

        op = Operation.from_row(row)

        assert op.id == "op-001"
        assert op.type == "reserve"
        assert op.payload == {"hotel_id": 123}
        assert op.status == "PROCESSED"
        assert op.error is None

    def test_from_row_with_null_payload(self):
        """Construye desde fila con payload NULL"""
        now = datetime.utcnow().isoformat() + "Z"
        row = ("op-001", "pay", None, "FAILED", "error msg", now, now)

        op = Operation.from_row(row)

        assert op.payload == {}
        assert op.error == "error msg"

    def test_state_immutability(self):
        """Métodos de transición no mutan el original"""
        op1 = Operation.pending("op-001", "pay", {"amount": 100})
        op2 = op1.mark_processing()

        assert op1.status == "PENDING"
        assert op2.status == "PROCESSING"
        assert op1.updated_at == op2.created_at


class TestPingEchoLogModel:
    """Tests para modelo PingEchoLog"""

    def test_echo_up_creation(self):
        """Crea log de echo exitoso"""
        log = PingEchoLog.echo_up("worker", "ping-001")

        assert log.service == "worker"
        assert log.request_id == "ping-001"
        assert log.status == "UP"
        assert log.timestamp.endswith("Z")

    def test_from_row(self):
        """Construye desde tupla de SQLite"""
        now = datetime.utcnow().isoformat() + "Z"
        row = (1, "worker", "ping-001", "UP", now)

        log = PingEchoLog.from_row(row)

        assert log.id == 1
        assert log.service == "worker"
        assert log.request_id == "ping-001"
        assert log.status == "UP"
        assert log.timestamp == now

    def test_to_dict(self):
        """Convierte a diccionario"""
        log = PingEchoLog.echo_up("broker", "ping-003")
        data = log.to_dict()

        assert isinstance(data, dict)
        assert data["service"] == "broker"
        assert data["status"] == "UP"
        assert "timestamp" in data
