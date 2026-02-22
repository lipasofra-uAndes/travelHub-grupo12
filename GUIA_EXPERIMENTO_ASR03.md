# Guía del Experimento ASR-03: Validación de Disponibilidad mediante Monitor Ping/Echo

## 1. Resumen del Experimento

### Objetivo
Validar que el sistema detecta la indisponibilidad de servicios críticos en menos de **20 segundos (MTTD)** y recupera el servicio en menos de **30 segundos (MTTR)** mediante un patrón de monitoreo **Ping/Echo asíncrono**.

### Hipótesis
> "Cuando el Monitor de Salud detecta N fallas consecutivas de un servicio crítico (reserves, payments, search), el sistema activa automáticamente la recuperación, logrando un MTTD ≤ 20s y MTTR ≤ 30s."

### Arquitectura
```
┌─────────────────┐     Ping (async)     ┌─────────────────┐
│                 │ ──────────────────── │                 │
│  Monitor de     │       Redis          │  Celery Worker  │
│  Salud (:5006)  │ ◄──────────────────  │     (:5005)     │
│                 │     Echo (async)     │                 │
└─────────────────┘                      └─────────────────┘
        │                                        │
        │  HTTP /health                 HTTP /health
        ▼                                        ▼
┌─────────────────┐                  ┌─────────────────────┐
│ Servicios:      │                  │ Servicios críticos: │
│ - API Gateway   │                  │ - Reserves (:5001)  │
│ - Redis         │                  │ - Payments (:5002)  │
│                 │                  │ - Search (:5003)    │
└─────────────────┘                  └─────────────────────┘
```

### Parámetros de Configuración
| Parámetro | Valor | Descripción |
|-----------|-------|-------------|
| `MONITOR_PING_INTERVAL_SECONDS` | 5s | Intervalo entre pings a todos los servicios |
| `CONSECUTIVE_FAILURES_THRESHOLD` | 3 | Nº de fallas consecutivas para crear incidente |
| `PING_TIMEOUT_SECONDS` | 5s | Timeout máximo de respuesta HTTP |
| `RECOVERY_CHECK_THRESHOLD` | 3 | UPs consecutivos para resolver incidente |

---

## 2. Pre-requisitos

```powershell
# Verificar Docker está corriendo
docker info

# Estar en el directorio del proyecto
cd D:\maestria-uniandes\arquitecturas-agiles\travelHub-grupo12
```

---

## 3. Ejecución del Experimento

### Paso 1: Levantar la infraestructura

```powershell
# Construir y levantar todos los servicios
docker-compose up -d --build

# Verificar que todos los contenedores están corriendo
docker-compose ps
```

Esperar ~30 segundos para que todos los servicios inicialicen.

### Paso 2: Verificar estado inicial

```powershell
# Verificar que el monitor está activo
curl.exe http://localhost:5006/status

# Verificar health de servicios críticos
curl.exe http://localhost:5001/health  # reserves
curl.exe http://localhost:5002/health  # payments
curl.exe http://localhost:5003/health  # search
curl.exe http://localhost:5005/health  # worker
```

### Paso 3: Inyectar falla (failure rate 100%)

```powershell
# Opción 1: Comillas simples (PowerShell 7+)
curl.exe -X POST http://localhost:5005/config/failure-rate -H "Content-Type: application/json" -d '{"rate": 1.0}'

# Opción 2: Escape con backtick (PowerShell 5.1)
curl.exe -X POST http://localhost:5005/config/failure-rate -H "Content-Type: application/json" -d "{`"rate`": 1.0}"

# Opción 3: Variable auxiliar
$body = '{"rate": 1.0}'
curl.exe -X POST http://localhost:5005/config/failure-rate -H "Content-Type: application/json" -d $body
```

**Nota:** `rate: 1.0` = 100% de fallas. Esto simula que el worker falla en todas las operaciones.

### Paso 4: Esperar detección y recuperación

El sistema debería:
1. Detectar las fallas en ~15 segundos (3 pings × 5s intervalo)
2. Crear un incidente automáticamente
3. Intentar recuperar el servicio (docker restart)
4. Resolver el incidente cuando el servicio responda

**Tiempo estimado:** 20-45 segundos para un ciclo completo.

### Paso 5: Verificar incidentes creados

```powershell
# Ver incidentes activos
curl.exe http://localhost:5006/incidents/active

# Ver todos los incidentes
curl.exe http://localhost:5006/incidents

# Ver incidentes de un servicio específico
curl.exe http://localhost:5006/incidents/worker
```

### Paso 6: Restaurar servicio (opcional)

```powershell
# Quitar la inyección de fallas
$body = '{"rate": 0.0}'
curl.exe -X POST http://localhost:5005/config/failure-rate -H "Content-Type: application/json" -d $body
```

---

## 4. Métricas a Revisar

### Endpoint Principal: `/metrics/experiment`

```powershell
# Métricas del experimento (última hora)
curl.exe "http://localhost:5006/metrics/experiment?window_hours=1"

