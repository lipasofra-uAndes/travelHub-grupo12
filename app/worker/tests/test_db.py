"""Tests para funciones de acceso a base de datos"""

import json
from datetime import datetime

import pytest

from app.models.operation import Operation
from app.models.monitoring import PingEchoLog
from app.worker.db import (
    get_operation,
    save_operation,
    update_operation_status,
    log_echo,
    get_last_echo,
    get_recent_echoes,
    init_db,
)


class TestOperationDB:
    """Tests para operaciones en SQLite"""

    def test_save_and_get_operation(self, initialized_db, sample_operation_id, sample_operation_data):
        """Guarda y recupera una operación"""
        op = Operation.pending(sample_operation_id, **sample_operation_data)

        save_operation(op)

        retrieved = get_operation(sample_operation_id)
        assert retrieved is not None
        assert retrieved.id == op.id
        assert retrieved.type == op.type
        assert retrieved.status == "PENDING"
        assert retrieved.payload == op.payload

    def test_get_nonexistent_operation(self, initialized_db):
        """Intenta recuperar operación inexistente"""
        result = get_operation("op-nonexistent")
        assert result is None

    def test_update_operation_status(self, initialized_db, sample_operation_id, sample_operation_data):
        """Actualiza estado de operación"""
        op = Operation.pending(sample_operation_id, **sample_operation_data)
        save_operation(op)

        update_operation_status(sample_operation_id, "PROCESSING")

        updated = get_operation(sample_operation_id)
        assert updated.status == "PROCESSING"
        assert updated.error is None

    def test_update_operation_with_error(self, initialized_db, sample_operation_id, sample_operation_data):
        """Actualiza operación con mensaje de error"""
        op = Operation.pending(sample_operation_id, **sample_operation_data)
        save_operation(op)

        error_msg = "Payment gateway timeout"
        update_operation_status(sample_operation_id, "FAILED", error=error_msg)

        updated = get_operation(sample_operation_id)
        assert updated.status == "FAILED"
        assert updated.error == error_msg

    def test_operation_state_transitions(self, initialized_db, sample_operation_id, sample_operation_data):
        """Prueba transiciones de estado: PENDING -> PROCESSING -> PROCESSED"""
        op = Operation.pending(sample_operation_id, **sample_operation_data)
        save_operation(op)

        # PENDING -> PROCESSING
        op = op.mark_processing()
        save_operation(op)
        assert get_operation(sample_operation_id).status == "PROCESSING"

        # PROCESSING -> PROCESSED
        op = op.mark_processed()
        save_operation(op)
        retrieved = get_operation(sample_operation_id)
        assert retrieved.status == "PROCESSED"
        assert retrieved.error is None

    def test_operation_with_complex_payload(self, initialized_db, sample_operation_id):
        """Guarda y recupera operación con payload complejo"""
        complex_payload = {
            "reservation": {
                "hotel_id": 123,
                "check_in": "2026-03-01",
                "nights": 5,
                "rooms": [
                    {"type": "deluxe", "quantity": 2, "price": 150.00},
                    {"type": "standard", "quantity": 1, "price": 80.00},
                ],
            },
            "guest": {"name": "John Doe", "email": "john@example.com"},
            "price_breakdown": {"subtotal": 380.0, "tax": 38.0, "total": 418.0},
        }

        op = Operation.pending(sample_operation_id, "reserve", complex_payload)
        save_operation(op)

        retrieved = get_operation(sample_operation_id)
        assert retrieved.payload == complex_payload
        assert retrieved.payload["reservation"]["hotel_id"] == 123


class TestPingEchoLog:
    """Tests para log de Ping/Echo"""

    def test_log_echo(self, initialized_db):
        """Registra un echo en SQLite"""
        service = "worker"
        request_id = "ping-001"
        status = "UP"
        ts = datetime.utcnow().isoformat() + "Z"

        log_echo(service, request_id, status, ts)

        last = get_last_echo(service)
        assert last is not None
        assert last.service == service
        assert last.request_id == request_id
        assert last.status == status
        assert last.timestamp == ts

    def test_get_last_echo_nonexistent_service(self, initialized_db):
        """Intenta obtener echo de servicio sin registros"""
        result = get_last_echo("nonexistent_service")
        assert result is None

    def test_get_recent_echoes(self, initialized_db):
        """Recupera múltiples ecos recientes"""
        service = "api"
        base_time = datetime.utcnow()

        # Registra 5 ecos
        for i in range(5):
            from datetime import timedelta

            ts = (base_time + timedelta(seconds=i)).isoformat() + "Z"
            log_echo(service, f"ping-{i:03d}", "UP", ts)

        echoes = get_recent_echoes(service, limit=3)
        assert len(echoes) == 3
        assert all(e.service == service for e in echoes)
        # Verifica que están en orden descendente (más recientes primero)
        assert echoes[0].request_id == "ping-004"
        assert echoes[2].request_id == "ping-002"

    def test_echo_with_unhealthy_status(self, initialized_db):
        """Registra echo con estado UNHEALTHY"""
        log_echo("worker", "ping-unhealthy", "UNHEALTHY", datetime.utcnow().isoformat() + "Z")

        last = get_last_echo("worker")
        assert last.status == "UNHEALTHY"



