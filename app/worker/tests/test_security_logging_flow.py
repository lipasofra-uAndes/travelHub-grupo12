"""Tests unitarios para flujo de seguridad/auditoria entre gateway y monitor."""

from unittest.mock import patch

from app.api_gateway.gateway import app as gateway_app, UpdateRatesOperation
from app.monitor.monitor_service import consume_security_log


class TestAuthorizationStub:
    """Tests del stub de autorizacion temporal."""

    def test_esta_autorizado_todo_stub_returns_false(self):
        """El stub de autorizacion debe retornar False para forzar flujo de denegacion."""
        resource = UpdateRatesOperation()
        assert resource._estaAutorizado("Bearer token", "123") is False


class TestGatewayDeniedFlow:
    """Tests del flujo denied que dispara _generateLog."""

    def test_update_rates_denied_calls_generate_log(self):
        """PUT a /tarifas/<hotel_id> debe responder 403 y encolar log de denegacion."""
        client = gateway_app.test_client()

        with patch.object(UpdateRatesOperation, "_generateLog") as mock_generate_log:
            response = client.put(
                "/tarifas/101",
                json={"rates": [{"roomType": "std", "value": 150}]},
                headers={"Authorization": "Bearer fake-token"},
            )

        assert response.status_code == 403
        body = response.get_json()
        assert body["error"] == "No autorizado"

        mock_generate_log.assert_called_once_with(
            action="UPDATE_RATES_DENIED",
            hotel_id="101",
            status="FORBIDDEN",
            http_code=403,
            message="Usuario no autorizado para modificar tarifas de este hotel",
            operation_data=None,
        )


class TestMonitorSecurityLogConsumer:
    """Tests unitarios del consumidor de seguridad en monitoreo."""

    @patch("app.monitor.monitor_service.logger.info")
    @patch("app.monitor.monitor_service.logger.warning")
    def test_consume_security_log_generates_model_logs(self, mock_warning, mock_info):
        """Consume mensaje y genera logs para SecurityViolationEvent y AuditLogEntry."""
        payload = {
            "event_id": "evt-001",
            "timestamp": "2026-03-12T12:00:00Z",
            "user_id": "user-001",
            "token_hotel_id": 10,
            "requested_hotel_id": 20,
            "endpoint": "/tarifas/20",
            "method": "PUT",
            "ip_address": "127.0.0.1",
            "action": "TARIFF_UPDATE",
            "log_id": "log-001",
            "status": "FORBIDDEN",
            "http_code": 403,
            "message": "Denied",
        }

        result = consume_security_log(**payload)

        assert result == {"processed": True, "event_id": "evt-001"}
        assert mock_warning.called
        assert mock_info.called
