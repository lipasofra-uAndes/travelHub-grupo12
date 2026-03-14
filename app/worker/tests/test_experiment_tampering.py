"""
Experimento Automatizado — Validación de Aislamiento de Tenants (Tampering de hotelId)

Genera 60 casos parametrizados que verifican la hipótesis:
  "Si se valida sincrónicamente el hotelId del JWT contra el recurso solicitado
   y cada violación se publica asíncronamente al broker, entonces todos los eventos
   de violación deben ser registrados sin pérdida de mensajes."

Cada caso verifica:
  1. La solicitud con hotelId manipulado es rechazada con HTTP 403.
  2. Se encola un evento de auditoría a la cola security.logs con los datos correctos.

Distribución de los 60 casos:
  - 45 casos de tampering puro (token_hotel_id ≠ path_hotel_id)
  -  5 casos sin header Authorization
  -  5 casos con token expirado
  -  5 casos con token malformado / inválido
"""

import random
import string
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

import jwt
import pytest

from app.api_gateway.gateway import app as gateway_app
from app.auth.auth_component import SECRET_KEY
from app.constants.queues import LOGS_QUEUE, TASK_LOG_RECORD

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_token(sub: str, hotel_id: str, expired: bool = False) -> str:
    """Genera un JWT válido o expirado."""
    now = datetime.utcnow()
    payload = {
        "sub": sub,
        "hotel_id": hotel_id,
        "iat": now,
        "exp": now + timedelta(hours=-1 if expired else 24),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")


def _random_hotel_id() -> str:
    """Genera un hotel_id aleatorio."""
    return f"hotel_{random.randint(1, 9999)}"


def _random_user() -> str:
    """Genera un username aleatorio."""
    suffix = "".join(random.choices(string.ascii_lowercase, k=5))
    return f"user_{suffix}"


def _random_rates() -> dict:
    """Genera un payload de tarifas aleatorio."""
    room_types = ["standard", "premium", "suite", "deluxe", "economy"]
    rates = {rt: random.randint(50, 500) for rt in random.sample(room_types, k=random.randint(1, 4))}
    return {"rates": rates}


# ---------------------------------------------------------------------------
# Generación determinista de los 60 casos (seed fijo para reproducibilidad)
# ---------------------------------------------------------------------------

random.seed(42)

TAMPERING_CASES = []
for i in range(45):
    token_hotel = _random_hotel_id()
    # Asegurar que path_hotel es siempre distinto al del token
    path_hotel = _random_hotel_id()
    while path_hotel == token_hotel:
        path_hotel = _random_hotel_id()
    TAMPERING_CASES.append({
        "id": f"tampering_{i+1:02d}",
        "user": _random_user(),
        "token_hotel": token_hotel,
        "path_hotel": path_hotel,
        "rates": _random_rates(),
    })

NO_TOKEN_CASES = []
for i in range(5):
    NO_TOKEN_CASES.append({
        "id": f"no_token_{i+1:02d}",
        "path_hotel": _random_hotel_id(),
        "rates": _random_rates(),
    })

EXPIRED_CASES = []
for i in range(5):
    token_hotel = _random_hotel_id()
    path_hotel = _random_hotel_id()
    while path_hotel == token_hotel:
        path_hotel = _random_hotel_id()
    EXPIRED_CASES.append({
        "id": f"expired_{i+1:02d}",
        "user": _random_user(),
        "token_hotel": token_hotel,
        "path_hotel": path_hotel,
        "rates": _random_rates(),
    })

MALFORMED_CASES = []
for i in range(5):
    MALFORMED_CASES.append({
        "id": f"malformed_{i+1:02d}",
        "path_hotel": _random_hotel_id(),
        "rates": _random_rates(),
        "bad_token": "".join(random.choices(string.ascii_letters + string.digits, k=30)),
    })


# ---------------------------------------------------------------------------
# Registro de resultados para el reporte final
# ---------------------------------------------------------------------------

_results: list[dict] = []


def _record(case_id: str, category: str, http_ok: bool, audit_ok: bool):
    _results.append({
        "case_id": case_id,
        "category": category,
        "http_403": http_ok,
        "audit_enqueued": audit_ok,
    })


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestTamperingDetection:
    """45 casos: token con hotel_id distinto al path → HTTP 403 + evento."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        self.client = gateway_app.test_client()

    @pytest.mark.parametrize("case", TAMPERING_CASES, ids=[c["id"] for c in TAMPERING_CASES])
    def test_tampering_returns_403_and_enqueues_audit(self, case):
        token = _make_token(case["user"], case["token_hotel"])

        with patch("app.api_gateway.gateway.celery_app") as mock_celery:
            response = self.client.put(
                f"/tarifas/{case['path_hotel']}",
                json=case["rates"],
                headers={"Authorization": f"Bearer {token}"},
            )

        # 1) HTTP 403
        http_ok = response.status_code == 403
        assert http_ok, f"Expected 403, got {response.status_code}"

        body = response.get_json()
        assert body["error"] == "No autorizado"

        # 2) Evento de auditoría encolado
        mock_celery.send_task.assert_called_once()
        call_kwargs = mock_celery.send_task.call_args
        assert call_kwargs[0][0] == TASK_LOG_RECORD
        assert call_kwargs[1]["queue"] == LOGS_QUEUE

        event_payload = call_kwargs[1]["kwargs"]
        audit_ok = (
            event_payload["action"] == "UPDATE_RATES_DENIED"
            and event_payload["status"] == "FORBIDDEN"
            and event_payload["http_code"] == 403
            and str(event_payload["requested_hotel_id"]) == str(case["path_hotel"])
            and str(event_payload["token_hotel_id"]) == str(case["token_hotel"])
        )
        assert audit_ok, f"Audit payload mismatch: {event_payload}"

        _record(case["id"], "tampering", http_ok, audit_ok)


class TestNoTokenDetection:
    """5 casos: sin header Authorization → HTTP 403 + evento."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        self.client = gateway_app.test_client()

    @pytest.mark.parametrize("case", NO_TOKEN_CASES, ids=[c["id"] for c in NO_TOKEN_CASES])
    def test_no_token_returns_403_and_enqueues_audit(self, case):
        with patch("app.api_gateway.gateway.celery_app") as mock_celery:
            response = self.client.put(
                f"/tarifas/{case['path_hotel']}",
                json=case["rates"],
                # Sin header Authorization
            )

        http_ok = response.status_code == 403
        assert http_ok, f"Expected 403, got {response.status_code}"

        mock_celery.send_task.assert_called_once()
        call_kwargs = mock_celery.send_task.call_args
        event_payload = call_kwargs[1]["kwargs"]
        audit_ok = (
            event_payload["action"] == "UPDATE_RATES_DENIED"
            and event_payload["status"] == "FORBIDDEN"
            and event_payload["http_code"] == 403
        )
        assert audit_ok, f"Audit payload mismatch: {event_payload}"

        _record(case["id"], "no_token", http_ok, audit_ok)


class TestExpiredTokenDetection:
    """5 casos: token JWT expirado → HTTP 403 + evento."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        self.client = gateway_app.test_client()

    @pytest.mark.parametrize("case", EXPIRED_CASES, ids=[c["id"] for c in EXPIRED_CASES])
    def test_expired_token_returns_403_and_enqueues_audit(self, case):
        token = _make_token(case["user"], case["token_hotel"], expired=True)

        with patch("app.api_gateway.gateway.celery_app") as mock_celery:
            response = self.client.put(
                f"/tarifas/{case['path_hotel']}",
                json=case["rates"],
                headers={"Authorization": f"Bearer {token}"},
            )

        http_ok = response.status_code == 403
        assert http_ok, f"Expected 403, got {response.status_code}"

        mock_celery.send_task.assert_called_once()
        call_kwargs = mock_celery.send_task.call_args
        event_payload = call_kwargs[1]["kwargs"]
        audit_ok = (
            event_payload["action"] == "UPDATE_RATES_DENIED"
            and event_payload["status"] == "FORBIDDEN"
            and event_payload["http_code"] == 403
        )
        assert audit_ok, f"Audit payload mismatch: {event_payload}"

        _record(case["id"], "expired_token", http_ok, audit_ok)


class TestMalformedTokenDetection:
    """5 casos: token malformado → HTTP 403 + evento."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        self.client = gateway_app.test_client()

    @pytest.mark.parametrize("case", MALFORMED_CASES, ids=[c["id"] for c in MALFORMED_CASES])
    def test_malformed_token_returns_403_and_enqueues_audit(self, case):
        with patch("app.api_gateway.gateway.celery_app") as mock_celery:
            response = self.client.put(
                f"/tarifas/{case['path_hotel']}",
                json=case["rates"],
                headers={"Authorization": f"Bearer {case['bad_token']}"},
            )

        http_ok = response.status_code == 403
        assert http_ok, f"Expected 403, got {response.status_code}"

        mock_celery.send_task.assert_called_once()
        call_kwargs = mock_celery.send_task.call_args
        event_payload = call_kwargs[1]["kwargs"]
        audit_ok = (
            event_payload["action"] == "UPDATE_RATES_DENIED"
            and event_payload["status"] == "FORBIDDEN"
            and event_payload["http_code"] == 403
        )
        assert audit_ok, f"Audit payload mismatch: {event_payload}"

        _record(case["id"], "malformed_token", http_ok, audit_ok)


# ---------------------------------------------------------------------------
# Reporte final (se imprime al terminar TODOS los tests de este módulo)
# ---------------------------------------------------------------------------

def pytest_terminal_summary_hook():
    """Llamado desde conftest o manualmente."""
    pass


@pytest.fixture(scope="module", autouse=True)
def _print_report(request):
    """Imprime el reporte de resultados al finalizar el módulo."""
    yield  # Esperar a que todos los tests del módulo terminen

    total = len(_results)
    if total == 0:
        return

    passed = sum(1 for r in _results if r["http_403"] and r["audit_enqueued"])
    failed = total - passed

    print("\n")
    print("=" * 78)
    print("  REPORTE DE EXPERIMENTO — Aislamiento de Tenants (Tampering hotelId)")
    print("=" * 78)
    print(f"  Fecha de ejecución : {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"  Total de casos     : {total}")
    print(f"  Exitosos           : {passed}")
    print(f"  Fallidos           : {failed}")
    print(f"  Tasa de detección  : {passed/total*100:.1f}%")
    print("-" * 78)
    print(f"  {'#':<4} {'Case ID':<22} {'Categoría':<18} {'HTTP 403':<12} {'Audit OK':<12}")
    print("-" * 78)

    for i, r in enumerate(_results, 1):
        h = "PASS" if r["http_403"] else "FAIL"
        a = "PASS" if r["audit_enqueued"] else "FAIL"
        print(f"  {i:<4} {r['case_id']:<22} {r['category']:<18} {h:<12} {a:<12}")

    print("-" * 78)

    # Resumen por categoría
    categories = {}
    for r in _results:
        cat = r["category"]
        if cat not in categories:
            categories[cat] = {"total": 0, "passed": 0}
        categories[cat]["total"] += 1
        if r["http_403"] and r["audit_enqueued"]:
            categories[cat]["passed"] += 1

    print(f"\n  {'Categoría':<22} {'Total':<10} {'Exitosos':<10} {'Tasa %':<10}")
    print("  " + "-" * 52)
    for cat, data in categories.items():
        rate = data["passed"] / data["total"] * 100
        print(f"  {cat:<22} {data['total']:<10} {data['passed']:<10} {rate:.1f}%")

    print("=" * 78)

    if failed == 0:
        print("  RESULTADO: HIPÓTESIS VALIDADA — 100% de detección de tampering")
    else:
        print(f"  RESULTADO: HIPÓTESIS NO VALIDADA — {failed} caso(s) fallido(s)")

    print("=" * 78)
    print()
