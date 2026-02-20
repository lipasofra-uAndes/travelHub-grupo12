import random
import time
from datetime import datetime
from celery.exceptions import MaxRetriesExceededError

from app.worker.celery_app import celery_app
from app.worker.db import get_operation, init_db, log_echo, update_operation_status
from app.worker.config import (
    get_failure_rate,
    get_force_failure,
    record_failure,
    has_recent_failure,
)
from app.constants.queues import (
    TASK_PROCESS_OPERATION,
    TASK_PING_WORKER,
    TASK_ECHO_RESPONSE,
    ECHO_QUEUE,
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
