import random
import time
from datetime import datetime
from celery.exceptions import MaxRetriesExceededError
import requests

from app.worker.celery_app import celery_app
from app.worker.db import get_operation, init_db, log_echo, update_operation_status, save_health_check
from app.worker.config import (
    get_failure_rate,
    get_force_failure,
    record_failure,
    has_recent_failure,
)
from app.models.monitoring import HealthCheck
from app.constants.queues import (
    TASK_PROCESS_OPERATION,
    TASK_PING_WORKER,
    TASK_PING_ALL_SERVICES,
    TASK_ECHO_RESPONSE,
    TASK_LOG_RECORD,
    ECHO_QUEUE,
    LOGS_QUEUE,
    MONITORED_SERVICES,
    PING_TIMEOUT_SECONDS,
)

init_db()


@celery_app.task(bind=True, name=TASK_PROCESS_OPERATION, max_retries=5)
def process_operation(self, operation_id: str):
    try:
        operation = get_operation(operation_id)
        if operation is None:
            raise ValueError(f"Operation {operation_id} not found")

        update_operation_status(operation_id, "PROCESSING")

        time.sleep(0.3)

        # Verificar si debe fallar según configuración dinámica
        force_fail = get_force_failure()
        fail_rate = get_failure_rate()

        if force_fail or (fail_rate > 0 and random.random() < fail_rate):
            record_failure()
            raise RuntimeError("Worker configured to fail")

        update_operation_status(operation_id, "PROCESSED")
        return {"operation_id": operation_id, "status": "PROCESSED"}

    except Exception as exc:
        retry_count = self.request.retries
        countdown = min(2 ** retry_count, 30)

        try:
            raise self.retry(exc=exc, countdown=countdown)
        except MaxRetriesExceededError:
            update_operation_status(operation_id, "FAILED", error=str(exc))
            raise


@celery_app.task(name=TASK_PING_WORKER)
def ping_worker(request_id: str):
    ts = datetime.utcnow().isoformat() + "Z"

    # Determinar si el worker está healthy
    # Si hubo un fallo en los últimos 30 segundos, reportar UNHEALTHY
    status = "UNHEALTHY" if has_recent_failure(seconds=30) else "UP"

    payload = {
        "service": "worker",
        "request_id": request_id,
        "status": status,
        "ts": ts,
    }

    log_echo(service="worker", request_id=request_id, status=status, ts=ts)

    celery_app.send_task(
        TASK_ECHO_RESPONSE,
        kwargs=payload,
        queue=ECHO_QUEUE,
    )

    return payload


