FROM python:3.9-slim

WORKDIR /app

# Copiar requirements e instalar dependencias
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar la aplicación
COPY . .

# Establecer PYTHONPATH para que Python encuentre el módulo 'app'
ENV PYTHONPATH=/app

# Nota: Los puertos específicos se exponen en docker-compose.yml
# El Gateway usa 5000, Worker usa 5005 para inyección de fallos,
# y las services internas (5001-5003) no se exponen al cliente

# Por defecto ejecutar el gateway (se puede sobrescribir con docker-compose)
CMD ["python", "app/api_gateway/gateway.py"]
