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