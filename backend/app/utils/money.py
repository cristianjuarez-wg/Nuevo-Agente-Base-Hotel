"""
Formateo de montos parametrizado por moneda (Fase 1.4).

Única fuente del formato de dinero en el backend, para que la etiqueta de moneda
("USD"/"ARS"/"MXN"/…) salga del BusinessProfile y no esté hardcodeada en cada f-string.

Alcance de la Fase 1.4 (honesto): parametriza la ETIQUETA y el formato de la moneda
mostrada. La CONVERSIÓN entre monedas sigue siendo USD→ARS vía exchange_rate_service
(la fuente de cotización — dolarapi — sólo cubre ARS). Un cliente con otra moneda
primaria monomoneda funciona (se muestra sólo la primaria); generalizar la fuente de
cotización a cualquier par queda para la fase de instancia (Fase 3).
"""


# Monedas sin decimales de uso frecuente (se muestran como enteros).
_ZERO_DECIMAL = {"ARS", "CLP", "COP", "JPY", "KRW", "PYG"}


def format_money(amount, currency: str = "USD") -> str:
    """Formatea un monto con su etiqueta de moneda.

    - ARS y otras monedas "grandes" se muestran con separador de miles y sin decimales
      (ej. "ARS 1.250.000") — preserva el formato histórico ARS del proyecto.
    - El resto se muestra con 0 decimales y sin separador (ej. "USD 990", "MXN 3500"),
      igual que el formato histórico USD.
    """
    if amount is None:
        return ""
    cur = (currency or "USD").upper()
    try:
        val = float(amount)
    except (TypeError, ValueError):
        return f"{amount} {cur}"
    if cur in _ZERO_DECIMAL:
        # Separador de miles con coma, formato histórico exacto del proyecto ("ARS 1,250,000").
        return f"{cur} {val:,.0f}"
    return f"{cur} {val:.0f}"


def format_price_pair(price_usd, price_ars, profile: dict | None = None,
                      amount_primary=None) -> str:
    """Formatea el precio para mostrar, según la moneda del perfil.

    Reglas:
    - primary_currency == "USD" (Hampton): muestra "USD X / ARS Y" — texto histórico exacto.
    - primary_currency == "ARS": muestra "ARS Y / USD X".
    - otra primaria (BRL, MXN...): muestra el precio REAL en esa moneda si viene `amount_primary`
      (de room_prices, Tarea B); si no, el valor USD guardado con la etiqueta primaria (fallback).
      Nunca muestra un "ARS" que no aplica.
    """
    prof = profile or {}
    primary = (prof.get("primary_currency") or "USD").upper()
    secondary = (prof.get("secondary_currency") or "").upper()

    if primary == "USD" and secondary == "ARS":
        return f"{format_money(price_usd, 'USD')} / {format_money(price_ars, 'ARS')}"
    if primary == "ARS":
        return f"{format_money(price_ars, 'ARS')} / {format_money(price_usd, 'USD')}"
    # Cliente con otra moneda primaria (BRL, MXN...): precio real en su moneda (Tarea B).
    monto = amount_primary if amount_primary is not None else price_usd
    return format_money(monto, primary)
