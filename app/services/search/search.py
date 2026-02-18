from flask import Flask, request
from flask_restful import Api, Resource
import logging

app = Flask(__name__)
api = Api(app)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Mock search database
search_db = [
    {"id": 1, "name": "Product A", "description": "Description for product A", "price": 100},
    {"id": 2, "name": "Product B", "description": "Description for product B", "price": 200},
    {"id": 3, "name": "Product C", "description": "Description for product C", "price": 150},
    {"id": 4, "name": "Product D", "description": "Description for product D", "price": 180},
]


class Search(Resource):
    """Handle search requests"""
    def get(self):
        try:
            query = request.args.get('q', '').lower()
            
            if not query:
                return {
                    "success": True,
                    "query": query,
                    "results": search_db,
                    "count": len(search_db)
                }, 200
            
            # Filter results based on query
            results = [
                item for item in search_db
                if query in item['name'].lower() or query in item['description'].lower()
            ]
            
            logger.info(f"Search query (GET): '{query}' - Found {len(results)} results")
            
            return {
                "success": True,
                "query": query,
                "results": results,
                "count": len(results)
            }, 200
        except Exception as e:
            logger.error(f"Error in search service (GET): {str(e)}")
            return {"error": str(e)}, 500


class Health(Resource):
    """Health check for search service"""
    def get(self):
        return {"status": "UP", "service": "Search"}, 200


# Registrar recursos
api.add_resource(Search, '/search')
api.add_resource(Health, '/health')


if __name__ == '__main__':
    logger.info("Starting Search Service on port 5003")
    app.run(host='0.0.0.0', port=5003, debug=False)
