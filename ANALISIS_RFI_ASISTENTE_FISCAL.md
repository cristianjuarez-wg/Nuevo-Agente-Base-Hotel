# Análisis técnico y go/no-go
## RFI — Asistente Virtual de Consultas Fiscales (Grupo San Cristóbal)

**Documento:** Evaluación interna de viabilidad
**Fecha:** 30 de junio de 2026
**RFI de referencia:** v1.0 — "Implementación de Asistente Virtual de Consultas Fiscales" (Grupo San Cristóbal)
**Plazo de respuesta del RFI:** 08 de julio de 2026
**Naturaleza:** documento interno, tono crudo (decisión go/no-go), sin endulzar

---

## 1. Resumen ejecutivo

Grupo San Cristóbal (asegurador) busca un **asistente virtual de IA para consultas fiscales**. Hoy su equipo de Impuestos responde manualmente, vía **tickets de Jira**, consultas de clientes y Productores de Seguros. El RFI pide un chatbot que: (a) construya una base de conocimiento a partir de **tickets de Jira resueltos**, (b) responda automático lo frecuente, (c) **proponga respuesta con validación humana** en casos similares, (d) **derive a Jira** (creando ticket) los casos nuevos, todo con **Microsoft Teams** como canal de Atención al Cliente.

**Veredicto: GO, con encuadre honesto.** El núcleo del RFI —RAG sobre el conocimiento del cliente + agente conversacional en español rioplatense + human-in-the-loop + multi-canal + trazabilidad— **es exactamente nuestra zona de fortaleza**: ya lo tenemos construido y operando en la plataforma de "Empleados Digitales" (Aura). El gap real **no es de inteligencia artificial**: es de **integración con el ecosistema Microsoft/Jira** y de **madurez enterprise** (SSO real, SLA 99%, multi-usuario, cumplimiento de privacidad).

**Dato decisivo:** Jira **ya está operativo** en el cliente (es el origen de los tickets) y la infraestructura Microsoft (Teams, Azure AD/Entra, M365) **la provee el cliente** bajo su contrato de licenciamiento. Esto transforma el riesgo de las tres integraciones grandes: no hay que *construir* el ecosistema, hay que *conectar adapters* a sistemas que el cliente ya opera. El riesgo de integración baja drásticamente.

**Como POC/demo estamos muy alineados. Como contrato enterprise hay plomería e infraestructura no trivial —pero viable—**, con dos gaps que sí exigen seriedad antes de firmar: la **privacidad del proveedor LLM** (R5) y la **cola de validación de borradores** (§3.2).

---

## 2. Qué pide el RFI (síntesis)

| Bloque | Exigencia |
|---|---|
| Objetivo (§2) | Base de conocimiento desde tickets Jira resueltos · respuesta automática a frecuentes · propuesta con validación humana · derivación a Jira de casos nuevos · canal Teams |
| Base de conocimiento (§3.1) | Extracción desde tickets · clasificación por casuística fiscal · actualización continua · panel de administración |
| Motor de respuesta (§3.2) | Clasificar en 3 categorías (coincidencia exacta / similitud alta / caso nuevo) · auto-respuesta · propuesta-con-validación · derivación a Jira con resumen |
| Teams (§3.3) | Bot accesible para Atención al Cliente · conversación natural · notificaciones al analista |
| Integraciones (§3.4) | Jira (REST/webhook) · Teams (Azure Bot/Graph) · Confluence (opcional) |
| Requisitos (§4) | R1 NLP español rioplatense fiscal · R2 umbral configurable · R3 trazabilidad · R4 panel admin · R5 privacidad/Ley 25.326 · R6 SLA 99% · R7 escalabilidad · R8 SSO Azure AD |
| Fuera de alcance (§5) | Canales externos (email/WhatsApp/web), dictámenes legales, ERP, multilingüe |

---

## 3. Qué tenemos hoy (inventario de la plataforma)

Nuestra plataforma de **Empleados Digitales** (agente "Aura" y hermanos) corre sobre:

