# Instagram como canal de Aura — Guía de setup (Meta, modo desarrollo)

Con esta guía dejás a Aura respondiendo DMs de Instagram **reales**. Funciona con la app de
Meta en **modo desarrollo**: hasta **25 testers invitados**, sin App Review — el equivalente
al sandbox de Twilio para WhatsApp (el "join" acá es aceptar una invitación de tester).

El código ya está desplegado: webhook en `/api/instagram/webhook` + envío por Graph API.
Solo falta crear las cuentas y cargar 3 variables en Render.

---

## Paso 1 — Cuenta de Instagram Business (el "Instagram del hotel")

1. Creá una cuenta de Instagram para el hotel demo (ej. `@hampton.bariloche.demo`), o usá una
   existente.
2. En la app de Instagram: **Configuración → Cuenta → Cambiar a cuenta profesional →
   Empresa** (Business). Gratis, al instante.

## Paso 2 — Página de Facebook vinculada

1. Creá una página de Facebook (ej. "Hampton Bariloche Demo") desde tu perfil de FB
   (Menú → Páginas → Crear).
2. Vinculá el Instagram a la página: en Instagram, **Configuración → Centro de cuentas →
   Cuentas → Agregar página de Facebook** (o desde la página de FB: Configuración →
   Instagram → Conectar cuenta).

## Paso 3 — App de Meta (developers.facebook.com)

1. Entrá a https://developers.facebook.com con tu usuario de Facebook → **My Apps →
   Create App**.
2. Tipo de app: **Business**. Nombre: ej. "Aura Hotel Demo".
3. En el dashboard de la app: **Add Product → Instagram** → Set up (elegí la opción de
   **Instagram API / Messaging**).
4. Conectá la cuenta de Instagram Business del Paso 1 cuando el flujo te lo pida.
5. La app queda en **Development Mode** (no la publiques — así funciona con testers sin
   App Review).

## Paso 4 — Webhook (que Meta le avise a nuestro backend)

1. En la app: **Instagram → Configuration → Webhooks** (o Products → Webhooks →
   suscripción "Instagram").
2. **Callback URL**: `https://hotel-backend-4xgz.onrender.com/api/instagram/webhook`
3. **Verify token**: inventá uno (ej. `aura-ig-2026`) — **el mismo** que vas a cargar en
   Render como `INSTAGRAM_VERIFY_TOKEN` (Paso 5). Cargalo en Render ANTES de tocar
   "Verify and save", porque Meta hace la verificación en ese momento.
4. Suscribite al campo **`messages`**.

## Paso 5 — Credenciales en Render

1. En la app de Meta → **Instagram → API setup / Generate token**: generá el **access token**
   de la cuenta IG conectada (long-lived, dura ~60 días; se regenera desde acá cuando vence).
2. Anotá también el **Instagram account ID** (aparece junto a la cuenta conectada; es un
   número largo).
3. En Render → servicio `hotel-backend` → **Environment**:
   - `INSTAGRAM_ACCESS_TOKEN` = el token generado
   - `INSTAGRAM_ACCOUNT_ID` = el ID de la cuenta
   - `INSTAGRAM_VERIFY_TOKEN` = el token que inventaste en el Paso 4
4. Guardá (Render redeploya solo).

## Paso 6 — Invitar testers (el "join" de Instagram)

Solo los testers invitados pueden chatear con la app en modo desarrollo (máx. 25 — de sobra
para demos).

1. En la app de Meta: **App roles → Roles → Add People → Instagram Tester** → poné el
   @usuario de Instagram del cliente (o el tuyo para probar primero).
2. El invitado acepta desde **su** Instagram: **Configuración → Sitios web y apps →
   Invitaciones de tester** (en la web de Instagram: Settings → Apps and websites →
   Tester invites) → Aceptar.

## Paso 7 — Probar 🎉

1. Desde el Instagram del tester, mandale un DM a la cuenta del hotel
   (`@hampton.bariloche.demo`): "Hola! quiero info de habitaciones".
2. **Aura responde en el DM real** (flujo de preventa completo: disponibilidad, precios,
   captura de datos).
3. En el backoffice:
   - **Conversaciones**: la charla aparece en vivo con badge de Instagram y el @usuario.
     Podés tomar el control y responder como humano (llega al Instagram real).
   - **Leads**: el lead se crea con origen **Instagram** (badge rosa).
   - **Analíticas**: Instagram aparece como canal en la distribución de conversaciones.

---

## Troubleshooting

| Problema | Causa probable |
|---|---|
| Meta no verifica el webhook ("callback failed") | `INSTAGRAM_VERIFY_TOKEN` no está en Render o no coincide con el de la app. Cargalo y esperá el redeploy antes de verificar. |
| El DM del tester no llega al backend | El tester no aceptó la invitación, o el campo `messages` no está suscripto en Webhooks. |
| Aura procesa pero la respuesta no llega al IG | `INSTAGRAM_ACCESS_TOKEN`/`INSTAGRAM_ACCOUNT_ID` faltan o vencieron (revisar logs de Render: "Meta rechazó el envío"). Regenerar el token (Paso 5). |
| Respuesta rechazada tras un día sin hablar | Ventana de 24 h de Meta (igual que WhatsApp): el usuario tiene que escribir de nuevo para reabrirla. |

## Notas

- **Producción real** (que cualquier persona pueda escribir, no solo testers) requiere App
  Review de Meta (`instagram_manage_messages` advanced access). El código no cambia: es solo
  el trámite de aprobación con la cuenta del cliente.
- El token long-lived vence ~cada 60 días en desarrollo: si el canal deja de responder,
  regenerarlo y actualizar `INSTAGRAM_ACCESS_TOKEN` en Render.
