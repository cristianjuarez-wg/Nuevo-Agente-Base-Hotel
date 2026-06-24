"""
Router para analytics y métricas del dashboard
"""
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.database import get_db
from app.models.conversation import Conversation
from app.services.agent_service import agent_service
from app.services.lead_service import lead_service
from app.services.metrics_service import metrics_service
from app.services.kanban_service import kanban_service
from app.services.business_metrics import resolve_period
from app.core.logging_config import get_logger
from typing import Dict, List
from datetime import datetime, timedelta
import re

logger = get_logger(__name__)
router = APIRouter(prefix="/api/analytics", tags=["Analytics"])

@router.get("/dashboard")
async def get_dashboard_analytics(period: str = "mes", db: Session = Depends(get_db)):
    """Métricas del dashboard. Las tarjetas de negocio se filtran por `period`; "En casa hoy"
    es siempre operativo (hoy). Reutiliza business_metrics → consistente con el asesor."""
    try:
        from app.services import business_metrics as bm
        from app.models.hotel import HotelTicket
        start, end, period_label = resolve_period(period)
        rev = bm.get_revenue(db, start, end)
        occ = bm.get_occupancy(db, start, end)
        leads_sum = bm.get_leads_summary(db, start, end)
        from datetime import datetime, time as _time
        tickets_total = db.query(func.count(HotelTicket.id)).filter(
            HotelTicket.created_at >= datetime.combine(start, _time.min),
            HotelTicket.created_at < datetime.combine(end, _time.min),
        ).scalar() or 0
        period_cards = {
            "revenue_usd": rev["usd"],
            "revenue_ars": rev["ars"],
            "bookings_count": rev["count"],
            "occupancy_pct": occ["occupancy_pct"],
            "leads": leads_sum["generated"],
            "leads_closed": leads_sum["closed"],
            "conversion_pct": leads_sum["conversion_pct"],
            "tickets_total": tickets_total,
            "period_label": period_label,
        }
        today_block = bm.get_guests_in_house(db)  # "En casa hoy" — siempre hoy

        agent_stats = agent_service.get_service_stats()
        lead_stats = lead_service.get_lead_stats()
        priority_leads = lead_service.get_active_leads(limit=10)

        # total_conversations desde la DB (no sesiones volátiles en memoria)
        total_conversations = db.query(Conversation).filter(
            Conversation.context_type != 'post_sale'
        ).count()
        total_messages = db.query(func.sum(Conversation.message_count)).filter(
            Conversation.context_type != 'post_sale'
        ).scalar() or 0

        trends = metrics_service.get_trends(db=db, days=30)

        # Etapas reales del pipeline (misma fuente que el Kanban, para coherencia)
        kanban_stats = kanban_service.get_kanban_stats(db)
        by_stage = kanban_stats.get("by_stage", {})
        leads_won = by_stage.get("won", 0)
        # "En negociación": leads activos que avanzaron del estado inicial (en contacto)
        leads_negotiating = by_stage.get("contacted", 0)
        # Conversión real de ventas: ganados / total de leads (idéntico al Kanban)
        sales_conversion_rate = kanban_stats.get("conversion_rate", 0)

        dashboard_data = {
            "overview": {
                "total_conversations": total_conversations,
                "total_messages": int(total_messages),
                "total_leads": lead_stats.get("total_leads", 0),
                "active_leads": lead_stats.get("active_leads", 0),
                "leads_with_contact": lead_stats.get("with_complete_contact", 0),
                "leads_negotiating": leads_negotiating,
                "leads_won": leads_won,
                "sales_conversion_rate": sales_conversion_rate,
                "conversion_rate": round(lead_stats.get("conversion_rate", 0), 1),
                "leads_ready_contact": lead_stats.get("ready_for_contact", 0),
                "avg_response_time": agent_stats.get("avg_response_time", 0)
            },
            "trends": {
                "conversations_trend": trends.get("conversations_trend", 0),
                "leads_trend": trends.get("leads_trend", 0),
                "conversion_trend": trends.get("conversion_trend", 0),
                "ready_contact_trend": trends.get("ready_contact_trend", 0)
            },
            "leads_by_type": {
                "calientes": lead_stats.get("by_type", {}).get("calientes", 0),
                "tibios": lead_stats.get("by_type", {}).get("tibios", 0),
                "frios": lead_stats.get("by_type", {}).get("frios", 0)
            },
            "system_health": {
                "openai_status": agent_stats.get("openai_circuit_breaker", {}).get("state", "unknown"),
                "active_sessions": agent_stats.get("active_sessions", 0),
                "model_config": agent_stats.get("model_config", {})
            },
            "recent_leads": priority_leads[:5],
            # Tarjetas filtradas por el período elegido (negocio).
            "period_cards": period_cards,
            # "En casa hoy" — operativo, NO depende del período.
            "today": today_block,
        }

        logger.info("Dashboard analytics retrieved", total_conversations=total_conversations)
        return {"success": True, "data": dashboard_data}

    except Exception as e:
        logger.error("Error getting dashboard analytics", error=str(e))
        raise HTTPException(status_code=500, detail=f"Error obteniendo analytics del dashboard: {str(e)}")


@router.get("/conversations/timeline")
async def get_conversations_timeline(period: str = "hourly", db: Session = Depends(get_db)):
    """Obtiene timeline REAL de conversaciones por hora del día o por día de la semana"""
    try:
        hourly_data = metrics_service.get_timeline_data(db, period="hourly")
        daily_data = metrics_service.get_timeline_data(db, period="daily")
        return {
            "success": True,
            "data": {
                "hourly": hourly_data,
                "daily": daily_data,
            }
        }
    except Exception as e:
        logger.error("Error getting conversations timeline", error=str(e))
        raise HTTPException(status_code=500, detail=f"Error obteniendo timeline: {str(e)}")


