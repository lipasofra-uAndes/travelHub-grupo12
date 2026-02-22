"""API Flask del Monitor Service - Endpoints para métricas y control"""

from flask import Flask, jsonify, request

from app.monitor.monitor_service import get_monitor
from app.monitor.metrics import (
    get_service_metrics,
    get_all_services_metrics,
    get_experiment_summary,
)
from app.monitor.incident_detector import check_all_services
from app.worker.db import (
    get_active_incident,
    get_incidents_by_service,
    get_all_incidents,
    get_recent_health_checks,
    init_db,
)
from app.constants.queues import MONITORED_SERVICES

# Inicializar DB
init_db()

app = Flask(__name__)


# ==================== HEALTH & STATUS ====================

@app.route("/health", methods=["GET"])
def health():
    """Health check del Monitor Service"""
    return jsonify({"status": "UP", "service": "Monitor"}), 200


@app.route("/status", methods=["GET"])
def status():
    """Estado actual del monitor"""
    monitor = get_monitor()
    return jsonify(monitor.get_status()), 200


# ==================== METRICS ====================

@app.route("/metrics", methods=["GET"])
def all_metrics():
    """
    Obtiene métricas de todos los servicios.
    
    Query params:
        window_hours: Ventana de tiempo en horas (default: 24)
    """
    window_hours = request.args.get("window_hours", 24, type=float)
    metrics = get_all_services_metrics(window_hours)
    return jsonify(metrics), 200


@app.route("/metrics/<service>", methods=["GET"])
def service_metrics(service: str):
    """
    Obtiene métricas de un servicio específico.
    
    Query params:
        window_hours: Ventana de tiempo en horas (default: 24)
    """
    window_hours = request.args.get("window_hours", 24, type=float)
    
    valid_services = list(MONITORED_SERVICES.keys()) + ["redis"]
    if service not in valid_services:
        return jsonify({"error": f"Service '{service}' not found. Valid: {valid_services}"}), 404
    
    metrics = get_service_metrics(service, window_hours)
    return jsonify(metrics.to_dict()), 200


@app.route("/metrics/experiment", methods=["GET"])
def experiment_metrics():
    """
    Genera resumen del experimento ASR-03.
    
    Query params:
        window_hours: Ventana de tiempo en horas (default: 1)
    """
    window_hours = request.args.get("window_hours", 1, type=float)
    summary = get_experiment_summary(window_hours)
    return jsonify(summary), 200


# ==================== INCIDENTS ====================

@app.route("/incidents", methods=["GET"])
def all_incidents():
    """
    Lista todos los incidentes.
    
    Query params:
        limit: Número máximo de incidentes (default: 50)
    """
    limit = request.args.get("limit", 50, type=int)
    incidents = get_all_incidents(limit)
    return jsonify({
        "total": len(incidents),
        "incidents": [i.to_dict() for i in incidents],
    }), 200


@app.route("/incidents/<service>", methods=["GET"])
def service_incidents(service: str):
    """
    Lista incidentes de un servicio específico.
    
    Query params:
        limit: Número máximo de incidentes (default: 50)
    """
    limit = request.args.get("limit", 50, type=int)
    
    valid_services = list(MONITORED_SERVICES.keys()) + ["redis"]
    if service not in valid_services:
        return jsonify({"error": f"Service '{service}' not found"}), 404
    
    incidents = get_incidents_by_service(service, limit)
    active = get_active_incident(service)
    
    return jsonify({
        "service": service,
        "has_active_incident": active is not None,
        "active_incident": active.to_dict() if active else None,
        "total": len(incidents),
        "incidents": [i.to_dict() for i in incidents],
    }), 200


@app.route("/incidents/active", methods=["GET"])
def active_incidents():
    """Lista todos los incidentes activos"""
    services = list(MONITORED_SERVICES.keys()) + ["redis"]
    active_incidents = []
    
    for service in services:
        incident = get_active_incident(service)
        if incident:
            active_incidents.append(incident.to_dict())
    
    return jsonify({
        "total": len(active_incidents),
        "incidents": active_incidents,
    }), 200


# ==================== HEALTH CHECKS ====================

@app.route("/health-checks/<service>", methods=["GET"])
def service_health_checks(service: str):
    """
    Obtiene los últimos health checks de un servicio.
    
    Query params:
        limit: Número máximo de checks (default: 50)
    """
    limit = request.args.get("limit", 50, type=int)
    
    valid_services = list(MONITORED_SERVICES.keys()) + ["redis"]
    if service not in valid_services:
        return jsonify({"error": f"Service '{service}' not found"}), 404
    
    checks = get_recent_health_checks(service, limit)
    
    return jsonify({
        "service": service,
        "total": len(checks),
        "checks": [c.to_dict() for c in checks],
    }), 200


# ==================== CONTROL ====================

@app.route("/ping", methods=["POST"])
def trigger_ping():
    """Envía un ping manual a todos los servicios"""
    monitor = get_monitor()
    request_id = monitor.send_ping()
    
    return jsonify({
        "message": "Ping sent",
        "request_id": request_id,
    }), 202


@app.route("/evaluate", methods=["POST"])
def evaluate_services():
    """Evalúa manualmente el estado de todos los servicios"""
    services = list(MONITORED_SERVICES.keys()) + ["redis"]
    results = check_all_services(services)
    
    return jsonify({
        "message": "Evaluation complete",
        "results": results,
    }), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5006, debug=False)
