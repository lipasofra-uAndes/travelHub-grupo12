"""Detector de incidentes basado en N fallas consecutivas"""

import logging
from typing import Optional, Tuple

from app.models.monitoring import Incident
from app.worker.db import (
    count_consecutive_failures,
    get_active_incident,
    save_incident,
    update_incident,
    get_recent_health_checks,
)
from app.constants.queues import (
    CONSECUTIVE_FAILURES_THRESHOLD,
    RECOVERY_CHECK_THRESHOLD,
    SEVERITY_CRITICAL,
    SEVERITY_WARNING,
)

logger = logging.getLogger(__name__)


def evaluate_service_health(service: str) -> Tuple[str, Optional[Incident]]:
    """
    Evalúa la salud de un servicio y detecta/resuelve incidentes.
    
    Returns:
        Tuple[str, Optional[Incident]]: (acción tomada, incidente si aplica)
        - acciones: "healthy", "incident_created", "incident_resolved", "incident_ongoing"
    """
    # Contar fallas consecutivas
    consecutive_failures, first_failure_ts = count_consecutive_failures(
        service, CONSECUTIVE_FAILURES_THRESHOLD
    )
    
    # Obtener incidente activo si existe
    active_incident = get_active_incident(service)
    
    # CASO 1: Hay fallas suficientes para crear/mantener incidente
    if consecutive_failures >= CONSECUTIVE_FAILURES_THRESHOLD:
        if active_incident is None:
            # Crear nuevo incidente
            severity = (
                SEVERITY_CRITICAL 
                if consecutive_failures >= CONSECUTIVE_FAILURES_THRESHOLD * 2 
                else SEVERITY_WARNING
            )
            incident = Incident.create(
                service=service,
                first_failure_time=first_failure_ts,
                consecutive_failures=consecutive_failures,
                severity=severity,
            )
            incident_id = save_incident(incident)
            incident.id = incident_id
            
            logger.warning(
                f"🚨 INCIDENT CREATED: {service} - "
                f"{consecutive_failures} consecutive failures - "
                f"MTTD: {incident.mttd_seconds:.2f}s"
            )
            
            return "incident_created", incident
        else:
            # Incidente ya existe, sigue activo
            logger.info(f"⚠️ INCIDENT ONGOING: {service} - {consecutive_failures} failures")
            return "incident_ongoing", active_incident
    
    # CASO 2: No hay suficientes fallas
    else:
        if active_incident is not None:
            # Verificar si hay suficientes UPs para resolver
            recent_checks = get_recent_health_checks(service, RECOVERY_CHECK_THRESHOLD)
            consecutive_ups = sum(1 for c in recent_checks if not c.is_failure())
            
            if consecutive_ups >= RECOVERY_CHECK_THRESHOLD:
                # Resolver incidente
                active_incident.resolve(action="auto-recovery")
                update_incident(active_incident)
                
                logger.info(
                    f"✅ INCIDENT RESOLVED: {service} - "
                    f"MTTR: {active_incident.mttr_seconds:.2f}s"
                )
                
                return "incident_resolved", active_incident
            else:
                # Aún no hay suficientes UPs
                return "incident_ongoing", active_incident
        else:
            # Todo healthy
            return "healthy", None


def check_all_services(services: list[str]) -> dict:
    """
    Evalúa la salud de todos los servicios.
    
    Returns:
        dict con el estado de cada servicio
    """
    results = {}
    
    for service in services:
        action, incident = evaluate_service_health(service)
        
        results[service] = {
            "action": action,
            "has_active_incident": incident is not None and incident.is_active() if incident else False,
            "incident_id": incident.id if incident else None,
            "mttd_seconds": incident.mttd_seconds if incident else None,
            "mttr_seconds": incident.mttr_seconds if incident else None,
        }
    
    return results
