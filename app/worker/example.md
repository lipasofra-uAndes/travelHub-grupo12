# Forzar 100% de probabilidad de fallo
curl -X POST http://localhost:5005/config/failure-rate \
  -H "Content-Type: application/json" \
  -d '{"rate": 1.0}'

# Ver configuración
curl http://localhost:5005/config
# → {"failure_rate": 1.0, "force_failure": false, "last_failure": null}

# El ping reportará UNHEALTHY después de un fallo
ping_worker('test-ping')
# → {"status": "UNHEALTHY", ...}

# Resetear
curl -X POST http://localhost:5005/config/reset

# Ping vuelve a UP
ping_worker('test-ping')
# → {"status": "UP", ...}