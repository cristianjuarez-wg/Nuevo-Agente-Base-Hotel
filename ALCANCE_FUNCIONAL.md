# Alcance Funcional — Plataforma de Experiencia del Huésped

**Producto:** Capa de Experiencia del Huésped (Guest Experience Layer) sobre el PMS del hotel
**Componentes:** Agente conversacional **Aura** (IA) + **Backoffice** de gestión
**Caso de referencia:** Hampton by Hilton Bariloche
**Última actualización:** 2026-06

---

## 1. Visión general

La plataforma es una **capa de experiencia del huésped** que se apoya sobre el PMS del hotel y suma dos cosas que el PMS no da:

1. **Aura**, un agente de IA conversacional multi-canal (web + WhatsApp) y multi-rol (huésped, equipo, gerencia) que atiende pre-venta, post-venta, restaurante, operaciones y BI.
2. Un **backoffice** desde donde el hotel configura todo (conocimiento, precios, promos, equipo, carta) y opera el día a día (reservas, leads, tickets, conversaciones en vivo), **sin tocar código y sin redeploy**.

**Principios transversales:**

- **Precios en USD como fuente de verdad**; el ARS se calcula al vuelo con la cotización vigente.
- **Re-ingesta instantánea al RAG:** cualquier cambio de conocimiento/promos/carta se refleja en el agente en el siguiente mensaje.
- **Visión 360° del huésped:** un `Contact` consolida reservas, conversaciones, leads, tickets, pedidos, consumo y alergias.
- **Seguridad por diseño:** clave de admin para acciones sensibles, topes de gasto de IA, rate limiting, guardrails anti-jailbreak.
- **Hora de Argentina** en toda la app (America/Argentina/Buenos_Aires).

---

## 2. El agente Aura

### 2.1 Ruteo automático por rol

Aura decide **quién le habla** y enruta sin que el usuario elija, vía matching de teléfono contra `StaffMember` (`role_service.resolve_role()`), con match exacto y match tolerante (formato viejo):

| Rol | Identidad | Orquestador | Memoria | Session ID |
|-----|-----------|-------------|---------|------------|
| **Huésped** (default) | teléfono no registrado en staff | triage → pre-venta / post-venta / casual | pre-venta indefinida; post-venta 24 h | `wa_<tel>` / `web-<hash>` |
| **Gerencia (owner)** | `StaffMember.role == owner` | `owner_orchestrator` | **persistente, sin expirar** | `owner_<tel>` |
| **Equipo (staff)** | `StaffMember.role == staff` | `staff_orchestrator` | RAM, acotada a 30 msgs | `staff_<tel>` |

### 2.2 Agente de pre-venta

Atiende a potenciales clientes: información, disponibilidad real, reservas, restaurante, atracciones.

**Herramientas:**

- **info_hotel** — RAG sobre la base de conocimiento (ChromaDB + embeddings OpenAI). Responde habitaciones, servicios, políticas, amenities, ubicación, sin inventar.
- **consultar_disponibilidad** — motor real de reservas; devuelve habitaciones disponibles por rango de fechas y composición (adultos/niños/bebés), con precio USD y ARS.
- **crear_reserva** — gate determinístico; crea reserva confirmada solo con todos los datos. Devuelve código `HTL-XXXX`. Aplica promo si corresponde.
- **consultar_reserva** — estado y detalle de una reserva por código.
- **info_pago** — titular, banco, CBU, alias, medios aceptados (multi-cuenta). Solo bajo pedido explícito.
- **como_llegar** — rutas con Google Maps (link + distancia/tiempo) desde el origen del cliente.
- **comercios_amigos** — acuerdos locales (gastronomía, heladerías) con descuentos para huéspedes; fallback a Google Maps.
- **excursiones_y_atracciones** — catálogo de la zona (Cerro Catedral, Circuito Chico, paseos).
- **promos_vigentes** — lista de promociones activas (sin cálculo de precio).
- **calcular_precio_promo** — aplica la mejor promo a una estadía concreta (ej. 4x3) y genera card visual. Se dispara cuando el cliente pide promo o muestra resistencia al precio.
- **ver_carta / armar_pedido_carta / registrar_pedido** — carta del restaurante, pre-carga de carrito por texto y confirmación de pedido (`RST-XXXX`).
- **reservar_mesa** — reserva de comedor (turno, personas, fecha, notas: cumpleaños, alergias).
- **comprar_voucher** — voucher pre-pagado para visitante no alojado (`VCH-XXXX`).
- **guardar_preferencia** — restricciones dietéticas y alergias en el perfil (seguridad alimentaria + sugerencias futuras).

**Lógica transversal:** triage pre/post/casual; análisis de lead por turno (intención, score, datos de contacto); flag de "disponibilidad mostrada" para ofrecer reservar; guardrail anti-jailbreak; bloque de contexto del huésped (nombre, fechas, composición).

