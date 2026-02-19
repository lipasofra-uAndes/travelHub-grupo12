# travelHub - Grupo 12

Aplicación de microservicios para la gestión de viajes.

## Arquitectura

- **API Gateway**: Punto de entrada único
- **Servicios**: Búsqueda, reservas y pagos

## Endpoints

- **API Gateway**: `/health`, `/status` y endpoints de los servicios
- **Microservicios**: Endpoint de demostración que cada microservicio responde

## Ejecución

```bash
docker-compose up
```

## Worker Celery

Servicios agregados:
- `redis` (broker/result backend)
- `celery-worker` (colas `ops.process` y `monitoring.ping`)

SQLite compartida en volumen Docker:
- ruta en contenedores: `/data/operations.db`

### Levantar stack

```bash
docker-compose up -d --build
```

### Publicar Ping al worker (Echo por cola)

```bash
docker-compose exec celery-worker python -c "from app.worker.tasks import ping_worker; r = ping_worker.delay('req-001'); print(r.id)"
```

### Publicar procesamiento asíncrono

```bash
docker-compose exec celery-worker python -c "from app.worker.tasks import process_operation; r = process_operation.delay('op-001'); print(r.id)"
```