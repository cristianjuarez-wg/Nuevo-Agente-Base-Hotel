"""
Hub de WebSocket en memoria para empujar mensajes al widget del chat web en vivo.

Caso de uso (Etapa 3 del takeover): cuando un humano responde una conversación tomada, el
backend transmite ese mensaje a los WebSockets suscritos a esa sesión, así el visitante lo ve
al instante (sin recargar). En WhatsApp esto ya lo cubre Twilio; esto es para el chat web.

Single-worker (uvicorn sin --workers en Render) → un solo pool en memoria alcanza, sin Redis.
Si se escalara a varios workers/instancias habría que mover a un pub/sub compartido.
"""
from typing import Dict, Set
import asyncio

from fastapi import WebSocket

from app.config import settings
from app.core.logging_config import get_logger

logger = get_logger(__name__)


class WSHub:
    """Mapea session_id -> conjunto de WebSockets conectados, y transmite a una sesión."""

    def __init__(self) -> None:
        self._rooms: Dict[str, Set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, session_id: str, ws: WebSocket) -> None:
        async with self._lock:
            self._rooms.setdefault(session_id, set()).add(ws)
        logger.info("WS conectado", session_id=session_id,
                    conns=len(self._rooms.get(session_id, ())))

    async def disconnect(self, session_id: str, ws: WebSocket) -> None:
        async with self._lock:
            conns = self._rooms.get(session_id)
            if conns:
                conns.discard(ws)
                if not conns:
                    self._rooms.pop(session_id, None)

    async def broadcast(self, session_id: str, payload: dict) -> int:
        """Envía `payload` (JSON) a todos los WS de la sesión. Descarta los que fallan.
        Devuelve a cuántos sockets se entregó. Best-effort: nunca lanza."""
        conns = list(self._rooms.get(session_id, ()))
        if not conns:
            return 0
        sent = 0
        dead = []
        for ws in conns:
            try:
                await ws.send_json(payload)
                sent += 1
            except Exception:  # noqa: BLE001 — socket muerto/cerrado
                dead.append(ws)
        if dead:
            async with self._lock:
                room = self._rooms.get(session_id)
                if room:
                    for ws in dead:
                        room.discard(ws)
                    if not room:
                        self._rooms.pop(session_id, None)
        return sent

    def has_listeners(self, session_id: str) -> bool:
        return bool(self._rooms.get(session_id))


ws_hub = WSHub()


def origin_allowed(origin: str | None) -> bool:
    """True si el Origin del handshake WS está permitido. El CORSMiddleware NO aplica al
    upgrade WS, así que validamos a mano contra la misma lista ALLOWED_ORIGINS del CORS.
    Sin Origin (clientes no-browser) se permite: el session_id ya acota el alcance."""
    if not origin:
        return True
    allowed = [o.strip() for o in (settings.ALLOWED_ORIGINS or "").split(",") if o.strip()]
    return origin in allowed
