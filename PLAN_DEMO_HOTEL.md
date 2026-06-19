# 🏨 Plan de Demo — Sistema de Gestión Hotelera (single-hotel) con Agente IA

**Fecha:** 18 de junio de 2026
**Objetivo:** Demo para un cliente de una landing de UN hotel + agente IA + motor de reserva real + backoffice (leads, posventa).
**Estrategia base:** Reutilizar la plataforma existente **"Demo Freeway - Turismo"** (FastAPI + React) y adaptarla a hotelería, construyendo solo lo que falta: **landing pública** y **motor de reserva**.

---

## 1. Decisión de arquitectura (por qué reutilizar Freeway)

Se descartó adoptar un repo de GitHub (QloApps, Quickstay, nextjs-hotel-booking) porque **ninguno trae leads + posventa**, que son las piezas más costosas y que Freeway **ya tiene construidas y probadas**.

| Pieza | Origen | Estado |
|---|---|---|
| Agente conversacional (perfiles JSON) | ♻️ Freeway | Existe |
| Captación de **leads** (CALIENTE/TIBIO/FRÍO) | ♻️ Freeway | Existe |
| **Posventa**: tickets, escalación LLM, kanban | ♻️ Freeway | Existe |
| Backoffice: dashboard, métricas, kanban | ♻️ Freeway | Existe |
| RAG sobre documentos (ChromaDB) | ♻️ Freeway | Existe |
| **Landing pública del hotel** | 🆕 Nuevo | A construir |
| **Motor de reserva** (rooms, disponibilidad, booking) | 🆕 Nuevo | A construir |
| Perfil de agente `hotel.json` + docs del hotel | 🆕 Config | A crear |

De GitHub se toma **solo inspiración de diseño** para la landing (referencia: OthmaneNissoukin/nextjs-hotel-booking).

---

## 2. Arquitectura objetivo

```
┌──────────────────────────────────────────────────────────┐
│  🆕 LANDING PÚBLICA DEL HOTEL                             │
│  React 18 + Vite + Tailwind (mismo stack que Freeway)    │
│  • Hero / habitaciones / galería / servicios / ubicación │
│  • 🆕 Motor de reserva (selección fechas + disponib.)    │
│  • Widget flotante del AGENTE (consume /api/chat)        │
└───────────────────────┬──────────────────────────────────┘
                        │ HTTP (axios) → API FastAPI
┌───────────────────────┴──────────────────────────────────┐
│  ♻️ BACKEND FREEWAY (FastAPI)  + 1 router nuevo          │
│  ✅ /api/chat   ✅ /api/leads   ✅ /api/postsale          │
│  ✅ /api/analytics  ✅ /api/kanban                        │
│  🆕 /api/reservations  (rooms · availability · bookings) │
│  🆕 perfil agente: data/agent_profiles/hotel.json        │
│  🆕 docsbase/ con info del hotel (habitaciones, FAQ...)  │
└───────────────────────┬──────────────────────────────────┘
                        │ SQLite (SQLAlchemy) + ChromaDB
┌───────────────────────┴──────────────────────────────────┐
│  ♻️ BACKOFFICE FREEWAY (React, reutilizado tal cual)     │
│  ✅ Leads · ✅ Kanban tickets · ✅ Dashboard · ✅ Posventa│
│  🆕 (opcional) vista de Reservas en el backoffice        │
└──────────────────────────────────────────────────────────┘
```

**Persistencia:** SQLite (ya en uso en Freeway) — perfecto para demo, cero infra. No se necesita Supabase ni Mongo.

---

## 3. Componente NUEVO #1 — Motor de Reserva

### 3.1 Modelos de datos (SQLAlchemy / SQLite)

