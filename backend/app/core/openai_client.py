"""
Clientes OpenAI compartidos (singletons).

Antes cada servicio creaba su propia instancia de AsyncOpenAI/OpenAI (>20 en total),
y cada una mantenía su propio pool de conexiones HTTP → renegociación TLS repetida y
overhead innecesario. Este módulo expone instancias ÚNICAS y reutilizables.

Uso:
    from app.core.openai_client import get_async_openai, get_sync_openai

    client = get_async_openai()   # AsyncOpenAI compartido
    sync   = get_sync_openai()    # OpenAI (sync) compartido

Ambos clientes usan la misma API key (settings.OPENAI_API_KEY) y los timeouts/reintentos
nativos del SDK de OpenAI. El SDK de Agents usa este mismo cliente async vía
set_default_openai_client (ver agent_sdk_orchestrator / triage / postsale).
"""
from openai import AsyncOpenAI, OpenAI
from app.config import settings

_async_client: AsyncOpenAI | None = None
_sync_client: OpenAI | None = None


def get_async_openai() -> AsyncOpenAI:
    """Devuelve el cliente AsyncOpenAI compartido (lo crea la primera vez)."""
    global _async_client
    if _async_client is None:
        _async_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    return _async_client


def get_sync_openai() -> OpenAI:
    """Devuelve el cliente OpenAI (sync) compartido (lo crea la primera vez)."""
    global _sync_client
    if _sync_client is None:
        _sync_client = OpenAI(api_key=settings.OPENAI_API_KEY)
    return _sync_client
