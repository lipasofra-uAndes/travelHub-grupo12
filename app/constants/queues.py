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
TASK_ECHO_RESPONSE = "echo_response"

# Timeouts y delays
PING_TIMEOUT_SECONDS = 5
ECHO_TIMEOUT_SECONDS = 2
OPERATION_TIMEOUT_SECONDS = 30
