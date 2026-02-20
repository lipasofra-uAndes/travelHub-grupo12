"""Flask app para configurar dinámicamente el worker"""

from flask import Flask, jsonify, request

from app.worker.config import (
    set_failure_rate,
    set_force_failure,
    get_failure_config,
    reset_config,
)

flask_app = Flask(__name__)


@flask_app.route("/config", methods=["GET"])
def get_config():
    """Obtiene la configuración actual del worker"""
    return jsonify(get_failure_config()), 200


@flask_app.route("/config/failure-rate", methods=["POST"])
def set_failure_rate_endpoint():
    """
    Establece la probabilidad de fallo.
    
    Body JSON:
        {"rate": 0.5}  → 50% de probabilidad
        {"rate": 0.0}  → Sin fallos
        {"rate": 1.0}  → Siempre falla
    """
    try:
        data = request.get_json()
        if not data or "rate" not in data:
            return jsonify({"error": "Parámetro 'rate' requerido"}), 400
        
        rate = float(data["rate"])
        set_failure_rate(rate)
        
        return jsonify({
            "message": f"Failure rate establecido en {rate}",
            "config": get_failure_config()
        }), 200
    
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@flask_app.route("/config/force-failure", methods=["POST"])
def set_force_failure_endpoint():
    """
    Fuerza que todas las operaciones fallen.
    
    Body JSON:
        {"force": true}   → Todas fallan
        {"force": false}  → Deshabilita fallo forzado
    """
    try:
        data = request.get_json()
        if not data or "force" not in data:
            return jsonify({"error": "Parámetro 'force' requerido"}), 400
        
        force = bool(data["force"])
        set_force_failure(force)
        
        return jsonify({
            "message": f"Force failure: {force}",
            "config": get_failure_config()
        }), 200
    
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@flask_app.route("/config/reset", methods=["POST"])
def reset_config_endpoint():
    """Resetea toda la configuración a valores por defecto"""
    reset_config()
    return jsonify({
        "message": "Configuración reseteada",
        "config": get_failure_config()
    }), 200


@flask_app.route("/health", methods=["GET"])
def health():
    """Health check del worker"""
    return jsonify({"status": "OK"}), 200


if __name__ == "__main__":
    flask_app.run(host="0.0.0.0", port=5005, debug=False)
