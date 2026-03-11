"""
Servicio de Auditoría
Encargado de consumir eventos de auditoría y seguridad de la cola LOGS_QUEUE
e imprimir registros de auditoría formateados.
"""

import logging
from app.worker.celery_app import celery_app
from app.constants.queues import TASK_LOG_RECORD

logger = logging.getLogger(__name__)


@celery_app.task(name=TASK_LOG_RECORD)
def log_record(timestamp: str, action: str, hotel_id: str, status: str, 
               http_code: int, message: str, log_id: str, **kwargs):
    """
    Servicio consumidor de logs de auditoría y seguridad.
    
    Componente: Auditoría
    Función: Consume mensajes de la cola LOGS_QUEUE que contienen eventos de seguridad
    (intentos de acceso, autorizaciones, denegaciones, etc.) y los registra.
    
    Args:
        timestamp: Timestamp del evento en ISO 8601 format
        action: Tipo de acción (UPDATE_RATES_STARTED, UPDATE_RATES_DENIED, etc.)
        hotel_id: ID del hotel afectado por la operación
        status: Estado (AUTHORIZED, FORBIDDEN, ERROR, etc.)
        http_code: Código HTTP de la respuesta
        message: Mensaje descriptivo del evento
        log_id: ID único del log
    
    Returns:
        dict: Confirmación del log registrado
    """
    try:
        # Construir mensaje de log formateado con borde ASCII
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
        
        # También registrar en los logs del worker según el tipo de evento
        if status == "AUTHORIZED":
            logger.info(f"[{action}] Hotel {hotel_id}: {message} (Code: {http_code})")
        elif status == "FORBIDDEN":
            logger.warning(f"[{action}] Hotel {hotel_id}: {message} (Code: {http_code})")
        elif status == "ERROR":
            logger.error(f"[{action}] Hotel {hotel_id}: {message} (Code: {http_code})")
        else:
            logger.info(f"[{action}] Hotel {hotel_id}: {message} (Code: {http_code})")
        
        # hacemos print
        
        return {
            "log_id": log_id,
            "status": "LOGGED",
            "message": "Log registrado exitosamente"
        }
        
    except Exception as e:
        logger.error(f"Error procesando log de seguridad {log_id}: {str(e)}")
        raise
