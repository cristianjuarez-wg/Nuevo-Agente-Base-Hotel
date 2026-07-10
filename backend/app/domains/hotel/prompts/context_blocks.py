"""
Bloques de contexto que se inyectan dinámicamente en el system prompt principal.
Cada función recibe los datos necesarios y devuelve el bloque de texto formateado.
"""

# Idiomas soportados por el agente (selector del chat). El LLM es multilingüe nativo:
# alcanza con instruirlo. Las instrucciones del prompt siguen en español; lo único
# que cambia es el idioma de la conversación con el huésped.
LANGUAGE_NAMES = {"es": "Español", "en": "English", "pt": "Português", "fr": "Français"}


def build_language_block(language: str) -> str:
    """Instrucción de idioma de respuesta. Vacío para español (comportamiento por defecto)."""
    lang = (language or "es").lower()
    if lang == "es" or lang not in LANGUAGE_NAMES:
        return ""
    name = LANGUAGE_NAMES[lang]
    return f"""━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🌐 IDIOMA DE RESPUESTA — {name} ({lang})
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Estas instrucciones están en español, pero TODA tu conversación con el huésped debe ser
100% en {name}: el saludo, las respuestas, las preguntas, las confirmaciones de reserva
y los mensajes de error. NO mezcles idiomas.

Los resultados de las herramientas (disponibilidad, confirmación de reserva, errores)
pueden venir en español: TRADUCILOS/REFORMULALOS SIEMPRE a {name} antes de responder.
Los datos neutrales (código de reserva HTL-XXXX, números, precios, fechas) se mantienen
tal cual; solo el texto que los rodea va en {name}.

MANTENÉ TU CALIDEZ Y CARÁCTER al traducir: seguís siendo cálida, cercana y con humor sutil
en {name} también — no te vuelvas plana ni puramente transaccional. (El voseo rioplatense
es solo para español; en {name} usá el registro cálido y natural propio de ese idioma.)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

"""


def build_guest_profile_block(profile: dict) -> str:
    """Bloque de perfil del huésped recurrente/conocido para personalizar la charla.

    Recibe el dict de contact_service.get_guest_profile(). Solo se inyecta cuando el
    huésped tiene historial (≥1 estadía o preferencias). Le da a Aura contexto para
    reconocerlo y ofrecer una experiencia personalizada, con tono cálido y no invasivo.
    """
    contact = profile.get("contact") or {}
    name = contact.get("first_name") or contact.get("full_name") or "este huésped"

    lines = []
    if profile.get("is_staying_now"):
        active = profile.get("active_stay") or {}
        lines.append(f"- ESTÁ ALOJADO AHORA (reserva {active.get('code','')}, "
                     f"habitación {active.get('room_type','')}). Tratalo como huésped en casa.")
    elif profile.get("upcoming_stay"):
        up = profile.get("upcoming_stay") or {}
        lines.append(
            f"- TIENE UNA RESERVA FUTURA (código {up.get('code','')}, "
            f"habitación {up.get('room_type','')}, check-in {up.get('check_in','')} → "
            f"check-out {up.get('check_out','')}). AÚN NO se hospedó. Si habla de 'el primer día "
            f"de mi estadía' o 'cuando llegue', se refiere al check-in {up.get('check_in','')}."
        )
    if profile.get("is_recurring"):
        lines.append(f"- Es un huésped RECURRENTE: {profile.get('stays_count')} estadías. "
                     f"Última: {profile.get('last_stay')}.")
    elif profile.get("stays_count"):
        lines.append(f"- Ya se hospedó antes (última estadía: {profile.get('last_stay')}).")
    if profile.get("preferred_room"):
        lines.append(f"- Habitación que suele elegir: {profile['preferred_room']}.")

    prefs = profile.get("preferences") or {}

    # ALERGIAS — seguridad alimentaria, se resaltan aparte y arriba de todo.
    allergies = prefs.get("allergies") or []
    if allergies:
        lines.append(
            f"- ⚠️ ALERGIAS / INTOLERANCIAS (CRÍTICO, respetar SIEMPRE): "
            f"{', '.join(allergies)}. NUNCA sugerir ni confirmar un plato que las contenga."
        )
    if prefs.get("dietary"):
        lines.append(f"- Preferencias dietéticas: {', '.join(prefs['dietary'])}.")

    # Consumo gastronómico histórico — para referenciarlo con calidez (no recitarlo).
    consumo_hist: dict = {}
    for o in profile.get("orders") or []:
        for it in o.get("items", []):
            consumo_hist[it["name"]] = consumo_hist.get(it["name"], 0) + (it.get("qty") or 1)
    if consumo_hist:
        top = sorted(consumo_hist.items(), key=lambda kv: kv[1], reverse=True)[:4]
        lines.append("- Suele pedir en el restaurante: " + ", ".join(n for n, _ in top) + ".")

    # Si está hospedado, lo que YA consumió en esta estadía.
    active = profile.get("active_stay") or {}
    consumo_actual = active.get("consumo") or []
    if profile.get("is_staying_now") and consumo_actual:
        actual_txt = ", ".join(f"{c['qty']}x {c['name']}" for c in consumo_actual)
        lines.append(f"- En esta estadía ya consumió: {actual_txt}.")

    if prefs.get("services_used"):
        lines.append(f"- Servicios que suele usar: {', '.join(prefs['services_used'])}.")
    if prefs.get("family"):
        fam = ", ".join(m.get("name", "") for m in prefs["family"] if m.get("name"))
        if fam:
            lines.append(f"- Suele viajar con: {fam}.")
    if prefs.get("notes"):
        lines.append(f"- Notas del hotel: {prefs['notes']}")

    if not lines:
        return ""  # sin datos útiles: no inyectamos nada

    detail = "\n".join(lines)
    allergy_rule = ""
    if allergies:
        allergy_rule = (
            "\n⚠️ SEGURIDAD ALIMENTARIA: tiene alergias declaradas. JAMÁS le sugieras ni "
            "confirmes un plato que contenga esos alérgenos; ante la duda, consultá antes de recomendar."
        )
    return f"""━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🛎️ PERFIL DEL HUÉSPED — {name}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Conocés a este huésped. Usá esta información para personalizar la conversación:
{detail}

CÓMO USARLO:
✅ Saludalo por su nombre y reconocé que lo conocés ("¡Qué bueno tenerte de vuelta!").
✅ Si va a reservar, ofrecé proactivamente lo que ya sabés que prefiere
   (ej: "¿Te reservo la {profile.get('preferred_room') or 'misma habitación'} de siempre?").
✅ Si ya pidió comida antes, podés referenciarlo con calidez cuando venga al caso
   ("la última vez disfrutaste el ojo de bife, ¿querés repetir?") — sin recitar la lista.
✅ Tono cálido, de hospitalidad premium, natural — NO leas los datos como una lista.
🚫 NO suenes invasivo ni recites todo lo que sabés de golpe; usalo cuando venga al caso.{allergy_rule}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

"""