# Métricas de las últimas 24 horas
curl.exe "http://localhost:5006/metrics/experiment?window_hours=24"
```

**Respuesta ejemplo:**
```json
{
  "experiment": "ASR-03",
  "description": "Validación de disponibilidad de servicios críticos",
  "window_hours": 1,
  "global_metrics": {
    "total_incidents": 5,
    "resolved_incidents": 4,
    "active_incidents": 1,
    "mttd_avg_seconds": 15.2,
    "mttr_avg_seconds": 22.5,
    "overall_availability_percent": 98.5
  },
  "hypothesis_validation": {
    "mttd_target_seconds": 20,
    "mttd_actual_seconds": 15.2,
    "mttd_met": true,
    "mttr_target_seconds": 30,
    "mttr_actual_seconds": 22.5,
    "mttr_met": true,
    "hypothesis_validated": true
  },
  "per_service": { ... }
}
```

### Métricas Clave

| Métrica | Objetivo | Descripción |
|---------|----------|-------------|
| **MTTD** | ≤ 20s | Mean Time To Detect - Tiempo desde que inicia la falla hasta que se detecta |
| **MTTR** | ≤ 30s | Mean Time To Recover - Tiempo desde detección hasta recuperación |
| **MTBF** | - | Mean Time Between Failures - Tiempo entre fallas |
| **Availability %** | ≥ 99% | Porcentaje de tiempo que el servicio estuvo disponible |

### Otros Endpoints de Métricas

```powershell
# Métricas de todos los servicios
curl.exe "http://localhost:5006/metrics?window_hours=1"

# Métricas de un servicio específico
curl.exe "http://localhost:5006/metrics/worker?window_hours=1"
curl.exe "http://localhost:5006/metrics/reserves?window_hours=1"

# Health checks recientes
curl.exe "http://localhost:5006/health-checks?limit=20"
curl.exe "http://localhost:5006/health-checks/worker?limit=10"
```

---

## 5. Generación de 60 Datos

Para cumplir con el requisito del profesor de **60 datos**, se deben ejecutar múltiples ciclos de inyección de falla → detección → recuperación.

### Estrategia Recomendada

| Servicio | Iteraciones | Total Incidentes |
|----------|-------------|------------------|
| worker | 20 | 20 |
| reserves | 20 | 20 |
| payments | 20 | 20 |
| **Total** | | **60** |

### Script de Automatización

Crear archivo `run_experiment.ps1`:

```powershell
# Configuración
$iterations = 20
$waitBetweenInjections = 60  # segundos entre inyecciones

Write-Host "=== Experimento ASR-03: Generando $($iterations) incidentes ===" -ForegroundColor Cyan

for ($i = 1; $i -le $iterations; $i++) {
    Write-Host "`n--- Iteración $i de $iterations ---" -ForegroundColor Yellow
    
    # 1. Inyectar falla
    Write-Host "Inyectando falla..."
    $body = '{"rate": 1.0}'
    curl.exe -X POST http://localhost:5005/config/failure-rate -H "Content-Type: application/json" -d $body -s | Out-Null
    
    # 2. Esperar detección y recuperación (~30s)
    Write-Host "Esperando detección y recuperación..."
    Start-Sleep -Seconds 30
    
    # 3. Restaurar servicio
    Write-Host "Restaurando servicio..."
    $body = '{"rate": 0.0}'
    curl.exe -X POST http://localhost:5005/config/failure-rate -H "Content-Type: application/json" -d $body -s | Out-Null
    
    # 4. Esperar estabilización
    Write-Host "Esperando estabilización..."
    Start-Sleep -Seconds $waitBetweenInjections
    
    # 5. Mostrar progreso
    $metrics = curl.exe "http://localhost:5006/metrics/experiment?window_hours=24" -s | ConvertFrom-Json
    Write-Host "Incidentes totales: $($metrics.global_metrics.total_incidents)"
}

Write-Host "`n=== Experimento completado ===" -ForegroundColor Green
curl.exe "http://localhost:5006/metrics/experiment?window_hours=24"
```

Ejecutar:
```powershell
.\run_experiment.ps1
```

**Tiempo estimado:** ~30 minutos para 20 iteraciones.

### Método Manual (paso a paso)

1. **Inyectar falla:**
   ```powershell
   curl.exe -X POST http://localhost:5005/config/failure-rate -H "Content-Type: application/json" -d '{"rate": 1.0}'
   ```

2. **Esperar 30-45 segundos** (detección + recuperación)

3. **Restaurar:**
   ```powershell
   curl.exe -X POST http://localhost:5005/config/failure-rate -H "Content-Type: application/json" -d '{"rate": 0.0}'
   ```

4. **Esperar 60 segundos** (estabilización)

5. **Repetir** hasta tener 60 incidentes

---

## 6. Reiniciar el Experimento (Datos Nuevos)

Para empezar de cero con métricas limpias:

### Opción 1: Recrear base de datos

```powershell
# Detener servicios
docker-compose down

