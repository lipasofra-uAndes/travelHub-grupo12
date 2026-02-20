FROM python:3.9-slim

WORKDIR /app

# Copiar requirements e instalar dependencias
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar la aplicación
COPY . .

# Exponer todos los puertos que usaremos
EXPOSE 5000 5001 5002 5003

# Por defecto ejecutar el gateway (se puede sobrescribir con docker-compose)
CMD ["python", "app/api_gateway/gateway.py"]
