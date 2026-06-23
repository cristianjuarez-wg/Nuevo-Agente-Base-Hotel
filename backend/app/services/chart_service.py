"""
Generación de gráficos vía QuickChart (sin dependencias locales).

QuickChart (https://quickchart.io) toma una config Chart.js en la URL y devuelve un PNG
público. Lo usamos para mandar gráficos al dueño por WhatsApp (send_media los acepta como
media_url). Helpers que arman las configs de los gráficos típicos de gerencia.
"""
import json
from urllib.parse import quote

from app.core.logging_config import get_logger

logger = get_logger(__name__)

_BASE = "https://quickchart.io/chart"
_HILTON = "#005aa9"
# Paleta para gráficos de torta (distribuciones): azul Hilton + derivados/acentos.
_PALETTE = ["#005aa9", "#4a90d9", "#7bb5e8", "#f0a500", "#2e8b57", "#9b59b6", "#e67e22", "#95a5a6"]


def build_chart_url(chart_config: dict, width: int = 600, height: int = 350) -> str:
    """Arma la URL de QuickChart para una config Chart.js dada (PNG público)."""
    c = quote(json.dumps(chart_config, ensure_ascii=False))
    return f"{_BASE}?w={width}&h={height}&bkg=white&c={c}"


def occupancy_chart_url(daily: list, label: str = "Ocupación") -> str:
    """Línea de ocupación diaria (%). `daily` = [{date, pct}]."""
    # Etiquetas compactas: día/mes.
    labels = []
    for d in daily:
        iso = d.get("date", "")
        labels.append(iso[8:10] + "/" + iso[5:7] if len(iso) >= 10 else iso)
    data = [d.get("pct", 0) for d in daily]
    config = {
        "type": "line",
        "data": {
            "labels": labels,
            "datasets": [{
                "label": label + " (%)",
                "data": data,
                "borderColor": _HILTON,
                "backgroundColor": "rgba(0,90,169,0.1)",
                "fill": True,
                "tension": 0.3,
                "pointRadius": 2,
            }],
        },
        "options": {
            "plugins": {"legend": {"display": True}},
            "scales": {"y": {"beginAtZero": True, "max": 100, "title": {"display": True, "text": "%"}}},
        },
    }
    return build_chart_url(config)


def pie_chart_url(labels: list, values: list, title: str = "") -> str:
    """Torta (distribución de un total): reservas por tipo de habitación, leads por canal,
    tickets por categoría. `labels` y `values` en el mismo orden. Cada porción su color."""
    config = {
        "type": "doughnut",  # doughnut = torta con centro; más legible que pie en WhatsApp
        "data": {
            "labels": labels,
            "datasets": [{
                "data": values,
                "backgroundColor": _PALETTE[:len(values)] or _PALETTE,
            }],
        },
        "options": {
            "plugins": {
                "legend": {"position": "right"},
                "title": {"display": bool(title), "text": title},
            },
        },
    }
    return build_chart_url(config)


def bars_chart_url(labels: list, values: list, title: str = "") -> str:
    """Barras simples (ej. ocupación por tipo de habitación, ingresos por período)."""
    config = {
        "type": "bar",
        "data": {
            "labels": labels,
            "datasets": [{
                "label": title,
                "data": values,
                "backgroundColor": _HILTON,
                "borderRadius": 4,
            }],
        },
        "options": {
            "plugins": {"legend": {"display": bool(title)}},
            "scales": {"y": {"beginAtZero": True}},
        },
    }
    return build_chart_url(config)
