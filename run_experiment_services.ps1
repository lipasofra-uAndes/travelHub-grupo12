# ============================================================
# Script de Experimento ASR-03: Generacion de Incidentes
# Servicios: payments, reserves, search
# ============================================================
# Este script automatiza la generacion de incidentes para medir
# MTTD (Mean Time To Detect) y MTTR (Mean Time To Recover)
# ============================================================

param(
    [int]$TotalIncidents = 60,
    [int]$WaitForDetection = 25,      # Segundos para que detecte (3 pings x 5s + margen)
    [int]$WaitForRecovery = 25,       # Segundos para que se recupere
    [int]$WaitBetweenCycles = 10,     # Segundos entre ciclos
    [string]$TargetService = "all",   # all, payments, reserves, search
    [switch]$DryRun = $false          # Si es true, solo muestra que haria
)

$ErrorActionPreference = "Stop"

# Mapeo de servicios a contenedores Docker
$ServiceContainers = @{
    "payments" = "payments-service"
    "reserves" = "reserves-service"
    "search" = "search-service"
}

# Colores para output
function Write-Status { param($msg) Write-Host $msg -ForegroundColor Cyan }
function Write-Success { param($msg) Write-Host $msg -ForegroundColor Green }
function Write-Warning { param($msg) Write-Host $msg -ForegroundColor Yellow }
function Write-Err { param($msg) Write-Host $msg -ForegroundColor Red }

# Banner
Write-Host ""
Write-Host "============================================================" -ForegroundColor Magenta
Write-Host "   EXPERIMENTO ASR-03: Validacion Disponibilidad Servicios" -ForegroundColor Magenta
Write-Host "   Servicios objetivo: payments, reserves, search" -ForegroundColor Magenta
Write-Host "============================================================" -ForegroundColor Magenta
Write-Host ""

# Determinar servicios a probar
if ($TargetService -eq "all") {
    $ServicesToTest = @("payments", "reserves", "search")
    $incidentsPerService = [math]::Ceiling($TotalIncidents / 3)
} else {
    $ServicesToTest = @($TargetService)
    $incidentsPerService = $TotalIncidents
}

Write-Status "Configuracion:"
Write-Host "  - Incidentes totales:   $TotalIncidents"
Write-Host "  - Servicios a probar:   $($ServicesToTest -join ', ')"
Write-Host "  - Incidentes/servicio:  $incidentsPerService"
Write-Host "  - Espera deteccion:     ${WaitForDetection}s"
Write-Host "  - Espera recuperacion:  ${WaitForRecovery}s"
Write-Host "  - Pausa entre ciclos:   ${WaitBetweenCycles}s"
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
    Write-Success "  Monitor: $($monitorStatus.status)"
    
    foreach ($svc in $ServicesToTest) {
        $port = switch ($svc) {
            "payments" { 5002 }
            "reserves" { 5001 }
            "search" { 5003 }
        }
        $svcStatus = curl.exe -s "http://localhost:$port/health" | ConvertFrom-Json
        Write-Success "  ${svc}: $($svcStatus.status)"
    }
} catch {
    Write-Err "Error: Algunos servicios no estan disponibles. Ejecuta 'docker-compose up -d' primero."
    exit 1
}

Write-Host ""
Write-Warning "Presiona ENTER para iniciar o Ctrl+C para cancelar..."
Read-Host

$startTime = Get-Date
$successfulIncidents = 0
$incidentCount = 0