- **Orquestación:** OpenAI Agents SDK (run-loop, tools vía `@function_tool`), FastAPI. Agentes definidos por perfil + prompts; capa de canal **desacoplada** del cerebro (`agent_service.chat()` es agnóstico de canal).
- **RAG / base de conocimiento:** **ChromaDB** persistente + embeddings `text-embedding-3-small`; ingesta de **PDF/MD/TXT** con chunking configurable; **re-ingesta en caliente sin redeploy**; retrieval con **score de similitud**, top-k, dedup por documento y umbral, devolviendo **atribución de fuente**.
- **Gestión de conocimiento:** backoffice con CRUD de entradas y documentos, activar/desactivar (soft-delete), entrenamiento por agente.
- **Human-in-the-loop:** **takeover** humano persistido en DB con auto-release a los 10 min; pre-resolución de tickets con validación.
- **Tickets internos:** modelo de tickets con estados, eventos/auditoría y asignación por área.
- **Multi-agente:** tres agentes con roles distintos (huésped/gerencia/operaciones), cada uno con legajo, skills, entrenamiento y métricas propias.
- **Skills con "techo duro":** parámetros configurables por el cliente validados y recortados server-side (`policy_values`) — el cliente ajusta perillas sin poder romper el motor.
- **Trazabilidad:** log por mensaje (rol, contenido, modelo, tokens, **fuentes usadas**, tipo de contexto) + audit JSONL + atribución de fuente del RAG.
- **Canales:** web chat + WhatsApp (Twilio).
- **LLM:** OpenAI `gpt-4o` (+ `gpt-4o-mini` para clasificación). Un solo proveedor.
- **Auth:** sólo `X-Admin-Key` (header compartido), sin multi-usuario.

---

## 4. Mapa de cobertura RFI → plataforma

**Leyenda:** ✅ ya existe · 🟡 existe el patrón, hay que adaptar · 🔴 hay que construir/integrar

