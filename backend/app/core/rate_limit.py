"""
Rate limiting por IP para proteger el endpoint del agente.

slowapi (sobre `limits`) ya viene en requirements. Este módulo expone un Limiter
ÚNICO y compartido, con la key derivada de la IP del cliente. Si
`settings.RATE_LIMIT_ENABLED` es False, el limiter se crea deshabilitado (no
bloquea nada), útil para entornos de test/local.

Uso:
    from app.core.rate_limit import limiter, CHAT_RATE_LIMIT

    @router.post("/message")
    @limiter.limit(CHAT_RATE_LIMIT)
    async def send_message(request: Request, ...):
        ...

El endpoint decorado DEBE recibir `request: Request` (requisito de slowapi).
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import settings

# Límite combinado por IP: por minuto y por hora. Construido desde settings para
# poder ajustarlo sin tocar código.
CHAT_RATE_LIMIT = f"{settings.RATE_LIMIT_PER_MINUTE}/minute;{settings.RATE_LIMIT_PER_HOUR}/hour"

# Limiter compartido. `enabled=False` lo vuelve un no-op (no cuenta ni bloquea).
limiter = Limiter(
    key_func=get_remote_address,
    enabled=settings.RATE_LIMIT_ENABLED,
)