### 2.3 Agente de post-venta

Atiende huéspedes con reserva confirmada (gate por `HTL-XXXX`).

- **analizar_escalacion** — obligatorio antes de responder; decide si es informativo (lo resuelve Aura) o requiere asesor humano (cambios de fecha, cancelaciones, reembolsos, reclamos, cobros).
- **consultar_info_hotel** — RAG de políticas y amenities durante la estadía.
- **solicitar_servicio** — crea ticket interno (housekeeping / mantenimiento / recepción) con urgencia.
- **ver_fotos_habitacion** — galería de su habitación.
- **registrar_preferencia / consultar_pago** — preferencias y estado de pago.
- **ver_carta / armar_pedido_carta / registrar_pedido / reservar_mesa** — restaurante con su reserva pre-cargada.

### 2.4 Agente de gerencia (copiloto de negocio)

BI conversacional con gráficos enviados por WhatsApp (QuickChart → PNG):

- **consultar_ocupacion** — % ocupación, breakdown por tipo, serie diaria.
- **consultar_ingresos** — facturación USD/ARS, realizado vs. proyectado.
- **consultar_leads** — generados, cerrados, conversión, por canal.
- **consultar_quejas** — tickets abiertos/resueltos por urgencia y categoría.
- **consultar_resumen_negocio** — combinado, varios gráficos a la vez.

Períodos flexibles ("hoy", "semana", "mes", "trimestre", meses por nombre, estaciones del hemisferio sur, años explícitos). Memoria persistente de largo plazo (rehidratada tras deploy). Anti-duplicado de gráficos.

### 2.5 Agente de equipo (operaciones)

Empleado digital por WhatsApp (texto o audio transcrito):

- **resolver_ticket** — marca una tarea resuelta (por nº `HT-XXXXXX` o por habitación).
- **reportar_incidencia** — crea ticket nuevo, deduce área y asigna.
- **mis_tickets** — pendientes del miembro.

---

## 3. Canales

### 3.1 WhatsApp (Twilio)

- **Texto, audio (Whisper) e imágenes** (estas últimas en el flujo de check-in express, guardadas en `/media/checkin/`).
- Webhook → normaliza teléfono → transcribe audio → enruta por rol → responde.
- Markdown convertido a formato WhatsApp; hasta 3 tarjetas de habitación por turno; indicadores de escritura/lectura; fallback a texto si falla el media.

### 3.2 Chat web

- Markdown + **tarjetas interactivas React**: `RoomCard` (foto, capacidad, cama, vista, precio USD/ARS, promo tachada, botón Reservar), `MenuCard` (filtros + carrito), `DatePickerCard`, `TableReservationCard`, `MenuOrderCard` (carrito pre-cargado).
- Sesión persistente en localStorage; efecto typewriter; indicadores de tipeo/pensamiento; tema visual configurable; selector de idioma.
- **WebSocket para takeover humano:** un asesor toma la conversación en vivo y sus mensajes se inyectan sin romper la secuencia.

### 3.3 Multi-idioma

Español, inglés, portugués (y francés en el agente). Detección navegador → localStorage → default; tarjetas, labels y errores siguen el idioma activo; el agente responde en el idioma del cliente.

---

## 4. Memoria, contexto y RAG

- **`conversation_messages`**: pares user/assistant con `session_id`, `context_type` (pre_sale / post_sale / management), tokens, modelo, tiempo de respuesta, fuentes RAG.
- Rehidratación robusta tras reinicio/deploy (no se pierde la conversación, en especial con gerencia).
- **RAG (ChromaDB):** indexa el conocimiento activo; enriquece la query con las últimas consultas del usuario; filtra por similitud y deduplica por documento.

---

## 5. Base de conocimiento (cargada por el cliente)

### 5.1 Entradas estructuradas (`KnowledgeEntry`)

Siete categorías vía formularios del backoffice: **pagos** (multi-cuenta: titular, banco, CBU, alias, moneda, default), **checkin**, **cancelacion**, **mascotas**, **servicios**, **faq** (pares q/a), **general**.

### 5.2 Lugares y comercios amigos (`Place`)

Categorías: `excursion`, `gastronomia`, `atraccion`, `transporte`, `hotel`. Campos: nombre, descripción, dirección, info de precio, imagen, Google Maps. Con `is_partner=true` se habilitan teléfono, WhatsApp y descripción del descuento. **Viven en el RAG**, no en una docsbase aparte.

### 5.3 Documentos libres (PDF / Markdown / texto)

Subida nativa de **PDF y Markdown** (o texto pegado), máx. 5 MB. La IA **extrae campos automáticamente** (GPT-4o-mini) y el cliente revisa antes de guardar.

