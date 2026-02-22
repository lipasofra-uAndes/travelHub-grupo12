"""Monitor Service - Loop principal de Ping/Echo híbrido

Diseño:
- Worker: Ping HTTP directo (sin depender de Celery)
- Otros servicios: Via cola asíncrona Celery
"""

import logging
import os
import sys
import time
import threading
import requests
from datetime import datetime
from uuid import uuid4

from celery import Celery

# Asegurar que la app está en el path
sys.path.insert(0, '/app')

from app.worker.db import init_db, save_health_check
from app.models.monitoring import HealthCheck
from app.monitor.incident_detector import evaluate_service_health, check_all_services
from app.constants.queues import (
    ECHO_QUEUE,
    PING_QUEUE,
    TASK_PING_ALL_SERVICES,
    TASK_ECHO_RESPONSE,
    MONITOR_PING_INTERVAL_SECONDS,
    PING_TIMEOUT_SECONDS,
    MONITORED_SERVICES,
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("monitor")

# Configuración Celery para el Monitor
BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0")
RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", BROKER_URL)

monitor_celery = Celery("monitor", broker=BROKER_URL, backend=RESULT_BACKEND)
monitor_celery.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)


class MonitorService:
    """Servicio de monitoreo con Ping/Echo asíncrono"""
    
    def __init__(self, ping_interval: int = MONITOR_PING_INTERVAL_SECONDS):
        self.ping_interval = ping_interval
        self.running = False
        self.last_ping_time = None
        self.last_echo_time = None
        self.ping_count = 0
        self.echo_count = 0
        
        # Inicializar DB
        init_db()
        logger.info("Monitor Service initialized")
    
    def send_ping(self) -> str:
        """
        Ejecuta ping híbrido:
        1. HTTP directo al Worker (para detectar si Celery está caído)
        2. Tarea Celery para los otros servicios
        """
        request_id = f"ping-{uuid4().hex[:8]}"
        
        # 1. PING DIRECTO AL WORKER (HTTP)
        worker_result = self._ping_worker_direct(request_id)
        self._log_ping_result(worker_result)
        
        # Evaluar incidente del worker inmediatamente
        worker_incident = evaluate_service_health("worker")
        if worker_incident[0] == "incident_created":
            logger.warning(f"🚨 NEW INCIDENT: worker (detected via direct HTTP)")
        elif worker_incident[0] == "incident_resolved":
            logger.info(f"✅ INCIDENT RESOLVED: worker")
        
        # 2. PING VIA CELERY para otros servicios (solo si el worker está UP)
        if worker_result["status"] == "UP":
            try:
                monitor_celery.send_task(
                    TASK_PING_ALL_SERVICES,
                    kwargs={"request_id": request_id},
                    queue=PING_QUEUE,
                )
                logger.debug(f"📤 Celery PING sent: {request_id}")
            except Exception as e:
                logger.error(f"Failed to send Celery ping: {e}")
        else:
            logger.warning(f"⚠️ Skipping Celery ping - Worker is DOWN")
        
        self.last_ping_time = datetime.utcnow()
        self.ping_count += 1
        
        return request_id
    
    def _ping_worker_direct(self, request_id: str) -> dict:
        """
        Hace ping HTTP directo al worker.
        Esto permite detectar si el worker/Celery está caído.
        """
        worker_url = MONITORED_SERVICES.get("worker", "http://celery-worker:5005/health")
        start_time = time.time()
        status = "DOWN"
        http_code = None
        is_timeout = False
        error_message = None
        
        try:
            response = requests.get(worker_url, timeout=PING_TIMEOUT_SECONDS)
            http_code = response.status_code
            status = "UP" if response.ok else "DOWN"
        except requests.Timeout:
            is_timeout = True
            error_message = "Timeout"
        except requests.ConnectionError as e:
            error_message = f"Connection error: {str(e)[:100]}"
        except Exception as e:
            error_message = str(e)[:100]
        
        latency_ms = (time.time() - start_time) * 1000
        
        # Guardar en SQLite
        health_check = HealthCheck(
            id=0,  # Auto-increment en DB
            service="worker",
            request_id=request_id,
            status=status,
            timestamp=datetime.utcnow().isoformat(),
            latency_ms=latency_ms,
            http_code=http_code,
            is_timeout=is_timeout,
            error_message=error_message,
        )
        save_health_check(health_check)
        
        return {
            "service": "worker",
            "status": status,
            "latency_ms": round(latency_ms, 2),
            "http_code": http_code,
            "is_failure": status == "DOWN",
            "method": "HTTP_DIRECT",
        }
    
    def _log_ping_result(self, result: dict):
        """Log del resultado de un ping"""
        status_emoji = "✅" if result["status"] == "UP" else "❌"
        method = result.get("method", "CELERY")
        logger.info(
            f"   {status_emoji} {result['service']}: {result['status']} "
            f"(latency: {result.get('latency_ms', 'N/A')}ms) [{method}]"
        )
    
    def process_echo(self, **kwargs):
        """Procesa un echo recibido del Worker (para servicios via Celery)"""
        request_id = kwargs.get("request_id")
        results = kwargs.get("results", [])
        
        self.last_echo_time = datetime.utcnow()
        self.echo_count += 1
        
        logger.info(f"📥 ECHO received: {request_id} with {len(results)} service results")
        
        # Log resultados (excepto worker que ya se verificó por HTTP directo)
        for result in results:
            if result.get("service") != "worker":  # Worker ya se verificó
                self._log_ping_result({**result, "method": "CELERY"})
        
        # Evaluar incidentes para servicios (excepto worker)
        services_to_check = [s for s in MONITORED_SERVICES.keys() if s != "worker"]
        services_to_check.append("redis")
        incident_results = check_all_services(services_to_check)
        
        # Log de incidentes
        for service, incident_info in incident_results.items():
            if incident_info["action"] == "incident_created":
                logger.warning(f"🚨 NEW INCIDENT: {service}")
            elif incident_info["action"] == "incident_resolved":
                logger.info(f"✅ INCIDENT RESOLVED: {service}")
    
    def ping_loop(self):
        """Loop principal que envía pings periódicamente"""
        logger.info(f"🚀 Starting ping loop (interval: {self.ping_interval}s)")
        
        while self.running:
            try:
                self.send_ping()
                time.sleep(self.ping_interval)
            except Exception as e:
                logger.error(f"Error in ping loop: {e}")
                time.sleep(1)  # Pequeña pausa antes de reintentar
    
    def start(self):
        """Inicia el servicio de monitoreo"""
        self.running = True
        
        # Iniciar thread de ping
        ping_thread = threading.Thread(target=self.ping_loop, daemon=True)
        ping_thread.start()
        
        logger.info("Monitor Service started")
        
        return ping_thread
    
    def stop(self):
        """Detiene el servicio de monitoreo"""
        self.running = False
        logger.info("Monitor Service stopped")
    
    def get_status(self) -> dict:
        """Retorna el estado actual del monitor"""
        return {
            "running": self.running,
            "ping_interval_seconds": self.ping_interval,
            "ping_count": self.ping_count,
            "echo_count": self.echo_count,
            "last_ping_time": self.last_ping_time.isoformat() if self.last_ping_time else None,
            "last_echo_time": self.last_echo_time.isoformat() if self.last_echo_time else None,
        }


# Task para recibir Echo responses
@monitor_celery.task(name=TASK_ECHO_RESPONSE)
def echo_response(**kwargs):
    """Task que procesa los echo responses del worker"""
    # Esta task será consumida por el monitor worker
    # Los resultados ya están guardados en SQLite por el worker
    
    request_id = kwargs.get("request_id")
    results = kwargs.get("results", [])
    
    logger.info(f"Echo response processed: {request_id}")
    
    # Evaluar incidentes
    services = list(MONITORED_SERVICES.keys()) + ["redis"]
    check_all_services(services)
    
    return {"processed": True, "request_id": request_id}


# Instancia global del monitor
_monitor_instance = None


def get_monitor() -> MonitorService:
    """Obtiene la instancia global del monitor"""
    global _monitor_instance
    if _monitor_instance is None:
        _monitor_instance = MonitorService()
    return _monitor_instance


if __name__ == "__main__":
    # Ejecutar monitor standalone (para testing)
    monitor = get_monitor()
    
    try:
        ping_thread = monitor.start()
        ping_thread.join()
    except KeyboardInterrupt:
        monitor.stop()
        print("\n📴 Monitor stopped")
