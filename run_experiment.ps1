# ============================================================
# Script de Experimento ASR-03: Generación de 60 Incidentes
# ============================================================
# Este script automatiza la generación de incidentes para medir
# MTTD (Mean Time To Detect) y MTTR (Mean Time To Recover)
# ============================================================

param(
    [int]$TotalIncidents = 60,
    [int]$WaitForDetection = 25,      # Segundos para que detecte (3 pings x 5s + margen)
    [int]$WaitForRecovery = 25,       # Segundos para que se recupere
    [int]$WaitBetweenCycles = 10,     # Segundos entre ciclos
    [switch]$DryRun = $false          # Si es true, solo muestra qué haría
)

$ErrorActionPreference = "Stop"

# Colores para output
function Write-Status { param($msg) Write-Host $msg -ForegroundColor Cyan }
function Write-Success { param($msg) Write-Host $msg -ForegroundColor Green }
function Write-Warning { param($msg) Write-Host $msg -ForegroundColor Yellow }
function Write-Error { param($msg) Write-Host $msg -ForegroundColor Red }

# Banner
Write-Host ""
Write-Host "============================================================" -ForegroundColor Magenta
Write-Host "   EXPERIMENTO ASR-03: Validacion Disponibilidad Servicios" -ForegroundColor Magenta
Write-Host "============================================================" -ForegroundColor Magenta
Write-Host ""
Write-Status "Configuracion:"
Write-Host "  - Incidentes a generar: $TotalIncidents"
Write-Host "  - Espera deteccion:     $WaitForDetection s"
Write-Host "  - Espera recuperacion:  $WaitForRecovery s"
Write-Host "  - Pausa entre ciclos:   $WaitBetweenCycles s"
Write-Host ""

$totalTimeEstimate = $TotalIncidents * ($WaitForDetection + $WaitForRecovery + $WaitBetweenCycles)
$minutes = [math]::Round($totalTimeEstimate / 60, 1)
Write-Warning "Tiempo estimado: ~$minutes minutos"
Write-Host ""

if ($DryRun) {
    Write-Warning "MODO DRY-RUN: No se ejecutaran comandos reales"
    Write-Host ""
}

# Verificar que los servicios estan corriendo
Write-Status "Verificando servicios..."
try {
    $monitorStatus = curl.exe -s http://localhost:5006/health | ConvertFrom-Json
    $workerStatus = curl.exe -s http://localhost:5005/health | ConvertFrom-Json
    Write-Success "  Monitor: $($monitorStatus.status)"
    Write-Success "  Worker:  $($workerStatus.status)"
} catch {
    Write-Error "Error: Los servicios no estan disponibles. Ejecuta 'docker-compose up -d' primero."
    exit 1
}

Write-Host ""
Write-Warning "Presiona ENTER para iniciar o Ctrl+C para cancelar..."
Read-Host

$startTime = Get-Date
$successfulIncidents = 0
$failedIncidents = 0

for ($i = 1; $i -le $TotalIncidents; $i++) {
    $cycleStart = Get-Date
    
    Write-Host ""
    Write-Host "------------------------------------------------------------" -ForegroundColor DarkGray
    Write-Status "INCIDENTE $i de $TotalIncidents"
    Write-Host "------------------------------------------------------------" -ForegroundColor DarkGray
    
    # === PASO 1: Detener el worker ===
    Write-Warning "[$(Get-Date -Format 'HH:mm:ss')] Deteniendo worker..."
    if (-not $DryRun) {
        docker stop celery-worker 2>$null | Out-Null
    }
    
    # === PASO 2: Esperar detección ===
    Write-Status "[$(Get-Date -Format 'HH:mm:ss')] Esperando deteccion (${WaitForDetection}s)..."
    if (-not $DryRun) {
        Start-Sleep -Seconds $WaitForDetection
    }
    
    # Verificar que se creó el incidente
    if (-not $DryRun) {
        $activeIncidents = curl.exe -s http://localhost:5006/incidents/active | ConvertFrom-Json
        if ($activeIncidents.total -gt 0) {
            $incident = $activeIncidents.incidents | Where-Object { $_.service -eq "worker" }
            if ($incident) {
                Write-Success "[$(Get-Date -Format 'HH:mm:ss')] Incidente detectado - MTTD: $([math]::Round($incident.mttd_seconds, 2))s"
            }
        } else {
            Write-Warning "[$(Get-Date -Format 'HH:mm:ss')] No se detecto incidente aun..."
        }
    }
    
    # === PASO 3: Reiniciar el worker ===
    Write-Warning "[$(Get-Date -Format 'HH:mm:ss')] Reiniciando worker..."
    if (-not $DryRun) {
        docker start celery-worker 2>$null | Out-Null
    }
    
    # === PASO 4: Esperar recuperación ===
    Write-Status "[$(Get-Date -Format 'HH:mm:ss')] Esperando recuperacion (${WaitForRecovery}s)..."
    if (-not $DryRun) {
        Start-Sleep -Seconds $WaitForRecovery
    }
    
    # Verificar que se resolvió el incidente
    if (-not $DryRun) {
        $workerIncidents = curl.exe -s "http://localhost:5006/incidents/worker?limit=1" | ConvertFrom-Json
        if ($workerIncidents.incidents.Count -gt 0) {
            $lastIncident = $workerIncidents.incidents[0]
            if ($lastIncident.resolved_at) {
                Write-Success "[$(Get-Date -Format 'HH:mm:ss')] Incidente resuelto - MTTR: $([math]::Round($lastIncident.mttr_seconds, 2))s"
                $successfulIncidents++
            } else {
                Write-Warning "[$(Get-Date -Format 'HH:mm:ss')] Incidente aun activo, esperando mas..."
                Start-Sleep -Seconds 10
                $successfulIncidents++  # Contamos igual porque se creó
            }
        }
    } else {
        $successfulIncidents++
    }
    
    # === PASO 5: Pausa entre ciclos ===
    if ($i -lt $TotalIncidents) {
        Write-Status "[$(Get-Date -Format 'HH:mm:ss')] Pausa entre ciclos (${WaitBetweenCycles}s)..."
        if (-not $DryRun) {
            Start-Sleep -Seconds $WaitBetweenCycles
        }
    }
    
    # Progreso
    $cycleTime = ((Get-Date) - $cycleStart).TotalSeconds
    $progress = [math]::Round(($i / $TotalIncidents) * 100, 1)
    $remaining = $TotalIncidents - $i
    $etaMinutes = [math]::Round(($remaining * $cycleTime) / 60, 1)
    
    Write-Host ""
    Write-Host "  Progreso: $progress% | Completados: $successfulIncidents | ETA: ~$etaMinutes min" -ForegroundColor DarkCyan
}