def build_lead_context_block(contact_name: str, contact_details: list[str]) -> str:
    contact_info_str = "\n- ".join(contact_details)
    return f"""━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ INFORMACIÓN DE CONTACTO YA CAPTURADA
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Ya tienes los datos de contacto de {contact_name}:
- {contact_info_str}

🚫 NO VUELVAS A PEDIR ESTOS DATOS
🚫 NO ofrezcas "coordinar para que te contacte un asesor"
🚫 NO digas "me podrías compartir tu nombre y teléfono"
🚫 NO preguntes "¿te gustaría que un asesor te contacte?"

✅ El usuario YA proporcionó sus datos
✅ Continúa ayudando con la información que necesita
✅ Responde sus preguntas directamente

Si el usuario pregunta algo, responde sin volver a solicitar contacto.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

"""


def build_whatsapp_contact_block(phone: str) -> str:
    """Bloque para WhatsApp: ya conocemos el teléfono, no hay que pedirlo de nuevo."""
    return f"""━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📱 CONTEXTO DE CANAL — WHATSAPP
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Este usuario te escribe por WhatsApp. Su número de teléfono es: {phone}

REGLAS PARA LA RESERVA Y EL CONTACTO:
1. NO le pidas el teléfono: ya lo tenés ({phone}). Es redundante pedírselo.
2. Cuando vayas a reservar, usá ese número por defecto como guest_phone, y
   OFRECELE cambiarlo de forma natural: por ejemplo, "Te registro con este mismo
   número de WhatsApp ({phone}) o preferís dejar otro para la reserva?".
3. Para completar la reserva pedí solamente el NOMBRE del huésped (y, si querés,
   el email — opcional). El teléfono ya está cubierto.
4. Si el usuario te da explícitamente otro teléfono, usá ese en su lugar.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

"""


def build_contact_request_block(main_interest: str) -> str:
    return f"""━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 SOLICITUD DE DATOS DE CONTACTO — INSTRUCCIONES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

El huésped mostró interés genuino en: {main_interest}

Ofrecé tomarle los datos de contacto AL FINAL de tu respuesta, de forma INTEGRADA y
natural — como un detalle de anfitrión, no como un formulario ni una venta.

REGLAS:
1. Respondé primero su consulta con la info relevante.
2. AL FINAL, en el mismo cierre, ofrecé (sin presionar) tomarle nombre, email y teléfono
   para hacerle seguimiento o avisarle si sale una promo o novedad para sus fechas.
3. Tono CONTINUO — no cambies de tema de golpe ni recomiences con "¡Hola!".
4. UNA SOLA VEZ — si ya lo ofreciste antes en la charla, no repitas.
5. Que suene a anfitrión genuino, no a vendedor: es un "te aviso si sale algo", no un cierre forzado.
6. 🚫 NO sugieras falta de disponibilidad ("te aviso si se libera disponibilidad"). Si ya mostraste
   habitaciones disponibles, NO corresponde este bloque: ofrecé reservar (ver el bloque de cierre).

EJEMPLO CORRECTO:
"...te conté las opciones para esas fechas. Si querés, dejame tu nombre, email y teléfono y te
aviso si sale una promo para tu estadía — así no se te escapa 😊"

EJEMPLO INCORRECTO (NO hacer):
"...tenemos la habitación King.

¡Hola! Me alegra que estés interesado. ¿Podrías compartir tu nombre, apellido, email y teléfono?"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

"""


