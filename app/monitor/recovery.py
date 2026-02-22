"""Recovery module - Acciones de recuperación automática para servicios caídos"""

import logging
import os
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)

# Mapeo de servicios a nombres de containers Docker
SERVICE_TO_CONTAINER = {
    "api-gateway": "api-gateway",
    "reserves": "reserves-service",
    "payments": "payments-service",
    "search": "search-service",
    "worker": "celery-worker",
    "redis": "redis",
}

# Servicios que NO se deben reiniciar automáticamente
DO_NOT_RESTART = {"redis"}  # Redis es infraestructura crítica


def restart_container(container_name: str, timeout: int = 30) -> dict:
    """
    Reinicia un container Docker usando el CLI.
    
    Args:
        container_name: Nombre del container a reiniciar
        timeout: Timeout en segundos para el reinicio
    
    Returns:
        dict con resultado de la operación
    """
    try:
        logger.info(f"🔄 Restarting container: {container_name}")
        
        result = subprocess.run(
            ["docker", "restart", "--time", str(timeout), container_name],
            capture_output=True,
            text=True,
            timeout=timeout + 10,  # Un poco más que el timeout de docker
        )
        
        if result.returncode == 0:
            logger.info(f"✅ Container {container_name} restarted successfully")
            return {
                "success": True,
                "container": container_name,
                "action": "restart",
                "message": f"Container {container_name} restarted",
            }
        else:
            logger.error(f"❌ Failed to restart {container_name}: {result.stderr}")
            return {
                "success": False,
                "container": container_name,
                "action": "restart",
                "error": result.stderr,
            }
            
    except subprocess.TimeoutExpired:
        logger.error(f"❌ Timeout restarting container {container_name}")
        return {
            "success": False,
            "container": container_name,
            "action": "restart",
            "error": "Timeout expired",
        }
    except FileNotFoundError:
        logger.error("❌ Docker CLI not found. Is Docker installed?")
        return {
            "success": False,
            "container": container_name,
            "action": "restart",
            "error": "Docker CLI not found",
        }
    except Exception as e:
        logger.error(f"❌ Error restarting container {container_name}: {e}")
        return {
            "success": False,
            "container": container_name,
            "action": "restart",
            "error": str(e),
        }


def restart_service(service_name: str) -> dict:
    """
    Reinicia un servicio por su nombre lógico.
    
    Args:
        service_name: Nombre del servicio (ej: "worker", "reserves")
    
    Returns:
        dict con resultado de la operación
    """
    # Verificar si el servicio existe
    if service_name not in SERVICE_TO_CONTAINER:
        return {
            "success": False,
            "service": service_name,
            "action": "restart",
            "error": f"Unknown service: {service_name}",
        }
    
    # Verificar si el servicio está en la lista de no reiniciar
    if service_name in DO_NOT_RESTART:
        logger.warning(f"⚠️ Service {service_name} is in DO_NOT_RESTART list, skipping")
        return {
            "success": False,
            "service": service_name,
            "action": "restart",
            "error": f"Service {service_name} is protected from automatic restart",
        }
    
    container_name = SERVICE_TO_CONTAINER[service_name]
    result = restart_container(container_name)
    result["service"] = service_name
    
    return result


def recover_service(service_name: str, incident_id: Optional[int] = None) -> dict:
    """
    Ejecuta la acción de recuperación para un servicio con incidente.
    
    Esta es la función principal que debe llamar el incident_detector
    cuando detecta un incidente.
    
    Args:
        service_name: Nombre del servicio a recuperar
        incident_id: ID del incidente (para logging)
    
    Returns:
        dict con resultado de la recuperación
    """
    logger.warning(
        f"🚨 RECOVERY TRIGGERED for {service_name} "
        f"(incident_id: {incident_id})"
    )
    
    result = restart_service(service_name)
    
    if result["success"]:
        logger.info(
            f"✅ Recovery action completed for {service_name} "
            f"(incident_id: {incident_id})"
        )
        result["recovery_action"] = "restart"
    else:
        logger.error(
            f"❌ Recovery action FAILED for {service_name} "
            f"(incident_id: {incident_id}): {result.get('error')}"
        )
        result["recovery_action"] = "restart_failed"
    
    return result


def check_docker_available() -> bool:
    """Verifica si Docker CLI está disponible"""
    try:
        result = subprocess.run(
            ["docker", "version"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except:
        return False


def get_container_status(container_name: str) -> Optional[str]:
    """
    Obtiene el estado de un container.
    
    Returns:
        Estado del container (running, exited, etc.) o None si no existe
    """
    try:
        result = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Status}}", container_name],
            capture_output=True,
            text=True,
            timeout=5,
        )
        
        if result.returncode == 0:
            return result.stdout.strip()
        return None
        
    except:
        return None
