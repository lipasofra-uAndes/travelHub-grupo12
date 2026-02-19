"""Configuración dinámica del worker para inyectar fallos"""

from threading import Lock
from datetime import datetime, timedelta
from typing import Optional

_config_lock = Lock()
_failure_rate: float = 0.0  # Probabilidad de fallo (0.0 a 1.0)
_force_failure: bool = False  # Fuerza fallo garantizado
_last_failure: Optional[datetime] = None  # Timestamp del último fallo


def set_failure_rate(rate: float) -> None:
    """
    Establece la probabilidad de fallo.
    
    Args:
        rate: Número entre 0.0 (sin fallos) y 1.0 (fallo garantizado)
    """
    global _failure_rate
    if not (0.0 <= rate <= 1.0):
        raise ValueError(f"Failure rate debe estar entre 0.0 y 1.0, recibido: {rate}")
    
    with _config_lock:
        _failure_rate = rate


def set_force_failure(force: bool) -> None:
    """
    Fuerza fallo garantizado.
    
    Args:
        force: True para forzar siempre fallo, False para deshabilitar
    """
    global _force_failure
    with _config_lock:
        _force_failure = force


def get_failure_config() -> dict:
    """Retorna la configuración actual de fallos"""
    with _config_lock:
        return {
            "failure_rate": _failure_rate,
            "force_failure": _force_failure,
            "last_failure": _last_failure.isoformat() if _last_failure else None,
        }


def record_failure() -> None:
    """Registra que ocurrió un fallo"""
    global _last_failure
    with _config_lock:
        _last_failure = datetime.utcnow()


def should_fail() -> bool:
    """Determina si la próxima operación debe fallar"""
    with _config_lock:
        return _force_failure or _failure_rate > 0


def get_failure_rate() -> float:
    """Retorna la probabilidad de fallo actual"""
    with _config_lock:
        return _failure_rate


def get_force_failure() -> bool:
    """Retorna si el fallo está forzado"""
    with _config_lock:
        return _force_failure


def reset_config() -> None:
    """Resetea la configuración a valores por defecto"""
    global _failure_rate, _force_failure, _last_failure
    with _config_lock:
        _failure_rate = 0.0
        _force_failure = False
        _last_failure = None


def has_recent_failure(seconds: int = 30) -> bool:
    """
    Verifica si hubo un fallo en los últimos N segundos.
    
    Args:
        seconds: Ventana de tiempo en segundos
        
    Returns:
        True si hubo fallo reciente, False en caso contrario
    """
    with _config_lock:
        if _last_failure is None:
            return False
        
        time_since_failure = datetime.utcnow() - _last_failure
        return time_since_failure < timedelta(seconds=seconds)