# Eliminar volumen de datos (si existe)
docker volume rm travelhub-grupo12_db-data 2>$null

# O eliminar archivo SQLite directamente
Remove-Item -Path ".\operations.db" -Force 2>$null

# Reconstruir y levantar
docker-compose up -d --build
```

### Opción 2: Limpiar tablas desde SQLite

```powershell
# Conectar a SQLite dentro del contenedor
docker exec -it monitor-service sqlite3 /app/operations.db

# Dentro de SQLite:
DELETE FROM incidents;
DELETE FROM health_checks;
.quit
```

### Opción 3: Reinicio completo

```powershell
# Detener y eliminar todo
docker-compose down -v

# Reconstruir desde cero
docker-compose up -d --build
```

---

## 7. Criterios de Éxito/Falla

### El experimento es **EXITOSO** si:

| Criterio | Condición |
|----------|-----------|
| MTTD promedio | ≤ 20 segundos |
| MTTR promedio | ≤ 30 segundos |
| Detección automática | 100% de fallas inyectadas generaron incidente |
| Recuperación automática | El servicio se recuperó sin intervención manual |

### El experimento **FALLA** si:

- MTTD promedio > 20 segundos
- MTTR promedio > 30 segundos
- Incidentes no se crean automáticamente
- La recuperación requiere intervención manual

### Verificación Final

```powershell
# Obtener resumen final
curl.exe "http://localhost:5006/metrics/experiment?window_hours=24"
```

Buscar en la respuesta:
```json
{
  "hypothesis_validation": {
    "mttd_met": true,        // ← Debe ser true
    "mttr_met": true,        // ← Debe ser true
    "hypothesis_validated": true  // ← Debe ser true
  }
}
```

---

## 8. Troubleshooting

### El monitor no detecta fallas
```powershell
# Verificar logs del monitor
docker logs monitor-service -f

# Verificar que el monitor está corriendo
curl.exe http://localhost:5006/status
```

### Los incidentes no se crean
```powershell
# Verificar configuración
# CONSECUTIVE_FAILURES_THRESHOLD = 3 (necesita 3 fallas seguidas)

# Verificar health checks
curl.exe "http://localhost:5006/health-checks?limit=10"
```

### La recuperación automática no funciona
```powershell
# Verificar que Docker socket está montado
docker inspect monitor-service | Select-String "docker.sock"

# Verificar logs de recuperación
docker logs monitor-service 2>&1 | Select-String "recovery"
```

### Servicios no responden
```powershell
# Reiniciar un servicio manualmente
docker-compose restart celery-worker

# Ver logs de un servicio
docker-compose logs -f celery-worker
```

---

## 9. Exportar Datos para Análisis

### Obtener todos los incidentes en JSON

```powershell
# Guardar incidentes a archivo
curl.exe "http://localhost:5006/incidents?limit=100" -o incidentes.json

# Guardar métricas a archivo
curl.exe "http://localhost:5006/metrics/experiment?window_hours=24" -o metricas_experimento.json
```

### Formato CSV (para Excel)

```powershell
# Obtener incidentes y convertir a CSV
$incidents = curl.exe "http://localhost:5006/incidents?limit=100" -s | ConvertFrom-Json
$incidents.incidents | Export-Csv -Path "incidentes.csv" -NoTypeInformation
```

---

## 10. Resumen de Endpoints

| Endpoint | Método | Descripción |
|----------|--------|-------------|
| `/status` | GET | Estado del monitor |
| `/health` | GET | Health check del monitor |
| `/metrics` | GET | Métricas de todos los servicios |
| `/metrics/<service>` | GET | Métricas de un servicio |
| `/metrics/experiment` | GET | **Resumen del experimento ASR-03** |
| `/incidents` | GET | Lista todos los incidentes |
| `/incidents/active` | GET | Incidentes activos |
| `/incidents/<service>` | GET | Incidentes de un servicio |
| `/health-checks` | GET | Health checks recientes |
| `/health-checks/<service>` | GET | Health checks de un servicio |
| `/ping` | POST | Forzar ping a todos los servicios |
| `/evaluate` | POST | Forzar evaluación de incidentes |

---

**Autor:** TravelHub Grupo 12  
**Fecha:** Febrero 2026  
**Curso:** Arquitecturas Ágiles - Universidad de los Andes
