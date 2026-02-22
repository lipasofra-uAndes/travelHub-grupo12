#!/usr/bin/env python
"""Script de inicio para el Monitor Service con Celery + Flask + Ping Loop"""

import os
import sys
from multiprocessing import Process

# Asegurar que la app está en el path
sys.path.insert(0, '/app')

from app.monitor.monitor_service import MonitorService, monitor_celery
from app.monitor.api import app as flask_app
from app.worker.db import init_db
from app.constants.queues import ECHO_QUEUE


def run_celery():
    """Ejecuta el worker Celery que consume echo responses"""
    monitor_celery.worker_main(argv=[
        'worker',
        '--loglevel=info',
        f'--queues={ECHO_QUEUE}',
        '--hostname=monitor@%h',
    ])


def run_flask():
    """Ejecuta el servidor Flask con la API del monitor"""
    flask_app.run(
        host='0.0.0.0',
        port=5006,
        debug=False,
        use_reloader=False,
    )


def run_ping_loop():
    """Ejecuta el loop de ping del monitor"""
    monitor = MonitorService()
    monitor.running = True
    monitor.ping_loop()


if __name__ == '__main__':
    # Inicializar DB
    init_db()
    
    # Crear procesos para Celery, Flask y Ping Loop
    celery_process = Process(target=run_celery, daemon=False)
    flask_process = Process(target=run_flask, daemon=False)
    ping_process = Process(target=run_ping_loop, daemon=False)
    
    print("🔍 Iniciando Monitor Service...")
    print("   - Celery: escuchando cola monitoring.echo")
    print("   - Flask API: escuchando en puerto 5006")
    print("   - Ping Loop: enviando pings cada 5 segundos")
    
    celery_process.start()
    flask_process.start()
    ping_process.start()
    
    try:
        celery_process.join()
        flask_process.join()
        ping_process.join()
    except KeyboardInterrupt:
        print("\n📴 Deteniendo Monitor Service...")
        celery_process.terminate()
        flask_process.terminate()
        ping_process.terminate()
