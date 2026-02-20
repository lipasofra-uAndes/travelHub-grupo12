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

## Worker Celery + Flask

El worker ejecuta tanto Celery como un servidor Flask en paralelo para permitir configuración dinámica de fallos.

### Servicios

- `redis` (broker/result backend en puerto 6379)
- `celery-worker` (colas `ops.process` y `monitoring.ping`)
  - Celery: consume y procesa tasks de forma asíncrona
  - Flask: servidor de configuración en puerto 5005

### Levantar stack

```bash
docker-compose up -d --build
```

### Integración de Fallos Dinámicos

El worker ahora admite inyección dinámica de fallos mediante endpoints Flask:

#### GET /config
Obtiene la configuración actual de fallos

```bash
curl http://localhost:5005/config
# Respuesta:
# {
#   "failure_rate": 0.5,
#   "force_failure": false,
#   "last_failure": "2026-02-19T19:05:30.123456Z"
# }
```

#### POST /config/failure-rate
Establece la probabilidad de fallo (0.0 a 1.0)

```bash
# 50% de probabilidad de fallo
curl -X POST http://localhost:5005/config/failure-rate \
  -H "Content-Type: application/json" \
  -d '{"rate": 0.5}'

# Sin fallos
curl -X POST http://localhost:5005/config/failure-rate \
  -H "Content-Type: application/json" \
  -d '{"rate": 0.0}'

# 100% de probabilidad (siempre falla)
curl -X POST http://localhost:5005/config/failure-rate \
  -H "Content-Type: application/json" \
  -d '{"rate": 1.0}'
```

#### POST /config/force-failure
Fuerza que todas las operaciones fallen

```bash
# Forzar fallos
curl -X POST http://localhost:5005/config/force-failure \
  -H "Content-Type: application/json" \
  -d '{"force": true}'

# Deshabilitar fallo forzado
curl -X POST http://localhost:5005/config/force-failure \
  -H "Content-Type: application/json" \
  -d '{"force": false}'
```

#### POST /config/reset
Resetea toda la configuración a valores por defecto

```bash
curl -X POST http://localhost:5005/config/reset
```

#### GET /health
Health check del worker

```bash
curl http://localhost:5005/health
# Respuesta: {"status": "OK"}
```

### Detección de Salud por Ping/Echo

El worker detecta dinámicamente si está en buen estado:

- **UP**: No hay fallos recientes (sin fallos en los últimos 30 segundos)
- **UNHEALTHY**: Hay fallos recientes (últimas operaciones fallaron)

```bash
# Simular fallo
curl -X POST http://localhost:5005/config/force-failure \
  -H "Content-Type: application/json" \
  -d '{"force": true}'

# El siguiente ping reportará UNHEALTHY
docker-compose exec celery-worker python -c "from app.worker.tasks import ping_worker; r = ping_worker.delay('ping-001'); print(r.get())"
# Retorna: {"service": "worker", "request_id": "ping-001", "status": "UNHEALTHY", "ts": "..."}

# Resetear configuración
curl -X POST http://localhost:5005/config/reset

# El siguiente ping reportará UP nuevamente
docker-compose exec celery-worker python -c "from app.worker.tasks import ping_worker; r = ping_worker.delay('ping-002'); print(r.get())"
# Retorna: {"service": "worker", "request_id": "ping-002", "status": "UP", "ts": "..."}
```

### Ejemplo: Simular Degradación de Servicio

```bash
# 1. Configurar 30% de probabilidad de fallo
curl -X POST http://localhost:5005/config/failure-rate \
  -H "Content-Type: application/json" \
  -d '{"rate": 0.3}'

# 2. Procesar operaciones - algunas fallarán y se reintentar

# 3. Monitorear estado con pings - verán UNHEALTHY después de fallos

# 4. Resetear cuando la degradación ha pasado
curl -X POST http://localhost:5005/config/reset
```

### Publicar Ping al worker (Echo por cola)

```bash
docker-compose exec -T celery-worker python -c "from app.worker.tasks import ping_worker; r = ping_worker.delay('req-001'); print(r.get())"
```

### Publicar procesamiento asíncrono

```bash
docker-compose exec -T celery-worker python -c "from app.worker.celery_app import celery_app; from app.worker.db import save_operation; from app.models.operation import Operation; op = Operation.pending('op-001', 'payment', {'amount': 100}); save_operation(op); r = celery_app.send_task('worker.process_operation', args=('op-001',)); print(r.id)"
```