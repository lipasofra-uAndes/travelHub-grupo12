from flask import Flask, request
from flask_restful import Api, Resource
import logging
from datetime import datetime

app = Flask(__name__)
api = Api(app)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Mock data storage
reserves_db = []


class Reserve(Resource):
    """Handle reservation requests"""
    def post(self):
        try:
            data = request.get_json()
            
            # Validate required fields
            required_fields = ['user_id', 'item_id', 'date']
            for field in required_fields:
                if field not in data:
                    return {"error": f"Missing required field: {field}"}, 400
            
            # Create reservation object
            reservation = {
                "id": len(reserves_db) + 1,
                "user_id": data.get('user_id'),
                "item_id": data.get('item_id'),
                "date": data.get('date'),
                "status": "CONFIRMED",
                "created_at": datetime.now().isoformat()
            }
            
            reserves_db.append(reservation)
            logger.info(f"Reservation created: {reservation}")
            
            return {
                "success": True,
                "message": "Reservation confirmed",
                "reservation": reservation
            }, 201
            
        except Exception as e:
            logger.error(f"Error in reserve service: {str(e)}")
            return {"error": str(e)}, 500


class Health(Resource):
    """Health check for reserves service"""
    def get(self):
        return {"status": "UP", "service": "Reserves"}, 200


# Registrar recursos
api.add_resource(Reserve, '/reserve')
api.add_resource(Health, '/health')


if __name__ == '__main__':
    logger.info("Starting Reserves Service on port 5001")
    app.run(host='0.0.0.0', port=5001, debug=False)
