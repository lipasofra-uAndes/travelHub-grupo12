from flask import Flask
from flask_restful import Api, Resource
from flask import request
import requests
import logging

app = Flask(__name__)
api = Api(app)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# URLs de los microservicios
RESERVES_SERVICE = "http://localhost:5001"
PAYMENTS_SERVICE = "http://localhost:5002"
SEARCH_SERVICE = "http://localhost:5003"


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


class Reserve(Resource):
    """Proxy de solicitudes al servicio de reservas"""
    def post(self):
        try:
            data = request.get_json()
            response = requests.post(f"{RESERVES_SERVICE}/reserve", json=data, timeout=5)
            return response.json(), response.status_code
        except requests.exceptions.RequestException as e:
            logger.error(f"Error al llamar al servicio de reservas: {str(e)}")
            return {"error": "Servicio de reservas no disponible"}, 503


class Pay(Resource):
    """Proxy de solicitudes al servicio de pagos"""
    def post(self):
        try:
            data = request.get_json()
            response = requests.post(f"{PAYMENTS_SERVICE}/pay", json=data, timeout=5)
            return response.json(), response.status_code
        except requests.exceptions.RequestException as e:
            logger.error(f"Error al llamar al servicio de pagos: {str(e)}")
            return {"error": "Servicio de pagos no disponible"}, 503


class Search(Resource):
    """Proxy de solicitudes al servicio de búsqueda"""
    def get(self):
        try:
            params = request.args
            response = requests.get(f"{SEARCH_SERVICE}/search", params=params, timeout=5)
            return response.json(), response.status_code
        except requests.exceptions.RequestException as e:
            logger.error(f"Error al llamar al servicio de búsqueda: {str(e)}")
            return {"error": "Servicio de búsqueda no disponible"}, 503



# Registrar recursos
api.add_resource(Health, '/health')
api.add_resource(Ready, '/ready')
api.add_resource(Reserve, '/reserve')
api.add_resource(Pay, '/pay')
api.add_resource(Search, '/search')


if __name__ == '__main__':
    logger.info("Iniciando API Gateway en puerto 5000")
    app.run(host='0.0.0.0', port=5000, debug=False)
