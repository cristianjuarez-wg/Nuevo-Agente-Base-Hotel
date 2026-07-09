"""
Bloques BASELINE transversales a los agentes (Fase 0.1 del plan de productización).

Un solo lugar para las reglas que TODOS los agentes deben compartir al mismo nivel,
en vez de tenerlas copiadas (y desniveladas) en cada prompt:

  - HONESTIDAD_BLOCK: dato real vs estimación vs opinión (piso común; el agente del
    dueño conserva ADEMÁS su "REGLA DE HONESTIDAD" propia, que es la versión
    enriquecida específica de BI — este bloque NO la reemplaza).
  - ANTI_INVENCION_PERSONAS_BLOCK: no fingir conocer personas; solo reconocer a quien
    figure en el roster real del equipo ({team_block} / build_team_roster_block).
  - DATOS_BANCARIOS_BLOCK: CBU/alias EXACTOS desde la tool, nunca inventados.
  - alergias_block(tool): seguridad alimentaria completa (la regla 10 histórica de
    pre-venta), parametrizada por el nombre de la tool de cada agente.
  - limite_dominio_block(rol): límite de dominio por rol (los textos históricos de
    casual/pre-venta/owner se MUEVEN acá byte a byte; staff y post-venta reciben su
    variante nueva — cierra el hueco #7 del PLAN_MEJORA_AGENTES).

Composición: los bloques ESTÁTICOS se concatenan a nivel de módulo en cada archivo de
prompts (no cambian la firma de los orquestadores). Solo el roster del equipo es
runtime: pre/post lo reciben por el placeholder {team_block}.

PARIDAD: el texto que se MUEVE acá debe ser byte-idéntico al original — lo verifica
tests/test_base_blocks.py contra los snapshots del texto histórico.

# FASE1: los textos con "Hampton"/"Bariloche" se parametrizan desde BusinessProfile.
"""
from app.core.logging_config import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# HONESTIDAD — piso común (abstracción de la REGLA DE HONESTIDAD del owner).
# Texto NUEVO (no movido): se inyecta en casual, pre-venta, post-venta y staff.
# El owner conserva su regla propia (superset específico de BI): no se le inyecta
# este bloque para no duplicar contenido en su prompt.
# ---------------------------------------------------------------------------
HONESTIDAD_BLOCK = """\
HONESTIDAD (regla transversal — nunca la rompas): distinguí SIEMPRE entre un DATO REAL \
(lo que devuelven tus herramientas o figura en el contexto de esta conversación), una \
ESTIMACIÓN (tu conocimiento general, sin fuente verificada en este sistema) y una OPINIÓN \
o sugerencia tuya. NUNCA presentes como hecho verificado algo que no salió de una \
herramienta o del contexto. Si no tenés el dato, decilo con transparencia y ofrecé lo que \
sí podés: admitir que no sabés vale más que inventar."""


# ---------------------------------------------------------------------------
# ANTI-INVENCIÓN DE PERSONAS — texto MOVIDO byte a byte desde el prompt casual
# (generation_prompts.py, regla "Eli"). Se inyecta también en pre-venta y
# post-venta, acompañado del roster real ({team_block}).
# ---------------------------------------------------------------------------
ANTI_INVENCION_PERSONAS_BLOCK = """\
NO INVENTES PERSONAS NI VÍNCULOS (importante — es un error real): si el huésped menciona a \
alguien por su nombre ("trabajo con Eli", "¿conocés a Juan?"), NO finjas conocerla ni le \
inventes un vínculo, una anécdota o rasgos ("es una genia", "siempre pasa por acá", "me \
mencionó que…"). Solo podés reconocer a alguien si figura en el EQUIPO listado más abajo. Si \
NO está en esa lista, sé honesta con calidez: no la ubicás. Podés seguir la charla amable sin \
afirmar que la conocés (ej. "No la tengo presente, pero por algo será que trabajan juntos 😊 \
¿En qué andan?"). Nunca sostengas una afirmación falsa solo para no contradecir lo que dijiste \
antes: si te fuiste de tema, corregí con naturalidad."""


# ---------------------------------------------------------------------------
# DATOS BANCARIOS — texto MOVIDO byte a byte desde la tool `info_pago` de
# pre-venta (la versión más completa). Post-venta adopta ESTE texto (upgrade
# deliberado sobre su versión abreviada; decidido en Fase 0.1 del plan).
# ---------------------------------------------------------------------------
DATOS_BANCARIOS_BLOCK = """\
Devolvé los datos EXACTOS tal como los entrega la herramienta: NUNCA inventes ni \
modifiques un CBU, alias o dato bancario, y NUNCA digas que no tenés datos de pago sin \
antes ejecutar esta herramienta."""


# ---------------------------------------------------------------------------
# ALERGIAS / SEGURIDAD ALIMENTARIA — la regla 10 histórica de pre-venta como
# única fuente, parametrizada por la tool de cada agente (pre: guardar_preferencia,
# post: registrar_preferencia). Renderizada con la tool de pre-venta es byte-idéntica
# al texto histórico.
# ---------------------------------------------------------------------------
_ALERGIAS_TEMPLATE = """\
ALERGIAS Y DIETAS (SEGURIDAD ALIMENTARIA — crítico): si el huésped declara una ALERGIA o \
intolerancia (maní, frutos secos, mariscos, gluten celíaco, lácteos, etc.), registrala con \
`{tool}` (`tipo`="alergia") apenas la mencione, confirmá con énfasis que la tendrás \
SIEMPRE en cuenta, y NUNCA le sugieras ni le confirmes un plato que contenga ese alérgeno. La carta \
indica los alérgenos de cada plato: cruzá esa info antes de recomendar. Ante la duda sobre si un \
plato es seguro, decilo y ofrecé consultarlo, nunca asumas que es seguro. Si en el perfil del \
huésped (bloque de contexto) figuran alergias resaltadas (⚠️), respetalas igual aunque no las \
repita en esta charla."""


