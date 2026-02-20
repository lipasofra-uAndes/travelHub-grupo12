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
reserves_db = []


class Reserve(Resource):
    """Maneja solicitudes de reserva"""
    def post(self):
        try:
            data = request.get_json()
            
            # Validar campos requeridos
            required_fields = ['total', 'moneda']
            for field in required_fields:
                if field not in data:
                    return {"error": f"Campo requerido faltante: {field}"}, 400
            
            # Crear objeto de reserva
            reservation = {
                "id": str(uuid4()),
                "estado": "CONFIRMADA",
                "total": data.get('total'),
                "moneda": data.get('moneda'),
                "creadaEn": datetime.now().isoformat()
            }
            
            reserves_db.append(reservation)
            logger.info(f"Reserva creada: {reservation}")
            
            return {
                "success": True,
                "message": "Reserva confirmada",
                "reserva": reservation
            }, 201
            
        except Exception as e:
            logger.error(f"Error en servicio de reservas: {str(e)}")
            return {"error": str(e)}, 500


class Health(Resource):
    """Health check del servicio de reservas"""
    def get(self):
        return {"status": "UP", "service": "Reserves"}, 200


# Registrar recursos
api.add_resource(Reserve, '/reserve')
api.add_resource(Health, '/health')


if __name__ == '__main__':
    logger.info("Iniciando servicio de reservas en puerto 5001")
    app.run(host='0.0.0.0', port=5001, debug=False)
