# Hampton by Hilton Bariloche — Demo con agente IA

Demo de un hotel single-property con un **agente conversacional (Aura)** que capta leads,
consulta disponibilidad real, crea reservas y atiende post-venta; más un **backoffice** de
gestión. Basada en la plataforma del proyecto "Demo Freeway - Turismo", portada al dominio hotel.

## Arranque rápido

```powershell
.\iniciar_demo.ps1
```

Levanta el backend (FastAPI, puerto 8010) y la landing (Vite, puerto 5174) y abre el navegador.

### Manual

```powershell
# Backend
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8010

# Landing (en otra terminal)
cd landing
npm install   # solo la primera vez
npm run dev
```

## URLs

| Qué | URL |
|---|---|
| Sitio público + agente Aura | http://localhost:5174 |
| Backoffice (Dashboard, Reservas, Leads, Soporte) | http://localhost:5174/#admin |
| API (Swagger) | http://localhost:8010/docs |

## Recorrido sugerido para la presentación

1. **Landing** — mostrar el sitio del Hampton (habitaciones reales, servicios, ubicación).
2. **Motor de reserva** — sección "Reservar": fechas → disponibilidad → datos → código de reserva.
3. **Agente Aura** (botón azul, abajo a la derecha):
   - "¿Qué servicios tiene el hotel?" → responde con info real (RAG).
   - "¿Hay disponibilidad del 20 al 23 de octubre para 2 personas?" → consulta el motor real.
   - "Reservo la Twin, soy Juan Pérez, juan@mail.com" → **crea la reserva y da el código**.
   - En otra sesión, dar un código `HTL-XXXX` → flujo de post-venta (consulta / escalado).
4. **Backoffice** (`/#admin`) — mostrar la reserva recién creada por el agente entrando en
   "Reservas" (badge **Agente**), el lead captado en "Leads", y los tickets de soporte.

## Arquitectura

```
LANDING (React + Vite + Tailwind, :5174)
  landing pública  ·  motor de reserva  ·  widget de chat (Aura)  ·  backoffice (#admin)
        │  axios
        ▼
BACKEND (FastAPI, :8010)
  /api/chat            agente (pre-venta, post-venta, casual) — OpenAI Agents SDK
  /api/reservations    motor de reserva (rooms, availability, bookings)
  /api/leads           leads captados por el agente
  /api/hotel-tickets   tickets de soporte post-venta
  ChromaDB (hotel_documents)  ·  SQLite (hotel.db)
```

## Notas

- **Pago simulado**: las reservas nacen con `payment_status="paid"`.
- **Datos reales** del Hampton by Hilton Bariloche (habitaciones, precios estimados USD/ARS,
  servicios, ubicación, imágenes del sitio oficial).
- El proyecto "Demo Freeway - Turismo" queda **intacto**; esta demo es independiente.
- ⚠️ El `.env` contiene una API key de OpenAI que conviene **rotar** tras la demo.
