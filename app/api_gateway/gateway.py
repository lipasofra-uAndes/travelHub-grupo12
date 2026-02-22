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
from app.constants.queues import TASK_PROCESS_OPERATION, OPERATIONS_QUEUE, TASK_PING_WORKER, PING_QUEUE

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


# Registrar recursos
api.add_resource(Health, '/health')
api.add_resource(Ready, '/ready')
api.add_resource(ReserveOperation, '/reserve')
api.add_resource(PayOperation, '/pay')
api.add_resource(SearchOperation, '/search')
api.add_resource(OperationStatus, '/ops/<operation_id>')
api.add_resource(PingApi, '/ping')


if __name__ == '__main__':
    logger.info("Iniciando API Gateway en puerto 5000")
    app.run(host='0.0.0.0', port=5000, debug=False)
