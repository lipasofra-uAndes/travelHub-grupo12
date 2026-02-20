# travelHub - Grupo 12

Aplicación de microservicios para la gestión de viajes con procesamiento asíncrono y tolerancia a fallos.

## Inicio Rápido

```bash
docker-compose up -d
```

Todos los servicios están listos en ~5 segundos. El API Gateway acepta solicitudes en `http://localhost:5000`.

## Arquitectura

- **API Gateway** (puerto 5000): Punto de entrada único - recibe solicitudes y las encola
- **Celery Worker** (puerto 5005): Procesa operaciones asíncrono desde Redis
- **Redis** (puerto 6379): Broker de mensajes y almacén de resultados
- **Microservicios** (puertos 5001-5003): Servicios específicos de dominio (internos, no accesibles directamente)

## Endpoints /health, /ready, y operaciones críticas

### Health y Ready Checks

```bash
# Health check - verifica que el Gateway está vivo
curl http://localhost:5000/health
# {"status": "UP", "service": "API Gateway"}

# Ready check - verifica que está listo para aceptar solicitudes
curl http://localhost:5000/ready
# {"status": "READY", "service": "API Gateway", "message": "..."}
```

### Operaciones Asíncronas (Aceptación Rápida)

Todos estos endpoints responden **inmediatamente con 202 ACCEPTED** y encolan la operación para procesamiento asíncrono:

```bash
# 1. Encolación de reserva
curl -X POST http://localhost:5000/reserve \
  -H "Content-Type: application/json" \
  -d '{"total": 500, "moneda": "ARS"}'
# Respuesta (202 ACCEPTED):
# {
#   "operation_id": "uuid-xxx",
#   "status": "PENDING",
#   "status_url": "/ops/uuid-xxx"
# }

# 2. Encolación de pago
curl -X POST http://localhost:5000/pay \
  -H "Content-Type: application/json" \
  -d '{"monto": 100, "moneda": "USD", "token": "tok_test"}'
# Respuesta (202 ACCEPTED) con operation_id

# 3. Encolación de búsqueda
curl -X POST http://localhost:5000/search \
  -H "Content-Type: application/json" \
  -d '{"query": "propiedades en buenos aires"}'
# Respuesta (202 ACCEPTED) con operation_id
```

### Consultar Estado de Operaciones

```bash
# Consultar estado (normalmente pasa: PENDING → PROCESSING → PROCESSED)
curl http://localhost:5000/ops/uuid-xxx
# {
#   "operation_id": "uuid-xxx",
#   "type": "reserve",
#   "status": "PROCESSED",
#   "error": null,
#   "created_at": "2026-02-20T20:25:26Z",
#   "updated_at": "2026-02-20T20:25:27Z"
# }
```

### Ping/Echo para Monitoreo

```bash
# El API monitorea su salud respondiendo a pings
curl -X POST http://localhost:5000/ping \
  -H "Content-Type: application/json" \
  -d '{"request_id": "req-001"}'
# {
#   "service": "api",
#   "request_id": "req-001",
#   "status": "UP",
#   "ts": "2026-02-20T20:25:32Z"
# }
```

### Resilencia a Fallos del Worker

**El API Gateway sigue aceptando solicitudes aunque el Celery worker esté caído.**

```bash
# 1. Detener el worker
docker-compose stop celery-worker

# 2. Hacer solicitudes - siguen siendo aceptadas (202)
curl -X POST http://localhost:5000/reserve \
  -H "Content-Type: application/json" \
  -d '{"total": 100, "moneda": "USD"}'
# → Responde con 202 ACCEPTED

# 3. Reiniciar el worker - procesa las operaciones pendientes
docker-compose start celery-worker

# 4. Consultar estado - ahora están PROCESSED
curl http://localhost:5000/ops/operation-id
# → status: "PROCESSED"
```

## Configuracion dinamica de fallos

### Celery Worker con Flask

El worker ejecuta tanto Celery como un servidor Flask en paralelo para permitir configuración dinámica de fallos.

### Servicios

- `redis` (broker/result backend en puerto 6379)
- `celery-worker` (colas `ops.process` y `monitoring.ping`)
  - Celery: consume y procesa tasks de forma asíncrona
  - Flask: servidor de configuración en puerto 5005


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
