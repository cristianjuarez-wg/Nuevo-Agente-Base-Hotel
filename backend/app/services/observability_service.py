"""
Dashboard mínimo de observabilidad por instancia (Fase 3.4).

Agrega el audit JSONL de turnos (enriquecido con agent_key + prompt_config_version) en métricas
útiles para el gerente/operador:
  - tokens y costo estimado por AGENTE por día;
  - containment: % de turnos resueltos sin error/escalación;
  - errores (por error_type) y turnos de guardrail.

Lee del audit (no de la DB de usage) porque es la fuente que ya tiene el desglose por agente y
por turno. Best-effort: si no hay audit, devuelve métricas vacías.
"""
from collections import defaultdict
from typing import Optional

from app.core.observability.audit_log import read_entries
from app.core.llm.token_pricing import cost_usd_from_total


def summary(days: Optional[int] = None) -> dict:
    """Resumen de observabilidad. Si `days` se da, acota a los últimos N días (por el campo ts)."""
    entries = read_entries()
    if days:
        # ts es ISO "YYYY-MM-DDTHH:MM:SS"; comparamos por prefijo de fecha para no depender de tz.
        from datetime import date, timedelta
        cutoff = (date.today() - timedelta(days=days)).isoformat()
        entries = [e for e in entries if str(e.get("ts", ""))[:10] >= cutoff]

    total_turns = len(entries)
    by_agent = defaultdict(lambda: {"turns": 0, "tokens": 0, "cost_usd": 0.0, "errors": 0})
    by_day_agent = defaultdict(lambda: {"tokens": 0, "cost_usd": 0.0})
    errors_by_type = defaultdict(int)
    escalated = guardrail = errored = 0

    for e in entries:
        agent = e.get("agent_key") or "desconocido"
        tokens = int(e.get("tokens") or 0)
        model = e.get("model")
        cost = cost_usd_from_total(model, tokens) if tokens else 0.0
        day = str(e.get("ts", ""))[:10]

        a = by_agent[agent]
        a["turns"] += 1
        a["tokens"] += tokens
        a["cost_usd"] = round(a["cost_usd"] + cost, 6)

        d = by_day_agent[(day, agent)]
        d["tokens"] += tokens
        d["cost_usd"] = round(d["cost_usd"] + cost, 6)

        if e.get("error"):
            errored += 1
            a["errors"] += 1
            errors_by_type[e.get("error_type") or "desconocido"] += 1
        # containment: un turno "contenido" es el que el agente resolvió sin escalar a soporte.
        # Señal disponible en el audit: escalación se refleja como ticket_created/route postsale
        # con intent de escalación; acá usamos el error_type de guardrail y el flag de error.
        if e.get("error_type") == "guardrail":
            guardrail += 1
        route = e.get("route") or ""
        if "escal" in str(route).lower():
            escalated += 1

    contained = total_turns - errored - escalated
    containment_rate = round(contained / total_turns, 3) if total_turns else None

    # Serie por día/agente ordenada (para un gráfico simple en el frontend).
    daily = [
        {"day": day, "agent": agent, "tokens": v["tokens"], "cost_usd": v["cost_usd"]}
        for (day, agent), v in sorted(by_day_agent.items())
    ]

    return {
        "total_turns": total_turns,
        "containment_rate": containment_rate,
        "escalated": escalated,
        "errors": errored,
        "guardrail_turns": guardrail,
        "errors_by_type": dict(errors_by_type),
        "by_agent": {k: v for k, v in by_agent.items()},
        "daily_by_agent": daily,
    }
