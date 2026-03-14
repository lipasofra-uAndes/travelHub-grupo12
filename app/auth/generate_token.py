"""
Script para generar tokens JWT de prueba para Postman.
Uso: python -m app.auth.generate_token
"""

import jwt
from datetime import datetime, timedelta

from app.auth.auth_component import SECRET_KEY


def generate_token(sub: str, hotel_id: str, expires_hours: int = 24) -> str:
    payload = {
        "sub": sub,
        "hotel_id": hotel_id,
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + timedelta(hours=expires_hours),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")


if __name__ == "__main__":
    print("=" * 60)
    print("Tokens JWT de prueba para TravelHub")
    print("=" * 60)

    # Token autorizado para hotel_1
    token_auth = generate_token("admin_hotel_1", "hotel_1")
    print(f"\n--- Token AUTORIZADO (hotel_1) ---")
    print(f"sub: admin_hotel_1, hotel_id: hotel_1")
    print(f"Token: {token_auth}")
    print(f"Header Postman: Bearer {token_auth}")

    # Token no autorizado (hotel_2 intentando acceder a hotel_1)
    token_unauth = generate_token("admin_hotel_2", "hotel_2")
    print(f"\n--- Token NO AUTORIZADO para hotel_1 (hotel_2) ---")
    print(f"sub: admin_hotel_2, hotel_id: hotel_2")
    print(f"Token: {token_unauth}")
    print(f"Header Postman: Bearer {token_unauth}")

    print(f"\n--- Ejemplo de uso en Postman ---")
    print(f"PUT http://localhost:5000/tarifas/hotel_1")
    print(f'Header: Authorization: Bearer <token>')
    print(f'Body: {{"rates": {{"standard": 100, "premium": 200}}}}')
    print()