| # | Requisito RFI | Estado | Qué tenemos / qué falta |
|---|---|---|---|
| 2 / 3.1 | KB desde tickets Jira resueltos | 🟡 | RAG completo con re-ingesta en caliente. Ingesta hoy PDF/MD/TXT, no Jira. **Falta:** conector Jira→RAG (API REST). El motor ya está; falta la "boca" de Jira. |
| 3.1 | Clasificación por casuística fiscal | 🟡 | Patrón de clasificación con LLM ya existe. **Falta:** taxonomía fiscal (retenciones, IVA, IIBB, percepciones…). Trabajo de prompt/datos, no de arquitectura. |
| 3.1 | Actualización continua | 🟡 | Re-ingesta en caliente ya existe. **Falta:** webhook Jira "ticket cerrado" → re-ingestar. Directo, Jira ya vivo. |
| 3.1 / R4 | Panel de administración | ✅🟡 | CRUD de conocimiento y docs ya existe (activar/desactivar, soft-delete). **Falta:** vista curada "entradas derivadas de Jira". Reutiliza el panel. |
| 3.2 | 3 bandas: exacto / similitud alta / nuevo | 🟡 | El RAG ya devuelve **score de similitud** y filtra por umbral. Materializar las 3 bandas es configuración sobre algo que ya medimos. |
| 3.2 / R2 | Umbral configurable (auto/validar/derivar) | 🟡 | Tenemos similitud + analizador de escalación. **Falta:** exponer el umbral como **perilla configurable** — calza exacto en el patrón **Skills + techo duro** ya construido. |
| 3.2 | Auto-respuesta en coincidencia exacta | ✅ | El agente ya responde solo desde RAG. Portar es trivial. |
| 3.2 | Propuesta de respuesta **con validación** | 🟡 | Lo más cercano: takeover + pre-resolución. **Falta** el flujo "IA redacta borrador → cola de validación → analista aprueba/edita → envía". **Gap funcional #1.** |
| 2 / 3.2 | Derivar caso nuevo → crear ticket Jira | 🟡🔴 | Tenemos creación interna de tickets + resumidor LLM. **Falta:** conector de **salida** a Jira (POST issue). Riesgo bajo (Jira vivo, API conocida). |
| 3.3 | Canal Microsoft Teams | 🔴 | Hoy web + WhatsApp; capa de canal desacoplada. **Falta:** adapter de Teams (Azure Bot Service / Bot Framework). El cliente pone la infra Microsoft. **Gap de canal #1.** |
| R1 | NLP español rioplatense + fiscal AR | ✅ | Aura ya es voseo rioplatense nativo. Terminología fiscal = conocimiento, no arquitectura. **Fuerte.** |
| R3 | Trazabilidad completa | ✅🟡 | Ya logueamos pregunta/respuesta/modelo/tokens/**fuente**. **Falta:** campo "validado por humano / quién / cuándo" (con la cola de aprobación). |
| R5 | Privacidad: datos no salen del entorno · Ley 25.326 | 🔴 | Hoy usamos OpenAI cloud + embeddings OpenAI. Choca de frente. **Camino:** Azure OpenAI en el tenant del cliente + abstracción de proveedor. **El gap más sensible.** |
| R6 | Alta disponibilidad, SLA 99% | 🔴🟡 | Tenemos circuit breaker + retries. **Falta:** despliegue HA real, SLA operativo, on-call. Infra, no producto. |
| R7 | Escalabilidad por volumen | 🟡 | Stateless por request + Postgres + Chroma. Razonable; no probado a volumen enterprise. |
| R8 | SSO / Azure AD (Entra) / M365 | 🔴 | Hoy sólo `X-Admin-Key`, sin multi-usuario. **Falta:** OIDC/SAML contra el tenant del cliente, con roles. |
| 3.4 | Confluence (opcional) | 🟡 | Mismo patrón que Jira: conector REST→RAG. Diferible. |
| 5 | Fuera de alcance fase 1 | ✅ | Nos juega a favor: lo que excluyen es lo que no tenemos pulido para fiscal. Reduce alcance. |

---

## 5. Fortalezas que nos posicionan (no improvisamos)

- **Motor RAG con re-ingesta en caliente** — el corazón del RFI (§3.1) ya funciona en producción.
- **Score de similitud del RAG** — base directa para las "3 bandas" del §3.2.
- **Patrón "Skills + techo duro" (`policy_values` validados server-side)** — es *literalmente* el "umbral configurable" del R2: el cliente ajusta la perilla sin romper el motor.
- **Human-in-the-loop real** — takeover persistido en DB con auto-release; base sólida sobre la cual montar la validación humana.
- **Trazabilidad por mensaje con atribución de fuente** — R3 casi cubierto de fábrica.
- **Agente español rioplatense nativo** — R1 casi gratis.
- **Capa de canal desacoplada** — agregar Teams es un adapter, no un rediseño.
- **Concepto "Empleado Digital que rinde cuentas"** — diferenciador frente a "un chatbot que responde": legajo, skills, métricas y parte de fin de día por agente.

---

## 6. Gaps a cubrir (ordenados por peso y riesgo)

| Prioridad | Gap | Por qué importa | Camino recomendado |
|---|---|---|---|
| 🔴 1 | **Privacidad / proveedor LLM (R5)** | "Los datos no salen del entorno corporativo" + Ley 25.326. Hoy todo va a OpenAI cloud. **Condición de cumplimiento, no opcional.** | **Azure OpenAI** en el tenant/región del cliente (coherente con su licencia Microsoft) + abstraer el provider en el cliente OpenAI/config. |
| 🔴 2 | **Cola de validación de borradores (§3.2)** | Es el corazón funcional del RFI ("IA propone → analista valida → envía") y hoy estamos en alpha (sólo takeover). | Construir workflow + estado "pendiente de validación" + UI de cola + registro de quién validó. |
| 🔴 3 | **Conector Jira bidireccional** | Entrada (tickets resueltos→RAG + webhook de cierre) y salida (caso nuevo→crear issue con resumen). | API REST de Jira (ya vivo en el cliente). Riesgo bajo, pero hay que escribirlo. |
| 🔴 4 | **Adapter Microsoft Teams (§3.3)** | Canal exigido para Atención al Cliente + notificaciones al analista. | Azure Bot Service / Bot Framework contra `agent_service.chat()`. El cliente pone la infra. |
| 🔴 5 | **SSO Entra ID + multi-usuario (R8)** | Pasar de header compartido a auth corporativa con roles (analista, atención, admin). | OIDC/SAML contra el tenant Entra del cliente. |
| 🟡 6 | **Umbral de 3 bandas configurable (R2/3.2)** | Materializar exacto/alto/nuevo sobre el score del RAG, como perilla. | Extiende el modelo de Skills/techo duro. Bajo riesgo. |
| 🟡 7 | **Taxonomía fiscal + clasificación (3.1)** | Categorías fiscales en prompt/datos. | Trabajo de dominio, no de arquitectura. |
| 🔴 8 | **HA / SLA 99% (R6)** | Despliegue redundante + operación. | Infra/operación; idealmente sobre Azure del cliente. |

---

## 7. Estimación de esfuerzo (orden de magnitud)

> Estimación gruesa para dimensionar, **no compromiso**. Supone equipo chico (1–2 devs) y que el cliente provee accesos a Jira/Teams/Entra y entorno Azure. Unidad: semanas-persona.

| Gap | Esfuerzo | Riesgo | Notas |
|---|---|---|---|
| Conector Jira (in: tickets→RAG + webhook; out: crear issue) | 1.5–2.5 sem | Bajo | API REST conocida; Jira ya operativo. |
| Taxonomía fiscal + clasificación | 1–2 sem | Bajo | Depende de calidad/volumen de tickets históricos. |
| Umbral 3 bandas configurable (sobre Skills) | 1–1.5 sem | Bajo | Reusa `policy_values` / techo duro. |
| Cola de validación de borradores (back + UI) | 2.5–4 sem | Medio | Workflow nuevo + estados + UI + trazabilidad de validación. |
| Adapter Microsoft Teams | 2–3 sem | Medio | Bot Framework/Azure Bot; depende de accesos del cliente. |
| Azure OpenAI + abstracción de proveedor | 1.5–3 sem | Medio-alto | Migración de provider + pruebas de paridad de calidad. |
| SSO Entra ID + roles multi-usuario | 2–3 sem | Medio | OIDC + RBAC en backoffice. |
| HA / SLA 99% (infra) | 2–4 sem | Medio | Despliegue redundante + observabilidad + on-call (continuo). |
| **Total POC Fase 1 (Jira + RAG + 3 bandas + validación + Teams mínimo + Azure OpenAI)** | **~8–12 sem** | Medio | Alcance acotado, sin SSO enterprise ni SLA 99%. |
| **Total contrato enterprise (todo + HA + SSO)** | **~14–22 sem** | Medio-alto | Incluye endurecimiento operativo. |

---

## 8. Fundamentos de la recomendación

1. **El RFI cae sobre nuestra zona de fortaleza.** RAG sobre conocimiento del cliente, agente en español, HITL y trazabilidad ya existen y operan. No partimos de cero en lo difícil (el motor); partimos de cero en lo conocido (integraciones).
2. **El miedo principal —las integraciones Microsoft/Jira— se desinfla.** El cliente ya opera Jira, Teams y Entra bajo su licenciamiento. Conectamos adapters; no construimos el ecosistema. Eso reduce el riesgo y el costo de las tres piezas que parecían más caras.
3. **Lo que sí exige seriedad antes de firmar** son dos cosas concretas y acotadas: privacidad (Azure OpenAI) y la cola de validación. Ambas son alcanzables y bien delimitadas.
4. **Lo que el cliente excluye nos favorece.** Email/WhatsApp/web externos, dictámenes legales, ERP y multilingüe quedan fuera de fase 1 — justo lo que no tenemos pulido para fiscal.
5. **La jugada no es competir en "el motor"** (se comoditiza), sino en **vertical + cercanía + Azure-nativo**: ser el implementador que entiende el dominio fiscal AR y se integra limpio al stack Microsoft que el cliente ya tiene.

**Riesgo a vigilar (honesto):** somos un equipo chico frente a un asegurador que pedirá referencias en sector financiero, SLA y cumplimiento de Ley 25.326. No prometer en fase 1 lo que es propio de un proveedor enterprise grande (SLA 99% contractual, SSO completo, on-call 24/7). Acotar la POC y crecer por etapas.

---

## 9. Recomendación y próximos pasos

**GO**, con alcance por etapas.

- **Para responder el RFI (vence 08-jul):** posicionar fortalezas reales (RAG, español rioplatense, HITL, trazabilidad, "empleado digital que rinde cuentas"), declarar gaps con honestidad, y proponer una **POC Fase 1 acotada**: Jira-in → RAG → respuesta automática / propuesta-con-validación, sobre **Azure OpenAI**, con un **adapter mínimo de Teams**. No comprometer SLA 99% ni SSO enterprise en fase 1.
- **Si avanza:** dimensionar formalmente los gaps 🔴 (Azure OpenAI, cola de validación, conector Jira, adapter Teams, SSO Entra) en un plan de implementación con hitos y dependencias de accesos del cliente.

---

## Anexo — Archivos de la plataforma (reuso, no reinvención)

| Componente | Ubicación |
|---|---|
| RAG / re-ingesta | `backend/app/services/rag_service.py`, `vector_store.py`, `routers/knowledge.py`, `routers/documents.py` |
| Human-in-the-loop / validación | `backend/app/services/conversation_control_service.py`, `routers/hotel_tickets.py` (`pre-resolve`), `services/escalation_analyzer.py` |
| Umbral configurable (patrón Skills/techo duro) | `landing/src/admin/views/centro/EmployeeSkills.jsx` + modelo `policy_values` |
| Canal desacoplado / entrada agnóstica | `backend/app/services/agent_service.py` (`chat()`), `routers/whatsapp.py` (referencia de adapter) |
| LLM provider (a abstraer para Azure OpenAI) | `backend/app/core/openai_client.py`, `app/config.py` |
| Auth (a reemplazar por SSO) | `backend/app/core/admin_auth.py` |
| Trazabilidad | `backend/app/models/conversation_message.py`, audit `logs/aura_audit.jsonl` |
| Estrategia / visión de producto | `FLUJOS_Y_ESTRATEGIA.md` |

---

*Documento interno de evaluación. No constituye oferta ni compromiso contractual. Estimaciones de esfuerzo en orden de magnitud, sujetas a relevamiento de accesos e infraestructura del cliente.*
