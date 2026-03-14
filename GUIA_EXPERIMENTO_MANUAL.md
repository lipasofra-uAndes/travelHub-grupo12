# Guía de Experimento Manual — Aislamiento de Tenants y Pipeline de Auditoría

## Objetivo

Validar que:
1. El 100% de solicitudes con `hotelId` manipulado son rechazadas con HTTP 403.
2. El 100% de los intentos detectados generan un evento de auditoría en el Monitor.
3. Bajo concurrencia moderada (~20 solicitudes simultáneas) no se pierden eventos en el pipeline asíncrono.

---

## Requisitos previos

- Docker Desktop corriendo
- Repositorio clonado con `docker-compose.yml` disponible

---

## Paso 0 — Levantar la infraestructura

```powershell
docker-compose up -d --build
```

Esperar ~15 segundos y verificar que los 7 contenedores estén corriendo:

```powershell
docker-compose ps
```

**Esperado:** `redis`, `api-gateway`, `celery-worker`, `reserves-service`, `payments-service`, `search-service`, `monitor` — todos en estado `Up`.

---

## Paso 1 — Verificar salud de los servicios

```powershell
curl http://localhost:5000/health    # API Gateway
curl http://localhost:5005/health    # Worker
curl http://localhost:5006/health    # Monitor
curl http://localhost:5001/health    # Reserves
curl http://localhost:5002/health    # Payments
curl http://localhost:5003/health    # Search
```

**Esperado:** Todos responden `{"status": "UP", ...}` con HTTP 200.

---

## Paso 2 — Generar tokens JWT de prueba

```powershell
docker exec api-gateway python -m app.auth.generate_token
```

Se imprimen dos tokens:

| Token | `sub` | `hotel_id` | Uso |
|-------|--------|-----------|-----|
| AUTORIZADO | `admin_hotel_1` | `hotel_1` | Acceder a `/tarifas/hotel_1` (legítimo) |
| NO AUTORIZADO | `admin_hotel_2` | `hotel_2` | Acceder a `/tarifas/hotel_1` (tampering) |

Copiar ambos tokens para los pasos siguientes.

---

## Paso 3 — Caso legítimo (hotel coincide)

```powershell
curl -X PUT http://localhost:5000/tarifas/hotel_1 `
  -H "Content-Type: application/json" `
  -H "Authorization: Bearer <TOKEN_AUTORIZADO>" `
  -d '{"rates": {"standard": 100, "premium": 200}}'
```

**Esperado:**
- HTTP **202 Accepted**
- Body contiene `"status": "PENDING"` y un `operation_id`

Verificar en logs del monitor:

```powershell
docker logs monitor --tail 20
```

Debe aparecer un `[AUDIT ENTRY]` con `status=AUTHORIZED` y `action=UPDATE_RATES_STARTED`.

---

## Paso 4 — Caso de tampering (hotel NO coincide)

Un usuario de `hotel_2` intenta modificar tarifas de `hotel_1`:

```powershell
curl -X PUT http://localhost:5000/tarifas/hotel_1 `
  -H "Content-Type: application/json" `
  -H "Authorization: Bearer <TOKEN_NO_AUTORIZADO>" `
  -d '{"rates": {"standard": 999, "premium": 999}}'
```

**Esperado:**
- HTTP **403 Forbidden**
- Body: `{"error": "No autorizado", "message": "No tienes permiso para modificar las tarifas de este hotel"}`

---

## Paso 5 — Verificar evento de auditoría del tampering

```powershell
docker logs monitor --tail 50
```

**Esperado:** Aparecen dos entradas relacionadas al intento de tampering:

```
[SECURITY EVENT] SecurityViolationEvent eventId=...
  userId=admin_hotel_2 tokenHotelId=hotel_2 requestedHotelId=hotel_1
  endpoint=/tarifas/hotel_1 method=PUT action=UPDATE_RATES_DENIED

[AUDIT ENTRY] AuditLogEntry id=... eventId=...
  status=FORBIDDEN payload_keys=[...]
```

Esto confirma que:
1. La solicitud fue rechazada con 403
2. El evento viajó por Celery (cola `security.logs`)
3. El Monitor lo consumió y registró

---

## Paso 6 — Edge case: sin token

```powershell
curl -X PUT http://localhost:5000/tarifas/hotel_1 `
  -H "Content-Type: application/json" `
  -d '{"rates": {"standard": 100}}'
```

**Esperado:** HTTP **403** — header `Authorization` ausente.

---

## Paso 7 — Edge case: token expirado

Generar un token con expiración inmediata:

```powershell
docker exec api-gateway python -c "
from app.auth.generate_token import generate_token
print(generate_token('admin_hotel_1', 'hotel_1', expires_hours=0))
"
```

Usar ese token:

```powershell
curl -X PUT http://localhost:5000/tarifas/hotel_1 `
  -H "Content-Type: application/json" `
  -H "Authorization: Bearer <TOKEN_EXPIRADO>" `
  -d '{"rates": {"standard": 100}}'
```

**Esperado:** HTTP **403** — token expirado.

---

## Paso 8 — Prueba de concurrencia (~20 solicitudes simultáneas)

```powershell
$token = "<TOKEN_NO_AUTORIZADO>"
$jobs = 1..20 | ForEach-Object {
    Start-Job -ScriptBlock {
        param($t, $i)
        $result = curl.exe -s -o NUL -w "%{http_code}" `
          -X PUT "http://localhost:5000/tarifas/hotel_1" `
          -H "Content-Type: application/json" `
          -H "Authorization: Bearer $t" `
          --data '{"rates":{"standard":999}}'
        "Request ${i}: HTTP $result"
    } -ArgumentList $token, $_
}
$jobs | Wait-Job | Receive-Job
$jobs | Remove-Job
```

**Esperado:** Las 20 solicitudes devuelven HTTP **403**.

Verificar que no se perdieron eventos:

```powershell
docker logs monitor --tail 200 | Select-String "SECURITY EVENT" | Measure-Object
```

**Esperado:** `Count: 20` — un evento de seguridad por cada solicitud, sin pérdida de mensajes.

---

## Resumen de verificaciones

| Paso | Qué se valida | Resultado esperado |
|------|---------------|-------------------|
| 0 | Infraestructura levantada | 7 contenedores `Up` |
| 1 | Salud de servicios | Todos responden HTTP 200 |
| 3 | Solicitud legítima | HTTP 202 + log `AUTHORIZED` |
| 4 | Tampering de hotelId | HTTP 403 + log `FORBIDDEN` |
| 5 | Pipeline de auditoría | Evento en logs del Monitor |
| 6 | Sin token | HTTP 403 |
| 7 | Token expirado | HTTP 403 |
| 8 | 20 solicitudes concurrentes | 20× 403 + 20 eventos en auditoría |

---

## Criterios de éxito

- **Aislamiento de tenants:** 100% de solicitudes con hotelId manipulado rechazadas (403).
- **Confiabilidad del pipeline:** 100% de violaciones detectadas generan un evento de auditoría.
- **Concurrencia:** 0 eventos perdidos bajo 20 solicitudes simultáneas.
