"""
Escenarios de eval POR INSTANCIA (Fase 3.3).

Cada cliente tiene un archivo `<cliente>.py` con una lista `SCENARIOS` de escenarios que
dependen de SUS hechos (servicios que tiene o no, promos propias, lugares de su zona). El
formato es idéntico al de evals/scenarios.py.

Los escenarios genéricos del vertical hotel (disponibilidad, reserva, honestidad, seguridad,
pago) viven en evals/scenarios.py con tier="core" y se reusan en todos los clientes SIN
cambios. Acá va solo lo específico del cliente.

Uso: al dar de alta un cliente (runbook 3.1), copiar example.py a <cliente>.py, reescribir los
hechos, y correr junto a los core en el go-live.
"""