@celery_app.task(name=TASK_PING_ALL_SERVICES)
def ping_all_services(request_id: str):
    """
    Hace ping HTTP a todos los microservicios y reporta resultados.
    Este task es consumido por el Worker y el resultado va a la cola echo.
    """
    results = []
    ts = datetime.utcnow().isoformat() + "Z"
    
    for service_name, url in MONITORED_SERVICES.items():
        start = time.time()
        
        try:
            # Caso especial: worker se evalúa internamente
            if service_name == "worker":
                latency = (time.time() - start) * 1000
                status = "UNHEALTHY" if has_recent_failure(seconds=30) else "UP"
                check = HealthCheck(
                    id=0,
                    service=service_name,
                    request_id=request_id,
                    status=status,
                    latency_ms=latency,
                    http_code=200 if status == "UP" else 503,
                    timestamp=ts,
                    is_timeout=False,
                )
            else:
                # Ping HTTP a otros servicios
                response = requests.get(url, timeout=PING_TIMEOUT_SECONDS)
                latency = (time.time() - start) * 1000
                
                if response.status_code == 200:
                    check = HealthCheck.up(service_name, request_id, latency, response.status_code)
                else:
                    check = HealthCheck(
                        id=0,
                        service=service_name,
                        request_id=request_id,
                        status="DEGRADED",
                        latency_ms=latency,
                        http_code=response.status_code,
                        timestamp=ts,
                        is_timeout=False,
                    )
                    
        except requests.exceptions.Timeout:
            check = HealthCheck.timeout(service_name, request_id, PING_TIMEOUT_SECONDS * 1000)
            
        except requests.exceptions.ConnectionError:
            check = HealthCheck.down(service_name, request_id)
            
        except Exception as e:
            check = HealthCheck(
                id=0,
                service=service_name,
                request_id=request_id,
                status="DOWN",
                latency_ms=None,
                http_code=None,
                timestamp=ts,
                is_timeout=False,
            )
        
        # Guardar en SQLite
        save_health_check(check)
        
        results.append({
            "service": check.service,
            "status": check.status,
            "latency_ms": check.latency_ms,
            "http_code": check.http_code,
            "is_failure": check.is_failure(),
        })
    
    # También hacer ping a Redis
    try:
        import redis
        start = time.time()
        r = redis.Redis(host='redis', port=6379, socket_timeout=PING_TIMEOUT_SECONDS)
        r.ping()
        latency = (time.time() - start) * 1000
        
        check = HealthCheck.up("redis", request_id, latency)
        save_health_check(check)
        
        results.append({
            "service": "redis",
            "status": "UP",
            "latency_ms": latency,
            "http_code": None,
            "is_failure": False,
        })
    except Exception:
        check = HealthCheck.down("redis", request_id)
        save_health_check(check)
        
        results.append({
            "service": "redis",
            "status": "DOWN",
            "latency_ms": None,
            "http_code": None,
            "is_failure": True,
        })
    
    # Enviar Echo al Monitor con todos los resultados
    payload = {
        "request_id": request_id,
        "ts": ts,
        "results": results,
    }
    
    celery_app.send_task(
        TASK_ECHO_RESPONSE,
        kwargs=payload,
        queue=ECHO_QUEUE,
    )
    
    return payload


@celery_app.task(name=TASK_LOG_RECORD)
def log_record(timestamp: str, action: str, hotel_id: str, status: str, 
               http_code: int, message: str, log_id: str, **kwargs):
    """
    Servicio consumidor de logs de auditoría y seguridad.
    
    Consume mensajes de la cola LOGS_QUEUE que contienen eventos de seguridad
    (intentos de acceso, autorizaciones, denegaciones, etc.) y los registra.
    
    Args:
        timestamp: Timestamp del evento en ISO 8601 format
        action: Tipo de acción (UPDATE_RATES_STARTED, UPDATE_RATES_DENIED, etc.)
        hotel_id: ID del hotel afectado por la operación
        status: Estado (AUTHORIZED, FORBIDDEN, ERROR, etc.)
        http_code: Código HTTP de la respuesta
        message: Mensaje descriptivo del evento
        log_id: ID único del log
    """
    try:
        # Construir mensaje de log formateado
        log_output = f"""
╔════════════════════════════════════════════════════════════════╗
║                    SECURITY LOG RECORD                         ║
╠════════════════════════════════════════════════════════════════╣
║ Log ID          : {log_id}
║ Timestamp       : {timestamp}
║ Action          : {action}
║ Hotel ID        : {hotel_id}
║ Status          : {status}
║ HTTP Code       : {http_code}
║ Message         : {message}
╚════════════════════════════════════════════════════════════════╝
"""
        
        # Imprimir el log en consola (salida estándar del worker)
        print(log_output)
        
        # También registrar en los logs del worker
        if status == "AUTHORIZED":
            logger.info(f"[{action}] Hotel {hotel_id}: {message} (Code: {http_code})")
        elif status == "FORBIDDEN":
            logger.warning(f"[{action}] Hotel {hotel_id}: {message} (Code: {http_code})")
        elif status == "ERROR":
            logger.error(f"[{action}] Hotel {hotel_id}: {message} (Code: {http_code})")
        else:
            logger.info(f"[{action}] Hotel {hotel_id}: {message} (Code: {http_code})")
        
        # ETAPA 2 extendido: Aquí podría guardarse en BD si fuera necesario
        # Por ahora solo hacemos print como requerimiento de Etapa 3
        
        return {
            "log_id": log_id,
            "status": "LOGGED",
            "message": "Log registrado exitosamente"
        }
        
    except Exception as e:
        logger.error(f"Error procesando log de seguridad {log_id}: {str(e)}")
        raise