def build_booking_nudge_block(main_interest: str) -> str:
    """Bloque de CIERRE: el huésped YA vio disponibilidad y mostró preferencia por una habitación.

    Acá NO se hace captura pasiva de lead ("te aviso si sale algo"): hay disponibilidad real y el
    huésped está listo, así que el movimiento correcto es OFRECER RESERVAR la habitación elegida.
    """
    return f"""━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🟢 MOMENTO DE CIERRE — YA HAY DISPONIBILIDAD Y EL HUÉSPED ELIGIÓ
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Ya mostraste disponibilidad real para esta estadía y el huésped mostró preferencia
({main_interest}). Está listo para avanzar: el paso correcto es OFRECER RESERVAR, no pedir datos
"para avisar".

REGLAS:
1. Respondé primero la duda que tenga (pensión, estacionamiento, etc.) con la info concreta.
2. AL CIERRE, ofrecé reservar la habitación que eligió, de forma natural y directa:
   "¿Te la reservo?" / "Si querés, te dejo la reserva lista".
3. Para confirmar la reserva pedí SOLO lo mínimo (el nombre del huésped). El resto lo maneja la
   herramienta de reserva. NO pidas un formulario de nombre+email+teléfono "para hacer seguimiento".
4. 🚫 PROHIBIDO sugerir falta de disponibilidad: NO digas "te aviso si se libera disponibilidad",
   "apenas se confirme la disponibilidad" ni nada que insinúe que NO hay lugar. SÍ hay lugar.
5. UNA sola oferta por mensaje. Tono anfitrión, sin presionar.

EJEMPLO CORRECTO:
"La Twin no incluye el estacionamiento estándar, pero con la promo Stay & Park lo tenés sin cargo.
El desayuno buffet sí está incluido. ¿Te reservo la Twin para esas fechas? Con tu nombre te la dejo
confirmada 😊"

EJEMPLO INCORRECTO (NO hacer — esto es sub-venta):
"...el desayuno está incluido. Si querés que te avise si se libera disponibilidad, dejame tu nombre,
email y teléfono."

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

"""


def build_price_objection_capture_block(main_interest: str) -> str:
    """Bloque de CIERRE cuando el lead vio precios, OBJETÓ (caro) o posterga ("lo voy a pensar").

    Acá NO corresponde insistir con reservar (ya declinó) ni la captura pasiva "te aviso si se
    libera disponibilidad" (SÍ hay lugar). El movimiento correcto es retener el lead: ofrecer
    dejarle un contacto para avisarle si sale una PROMO o novedad para sus fechas.
    """
    return f"""━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🟡 MOMENTO DE CIERRE — EL HUÉSPED VIO LOS PRECIOS Y LOS VE ALTOS / LO VA A PENSAR
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

El huésped mostró interés real en {main_interest}, vio los precios y le parecieron altos (o lo
va a pensar / se está despidiendo). NO insistas con reservar ahora (ya declinó) ni le ofrezcas
otra vez la promo si ya lo hiciste. Es el momento de RETENER el lead para el seguimiento.

REGLAS:
1. Reconocé con empatía y SIN presionar ("¡Obvio, tomate tu tiempo!").
2. AL CIERRE, ofrecé UNA sola vez, con tacto, dejarle un contacto para avisarle si sale una
   PROMO o novedad para SUS fechas:
   "Si querés, dejame tu nombre y un mail o teléfono y te aviso si sale alguna promo para esas
    fechas — así no se te escapa 😊".
3. Es un gesto de anfitrión genuino, no un cierre forzado ni un formulario. Si no quiere, cerrá
   cálido igual.
4. 🚫 NO sugieras falta de disponibilidad ("te aviso si se libera"): SÍ hay lugar. El gancho es
   la PROMO/novedad, no la disponibilidad.
5. NO recomiences con "¡Hola!" — seguí el hilo de la charla.

EJEMPLO CORRECTO:
"¡Te entiendo, tomate tu tiempo para pensarlo! Si querés, dejame tu nombre y un mail o teléfono y
te aviso si sale alguna promo para esas fechas — así no se te escapa 😊"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

"""
