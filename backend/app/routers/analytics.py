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
from app.core.logging_config import get_logger
from typing import Dict, List
from datetime import datetime, timedelta
from collections import Counter
import re

logger = get_logger(__name__)
router = APIRouter(prefix="/api/analytics", tags=["Analytics"])

@router.get("/dashboard")
async def get_dashboard_analytics(db: Session = Depends(get_db)):
    """Obtiene todas las métricas para el dashboard principal con tendencias reales"""
    try:
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
            "recent_leads": priority_leads[:5]
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
async def get_postsale_metrics(db: Session = Depends(get_db)):
    """Métricas de negocio del agente post-venta: tasa de escalación y auto-resolución."""
    try:
        data = metrics_service.get_postsale_metrics(db)
        return {"success": True, "data": data}
    except Exception as e:
        logger.error("Error getting postsale metrics", error=str(e))
        raise HTTPException(status_code=500, detail=f"Error obteniendo métricas post-venta: {str(e)}")


@router.get("/conversations/heatmap")
async def get_conversations_heatmap(days: int = 7, db: Session = Depends(get_db)):
    """Obtiene datos para heatmap de conversaciones (día × hora)"""
    try:
        heatmap_data = metrics_service.get_heatmap_data(db, days=days)
        return {"success": True, "data": heatmap_data}
    except Exception as e:
        logger.error("Error getting conversations heatmap", error=str(e))
        raise HTTPException(status_code=500, detail=f"Error obteniendo heatmap: {str(e)}")


@router.get("/destinations/top")
async def get_top_destinations(db: Session = Depends(get_db)):
    """
    Destinos más consultados extraídos de conversaciones reales.
    Devuelve top 7 con nombre, cantidad de consultas y porcentaje.
    """
    try:
        conversations = db.query(Conversation).filter(
            Conversation.destinations_mentioned.isnot(None),
            Conversation.context_type != 'post_sale'
        ).all()

        counter: Counter = Counter()
        for conv in conversations:
            if conv.destinations_mentioned:
                for dest in conv.destinations_mentioned:
                    if dest and dest.strip():
                        counter[dest.strip().title()] += 1

        total = sum(counter.values()) or 1
        top = [
            {"name": name, "count": cnt, "percentage": round(cnt / total * 100, 1)}
            for name, cnt in counter.most_common(7)
        ]

        return {
            "success": True,
            "data": {
                "destinations": top,
                "total_mentions": sum(counter.values()),
                "unique_destinations": len(counter)
            }
        }
    except Exception as e:
        logger.error("Error getting top destinations", error=str(e))
        raise HTTPException(status_code=500, detail=f"Error obteniendo destinos: {str(e)}")


@router.get("/content/metrics")
async def get_content_metrics(db: Session = Depends(get_db)):
    """Métricas de contenido: destinos, paquetes y documentos más consultados"""
    try:
        content_metrics = metrics_service.get_content_metrics(db)
        return {"success": True, "data": content_metrics}
    except Exception as e:
        logger.error("Error getting content metrics", error=str(e))
        raise HTTPException(status_code=500, detail=f"Error obteniendo content metrics: {str(e)}")


@router.get("/destinations/popular")
async def get_popular_destinations(db: Session = Depends(get_db)):
    """Obtiene destinos más consultados a partir de conversaciones reales"""
    try:
        from app.models.conversation_message import ConversationMessage
        from app.core.geography import geography_service

        messages = (
            db.query(ConversationMessage.content)
            .filter(ConversationMessage.role == "user")
            .limit(2000)
            .all()
        )

        country_counter: Counter = Counter()
        continent_counter: Counter = Counter()

        for (content,) in messages:
            analysis = geography_service.get_geographic_analysis(content)
            for country in analysis.get("countries", []):
                country_counter[country.title()] += 1
            if analysis.get("continent"):
                continent_counter[analysis["continent"].title()] += 1

        total_country = sum(country_counter.values()) or 1
        total_continent = sum(continent_counter.values()) or 1

        return {
            "success": True,
            "data": {
                "countries": [
                    {"name": n, "queries": c, "percentage": round(c / total_country * 100, 1)}
                    for n, c in country_counter.most_common(10)
                ],
                "continents": [
                    {"name": n, "queries": c, "percentage": round(c / total_continent * 100, 1)}
                    for n, c in continent_counter.most_common(10)
                ]
            }
        }
    except Exception as e:
        logger.error("Error getting popular destinations", error=str(e))
        raise HTTPException(status_code=500, detail=f"Error obteniendo destinos populares: {str(e)}")


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
