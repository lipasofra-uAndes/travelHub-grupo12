#!/usr/bin/env python
"""Script de inicio para el worker con Celery + Flask"""

import os
import sys
from multiprocessing import Process

# Asegurar que la app está en el path
sys.path.insert(0, '/app')

from app.worker.celery_app import celery_app
from app.worker.flask_app import flask_app


def run_celery():
    """Ejecuta el worker Celery"""
    celery_app.worker_main(argv=[
        'worker',
        '--loglevel=info',
        '--queues=ops.process,monitoring.ping',
    ])


def run_flask():
    """Ejecuta el servidor Flask"""
    flask_app.run(
        host='0.0.0.0',
        port=5005,
        debug=False,
        use_reloader=False,
    )


if __name__ == '__main__':
    # Crear procesos para Celery y Flask
    celery_process = Process(target=run_celery, daemon=False)
    flask_process = Process(target=run_flask, daemon=False)
    
    print("🚀 Iniciando Worker con Celery + Flask...")
    print("   - Celery: escuchando colas ops.process, monitoring.ping")
    print("   - Flask: escuchando en puerto 5005")
    
    celery_process.start()
    flask_process.start()
    
    try:
        celery_process.join()
        flask_process.join()
    except KeyboardInterrupt:
        print("\n📴 Deteniendo worker...")
        celery_process.terminate()
        flask_process.terminate()
        celery_process.join()
        flask_process.join()
