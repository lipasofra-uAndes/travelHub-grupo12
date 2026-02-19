# Tests del Worker - Guía Rápida

## Estructura

```
app/worker/tests/
├── __init__.py
├── conftest.py              # Fixtures compartidas
├── test_db.py               # Tests de acceso a base de datos
├── test_tasks.py            # Tests de tasks Celery
└── test_models.py           # Tests de modelos
```

## Ejecutar Tests

### Todos los tests
```bash
docker-compose exec celery-worker pytest
```

### Solo tests de DB
```bash
docker-compose exec celery-worker pytest app/worker/tests/test_db.py -v
```

### Solo tests de tasks
```bash
docker-compose exec celery-worker pytest app/worker/tests/test_tasks.py -v
```

### Solo tests de modelos
```bash
docker-compose exec celery-worker pytest app/worker/tests/test_models.py -v
```

### Con reporte de cobertura
```bash
docker-compose exec celery-worker pytest --cov=app/worker --cov-report=html
```

## Fixtures Disponibles (conftest.py)

### `initialized_db`
Base de datos temporal SQLite inicializada para cada test.

### `sample_operation_id`
ID de operación de prueba: `"op-test-001"`

### `sample_operation_data`
Datos de operación de prueba.

### `sample_ping_request_data`
Datos de ping para pruebas.

### `celery_app_for_testing`
App Celery configurada para tests con broker en memoria.

## Cobertura de Tests

### test_db.py (130+ tests conceptuales)
- ✅ Guardar y recuperar operaciones
- ✅ Actualizar estado de operación
- ✅ Registrar y recuperar ecos
- ✅ Crear incidentes de falla
- ✅ Recuperación de incidentes
- ✅ Transiciones de estado completas

### test_tasks.py (60+ tests conceptuales)
- ✅ Task `process_operation` exitosa
- ✅ Task `process_operation` con fallas
- ✅ Task `ping_worker` registra echo
- ✅ Múltiples operaciones en paralelo
- ✅ Ciclo completo operación + ping

### test_models.py (40+ tests conceptuales)
- ✅ Creación de modelos con estado
- ✅ Transiciones de estado
- ✅ Conversión a/desde diccionarios
- ✅ Construcción desde tuplas SQLite
- ✅ Modelos de monitoreo (incidentes)

## Patrón: Arrange-Act-Assert

Todos los tests siguen el patrón AAA:

```python
def test_example(initialized_db):
    # ARRANGE: prepara datos
    op = Operation.pending("op-001", "pay", {"amount": 100})
    save_operation(op)
    
    # ACT: ejecuta lógica
    update_operation_status("op-001", "PROCESSING")
    
    # ASSERT: verifica resultados
    updated = get_operation("op-001")
    assert updated.status == "PROCESSING"
```

## Marcadores (markers)

```bash
# Solo tests unitarios (rápidos)
pytest -m unit

# Solo tests de integración (con DB)
pytest -m integration
```

## Troubleshooting

### "ModuleNotFoundError: No module named 'app'"

Asegúrate de ejecutar desde dentro del contenedor:
```bash
docker-compose exec celery-worker pytest
```

### Tests lentos

Algunos tests de DB pueden ser lentos. Usa:
```bash
pytest --timeout=10  # timeout de 10s por test
```

### Limpiar base de datos de tests

Los tests automáticamente usan DB temporal. Si hay problemas:
```bash
docker-compose exec celery-worker rm -rf /data/test_*.db
```

---

**Última actualización:** 2026-02-19