```python
# app/models/hotel.py  (nuevo)

class Room(Base):                 # Tipo de habitación
    id, room_type (str)           # "Doble Superior", "Suite", ...
    description, capacity (int)
    base_price (float)            # precio por noche
    total_units (int)             # cuántas habitaciones de este tipo hay
    images (JSON), amenities (JSON)

class Booking(Base):              # Reserva
    id, code (str, único)         # ej "HTL-7F3A" (sirve para posventa)
    room_id (FK Room)
    guest_name, guest_email, guest_phone
    check_in (date), check_out (date)
    guests (int), nights (int)
    total_price (float)
    status (str)                  # pending / confirmed / cancelled / completed
    payment_status (str)          # pending / paid / refunded
    created_at, source (str)      # "web" | "agente"
```

> **Disponibilidad** se calcula (no se almacena por día): para un rango de fechas, una `Room` está disponible si `total_units` − (bookings que solapan el rango y no están cancelados) > 0. Simple y suficiente para demo.

### 3.2 Endpoints — `app/routers/reservations.py` (nuevo)

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/api/reservations/rooms` | Lista tipos de habitación (para la landing) |
| GET | `/api/reservations/availability?check_in&check_out&guests` | Habitaciones disponibles + precio total |
| POST | `/api/reservations/bookings` | Crea reserva → devuelve `code` |
| GET | `/api/reservations/bookings/{code}` | Consulta una reserva (la usa el agente y posventa) |
| POST | `/api/reservations/bookings/{code}/cancel` | Cancela (opcional para demo) |
| GET | `/api/reservations/bookings` | Lista reservas (backoffice) |

### 3.3 UI del motor de reserva (landing)
- Selector de fechas (`react-datepicker` o el `date-fns` ya presente) + nº de huéspedes.
- Listado de habitaciones disponibles con precio calculado.
- Formulario de datos del huésped → confirmación con código de reserva.
- (Pago: ver sección 6 — simulado o Stripe test).

---

## 4. Componente NUEVO #2 — Landing pública del hotel

Nuevo proyecto React+Vite+Tailwind (clonando la config del frontend de Freeway para mantener coherencia). Secciones:

1. **Hero** — nombre del hotel, imagen, CTA "Reservar".
2. **Habitaciones** — cards desde `/api/reservations/rooms`.
3. **Galería** — fotos.
4. **Servicios / amenities** — íconos (lucide-react ya está).
5. **Ubicación** — mapa (Freeway ya tiene `maps_service`).
6. **Motor de reserva** — sección 3.3.
7. **Widget de chat flotante** — sección 5.

> Estructura y diseño tomando como referencia visual nextjs-hotel-booking, pero implementado en el stack propio.

---

## 5. Componente de adaptación — Agente para hotel

El agente cambia de dominio **sin tocar código del core**, solo configuración:

### 5.1 Nuevo perfil `data/agent_profiles/hotel.json`
Basado en `template.json` / `turismo.json`. Define:
- `agent_name` (ej. el concierge del hotel),
- `system_prompt_template` orientado a hotelería,
- `greeting_message`, `no_info_response`,
- `capabilities` y `conversation_starters` de hotel.

### 5.2 Conocimiento del agente (`docsbase/`)
Reemplazar los PDFs de viajes por documentos del hotel: tipos de habitación, tarifas, políticas (check-in/out, mascotas, cancelación), servicios, FAQ, gastronomía. El RAG (ChromaDB) los indexa igual que hoy.

### 5.3 Las 3 funciones del agente (lo que pediste)
| Función | Cómo se logra |
|---|---|
| **Captar leads** | ✅ `lead_service` ya lo hace; solo ajustar criterios al contexto hotel |
| **Crear/consultar reservas** | 🆕 dar al agente acceso a `/api/reservations` (consultar disponibilidad, crear booking, consultar por código) |
| **Posventa / follow-up** | ✅ `postsale_service` ya lo hace; el `code` de Booking funciona como código de reserva para validar acceso |

### 5.4 Widget de chat en la landing
Componente flotante que consume los endpoints existentes:
- `GET /api/chat/greeting` (saludo inicial)
- `POST /api/chat/message` (`{ message, session_id }`)
- `POST /api/chat/clear/{session_id}`

El front ya tiene `apiClient` (axios) reutilizable.

---

## 6. Pago (motor de reserva real)

**Decidido: pago simulado.** Al confirmar la reserva, el booking se marca `payment_status = paid` directamente, sin pasarela. Suficiente para la demo visual y sin complejidad de webhooks. Stripe test mode queda documentado como **mejora futura** (sección 11).

---

## 7. Estructura de carpetas propuesta (en `Productos/Hoteles`)

```
Hoteles/
├── PLAN_DEMO_HOTEL.md          ← este documento
├── backend/                    ← copia de Freeway backend, adaptada
│   ├── app/
│   │   ├── models/hotel.py     🆕
│   │   ├── routers/reservations.py 🆕
│   │   └── ... (resto reutilizado)
│   ├── data/agent_profiles/hotel.json 🆕
│   └── docsbase/               🆕 (docs del hotel)
└── landing/                    🆕 (React+Vite+Tailwind)
    └── src/{components,sections,services}
