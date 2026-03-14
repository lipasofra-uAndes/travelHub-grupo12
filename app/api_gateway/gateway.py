from flask import Flask
from flask_restful import Api, Resource
from flask import request
import requests
import logging
from datetime import datetime
from uuid import uuid4

# Importar Celery y funciones de BD
from app.worker.celery_app import celery_app
from app.worker.db import get_operation, save_operation, log_echo, init_db
from app.models.operation import Operation
from app.constants.queues import TASK_PROCESS_OPERATION, OPERATIONS_QUEUE, TASK_PING_WORKER, PING_QUEUE, TASK_LOG_RECORD, LOGS_QUEUE
from app.auth.auth_component import estaAutorizado

# Inicializar BD
init_db()

app = Flask(__name__)
api = Api(app)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class Health(Resource):
    """Health check del API Gateway"""
    def get(self):
        return {
            "status": "UP",
            "service": "API Gateway"
        }, 200


class Ready(Resource):
    """Verificación de disponibilidad del API Gateway"""
    def get(self):
        return {
            "status": "READY",
            "service": "API Gateway",
            "message": "API Gateway listo para aceptar solicitudes"
        }, 200


class ReserveOperation(Resource):
    """Encolador de operación de reserva - responde rápido (202)"""
    def post(self):
        try:
            data = request.get_json()
            
            # Validar campos requeridos
            required_fields = ['total', 'moneda']
            for field in required_fields:
                if field not in data:
                    return {"error": f"Campo requerido faltante: {field}"}, 400
            
            # Crear operación en estado PENDING
            operation_id = str(uuid4())
            operation = Operation.pending(operation_id, "reserve", data)
            save_operation(operation)
            
            # Encolar tarea al worker
            celery_app.send_task(
                TASK_PROCESS_OPERATION,
                args=(operation_id,),
                queue=OPERATIONS_QUEUE
            )
            
            logger.info(f"Operación de reserva encolada: {operation_id}")
            
            return {
                "operation_id": operation_id,
                "status": "PENDING",
                "message": "Operación encolada para procesamiento",
                "status_url": f"/ops/{operation_id}"
            }, 202
            
        except Exception as e:
            logger.error(f"Error al encolar reserva: {str(e)}")
            return {"error": str(e)}, 500


class PayOperation(Resource):
    """Encolador de operación de pago - responde rápido (202)"""
    def post(self):
        try:
            data = request.get_json()
            
            # Validar campos requeridos
            required_fields = ['monto', 'moneda', 'token']
            for field in required_fields:
                if field not in data:
                    return {"error": f"Campo requerido faltante: {field}"}, 400
            
            # Validar monto
            try:
                monto = float(data.get('monto'))
                if monto <= 0:
                    return {"error": "Monto debe ser mayor a 0"}, 400
            except (ValueError, TypeError):
                return {"error": "Formato de monto inválido"}, 400
            
            # Crear operación en estado PENDING
            operation_id = str(uuid4())
            operation = Operation.pending(operation_id, "pay", data)
            save_operation(operation)
            
            # Encolar tarea al worker
            celery_app.send_task(
                TASK_PROCESS_OPERATION,
                args=(operation_id,),
                queue=OPERATIONS_QUEUE
            )
            
            logger.info(f"Operación de pago encolada: {operation_id}")
            
            return {
                "operation_id": operation_id,
                "status": "PENDING",
                "message": "Operación encolada para procesamiento",
                "status_url": f"/ops/{operation_id}"
            }, 202
            
        except Exception as e:
            logger.error(f"Error al encolar pago: {str(e)}")
            return {"error": str(e)}, 500


