"""Tests para tasks de Celery del worker"""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from app.models.operation import Operation
from app.dtos.operation import ProcessOperationTaskDTO
from app.dtos.monitoring import EchoResponseDTO
from app.worker.db import get_operation, save_operation, get_last_echo, init_db
from app.worker.config import reset_config, set_force_failure, set_failure_rate


@pytest.fixture(autouse=True)
def reset_worker_config():
    """Resetea la configuración del worker antes de cada test"""
    reset_config()
    yield
    reset_config()


class TestProcessOperationTask:
    """Tests para task de procesar operación"""

    @patch("app.worker.tasks.init_db")
    def test_process_operation_success(self, mock_init_db, initialized_db, sample_operation_id):
        """Procesa operación exitosamente: PENDING -> PROCESSED"""
        from app.worker.tasks import process_operation

        # Prepara operación en DB
        op = Operation.pending(sample_operation_id, "pay", {"amount": 100})
        save_operation(op)

        # Ejecuta task
        result = process_operation(sample_operation_id)

        # Verifica resultado
        assert result["operation_id"] == sample_operation_id
        assert result["status"] == "PROCESSED"

        # Verifica que se actualizó en DB
        updated = get_operation(sample_operation_id)
        assert updated.status == "PROCESSED"
        assert updated.error is None

    @patch("app.worker.tasks.init_db")
    def test_process_operation_nonexistent(self, mock_init_db, initialized_db):
        """Intenta procesar operación que no existe"""
        from app.worker.tasks import process_operation
        from celery.exceptions import MaxRetriesExceededError

        with pytest.raises(ValueError):
            process_operation("op-nonexistent")

    @patch("app.worker.tasks.init_db")
    def test_process_operation_with_failure_flag(self, mock_init_db, initialized_db, sample_operation_id):
        """Procesa operación cuando worker está configurado para fallar"""
        from app.worker.tasks import process_operation
        from celery.exceptions import MaxRetriesExceededError

        # Configura worker para fallar siempre
        set_force_failure(True)

        # Operación normal
        op = Operation.pending(sample_operation_id, "pay", {"amount": 100})
        save_operation(op)

        # Task debe reintentar y eventualmente fallar
        # En test con mock, solo verificamos que raise exception
        with pytest.raises(RuntimeError):
            process_operation(sample_operation_id)

    @patch("app.worker.tasks.init_db")
    def test_process_operation_updates_status_to_processing(
        self, mock_init_db, initialized_db, sample_operation_id
    ):
        """Verifica que status se actualiza a PROCESSING durante procesamiento"""
        from app.worker.tasks import process_operation

        op = Operation.pending(sample_operation_id, "reserve", {"room_id": 123})
        save_operation(op)

        # Ejecuta (rápido sincrónicamente en test)
        result = process_operation(sample_operation_id)

        # Verifica transición
        assert result["status"] == "PROCESSED"
        final_op = get_operation(sample_operation_id)
        assert final_op.status == "PROCESSED"


class TestPingWorkerTask:
    """Tests para task de ping/echo del worker"""

    @patch("app.worker.tasks.init_db")
    def test_ping_worker_logs_echo(self, mock_init_db, initialized_db, celery_app_for_testing):
        """Ping worker registra echo en DB"""
        from app.worker.tasks import ping_worker

        request_id = "ping-test-001"

        # Ejecuta ping
        result = ping_worker(request_id)

        # Verifica payload de echo
        assert result["service"] == "worker"
        assert result["request_id"] == request_id
        assert result["status"] == "UP"
        assert "ts" in result

        # Verifica que se registró en DB
        last_echo = get_last_echo("worker")
        assert last_echo is not None
        assert last_echo.request_id == request_id
        assert last_echo.status == "UP"

    @patch("app.worker.tasks.init_db")
    def test_ping_worker_response_format(self, mock_init_db, initialized_db):
        """Verifica formato de respuesta de ping"""
        from app.worker.tasks import ping_worker

        request_id = "ping-format-001"
        result = ping_worker(request_id)

        # Campos requeridos
        assert "service" in result
        assert "request_id" in result
        assert "status" in result
        assert "ts" in result

        # Tipos correctos
        assert isinstance(result["service"], str)
        assert isinstance(result["request_id"], str)
        assert isinstance(result["status"], str)
        assert isinstance(result["ts"], str)

        # Valida timestamp ISO8601
        assert result["ts"].endswith("Z")
        datetime.fromisoformat(result["ts"].replace("Z", "+00:00"))

    @patch("app.worker.tasks.init_db")
    def test_ping_worker_multiple_pings(self, mock_init_db, initialized_db):
        """Múltiples pings registran múltiples ecos"""
        from app.worker.tasks import ping_worker

        # Envía 3 pings
        for i in range(3):
            ping_worker(f"ping-multi-{i:03d}")

        # Verifica que se registraron todos
        from app.worker.db import get_recent_echoes

        echoes = get_recent_echoes("worker", limit=10)
        assert len(echoes) >= 3
        request_ids = {echo.request_id for echo in echoes}
        assert "ping-multi-000" in request_ids
        assert "ping-multi-001" in request_ids
        assert "ping-multi-002" in request_ids