```

> A decidir: ¿el backoffice de Freeway se **copia** a Hoteles o se **comparte** el de la carpeta Turismo? (sección 9).

---

## 8. Fases de implementación

| Fase | Entregable | Depende de |
|---|---|---|
| **F0** | Copiar backend de Freeway a `Hoteles/backend`, levantar y verificar que arranca | — |
| **F1** | Modelos `Room`/`Booking` + router `/api/reservations` + datos seed de 1 hotel | F0 |
| **F2** | Perfil `hotel.json` + docs en `docsbase/` + reindexar RAG | F0 |
| **F3** | Landing pública (hero, habitaciones, galería, servicios) | F1 |
| **F4** | Motor de reserva en la landing (fechas, disponibilidad, booking) | F1, F3 |
| **F5** | Widget de chat del agente en la landing | F2, F3 |
| **F6** | Dar al agente las "tools" de reserva (consultar/crear) | F1, F5 |
| **F7** | Pago (simulado o Stripe) | F4 |
| **F8** | (Opcional) Vista de Reservas en backoffice + pulido demo | F1 |

---

## 9. Decisiones tomadas (18-jun-2026) ✅

1. **Backoffice:** **Copiar Freeway a `Hoteles/`** → demo 100% independiente de Turismo. Turismo queda intacto.
2. **Datos del hotel:** **Hotel ficticio** inventado (nombre + 4-5 tipos de habitación + servicios + fotos placeholder). Arrancamos ya.
3. **Pago:** **Simulado** → al confirmar, `payment_status = paid` sin pasarela. (Stripe queda como mejora futura).
4. **Agente-reserva:** **Consultar + crear + posventa** → el agente ve disponibilidad, crea bookings (devuelve código) y atiende posventa usando el código de reserva.
5. **Idioma/branding:** Español (pendiente paleta/branding final — se define al construir la landing).

---

## 10. Riesgos / notas

- El `agent_service.py` es grande (~1.124 líneas) y tiene lógica específica de turismo (filtrado de países, análisis geográfico). Para hotel single-property, parte de eso sobra → se puede **desactivar por config** sin borrar, para no romper nada.
- Reindexar ChromaDB con los nuevos docs del hotel (los de turismo no deben mezclarse).
- Mantener stack homogéneo: todo React+Vite+Tailwind / FastAPI+SQLite. No introducir Supabase/Mongo.

---

## 11. Mejoras futuras (post-demo)

- **Stripe test mode** real en el motor de reserva (reemplaza el pago simulado).
- Vista dedicada de Reservas en el backoffice con filtros y estados.
- Disponibilidad por unidad/día (calendario real) si el cliente quiere overbooking control fino.
- Swap de hotel ficticio → datos reales del cliente.

---

**FIN DEL PLAN**
