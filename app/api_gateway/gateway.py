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
    """Health check endpoint"""
    def get(self):
        return {
            "status": "UP",
            "service": "API Gateway"
        }, 200


class Ready(Resource):
    """Readiness check endpoint"""
    def get(self):
        return {
            "status": "READY",
            "service": "API Gateway",
            "message": "API Gateway is ready to accept requests"
        }, 200


class Reserve(Resource):
    """Proxy requests to reserves service"""
    def post(self):
        try:
            data = request.get_json()
            response = requests.post(f"{RESERVES_SERVICE}/reserve", json=data, timeout=5)
            return response.json(), response.status_code
        except requests.exceptions.RequestException as e:
            logger.error(f"Error calling reserves service: {str(e)}")
            return {"error": "Reserves service unavailable"}, 503


class Pay(Resource):
    """Proxy requests to payments service"""
    def post(self):
        try:
            data = request.get_json()
            response = requests.post(f"{PAYMENTS_SERVICE}/pay", json=data, timeout=5)
            return response.json(), response.status_code
        except requests.exceptions.RequestException as e:
            logger.error(f"Error calling payments service: {str(e)}")
            return {"error": "Payments service unavailable"}, 503


class Search(Resource):
    """Proxy requests to search service"""
    def get(self):
        try:
            params = request.args
            response = requests.get(f"{SEARCH_SERVICE}/search", params=params, timeout=5)
            return response.json(), response.status_code
        except requests.exceptions.RequestException as e:
            logger.error(f"Error calling search service: {str(e)}")
            return {"error": "Search service unavailable"}, 503



# Registrar recursos
api.add_resource(Health, '/health')
api.add_resource(Ready, '/ready')
api.add_resource(Reserve, '/reserve')
api.add_resource(Pay, '/pay')
api.add_resource(Search, '/search')


if __name__ == '__main__':
    logger.info("Starting API Gateway on port 5000")
    app.run(host='0.0.0.0', port=5000, debug=False)