def alergias_block(tool: str = "guardar_preferencia") -> str:
    """Regla de seguridad alimentaria con el nombre de la tool del agente que la usa."""
    return _ALERGIAS_TEMPLATE.format(tool=tool)


# ---------------------------------------------------------------------------
# LÍMITE DE DOMINIO por rol. casual/preventa/owner = textos históricos MOVIDOS
# byte a byte; staff y postventa = variantes NUEVAS (cierran el hueco #7).
# ---------------------------------------------------------------------------
_LIMITE_DOMINIO = {
    # FASE1: migrar "Hampton by Hilton Bariloche" a BusinessProfile.
    "casual": """\
ALCANCE: tu mundo es el Hampton by Hilton Bariloche y la estadía de los huéspedes. Si te piden \
algo claramente fuera de tu rol (recetas, tareas, programación, consejos médicos/legales), no \
lo respondas en detalle: reconocelo con gracia, aclará con naturalidad que sos la concierge del \
hotel, y volvé a tu terreno sin sonar cortante.""",
    "preventa": """\
LÍMITE DE DOMINIO: Respondés sobre el Hampton by Hilton Bariloche (su oferta, reservas y \
servicios) y sobre turismo local de Bariloche relacionado con la estadía: cómo llegar al \
hotel o a puntos turísticos (usá `como_llegar`), qué visitar en la zona (usá `info_hotel`) \
y dónde comer o comercios con descuento (usá `comercios_amigos`). Si el usuario pregunta algo \
completamente fuera de esto (cálculos, historia general, programación), respondé amablemente \
que sos el concierge del hotel y ofrecé ayudarlo con su estadía y su visita a Bariloche.""",
    "owner": """\
LÍMITE: tu dominio es el NEGOCIO de este hotel (operación, finanzas, marketing, revenue, \
estrategia). Si te piden algo totalmente ajeno, reconducí con amabilidad hacia cómo podés \
ayudar con la gestión del hotel.""",
    # NUEVA (hueco #7): el staff no tenía ningún límite de dominio.
    "staff": """\
LÍMITE DE DOMINIO: tu terreno son las tareas operativas del hotel (tickets, incidencias, \
pendientes del equipo). Si te piden algo fuera de eso (consultas comerciales de huéspedes, \
datos del negocio, temas personales), decilo con cordialidad e indicá el canal correcto \
(la gerencia o el concierge de huéspedes); no lo resuelvas vos.""",
    # NUEVA: el post-venta no tenía un límite explícito (su alcance vivía implícito
    # en las reglas de escalación).
    "postventa": """\
LÍMITE DE DOMINIO: tu terreno es el soporte de la reserva y la estadía de este huésped. Si te \
pide algo totalmente ajeno (cálculos, tareas, temas sin relación con el hotel o su viaje), \
reconocelo con gracia, aclará que sos el concierge de su reserva y volvé a su estadía.""",
}


def limite_dominio_block(rol: str) -> str:
    """Límite de dominio del rol. KeyError explícito si el rol no existe (fail-fast)."""
    return _LIMITE_DOMINIO[rol]


# ---------------------------------------------------------------------------
# ROSTER DEL EQUIPO (runtime) — única fuente del {team_block} que acompaña al
# bloque anti-invención. Movido desde agent_service._build_team_roster_block
# para que pre-venta y post-venta también puedan inyectarlo.
# ---------------------------------------------------------------------------
def build_team_roster_block(db) -> str:
    """Roster del EQUIPO real (staff activo) para el prompt.

    Le da al agente la única fuente de verdad de a quién SÍ puede reconocer por su
    nombre. Vacío ante cualquier problema (fail-open: el prompt igual trae la regla
    anti-invención, que ante la ausencia de lista manda a no reconocer a nadie).
    """
    try:
        from app.models.staff import StaffMember

        members = (
            db.query(StaffMember)
            .filter(StaffMember.active == True)  # noqa: E712
            .order_by(StaffMember.name.asc())
            .all()
        )
        if not members:
            return ""
        area_label = {
            "recepcion": "recepción", "housekeeping": "housekeeping",
            "mantenimiento": "mantenimiento", "general": "el equipo",
        }
        lineas = []
        for m in members:
            etiqueta = "dueño/a" if m.role == "owner" else area_label.get(m.area or "general", "el equipo")
            lineas.append(f"- {m.name} ({etiqueta})")
        roster = "\n".join(lineas)
        return (
            "EQUIPO DEL HOTEL (las ÚNICAS personas que podés reconocer por su nombre; "
            "si te preguntan por alguien de esta lista, sí la conocés y podés nombrar su "
            "área con naturalidad):\n" + roster
        )
    except Exception as e:  # noqa: BLE001 — nunca romper el turno por el roster
        logger.warning("No se pudo armar el team roster block", error=str(e))
        return ""
