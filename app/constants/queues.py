"""Constantes de colas Celery - compartidas entre todos los servicios"""

# Cola de procesamiento de operaciones de negocio
OPERATIONS_QUEUE = "ops.process"

# Cola de ping para verificar disponibilidad del worker
PING_QUEUE = "monitoring.ping"

# Cola de echo/respuesta del worker
ECHO_QUEUE = "monitoring.echo"

# Task names
TASK_PROCESS_OPERATION = "worker.process_operation"
TASK_PING_WORKER = "worker.ping_worker"
TASK_PING_ALL_SERVICES = "worker.ping_all_services"
TASK_ECHO_RESPONSE = "monitor.echo_response"

# Timeouts y delays
PING_TIMEOUT_SECONDS = 5
ECHO_TIMEOUT_SECONDS = 2
OPERATION_TIMEOUT_SECONDS = 30

# Configuración del Monitor
MONITOR_PING_INTERVAL_SECONDS = 5  # Intervalo entre pings
CONSECUTIVE_FAILURES_THRESHOLD = 3  # Fallas consecutivas para crear incidente
RECOVERY_CHECK_THRESHOLD = 3  # UPs consecutivos para resolver incidente

# Servicios a monitorear (nombre: URL interna)
MONITORED_SERVICES = {
    "api-gateway": "http://api-gateway:5000/health",
    "reserves": "http://reserves-service:5001/health",
    "payments": "http://payments-service:5002/health",
    "search": "http://search-service:5003/health",
    "worker": "http://celery-worker:5005/health",
}

# Severidades de incidentes
SEVERITY_WARNING = "WARNING"
SEVERITY_CRITICAL = "CRITICAL"
