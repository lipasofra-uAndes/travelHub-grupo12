from flask import Flask, request
from flask_restful import Api, Resource
import logging
from uuid import uuid4

app = Flask(__name__)
api = Api(app)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Almacenamiento de datos mock - Propiedades/Hospedajes
propiedades_db = [
    {
        "id": str(uuid4()),
        "nombre": "Hotel Central",
        "pais": "Argentina",
        "direccion": "Av. Corrientes 123, Buenos Aires"
    },
    {
        "id": str(uuid4()),
        "nombre": "Hostal Andino",
        "pais": "Chile",
        "direccion": "Calle Lastarria 50, Santiago"
    },
    {
        "id": str(uuid4()),
        "nombre": "Posada del Viajero",
        "pais": "Perú",
        "direccion": "Jr. Pachacutec 200, Lima"
    },
    {
        "id": str(uuid4()),
        "nombre": "Casa Paraíso",
        "pais": "Colombia",
        "direccion": "Carrera 7 No. 45-100, Bogotá"
    },
]


class Search(Resource):
    """Maneja solicitudes de búsqueda"""
    def get(self):
        try:
            query = request.args.get('q', '').lower()
            
            if not query:
                return {
                    "success": True,
                    "query": query,
                    "resultados": propiedades_db,
                    "cantidad": len(propiedades_db)
                }, 200
            
            # Filtrar resultados basados en la búsqueda (nombre, país, dirección)
            resultados = [
                propiedad for propiedad in propiedades_db
                if query in propiedad['nombre'].lower() 
                or query in propiedad['pais'].lower() 
                or query in propiedad['direccion'].lower()
            ]
            
            logger.info(f"Búsqueda (GET): '{query}' - Se encontraron {len(resultados)} resultados")
            
            return {
                "success": True,
                "query": query,
                "resultados": resultados,
                "cantidad": len(resultados)
            }, 200
        except Exception as e:
            logger.error(f"Error en servicio de búsqueda (GET): {str(e)}")
            return {"error": str(e)}, 500


class Health(Resource):
    """Health check del servicio de búsqueda"""
    def get(self):
        return {"status": "UP", "service": "Search"}, 200


class Ready(Resource):
    """Ready check - indica si el servicio puede aceptar solicitudes"""
    def get(self):
        # Verificar que el servicio está listo para procesar
        return {
            "status": "READY",
            "service": "Search",
            "message": "Service ready to accept requests"
        }, 200


# Registrar recursos
api.add_resource(Search, '/search')
api.add_resource(Health, '/health')
api.add_resource(Ready, '/ready')


if __name__ == '__main__':
    logger.info("Iniciando servicio de búsqueda en puerto 5003")
    app.run(host='0.0.0.0', port=5003, debug=False)
