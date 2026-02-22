import os
from celery import Celery

from app.constants.queues import (
    OPERATIONS_QUEUE,
    PING_QUEUE,
    ECHO_QUEUE,
    TASK_PROCESS_OPERATION,
    TASK_PING_WORKER,
    TASK_PING_ALL_SERVICES,
    TASK_ECHO_RESPONSE,
)

BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0")
RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", BROKER_URL)

celery_app = Celery("travelhub_worker", broker=BROKER_URL, backend=RESULT_BACKEND)
celery_app.conf.update(
    task_default_queue=OPERATIONS_QUEUE,
    task_routes={
        TASK_PROCESS_OPERATION: {"queue": OPERATIONS_QUEUE},
        TASK_PING_WORKER: {"queue": PING_QUEUE},
        TASK_PING_ALL_SERVICES: {"queue": PING_QUEUE},
        TASK_ECHO_RESPONSE: {"queue": ECHO_QUEUE},
    },
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)

celery_app.autodiscover_tasks(["app.worker"])