# === RESUMEN FINAL ===
$endTime = Get-Date
$totalTime = ($endTime - $startTime).TotalMinutes

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "   EXPERIMENTO COMPLETADO" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host ""
Write-Success "  Incidentes generados: $successfulIncidents / $TotalIncidents"
Write-Success "  Tiempo total: $([math]::Round($totalTime, 1)) minutos"
Write-Host ""

# Mostrar metricas finales
Write-Status "Obteniendo metricas finales..."
if (-not $DryRun) {
    $metrics = curl.exe -s "http://localhost:5006/metrics/experiment?window_hours=24" | ConvertFrom-Json
    
    Write-Host ""
    Write-Host "------------------------------------------------------------" -ForegroundColor DarkGray
    Write-Host "METRICAS DEL EXPERIMENTO" -ForegroundColor Cyan
    Write-Host "------------------------------------------------------------" -ForegroundColor DarkGray
    
    $workerMetrics = $metrics.per_service.worker
    
    Write-Host ""
    Write-Host "  MTTD (Mean Time To Detect):" -ForegroundColor Yellow
    Write-Host "    - Promedio: $($workerMetrics.mttd.avg_seconds) segundos"
    Write-Host "    - Minimo:   $($workerMetrics.mttd.min_seconds) segundos"
    Write-Host "    - Maximo:   $($workerMetrics.mttd.max_seconds) segundos"
    Write-Host "    - Objetivo: <=20 segundos" -ForegroundColor DarkGray
    
    Write-Host ""
    Write-Host "  MTTR (Mean Time To Recover):" -ForegroundColor Yellow
    Write-Host "    - Promedio: $($workerMetrics.mttr.avg_seconds) segundos"
    Write-Host "    - Minimo:   $($workerMetrics.mttr.min_seconds) segundos"
    Write-Host "    - Maximo:   $($workerMetrics.mttr.max_seconds) segundos"
    Write-Host "    - Objetivo: <=30 segundos" -ForegroundColor DarkGray
    
    Write-Host ""
    Write-Host "  Incidentes:" -ForegroundColor Yellow
    Write-Host "    - Total:     $($workerMetrics.incidents.total)"
    Write-Host "    - Resueltos: $($workerMetrics.incidents.resolved)"
    Write-Host "    - Activos:   $($workerMetrics.incidents.active)"
    
    Write-Host ""
    Write-Host "  Disponibilidad: $($workerMetrics.availability.percent)%" -ForegroundColor Yellow
    
    # Validacion de hipotesis
    Write-Host ""
    $mttdOk = $workerMetrics.mttd.avg_seconds -le 20
    $mttrOk = $workerMetrics.mttr.avg_seconds -le 30
    
    if ($mttdOk -and $mttrOk) {
        Write-Success "  HIPOTESIS VALIDADA: MTTD <=20s y MTTR <=30s"
    } else {
        Write-Error "  HIPOTESIS NO VALIDADA:"
        if (-not $mttdOk) { Write-Error "    - MTTD > 20s" }
        if (-not $mttrOk) { Write-Error "    - MTTR > 30s" }
    }
}

Write-Host ""
Write-Host "Para ver el reporte completo:" -ForegroundColor DarkGray
Write-Host '  curl.exe "http://localhost:5006/metrics/experiment?window_hours=24"' -ForegroundColor DarkGray
Write-Host ""
