"""
Componente de Autorización
Valida JWT y verifica que el hotel_id del token coincida con el hotel_id solicitado.
Asume que la autenticación ya fue realizada; solo verifica autorización.
"""

import jwt
import logging

logger = logging.getLogger(__name__)

SECRET_KEY = "clave_secreta_experimento_travelHub"


def estaAutorizado(token: str, hotel_id: str) -> dict:
    """
    Decodifica el JWT y compara el hotel_id del payload con el hotel_id solicitado.

    Args:
        token: JWT string (sin prefijo 'Bearer ')
        hotel_id: ID del hotel que se intenta modificar

    Returns:
        dict con keys: authorized (bool), user_id (str|None),
        token_hotel_id (str|None), error (str|None)
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        user_id = payload.get("sub")
        token_hotel_id = str(payload.get("hotel_id", ""))

        authorized = token_hotel_id == str(hotel_id)

        if not authorized:
            logger.warning(
                f"Autorización denegada: token_hotel_id={token_hotel_id} "
                f"!= requested_hotel_id={hotel_id} (user={user_id})"
            )

        return {
            "authorized": authorized,
            "user_id": user_id,
            "token_hotel_id": token_hotel_id,
            "error": None,
        }

    except jwt.ExpiredSignatureError:
        logger.warning("Token JWT expirado")
        return {
            "authorized": False,
            "user_id": None,
            "token_hotel_id": None,
            "error": "Token expirado",
        }

    except jwt.InvalidTokenError as e:
        logger.warning(f"Token JWT inválido: {e}")
        return {
            "authorized": False,
            "user_id": None,
            "token_hotel_id": None,
            "error": "Token inválido",
        }
