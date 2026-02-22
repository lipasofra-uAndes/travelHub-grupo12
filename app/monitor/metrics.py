"""Cálculo de métricas de disponibilidad: MTTD, MTTR, Availability"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional

from app.models.monitoring import Incident, HealthCheck
from app.worker.db import get_incidents_by_service, get_all_incidents, get_recent_health_checks
from app.constants.queues import MONITORED_SERVICES


@dataclass
class ServiceMetrics:
    """Métricas de un servicio individual"""
    service: str
    total_incidents: int
    active_incidents: int
    resolved_incidents: int
    
    # MTTD - Mean Time To Detect (segundos)
    mttd_avg: Optional[float]
    mttd_min: Optional[float]
    mttd_max: Optional[float]
    
    # MTTR - Mean Time To Recover (segundos)
    mttr_avg: Optional[float]
    mttr_min: Optional[float]
    mttr_max: Optional[float]
    
    # MTBF - Mean Time Between Failures (segundos)
    mtbf_avg: Optional[float]
    
    # Availability
    availability_percent: float
    total_downtime_seconds: float
    
    # Health checks
    total_checks: int
    successful_checks: int
    failed_checks: int
    avg_latency_ms: Optional[float]

    def to_dict(self) -> dict:
        return {
            "service": self.service,
            "incidents": {
                "total": self.total_incidents,
                "active": self.active_incidents,
                "resolved": self.resolved_incidents,
            },
            "mttd": {
                "avg_seconds": round(self.mttd_avg, 2) if self.mttd_avg else None,
                "min_seconds": round(self.mttd_min, 2) if self.mttd_min else None,
                "max_seconds": round(self.mttd_max, 2) if self.mttd_max else None,
            },
            "mttr": {
                "avg_seconds": round(self.mttr_avg, 2) if self.mttr_avg else None,
                "min_seconds": round(self.mttr_min, 2) if self.mttr_min else None,
                "max_seconds": round(self.mttr_max, 2) if self.mttr_max else None,
            },
            "mtbf_avg_seconds": round(self.mtbf_avg, 2) if self.mtbf_avg else None,
            "availability": {
                "percent": round(self.availability_percent, 4),
                "total_downtime_seconds": round(self.total_downtime_seconds, 2),
            },
            "health_checks": {
                "total": self.total_checks,
                "successful": self.successful_checks,
                "failed": self.failed_checks,
                "success_rate": round(self.successful_checks / self.total_checks * 100, 2) if self.total_checks > 0 else 100.0,
                "avg_latency_ms": round(self.avg_latency_ms, 2) if self.avg_latency_ms else None,
            },
        }


def calculate_mttd(incidents: List[Incident]) -> tuple[Optional[float], Optional[float], Optional[float]]:
    """Calcula MTTD promedio, mínimo y máximo de una lista de incidentes"""
    mttd_values = [i.mttd_seconds for i in incidents if i.mttd_seconds is not None]
    
    if not mttd_values:
        return None, None, None
    
    return (
        sum(mttd_values) / len(mttd_values),
        min(mttd_values),
        max(mttd_values),
    )


def calculate_mttr(incidents: List[Incident]) -> tuple[Optional[float], Optional[float], Optional[float]]:
    """Calcula MTTR promedio, mínimo y máximo de incidentes resueltos"""
    mttr_values = [i.mttr_seconds for i in incidents if i.mttr_seconds is not None and i.resolved_at is not None]
    
    if not mttr_values:
        return None, None, None
    
    return (
        sum(mttr_values) / len(mttr_values),
        min(mttr_values),
        max(mttr_values),
    )


def calculate_mtbf(incidents: List[Incident]) -> Optional[float]:
    """
    Calcula MTBF - Mean Time Between Failures.
    Es el tiempo promedio entre el fin de un incidente y el inicio del siguiente.
    """
    resolved_incidents = sorted(
        [i for i in incidents if i.resolved_at is not None],
        key=lambda x: x.started_at
    )
    
    if len(resolved_incidents) < 2:
        return None
    
    time_between = []
    for i in range(1, len(resolved_incidents)):
        prev_resolved = datetime.fromisoformat(resolved_incidents[i-1].resolved_at.replace("Z", "+00:00"))
        curr_started = datetime.fromisoformat(resolved_incidents[i].started_at.replace("Z", "+00:00"))
        
        diff = (curr_started.replace(tzinfo=None) - prev_resolved.replace(tzinfo=None)).total_seconds()
        if diff > 0:  # Solo contar diferencias positivas
            time_between.append(diff)
    
    return sum(time_between) / len(time_between) if time_between else None


def calculate_availability(
    incidents: List[Incident], 
    window_hours: float = 24
) -> tuple[float, float]:
    """
    Calcula el porcentaje de disponibilidad y tiempo total de downtime.
    
    Args:
        incidents: Lista de incidentes
        window_hours: Ventana de tiempo en horas (default 24h)
    
    Returns:
        Tuple[availability_percent, total_downtime_seconds]
    """
    total_seconds = window_hours * 3600
    now = datetime.utcnow()
    window_start = now - timedelta(hours=window_hours)
    
    total_downtime = 0.0
    
    for incident in incidents:
        started = datetime.fromisoformat(incident.started_at.replace("Z", "+00:00")).replace(tzinfo=None)
        
        # Solo considerar incidentes dentro de la ventana
        if started < window_start and incident.resolved_at:
            resolved = datetime.fromisoformat(incident.resolved_at.replace("Z", "+00:00")).replace(tzinfo=None)
            if resolved < window_start:
                continue  # Incidente fuera de la ventana
            started = window_start  # Ajustar inicio a la ventana
        
        if incident.resolved_at:
            resolved = datetime.fromisoformat(incident.resolved_at.replace("Z", "+00:00")).replace(tzinfo=None)
            downtime = (resolved - started).total_seconds()
        else:
            # Incidente activo
            downtime = (now - started).total_seconds()
        
        if downtime > 0:
            total_downtime += downtime
    
    # Limitar downtime al máximo de la ventana
    total_downtime = min(total_downtime, total_seconds)
    
    availability = ((total_seconds - total_downtime) / total_seconds) * 100
    
    return availability, total_downtime


def calculate_health_check_stats(checks: List[HealthCheck]) -> tuple[int, int, int, Optional[float]]:
    """
    Calcula estadísticas de health checks.
    
    Returns:
        Tuple[total, successful, failed, avg_latency_ms]
    """
    total = len(checks)
    successful = sum(1 for c in checks if not c.is_failure())
    failed = total - successful
    
    latencies = [c.latency_ms for c in checks if c.latency_ms is not None]
    avg_latency = sum(latencies) / len(latencies) if latencies else None
    
    return total, successful, failed, avg_latency


def get_service_metrics(service: str, window_hours: float = 24) -> ServiceMetrics:
    """Obtiene todas las métricas de un servicio"""
    incidents = get_incidents_by_service(service, limit=100)
    checks = get_recent_health_checks(service, limit=500)
    
    active = [i for i in incidents if i.is_active()]
    resolved = [i for i in incidents if not i.is_active()]
    
    mttd_avg, mttd_min, mttd_max = calculate_mttd(incidents)
    mttr_avg, mttr_min, mttr_max = calculate_mttr(resolved)
    mtbf_avg = calculate_mtbf(resolved)
    availability, downtime = calculate_availability(incidents, window_hours)
    total_checks, successful_checks, failed_checks, avg_latency = calculate_health_check_stats(checks)
    
    return ServiceMetrics(
        service=service,
        total_incidents=len(incidents),
        active_incidents=len(active),
        resolved_incidents=len(resolved),
        mttd_avg=mttd_avg,
        mttd_min=mttd_min,
        mttd_max=mttd_max,
        mttr_avg=mttr_avg,
        mttr_min=mttr_min,
        mttr_max=mttr_max,
        mtbf_avg=mtbf_avg,
        availability_percent=availability,
        total_downtime_seconds=downtime,
        total_checks=total_checks,
        successful_checks=successful_checks,
        failed_checks=failed_checks,
        avg_latency_ms=avg_latency,
    )


def get_all_services_metrics(window_hours: float = 24) -> dict:
    """Obtiene métricas de todos los servicios monitoreados"""
    services = list(MONITORED_SERVICES.keys()) + ["redis"]
    
    results = {}
    for service in services:
        metrics = get_service_metrics(service, window_hours)
        results[service] = metrics.to_dict()
    
    # Calcular métricas globales
    all_incidents = get_all_incidents(limit=200)
    global_mttd_avg, _, _ = calculate_mttd(all_incidents)
    global_mttr_avg, _, _ = calculate_mttr([i for i in all_incidents if not i.is_active()])
    global_availability, global_downtime = calculate_availability(all_incidents, window_hours)
    
    results["_global"] = {
        "total_incidents": len(all_incidents),
        "active_incidents": sum(1 for i in all_incidents if i.is_active()),
        "mttd_avg_seconds": round(global_mttd_avg, 2) if global_mttd_avg else None,
        "mttr_avg_seconds": round(global_mttr_avg, 2) if global_mttr_avg else None,
        "availability_percent": round(global_availability, 4),
        "total_downtime_seconds": round(global_downtime, 2),
    }
    
    return results


def get_experiment_summary(window_hours: float = 1) -> dict:
    """
    Genera un resumen para el experimento de validación ASR-03.
    
    Incluye:
    - MTTD promedio (objetivo: minimizar)
    - MTTR promedio (objetivo: minimizar)
    - Disponibilidad (objetivo: >= 99.9%)
    - Referencia mensual de downtime permitido (21.6 min/mes)
    """
    metrics = get_all_services_metrics(window_hours)
    
    # Calcular extrapolación mensual (30 días * 24 horas)
    monthly_hours = 30 * 24
    downtime_ratio = metrics["_global"]["total_downtime_seconds"] / (window_hours * 3600)
    projected_monthly_downtime_seconds = downtime_ratio * monthly_hours * 3600
    projected_monthly_downtime_minutes = projected_monthly_downtime_seconds / 60
    
    # ASR-03: máximo 21.6 minutos de downtime mensual
    max_monthly_downtime_minutes = 21.6
    asr03_compliant = projected_monthly_downtime_minutes <= max_monthly_downtime_minutes
    
    return {
        "experiment_window_hours": window_hours,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "asr03_compliance": {
            "compliant": asr03_compliant,
            "projected_monthly_downtime_minutes": round(projected_monthly_downtime_minutes, 2),
            "max_allowed_monthly_downtime_minutes": max_monthly_downtime_minutes,
            "margin_minutes": round(max_monthly_downtime_minutes - projected_monthly_downtime_minutes, 2),
        },
        "metrics": {
            "mttd_avg_seconds": metrics["_global"]["mttd_avg_seconds"],
            "mttr_avg_seconds": metrics["_global"]["mttr_avg_seconds"],
            "availability_percent": metrics["_global"]["availability_percent"],
            "observed_downtime_seconds": metrics["_global"]["total_downtime_seconds"],
        },
        "per_service": {
            k: v for k, v in metrics.items() if k != "_global"
        },
    }