### 5.4 Re-ingesta sin redeploy

Crear/editar/borrar conocimiento, lugares, promos o carta → borra los chunks previos por `doc_source` y re-ingesta si está activo. El agente lo ve **al instante** en el próximo mensaje.

---

## 6. Configuración del agente

- **Temas / branding (`ChatTheme`):** colores (header, accent, burbujas, FAB), rango de activación mes/día (cruza año nuevo), estados active/pinned/inactive, efectos visuales (nieve, nieve+dorado, hojas, conejito).
- **Promociones (`Promotion`):** nombre, descripción, condiciones, tipo (percentage / free_night / other), valor, mínimo de noches, vigencia, estado. El agente las usa por tool determinística + RAG.
- **Límites y gasto (`AgentBudgetConfig`):** tope diario y mensual en USD con master switch; al superarse, el agente se **pausa** automáticamente.
- **Cotización USD→ARS (`ExchangeRateConfig`):** manual (valor fijo) o automático (dólar oficial vía dolarapi.com) con cache y fallbacks.

---

## 7. Operación y backoffice

- **Dashboard** — indicadores del negocio.
- **Conversaciones en vivo + históricas** — bandeja con takeover humano, vínculo lead↔cliente, perfil 360°, nombre del interlocutor.
- **Reservas** — listado, estado de estadía (upcoming / checked_in / past / cancelled), **check-in express por WhatsApp** (solo reservas próximas).
- **Huéspedes / perfil 360°** — datos consolidados, consumo F&B por estadía, **alergias separadas de dietas** (seguridad alimentaria).
- **Operaciones / tickets** — `HotelTicket` por área, estados pendiente → pre-resuelto → resuelto.
- **Leads** — Kanban (Nuevo / Contactado / Ganado / Perdido) con drag&drop y panel de gestión (bitácora de acciones de Aura, conversación, seguimiento, "Resumir con IA", editar) + vista Lista.
- **Analítica** — métricas de negocio.
- **Restaurante** — carta, pedidos, reservas de mesa, vouchers.
- **Habitaciones** — tipos y unidades físicas.
- **Equipo** — altas, rol y área.
- **Configuración de Aura** — conocimiento, temas, promos, límites, cotización.
- **Asesor de gerencia** — copiloto de negocio.
- **Consumo IA** — tokens/USD hoy y mes, costo por conversación, desglose por modelo, alerta si está pausado.

---

## 8. Restaurante (a fondo)

- **Carta (`MenuItem`)** — categorías (tapas, plato, sándwich, ensalada, pizza, postre, cerveza, trago, vino, cafetería, merienda, bebida), precio USD, foto, **alérgenos** y **tags** dietéticos, disponibilidad, `only_dinner`. Indexada al RAG.
- **Pedidos (`RestaurantOrder` + `OrderItem`)** — canal web/WhatsApp, fulfillment (room service / salón / retiro), pago a **folio** o link. **El precio nunca se confía del cliente/LLM: el servidor recalcula siempre contra la carta** y congela `unit_price_usd`. Estados pendiente → confirmado → en_preparacion → entregado/cancelado.
- **Folio (`ExtraCharge`)** — los pedidos a folio quedan abiertos contra el `Booking` hasta el check-out, donde se saldan a la factura total.
- **Reservas de mesa (`TableReservation`)** y **vouchers** (PDF de regalo con buyer + items).

---

## 9. Seguridad y plataforma

- **Clave de admin (`X-Admin-Key`)** — protege acciones sensibles (topes de gasto, cotización manual, reset, generar/limpiar demo). Sin clave en dev/local; obligatoria en producción.
- **Rate limiting** por IP (minuto/hora), configurable en el servidor.
- **Guardrails anti-jailbreak** en los orquestadores.
- **Control de gasto** de IA (ver §6).
- **Reset de datos en tres niveles:** poblar demo · limpiar solo demo (`is_demo=True`) · resetear todo lo operativo (con palabra de confirmación), preservando configuración y carta.
- **Trazabilidad** completa por mensaje (modelo, tokens, herramientas, tiempo, fuentes RAG) y eventos de lead.

---

## 10. Modelo de datos (resumen)

`Contact` (360°) · `Booking` (`HTL-XXXX`, `pre_checkin`, `stay_status()`) · `Lead` (tipo, score, status, kanban_stage) · `Conversation` / `ConversationMessage` · `HotelTicket` · `Room` / `RoomUnit` · `StaffMember` · `KnowledgeEntry` / `Place` · `Promotion` · `ChatTheme` · `MenuItem` / `RestaurantOrder` / `OrderItem` / `ExtraCharge` / `TableReservation` · `AgentBudgetConfig` / `ExchangeRateConfig`.