foreach ($currentService in $ServicesToTest) {
    $containerName = $ServiceContainers[$currentService]
    
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Yellow
    Write-Host "   PROBANDO SERVICIO: $currentService ($containerName)" -ForegroundColor Yellow
    Write-Host "============================================================" -ForegroundColor Yellow
    
    for ($i = 1; $i -le $incidentsPerService; $i++) {
        $incidentCount++
        if ($incidentCount -gt $TotalIncidents) { break }
        
        $cycleStart = Get-Date
        
        Write-Host ""
        Write-Host "------------------------------------------------------------" -ForegroundColor DarkGray
        Write-Status "INCIDENTE $incidentCount de $TotalIncidents [$currentService #$i]"
        Write-Host "------------------------------------------------------------" -ForegroundColor DarkGray
        
        # === PASO 1: Detener el servicio ===
        Write-Warning "[$(Get-Date -Format 'HH:mm:ss')] Deteniendo $containerName..."
        if (-not $DryRun) {
            docker stop $containerName 2>$null | Out-Null
        }
        
        # === PASO 2: Esperar deteccion ===
        Write-Status "[$(Get-Date -Format 'HH:mm:ss')] Esperando deteccion (${WaitForDetection}s)..."
        if (-not $DryRun) {
            Start-Sleep -Seconds $WaitForDetection
        }
        
        # Verificar que se creo el incidente
        if (-not $DryRun) {
            $activeIncidents = curl.exe -s http://localhost:5006/incidents/active | ConvertFrom-Json
            $incident = $activeIncidents.incidents | Where-Object { $_.service -eq $currentService }
            if ($incident) {
                Write-Success "[$(Get-Date -Format 'HH:mm:ss')] Incidente detectado - MTTD: $([math]::Round($incident.mttd_seconds, 2))s"
            } else {
                Write-Warning "[$(Get-Date -Format 'HH:mm:ss')] No se detecto incidente aun..."
            }
        }
        
        # === PASO 3: Reiniciar el servicio ===
        Write-Warning "[$(Get-Date -Format 'HH:mm:ss')] Reiniciando $containerName..."
        if (-not $DryRun) {
            docker start $containerName 2>$null | Out-Null
        }
        
        # === PASO 4: Esperar recuperacion ===
        Write-Status "[$(Get-Date -Format 'HH:mm:ss')] Esperando recuperacion (${WaitForRecovery}s)..."
        if (-not $DryRun) {
            Start-Sleep -Seconds $WaitForRecovery
        }
        
        # Verificar que se resolvio el incidente
        if (-not $DryRun) {
            $svcIncidents = curl.exe -s "http://localhost:5006/incidents/$currentService?limit=1" | ConvertFrom-Json
            if ($svcIncidents.incidents.Count -gt 0) {
                $lastIncident = $svcIncidents.incidents[0]
                if ($lastIncident.resolved_at) {
                    Write-Success "[$(Get-Date -Format 'HH:mm:ss')] Incidente resuelto - MTTR: $([math]::Round($lastIncident.mttr_seconds, 2))s"
                    $successfulIncidents++
                } else {
                    Write-Warning "[$(Get-Date -Format 'HH:mm:ss')] Incidente aun activo, esperando mas..."
                    Start-Sleep -Seconds 10
                    $successfulIncidents++
                }
            }
        } else {
            $successfulIncidents++
        }
        
        # === PASO 5: Pausa entre ciclos ===
        if ($incidentCount -lt $TotalIncidents) {
            Write-Status "[$(Get-Date -Format 'HH:mm:ss')] Pausa entre ciclos (${WaitBetweenCycles}s)..."
            if (-not $DryRun) {
                Start-Sleep -Seconds $WaitBetweenCycles
            }
        }
        
        # Progreso
        $cycleTime = ((Get-Date) - $cycleStart).TotalSeconds
        $progress = [math]::Round(($incidentCount / $TotalIncidents) * 100, 1)
        $remaining = $TotalIncidents - $incidentCount
        $etaMinutes = [math]::Round(($remaining * $cycleTime) / 60, 1)
        
        Write-Host ""
        Write-Host "  Progreso: $progress% | Completados: $successfulIncidents | ETA: ~$etaMinutes min" -ForegroundColor DarkCyan
    }
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
    
    foreach ($svc in $ServicesToTest) {
        $svcMetrics = $metrics.per_service.$svc
        
        Write-Host ""
        Write-Host "  === $($svc.ToUpper()) ===" -ForegroundColor Yellow
        Write-Host "    MTTD promedio: $($svcMetrics.mttd.avg_seconds)s (objetivo: <=20s)"
        Write-Host "    MTTR promedio: $($svcMetrics.mttr.avg_seconds)s (objetivo: <=30s)"
        Write-Host "    Incidentes:    $($svcMetrics.incidents.total) (resueltos: $($svcMetrics.incidents.resolved))"
        Write-Host "    Disponibilidad: $($svcMetrics.availability.percent)%"
    }
    
    # Validacion de hipotesis global
    Write-Host ""
    Write-Host "------------------------------------------------------------" -ForegroundColor DarkGray
    Write-Host "VALIDACION DE HIPOTESIS" -ForegroundColor Cyan
    Write-Host "------------------------------------------------------------" -ForegroundColor DarkGray
    
    $allMttdOk = $true
    $allMttrOk = $true
    
    foreach ($svc in $ServicesToTest) {
        $svcMetrics = $metrics.per_service.$svc
        if ($svcMetrics.mttd.avg_seconds -and $svcMetrics.mttd.avg_seconds -gt 20) { $allMttdOk = $false }
        if ($svcMetrics.mttr.avg_seconds -and $svcMetrics.mttr.avg_seconds -gt 30) { $allMttrOk = $false }
    }
    
    Write-Host ""
    if ($allMttdOk -and $allMttrOk) {
        Write-Success "  HIPOTESIS VALIDADA: MTTD <=20s y MTTR <=30s para todos los servicios"
    } else {
        Write-Err "  HIPOTESIS NO VALIDADA:"
        if (-not $allMttdOk) { Write-Err "    - Algun servicio tiene MTTD > 20s" }
        if (-not $allMttrOk) { Write-Err "    - Algun servicio tiene MTTR > 30s" }
    }
}

Write-Host ""
Write-Host "Para ver el reporte completo:" -ForegroundColor DarkGray
Write-Host '  curl.exe "http://localhost:5006/metrics/experiment?window_hours=24"' -ForegroundColor DarkGray
Write-Host ""
