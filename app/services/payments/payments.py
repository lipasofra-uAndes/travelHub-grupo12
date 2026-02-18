from flask import Flask, request
from flask_restful import Api, Resource
import logging
from datetime import datetime

app = Flask(__name__)
api = Api(app)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Mock data storage
payments_db = []


class Pay(Resource):
    """Handle payment requests"""
    def post(self):
        try:
            data = request.get_json()
            
            # Validate required fields
            required_fields = ['user_id', 'amount', 'method']
            for field in required_fields:
                if field not in data:
                    return {"error": f"Missing required field: {field}"}, 400
            
            # Validate amount
            try:
                amount = float(data.get('amount'))
                if amount <= 0:
                    return {"error": "Amount must be greater than 0"}, 400
            except (ValueError, TypeError):
                return {"error": "Invalid amount format"}, 400
            
            # Create payment object
            payment = {
                "id": len(payments_db) + 1,
                "user_id": data.get('user_id'),
                "amount": amount,
                "method": data.get('method'),
                "status": "SUCCESSFUL",
                "created_at": datetime.now().isoformat()
            }
            
            payments_db.append(payment)
            logger.info(f"Payment processed: {payment}")
            
            return {
                "success": True,
                "message": "Payment processed successfully",
                "payment": payment
            }, 201
            
        except Exception as e:
            logger.error(f"Error in payments service: {str(e)}")
            return {"error": str(e)}, 500


class Health(Resource):
    """Health check for payments service"""
    def get(self):
        return {"status": "UP", "service": "Payments"}, 200


# Registrar recursos
api.add_resource(Pay, '/pay')
api.add_resource(Health, '/health')


if __name__ == '__main__':
    logger.info("Starting Payments Service on port 5002")
    app.run(host='0.0.0.0', port=5002, debug=False)