@router.get("/postsale/metrics")
async def get_postsale_metrics(period: str = "mes", db: Session = Depends(get_db)):
    """Métricas del agente post-venta en un período: escalación y auto-resolución."""
    try:
        start, end, label = resolve_period(period)
        data = metrics_service.get_postsale_metrics(db, start, end)
        data["period_label"] = label
        return {"success": True, "data": data}
    except Exception as e:
        logger.error("Error getting postsale metrics", error=str(e))
        raise HTTPException(status_code=500, detail=f"Error obteniendo métricas post-venta: {str(e)}")


@router.get("/conversations/heatmap")
async def get_conversations_heatmap(period: str = "mes", channel: str = None, db: Session = Depends(get_db)):
    """Heatmap de conversaciones (día × hora) en un período. channel opcional: web | whatsapp."""
    try:
        start, end, label = resolve_period(period)
        heatmap_data = metrics_service.get_heatmap_data(db, start=start, end=end, channel=channel)
        heatmap_data["period_label"] = label
        return {"success": True, "data": heatmap_data}
    except Exception as e:
        logger.error("Error getting conversations heatmap", error=str(e))
        raise HTTPException(status_code=500, detail=f"Error obteniendo heatmap: {str(e)}")


@router.get("/conversations/channels")
async def get_conversations_channels(period: str = "mes", db: Session = Depends(get_db)):
    """Distribución de conversaciones por canal (web / whatsapp) en un período."""
    try:
        start, end, label = resolve_period(period)
        data = metrics_service.get_conversations_by_channel(db, start, end)
        data["period_label"] = label
        return {"success": True, "data": data}
    except Exception as e:
        logger.error("Error getting conversations by channel", error=str(e))
        raise HTTPException(status_code=500, detail=f"Error obteniendo canales: {str(e)}")


@router.get("/funnel")
async def get_funnel(period: str = "mes", channel: str = None, db: Session = Depends(get_db)):
    """Embudo conversaciones → leads → reservas en un período. channel opcional: web | whatsapp."""
    try:
        start, end, label = resolve_period(period)
        data = metrics_service.get_funnel(db, start, end, channel=channel)
        data["period_label"] = label
        return {"success": True, "data": data}
    except Exception as e:
        logger.error("Error getting funnel", error=str(e))
        raise HTTPException(status_code=500, detail=f"Error obteniendo embudo: {str(e)}")


@router.get("/performance/metrics")
async def get_performance_metrics():
    """Métricas de rendimiento del agente"""
    try:
        agent_stats = agent_service.get_service_stats()
        total_messages = agent_stats.get("total_messages", 0)
        error_count = agent_stats.get("error_count", 0)
        successful = total_messages - error_count
        success_rate = round(successful / total_messages * 100, 1) if total_messages > 0 else 100.0

        return {
            "success": True,
            "data": {
                "success_rates": {
                    "total_requests": total_messages,
                    "successful_responses": successful,
                    "success_rate": success_rate,
                    "error_rate": round(100 - success_rate, 1)
                },
                "circuit_breakers": {
                    "openai": agent_stats.get("openai_circuit_breaker", {}),
                    "vector_store": {"state": "CLOSED", "failure_count": 0}
                }
            }
        }
    except Exception as e:
        logger.error("Error getting performance metrics", error=str(e))
        raise HTTPException(status_code=500, detail=f"Error obteniendo métricas de rendimiento: {str(e)}")


@router.get("/leads/conversion-funnel")
async def get_conversion_funnel():
    """Datos del embudo de conversión de leads"""
    try:
        lead_stats = lead_service.get_lead_stats()
        agent_stats = agent_service.get_service_stats()

        total_conversations = agent_stats.get("active_sessions", 0)
        total_leads = lead_stats.get("total_leads", 0)
        leads_with_contact = lead_stats.get("with_complete_contact", 0)
        leads_ready = lead_stats.get("ready_for_contact", 0)

        funnel_data = {
            "stages": [
                {"name": "Conversaciones Totales", "count": total_conversations, "percentage": 100.0},
                {"name": "Leads Generados", "count": total_leads,
                 "percentage": round((total_leads / total_conversations * 100) if total_conversations > 0 else 0, 1)},
                {"name": "Con Datos de Contacto", "count": leads_with_contact,
                 "percentage": round((leads_with_contact / total_conversations * 100) if total_conversations > 0 else 0, 1)},
                {"name": "Listos para Contactar", "count": leads_ready,
                 "percentage": round((leads_ready / total_conversations * 100) if total_conversations > 0 else 0, 1)}
            ],
            "conversion_rates": {
                "conversation_to_lead": round((total_leads / total_conversations * 100) if total_conversations > 0 else 0, 1),
                "lead_to_contact": round((leads_with_contact / total_leads * 100) if total_leads > 0 else 0, 1),
                "contact_to_ready": round((leads_ready / leads_with_contact * 100) if leads_with_contact > 0 else 0, 1)
            }
        }

        return {"success": True, "data": funnel_data}
    except Exception as e:
        logger.error("Error getting conversion funnel", error=str(e))
        raise HTTPException(status_code=500, detail=f"Error obteniendo embudo de conversión: {str(e)}")