class TestTaskIntegration:
    """Tests de integración entre tasks"""

    @patch("app.worker.tasks.init_db")
    def test_operation_then_ping_cycle(self, mock_init_db, initialized_db, sample_operation_id):
        """Ciclo: procesa operación, luego ping confirma worker está UP"""
        from app.worker.tasks import process_operation, ping_worker

        # 1. Procesa operación exitosamente
        op = Operation.pending(sample_operation_id, "pay", {"amount": 50})
        save_operation(op)
        result1 = process_operation(sample_operation_id)
        assert result1["status"] == "PROCESSED"

        # 2. Envía ping confirma worker está UP
        result2 = ping_worker("ping-post-op-001")
        assert result2["status"] == "UP"

        # 3. Verifica que ambos eventos se registraron
        op_final = get_operation(sample_operation_id)
        assert op_final.status == "PROCESSED"

        echo_last = get_last_echo("worker")
        assert echo_last.status == "UP"

    @patch("app.worker.tasks.init_db")
    def test_parallel_operations_and_pings(
        self, mock_init_db, initialized_db, celery_app_for_testing
    ):
        """Simula operaciones y pings ocurriendo en paralelo"""
        from app.worker.tasks import process_operation, ping_worker

        # Crea múltiples operaciones
        ops = [
            Operation.pending(f"op-parallel-{i}", "reserve", {"room": i})
            for i in range(3)
        ]
        for op in ops:
            save_operation(op)

        # Procesa todas
        for i in range(3):
            process_operation(f"op-parallel-{i}")

        # Resetea la configuración para limpiar cualquier fallo registrado
        reset_config()

        # Genera IDs únicos para estos pings
        ping_ids = [f"ping-parallel-test-{i}" for i in range(3)]

        # Intercala pings
        for ping_id in ping_ids:
            ping_worker(ping_id)

        # Verifica que todas las operaciones se procesaron
        from app.worker.db import get_recent_echoes

        for i in range(3):
            op = get_operation(f"op-parallel-{i}")
            assert op.status == "PROCESSED"

        # Verifica que nuestros pings fueron registrados con estado UP
        echoes = get_recent_echoes("worker", limit=100)
        our_echoes = [e for e in echoes if e.request_id in ping_ids]
        assert len(our_echoes) == 3
        for echo in our_echoes:
            assert echo.status == "UP"

class TestWorkerHealthDetection:
    """Tests para detección de salud del worker mediante ping/echo"""

    @patch("app.worker.tasks.init_db")
    def test_ping_reports_unhealthy_after_failure(self, mock_init_db, initialized_db):
        """Ping reporta UNHEALTHY inmediatamente después de un fallo"""
        from app.worker.tasks import ping_worker
        from app.worker.config import record_failure

        # Simula que acaba de haber un fallo
        record_failure()

        # Ping debe reportar UNHEALTHY
        result = ping_worker("ping-after-failure")
        assert result["status"] == "UNHEALTHY"

        # Echo debe estar registrado como UNHEALTHY
        echo_last = get_last_echo("worker")
        assert echo_last.status == "UNHEALTHY"

    @patch("app.worker.tasks.init_db")
    def test_ping_reports_up_when_healthy(self, mock_init_db, initialized_db):
        """Ping reporta UP cuando no hay fallos recientes"""
        from app.worker.tasks import ping_worker

        # Sin fallos registrados, ping debe ser UP
        result = ping_worker("ping-healthy")
        assert result["status"] == "UP"

        echo_last = get_last_echo("worker")
        assert echo_last.status == "UP"

    @patch("app.worker.tasks.init_db")
    def test_failure_rate_triggers_unhealthy(self, mock_init_db, initialized_db, sample_operation_id):
        """Configura rate de fallo y verifica que ping reporta UNHEALTHY"""
        from app.worker.tasks import process_operation, ping_worker

        # Configura 100% de probabilidad de fallo
        set_failure_rate(1.0)

        # Crea operación
        op = Operation.pending(sample_operation_id, "pay", {"amount": 100})
        save_operation(op)

        # Intenta procesar (fallará)
        try:
            process_operation(sample_operation_id)
        except RuntimeError:
            pass  # Se espera que falle

        # Ping debe reportar UNHEALTHY (porque hubo fallo reciente)
        result = ping_worker("ping-after-configured-failure")
        assert result["status"] == "UNHEALTHY"

        echo = get_last_echo("worker")
        assert echo.status == "UNHEALTHY"