import os
import sqlite3
import tempfile
from datetime import datetime
from unittest.mock import patch

import pytest


@pytest.fixture(scope="session")
def temp_db_dir():
    """Crea directorio temporal para base de datos de test"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def test_db_path(temp_db_dir):
    """Ruta a base de datos temporal para cada test"""
    db_file = os.path.join(temp_db_dir, "test_operations.db")
    yield db_file
    # Limpieza
    if os.path.exists(db_file):
        os.remove(db_file)


@pytest.fixture
def mock_db_env(test_db_path, monkeypatch):
    """Configura variable de entorno para usar DB temporal"""
    monkeypatch.setenv("SQLITE_DB_PATH", test_db_path)
    yield test_db_path


@pytest.fixture
def initialized_db(mock_db_env):
    """Base de datos temporal inicializada"""
    from app.worker.db import init_db

    init_db()
    return mock_db_env


@pytest.fixture
def sample_operation_id():
    """ID de operación para tests"""
    return "op-test-001"


@pytest.fixture
def sample_operation_data():
    """Datos de ejemplo para operación"""
    return {
        "type": "pay",
        "payload": {"amount": 100.0, "currency": "ARS", "card_token": "tok_test"},
    }


@pytest.fixture
def sample_ping_request_data():
    """Datos de ejemplo para ping"""
    return {
        "request_id": "ping-test-001",
        "service": "worker",
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }


@pytest.fixture
def celery_config():
    """Configuración de Celery para tests"""
    return {
        "broker_url": "memory://",
        "result_backend": "cache+memory://",
        "task_serializer": "json",
        "accept_content": ["json"],
        "result_serializer": "json",
        "timezone": "UTC",
        "enable_utc": True,
    }


@pytest.fixture
def celery_app_for_testing(celery_config):
    """App Celery configurada para tests"""
    from celery import Celery

    app = Celery("test_worker")
    app.conf.update(celery_config)
    return app
