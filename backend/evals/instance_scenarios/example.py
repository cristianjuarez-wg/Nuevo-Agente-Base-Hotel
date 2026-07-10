"""
Plantilla de escenarios POR INSTANCIA — copiar a <cliente>.py y adaptar a los HECHOS del cliente.

Estos escenarios verifican que el agente respeta los hechos propios del cliente (lo que tiene y
lo que NO tiene) y sus promos/lugares. NO duplicar acá los flujos genéricos (disponibilidad,
reserva, pago, seguridad) — esos son core y ya se corren desde evals/scenarios.py.

Formato idéntico a evals/scenarios.py. `tier` se asume "instance".
"""

# Ejemplo para un hotel ficticio "Hotel Ejemplo" que SÍ tiene spa (a diferencia del Hampton).
SCENARIOS = [
    {
        "id": "INST-1",
        "tier": "instance",
        "name": "Hechos del cliente: SÍ tiene spa → lo confirma con naturalidad",
        # setup_knowledge sembraría el doc de servicios del cliente; acá es ilustrativo.
        "turns": [
            {"user": "Hola! el hotel tiene spa? me interesa relajarme.",
             "expect": {"tool_called": "info_hotel",
                        "response_not_contains": ["no tiene spa", "no contamos con spa"]}},
        ],
    },
    {
        "id": "INST-2",
        "tier": "instance",
        "name": "Hechos del cliente: NO tiene estacionamiento → lo dice claro (no inventa)",
        "turns": [
            {"user": "¿Tienen estacionamiento propio para dejar el auto?",
             "expect": {"response_not_contains": ["estacionamiento incluido", "cochera gratuita"]}},
        ],
    },
]