class SearchOperation(Resource):
    """Encolador de operación de búsqueda - responde rápido (202)"""
    def post(self):
        try:
            data = request.get_json()
            
            # Validar campo de búsqueda
            if not data or "query" not in data:
                return {"error": "Campo 'query' requerido"}, 400
            
            # Crear operación en estado PENDING
            operation_id = str(uuid4())
            operation = Operation.pending(operation_id, "search", data)
            save_operation(operation)
            
            # Encolar tarea al worker
            celery_app.send_task(
                TASK_PROCESS_OPERATION,
                args=(operation_id,),
                queue=OPERATIONS_QUEUE
            )
            
            logger.info(f"Operación de búsqueda encolada: {operation_id}")
            
            return {
                "operation_id": operation_id,
                "status": "PENDING",
                "message": "Operación encolada para procesamiento",
                "status_url": f"/ops/{operation_id}"
            }, 202
            
        except Exception as e:
            logger.error(f"Error al encolar búsqueda: {str(e)}")
            return {"error": str(e)}, 500


class OperationStatus(Resource):
    """Consulta el estado de una operación encolada"""
    def get(self, operation_id):
        try:
            operation = get_operation(operation_id)
            
            if operation is None:
                return {"error": f"Operación {operation_id} no encontrada"}, 404
            
            return {
                "operation_id": operation.id,
                "type": operation.type,
                "status": operation.status,
                "error": operation.error,
                "created_at": operation.created_at,
                "updated_at": operation.updated_at
            }, 200
            
        except Exception as e:
            logger.error(f"Error al consultar operación: {str(e)}")
            return {"error": str(e)}, 500


class PingApi(Resource):
    """Responde a PING del monitor con ECHO"""
    def post(self):
        try:
            data = request.get_json() or {}
            request_id = data.get("request_id", str(uuid4()))
            
            # Registrar echo en BD
            ts = datetime.utcnow().isoformat() + "Z"
            log_echo(service="api", request_id=request_id, status="UP", ts=ts)
            
            payload = {
                "service": "api",
                "request_id": request_id,
                "status": "UP",
                "ts": ts
            }
            
            logger.info(f"API respondió a PING: {request_id}")
            
            # Enviar echo a la cola de monitoreo (el monitor lo recibirá)
            # Por ahora solo respondemos HTTP
            
            return payload, 200
            
        except Exception as e:
            logger.error(f"Error en ping/echo de API: {str(e)}")
            return {"error": str(e)}, 500


