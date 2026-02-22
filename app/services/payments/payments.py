from flask import Flask, request
from flask_restful import Api, Resource
import logging
from datetime import datetime
from uuid import uuid4

app = Flask(__name__)
api = Api(app)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Almacenamiento de datos mock
payments_db = []


class Pay(Resource):
    """Maneja solicitudes de pago"""
    def post(self):
        try:
            data = request.get_json()
            
            # Validar campos requeridos
            required_fields = ['monto', 'moneda', 'token']
            for field in required_fields:
                if field not in data:
                    return {"error": f"Missing required field: {field}"}, 400
            
            # Validar monto
            try:
                monto = float(data.get('monto'))
                if monto <= 0:
                    return {"error": "Monto debe ser mayor a 0"}, 400
            except (ValueError, TypeError):
                return {"error": "Formato de monto inválido"}, 400
            
            # Crear transacción de pago
            transaccion = {
                "id": str(uuid4()),
                "monto": monto,
                "moneda": data.get('moneda'),
                "estado": "EXITOSA",
                "token": data.get('token'),
                "creadaEn": datetime.now().isoformat()
            }
            
            payments_db.append(transaccion)
            logger.info(f"Pago procesado: {transaccion}")
            
            return {
                "success": True,
                "message": "Pago procesado exitosamente",
                "transaccion": transaccion
            }, 201
            
        except Exception as e:
            logger.error(f"Error en servicio de pagos: {str(e)}")
            return {"error": str(e)}, 500


class Health(Resource):
    """Health check del servicio de pagos"""
    def get(self):
        return {"status": "UP", "service": "Payments"}, 200


class Ready(Resource):
    """Ready check - indica si el servicio puede aceptar solicitudes"""
    def get(self):
        # Verificar que el servicio está listo para procesar
        return {
            "status": "READY",
            "service": "Payments",
            "message": "Service ready to accept requests"
        }, 200


# Registrar recursos
api.add_resource(Pay, '/pay')
api.add_resource(Health, '/health')
api.add_resource(Ready, '/ready')


if __name__ == '__main__':
    logger.info("Iniciando servicio de pagos en puerto 5002")
    app.run(host='0.0.0.0', port=5002, debug=False)
