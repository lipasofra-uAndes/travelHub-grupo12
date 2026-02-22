"""Monitor Service - Loop principal de Ping/Echo asíncrono"""

import logging
import os
import sys
import time
import threading
from datetime import datetime
from uuid import uuid4

from celery import Celery

# Asegurar que la app está en el path
sys.path.insert(0, '/app')

from app.worker.db import init_db
from app.monitor.incident_detector import check_all_services
from app.constants.queues import (
    ECHO_QUEUE,
    PING_QUEUE,
    TASK_PING_ALL_SERVICES,
    TASK_ECHO_RESPONSE,
    MONITOR_PING_INTERVAL_SECONDS,
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
        """Envía un ping asíncrono a través de Celery"""
        request_id = f"ping-{uuid4().hex[:8]}"
        
        try:
            monitor_celery.send_task(
                TASK_PING_ALL_SERVICES,
                kwargs={"request_id": request_id},
                queue=PING_QUEUE,
            )
            
            self.last_ping_time = datetime.utcnow()
            self.ping_count += 1
            
            logger.debug(f"📤 PING sent: {request_id}")
            
        except Exception as e:
            logger.error(f"Failed to send ping: {e}")
        
        return request_id
    
    def process_echo(self, **kwargs):
        """Procesa un echo recibido y evalúa incidentes"""
        request_id = kwargs.get("request_id")
        results = kwargs.get("results", [])
        ts = kwargs.get("ts")
        
        self.last_echo_time = datetime.utcnow()
        self.echo_count += 1
        
        logger.info(f"📥 ECHO received: {request_id} with {len(results)} service results")
        
        # Log resultados
        for result in results:
            status_emoji = "✅" if not result.get("is_failure") else "❌"
            logger.info(
                f"   {status_emoji} {result['service']}: {result['status']} "
                f"(latency: {result.get('latency_ms', 'N/A')}ms)"
            )
        
        # Evaluar incidentes para cada servicio
        services = list(MONITORED_SERVICES.keys()) + ["redis"]
        incident_results = check_all_services(services)
        
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