class UpdateRatesOperation(Resource):
    """
    Endpoint PUT para modificación de tarifas con validación de acceso por hotelId.
    Valida que el usuario autenticado solo pueda modificar tarifas de su propio hotel.
    Rechaza con HTTP 403 si intenta acceder a otro hotel.
    """
    def put(self, hotel_id):
        try:
            data = request.get_json()
            
            # Validar campos requeridos
            if not data or "rates" not in data:
                return {"error": "Campo 'rates' requerido en el body"}, 400
            
            auth_header = request.headers.get('Authorization', '')
            
            auth_result = self._estaAutorizado(auth_header, hotel_id)

            if not auth_result["authorized"]:
                # Registrar intento de acceso no autorizado
                # generateLog() maneja el encolado del log a la cola
                self._generateLog(
                    action="UPDATE_RATES_DENIED",
                    hotel_id=hotel_id,
                    status="FORBIDDEN",
                    http_code=403,
                    message="Usuario no autorizado para modificar tarifas de este hotel",
                    operation_data=None,
                    user_id=auth_result["user_id"],
                    token_hotel_id=auth_result["token_hotel_id"],
                )
                
                logger.warning(f"Intento de acceso no autorizado a tarifas del hotel {hotel_id}")
                return {
                    "error": "No autorizado",
                    "message": "No tienes permiso para modificar las tarifas de este hotel"
                }, 403
            
            # Crear operación en estado PENDING
            operation_id = str(uuid4())
            operation = Operation.pending(operation_id, "update_rates", {
                "hotel_id": hotel_id,
                "rates": data.get('rates')
            })
            save_operation(operation)
            
            # generateLog() encola tanto el log como la operación (si está autorizada)
            # Pasar operation_id para que generateLog() encole la operación a OPERATIONS_QUEUE
            self._generateLog(
                action="UPDATE_RATES_STARTED",
                hotel_id=hotel_id,
                status="AUTHORIZED",
                http_code=202,
                message="Solicitud de modificación de tarifas autorizada y encolada",
                operation_data={"operation_id": operation_id},
                user_id=auth_result["user_id"],
                token_hotel_id=auth_result["token_hotel_id"],
            )
            
            logger.info(f"Operación de actualización de tarifas encolada: {operation_id} para hotel {hotel_id}")
            
            return {
                "operation_id": operation_id,
                "status": "PENDING",
                "message": "Operación de actualización de tarifas encolada para procesamiento",
                "status_url": f"/ops/{operation_id}"
            }, 202
            
        except Exception as e:
            logger.error(f"Error al procesar actualización de tarifas: {str(e)}")
            self._generateLog(
                action="UPDATE_RATES_ERROR",
                hotel_id=hotel_id,
                status="ERROR",
                http_code=500,
                message=f"Error interno: {str(e)}"
            )
            return {"error": str(e)}, 500

    def _estaAutorizado(self, auth_header: str, hotel_id: str) -> dict:
        """
        Valida el JWT del header Authorization y verifica que el hotel_id
        del token coincida con el hotel_id solicitado.
        """
        if not auth_header or not auth_header.startswith("Bearer "):
            return {
                "authorized": False,
                "user_id": None,
                "token_hotel_id": None,
                "error": "Header Authorization ausente o formato inválido",
            }

        token = auth_header[len("Bearer "):]
        return estaAutorizado(token, hotel_id)

    def _generateLog(
        self,
        action: str,
        hotel_id: str,
        status: str,
        http_code: int,
        message: str,
        operation_data: dict = None,
        user_id: str = None,
        token_hotel_id: str = None,
    ) -> dict:
        """
        Construye un JSON de auditoría y lo publica en LOGS_QUEUE mediante Celery.

        El worker consumirá este mensaje a través de la tarea TASK_LOG_RECORD
        (app.audit.audit_service.log_record).

        El payload incluye todos los campos necesarios para construir:
          - SecurityViolationEvent (event_id, timestamp, user_id, token_hotel_id,
                                    requested_hotel_id, endpoint, method, ip_address, action)
          - AuditLogEntry          (log_id, event_id, status, http_code, message, payload completo)
        """
        event_id = str(uuid4())
        timestamp = datetime.utcnow().isoformat() + "Z"

        payload = {
            # --- SecurityViolationEvent ---
            "event_id": event_id,
            "timestamp": timestamp,
            "user_id": user_id,
            "token_hotel_id": token_hotel_id,
            "requested_hotel_id": hotel_id,
            "endpoint": request.path,
            "method": request.method,
            "ip_address": request.remote_addr,
            "action": action,

            # --- AuditLogEntry ---
            "log_id": event_id,          # id del registro de auditoría
            "status": status,
            "http_code": http_code,
            "message": message,
        }

        if operation_data:
            payload["operation_data"] = operation_data

        celery_app.send_task(
            TASK_LOG_RECORD,
            kwargs=payload,
            queue=LOGS_QUEUE,
        )

        logger.info(
            f"[AUDIT] Log encolado: event_id={event_id} | action={action} "
            f"| requested_hotel_id={hotel_id} | status={status} | http_code={http_code}"
        )
        return payload


# Registrar recursos
api.add_resource(Health, '/health')
api.add_resource(Ready, '/ready')
api.add_resource(ReserveOperation, '/reserve')
api.add_resource(PayOperation, '/pay')
api.add_resource(SearchOperation, '/search')
api.add_resource(UpdateRatesOperation, '/tarifas/<hotel_id>')
api.add_resource(OperationStatus, '/ops/<operation_id>')
api.add_resource(PingApi, '/ping')


if __name__ == '__main__':
    logger.info("Iniciando API Gateway en puerto 5000")
    app.run(host='0.0.0.0', port=5000, debug=False)
