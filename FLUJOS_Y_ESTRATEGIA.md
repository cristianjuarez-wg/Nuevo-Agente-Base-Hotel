# Flujos del Agente + Estrategia de Producto

**Tipo:** documento de producto y estrategia
**Relación:** complementa `VISION_EMPLEADO_DIGITAL.md` y `CENTRO_EMPLEADO_DIGITAL.md`
**Origen:** nace al detectar que el legajo del agente no refleja (ni gobierna) el "cerebro" real de Aura
**Última actualización:** 2026-06

---

## 1. El hallazgo: el cerebro vive en código, no en el legajo

Al abrir "Empleados Digitales", las pestañas Entrenamiento y Skills se ven vacías, dando la impresión de que el agente "no tiene lógica ni rol". La realidad es la contraria: **Aura tiene un cerebro afinado y extenso, pero vive en el código, no expuesto en su legajo.**

| Pieza de lógica | Dónde vive | Tipo |
|---|---|---|
| Carácter, tono, voseo | `prompts/tool_agent_prompts.py` | Código (prompt) |
| Cuándo capturar el lead | prompt §6 **+** `lead_analyzer.py::should_request_contact` | Híbrido (prompt + reglas) |
| Qué info pedir (nombre, teléfono) | prompt | Código (prompt) |
| Clasificación de lead (caliente/tibio/frío, score) | `lead_analyzer.py::analyze_lead_intent` | Código (LLM + reglas) |
| Política de descuentos, alergias | prompt | Código (prompt) |
| Info del hotel (habitaciones, políticas, tours) | `KnowledgeEntry`/`Place` → RAG | **Dato editable** (lo único "en caliente") |

**Dos brechas reales:**
1. **El legajo no refleja lo que el agente ya es.** Parece vacío; en realidad hay ~310 líneas de prompt de pre-venta detrás.
2. **Lo que se carga en Entrenamiento/Skills no afecta al agente todavía.** Los `TrainingDocument` y `AgentSkill` se guardan en la base pero NO se inyectan al prompt ni al RAG (es "vínculo en datos", diferido a propósito).

Conclusión: el legajo es hoy una vitrina que ni muestra el cerebro real ni lo modifica. La observación que originó este documento es correcta.

---

## 2. La solución: flujos elegibles + parámetros, sin romper el cerebro

Para cada rol, el agente trae **flujos pre-definidos de fábrica** que el cliente **elige**, **parametriza** dentro de límites seguros y **activa/desactiva por etapas** — sin poder editar el motor.

**Ejemplo (pre-venta):**
- Flujos de fábrica: "Captación estándar", "Captación agresiva", "Solo informativo".
- El cliente elige uno y ajusta **perillas seguras**: desde qué score se pide el contacto, qué datos pedir, a los cuántos días se hace el seguimiento del lead.
- Puede prender/apagar etapas (ej. activar el seguimiento post-lead).
- El "cómo" (el cerebro) queda protegido: solo se exponen parámetros, no el motor.

### 2.1 Por qué es viable: es una extensión del modelo de Skills (Etapa 4)

Ya existe el patrón arquitectónico. Un "flujo" es como una skill más grande (orquesta varias etapas), pero la mecánica es idéntica:

| Skills (ya construido) | Flujos (propuesto) |
|---|---|
| Plantilla con parámetros + techos duros | Plantilla de flujo con parámetros + límites |
| El cliente activa y setea valores | El cliente **elige el flujo** y setea valores |
| `policy_values` validado/recortado server-side | Misma validación: perillas seguras, lógica protegida |
| El techo evita romper lo sensible | Los parámetros acotados evitan romper el cerebro |

Resuelve además la brecha del §1: el legajo dejaría de estar vacío — mostraría *"Aura usa el flujo Captación Estándar · seguimiento a los 5 días"*, y el cliente gobierna el comportamiento **sin** romper el motor.

### 2.2 El matiz técnico honesto

La lógica de pre-venta hoy está **partida**: parte en el prompt (lenguaje natural) y parte en código (`lead_analyzer`, con números concretos: score ≥7 = caliente, ≥2 mensajes para pedir contacto). Para que un flujo sea de verdad parametrizable, esos números tienen que **leerse de la config del flujo**, no estar hardcoded.
- **Buena noticia:** varios ya son números aislados en el código → candidatos directos a "parámetro de flujo".
- **Lo nuevo:** "seguimiento a los X días" hoy no existe — requiere un **scheduler** (disparo por tiempo), que el repo no tiene aún (el cron del check-in es externo). Es la pieza más pesada.

### 2.3 Los flujos son horizontales (reutilizables por rubro)

Un flujo de "captación + seguimiento" sirve para hotel, clínica o inmobiliaria — cambia el *contenido*, no la *forma*. Es el "acelerador horizontal + vertical" de la visión: el motor de flujos es genérico; la biblioteca de flujos y sus parámetros, por rubro.

---

## 3. Evaluación de mercado: ¿es un buen producto SaaS? (sin endulzar)

**Veredicto corto:** como SaaS **horizontal genérico, no** (te comen los gigantes). Como **SaaS vertical con flujos por industria + servicio de implementación, sí — hay un negocio real**, sobre todo en mercados que los grandes desatienden (Latam, español, pymes, WhatsApp-first).

### 3.1 A favor
- **El posicionamiento "empleado digital que rinde cuentas"** (actuar · decidir · rendir cuentas · persistir) es un diferenciador real frente al mercado, que mayormente vende **chatbots que responden** (Intercom Fin, Tidio, ManyChat, GPTs custom).
- **"Flujos elegibles + parámetros sin romper el cerebro"** es justo lo que separa un producto escalable de un proyecto a medida. Es el patrón de los SaaS que escalan.
- **El enfoque vertical** (hotel → clínica → inmobiliaria) es la jugada correcta: los horizontales están saturados; los verticales con flujos pre-armados por industria tienen espacio.

### 3.2 En contra (lo que hay que saber)
- **El mercado se llena rápido y hay gigantes:** Intercom, Salesforce (Agentforce), HubSpot, Zendesk ya empujan "agentes". Competir de frente es inviable.
- **El runtime se comoditiza** (coherente con §9 de la visión): nadie paga por "un agente que conversa".
- **El moat NO es la tecnología:** es el conocimiento del vertical + la relación + la implementación. Donde sí hay chance: ser *el* producto de empleados digitales para un vertical concreto en Latam, con flujos que entienden estacionalidad, dólar, OTAs, WhatsApp como canal rey — eso un gigante global no lo hace bien.

### 3.3 Veredicto
No será un unicornio horizontal. **Sí puede ser un producto rentable y defendible** como SaaS vertical + servicios, en un nicho que los grandes no atienden bien. La clave es no competir en "el motor", sino en "los flujos del rubro + la relación".

---

## 4. Modelo de negocio: flujos estándar vs. a medida

Estructuralmente sana para un SaaS:

| | **Flujos estándar** | **Flujos a medida** |
|---|---|---|
| Qué son | Captación, cierre, seguimiento, soporte, operaciones | Negociación con proveedor, integraciones raras, lógica muy específica |
| Cómo se cobran | **Suscripción** (parte del plan base) | **Cotización aparte** (setup/desarrollo premium) |
| Margen | Alto (se reutiliza entre clientes) | Por servicio + diferenciación |
| Quién los tiene | Todos los clientes del rubro | El cliente que lo pide y lo paga |

**Estructura resultante:** base recurrente (suscripción a flujos estándar) + servicios de alto valor (flujos custom). Es el modelo clásico de SaaS sostenible.

**Resuelve la "negociación con proveedor":** no es parte del core — es un **add-on premium que se cotiza**. (Ya se intuía: "es una función que se le da al agente"; ahora tiene su lugar en el modelo de negocio.)

**Distinción precisa:** pre-venta, soporte y operaciones tienen patrones repetibles → **estándar**. Negociación, integraciones específicas, lógica única del cliente → **a medida**.

---

## 5. Verificación técnica: los puntos de conexión (relevados en el código)

Se verificó contra el código real cómo se ensambla cada agente en cada turno. Conclusión: **la conexión del Centro al agente es barata — no es un cambio arquitectónico.**

Los tres datos que lo confirman:

1. **El Agent del SDK se crea NUEVO en cada turno** (`hotel_sdk_orchestrator.py:648`), y la lista de tools se pasa en esa construcción (`_TOOLS`, :428-433 → :651). Filtrar las tools según las skills activas del agente = una query + un filtro. Sin refactor del motor.
2. **El prompt ya se ensambla dinámicamente por turno** vía `.format()` con bloques inyectados (`{lead_block}`, `{naturalidad_block}`… en `_build_instructions` :478-496). Agregar un `{flow_block}` es el mismo patrón que ya existe.
3. **Los orquestadores ya leen la DB en cada turno** (Lead, Conversation, Contact). Leer la config de flujo/skills agrega una query a un patrón existente.

**Las perillas hardcoded que se vuelven parámetros de flujo:**

| Perilla | Valor hoy | Dónde |
|---|---|---|
| Score para pedir contacto (lead caliente) | ≥ 7 | `lead_analyzer.py:316` |
| Score lead tibio + mensajes mínimos | ≥ 6 y ≥ 4 msgs | `lead_analyzer.py:322` |
| No pedir contacto antes de N mensajes | 2 | `lead_analyzer.py:307` |
| Frases de despedida/objeción (gatillan captura) | lista fija | `lead_analyzer.py:269-283` |
| Post-venta: minutos para "sesión nueva" | 30 | `hotel_postsale_orchestrator.py:42` |
| Operaciones: tickets a listar al staff | 8 | `staff_orchestrator.py:146` |

Al conectar, estos valores actuales quedan como **defaults** → paridad total (cero cambio de comportamiento hasta que el cliente mueva una perilla).

---

## 6. Plan de deconstrucción por fases

**Modelo conceptual:** Flujo = Skill especial (`kind="flow"`, una por rol: elige variante + parámetros). Función adosable = Skill `kind="function"` (remís, etc.). Reusa `Skill`/`AgentSkill` + la validación con techos duros ya construida y probada.

**Regla rectora:** deconstruir NO es reescribir el cerebro (las ~310 líneas de prompt afinado). Es perforarlo en puntos quirúrgicos, con paridad primero y fail-open (sin config → comportamiento actual).

### Fase A — Conexión con PARIDAD (fundacional; cero cambio observable)
- Columna `kind` en `skills`; seed de 3 flow-skills con defaults = valores hardcoded actuales (tabla del §5).
- **Kill switch global:** flag único "usar configuración del Centro (sí/no)". Apagado → toda la capa nueva se ignora y el agente corre exactamente como hoy, sin deploy. Es el botón de pánico (ver §7).
- Helper `get_agent_flow_config(db, agent_id)` — **atado al agente, no al rol** (clave para escalar a N agentes). Cache corto; fail-open.
- Inyección: filtrado de tools por function-skills activas + `{flow_block}` en el prompt + umbrales de `lead_analyzer` leídos de config.
- Verificación: con defaults, respuestas idénticas (batería de mensajes antes/después); cambiar una perilla en el backoffice cambia el comportamiento. **Sin paridad verificada no se avanza a la Fase B.**

### Fase B — Variantes del flujo de venta
- 2-3 plantillas de `flow_block` (Captación estándar / agresiva / solo informativo) como variantes elegibles. La variante SOLO reemplaza el bloque de estilo comercial; carácter, seguridad y reglas de tools quedan fijos (cerebro protegido).

### Fase C — UI del legajo
- Pestaña nueva **"Flujos"** en el legajo (antes de Skills), con una card por flujo: variante activa, el bloque *"¿Qué hace este flujo?"* en lenguaje claro, y el modal de parámetros con techos visibles + "Restaurar valores de fábrica". Especificación completa y mockups en el §8. Identidad/Métricas muestran el flujo activo ("Aura · Captación estándar").

### Fase D — Primera función adosable real: reservar remís (premium)
- D1: skill `reservar_remis` (presupuesto máx con techo, proveedor → `Place` partner, datos a pedir) + tool que junta los datos del huésped.
- D2: **el motor de coordinación dual** (outbound al WhatsApp del proveedor, dos conversaciones hiladas con estado persistente, cierre de loop, bitácora) — la pieza de ingeniería pesada. Add-on premium según §4: el cliente la activa y parametriza; el calling lo construimos nosotros y se cotiza aparte.

### Fase E (futura) — Agentes nuevos sobre el motor genérico
El producto debe soportar crear agentes de roles NUEVOS — ej. un **"Entrenador de empleados del hotel"** — creados por nosotros (no por el cliente), gobernados desde su legajo.
- **Ya soportado hoy (capa de datos):** `Agent.role` es texto libre (una fila nueva = agente nuevo en el selector, con sus 4 pestañas); `Skill`/`AgentSkill` son genéricos (las reglas del flujo de entrenamiento son una flow-skill más); `TrainingDocument` por agente (el material de cursos se sube en la pestaña Entrenamiento, que ya funciona).
- **Lo que falta (capa de ejecución):** (1) la rama de ruteo en `agent_router` (su docstring lo dice: "sumar un rol nuevo = una rama acá"); (2) un **ejecutor genérico** que arme el agente desde config — las Fases A/B son el camino directo a eso; (3) **RAG por agente** (para un Entrenador es obligatorio: responde desde sus cursos).
- **Decisión pendiente para su momento:** identidad compartida — el teléfono de un empleado hoy rutea a Operaciones; si también habla con el Entrenador hay dos agentes para la misma identidad (se resuelve con número aparte, comando de cambio o canal web).
- El Entrenador es el caso ideal para validar el motor genérico: su cerebro es casi todo configuración (flujo + material + 2-3 tools genéricas).

---

## 7. Red de seguridad: por qué NO se rompe lo que hoy funciona

El miedo legítimo: "el agente hoy funciona bien; un cambio radical puede romper los flujos o hacerle perder el origen de los datos". El plan está diseñado contra eso, en cinco capas:

1. **El cerebro NO se muda — se queda en el código.** Los prompts (~310 líneas afinadas), las reglas de seguridad, el carácter y la lógica de tools quedan donde están, **versionados en git**. Lo único que pasa a leerse de la base son **números** (las perillas del §5) y, en Fase B, el bloque de estilo comercial. El RAG, el conocimiento y las tools **no cambian de origen**: nada se desconecta.
2. **Fail-open: sin config → comportamiento actual, siempre.** Los valores de hoy quedan como **defaults en el código, para siempre**. Tabla vacía, query fallida, config borrada → el agente corre exactamente como hoy. La base solo *sobreescribe* cuando hay un valor válido.
3. **Kill switch global.** Un interruptor único ("usar configuración del Centro: sí/no"). Apagado → todo el sistema ignora la capa nueva y vuelve al comportamiento actual **al instante, sin deploy**.
4. **Paridad verificada antes de avanzar.** La Fase A termina con la misma batería de mensajes antes y después: respuestas equivalentes o no se avanza.
5. **Git como red final.** Rama aparte, commit por fase, `master` intacto; cualquier fase se revierte en un comando.

**Sobre "migrar lo hardcodeado a Entrenamiento/Skills para que no se pierda": es al revés.** Lo que está en código no se puede perder (git lo versiona); una base de datos es *menos* segura para eso. El cerebro de fábrica **se espeja, no se muda**: en el backoffice aparecen (a) las perillas que sobreescriben defaults y (b) una descripción legible de qué hace cada flujo (solo lectura). **Entrenamiento queda reservado para lo que el CLIENTE agrega** (su tono, sus protocolos) — si el cerebro viviera ahí, el cliente podría romperlo, que es justo lo que se quiere evitar.

---

## 8. Cómo se verá en el backoffice (UX de la pestaña Flujos)

**Precisión de modelo primero:** Aura NO tiene los 3 flujos. Según §10.2 del documento de arquitectura ("un agente por identidad"): **Aura** tiene **2 flujos** (pre-venta y post-venta, sus dos sombreros con el huésped); el flujo de **operaciones pertenece al agente Operaciones**; el Asesor no tiene flujo configurable por ahora. Cada empleado digital, en su legajo, muestra *sus* flujos.

### 8.1 La pestaña "Flujos" del legajo (nueva, antes de Skills)

Una card por flujo asignado, con tres elementos: la **variante activa** (selector), el bloque **"¿Qué hace este flujo?"** en lenguaje claro (el "espejo del cerebro": lo escribimos nosotros al crear la plantilla; es solo lectura, no es el prompt crudo), y el botón de configuración.

```
Aura — pestaña «Flujos»

┌─ Flujo de PRE-VENTA ────────────────────────── ● Activo ─┐
│ Variante:  [ Captación estándar ▾ ]                      │
│                                                          │
│ ¿Qué hace este flujo?                                    │
│  · Atiende consultas y avanza la venta con calidez       │
│  · Pide las FECHAS antes que los datos de contacto       │
│  · Captura el lead cuando hay interés real (score ≥ 7)   │
│    o en el momento de cierre (despedida / objeción)      │
│  · Pide: nombre y teléfono; email opcional               │
│                                                          │
│ [ Configurar parámetros ]                                │
└──────────────────────────────────────────────────────────┘

┌─ Flujo de POST-VENTA ───────────────────────── ● Activo ─┐
│  · Atiende huéspedes con reserva confirmada              │
│  · Cada mensaje: ¿lo resuelvo yo o escalo a un humano?   │
│  · Considera "sesión nueva" tras 30 min de silencio      │
│ [ Configurar parámetros ]                                │
└──────────────────────────────────────────────────────────┘
```

### 8.2 El modal de parámetros (mismo patrón probado de Skills)

Labels amigables, techos visibles, validación server-side, y el botón **"Restaurar valores de fábrica"** (otra red de seguridad: siempre se puede volver al default con un click).

```
Parámetros · Flujo de pre-venta
─────────────────────────────────────────────────
Interés mínimo para pedir contacto (1-10)  [ 7 ]   máx: 9
Mensajes mínimos antes de pedir contacto   [ 2 ]
Datos a pedir       [✓] Nombre  [✓] Teléfono  [ ] Email
─────────────────────────────────────────────────
[ Restaurar valores de fábrica ]   [Cancelar] [Guardar]
```

### 8.3 Respuestas directas a las tres preguntas de producto

| Pregunta | Respuesta |
|---|---|
| ¿Se verá qué flujos tiene asignado cada agente? | Sí — en su legajo, pestaña Flujos (Aura: 2; Operaciones: 1). |
| ¿El usuario entenderá fácil qué hace cada flujo? | Sí — cada flujo trae su bloque "¿Qué hace este flujo?" en lenguaje claro, seedeado con la plantilla. |
| ¿Podrá editar las configuraciones básicas? | Sí — solo las perillas, con techos visibles y "Restaurar valores de fábrica". El cerebro no se toca. |

---

## 9. Estructura completa del backoffice del agente

```
EMPLEADOS DIGITALES (legajo por agente: Aura / Operaciones / Asesor)
│
├─ Identidad      → QUIÉN es (nombre, rol, estado, canales)
├─ Métricas       → CÓMO RINDE (desempeño, costo IA, parte de fin de día)
├─ Flujos         → CÓMO HACE su trabajo principal (variante + perillas)
├─ Skills         → QUÉ EXTRAS puede hacer (funciones adosables + políticas)
├─ Entrenamiento  → CON QUÉ CRITERIO Y VOZ trabaja (docs del cliente)
└─ Bitácora       → QUÉ HIZO y por qué (futura)

NEGOCIO (compartido — TODOS los agentes lo consumen)
├─ Conocimiento   → los HECHOS del hotel (políticas, pagos, FAQ, lugares, tours)
├─ Promociones    → la oferta comercial vigente
└─ Habitaciones   → el inventario
```

La estructura calca la **metáfora de RRHH** que vertebra el producto: Identidad = ficha personal · Flujos = el puesto y sus responsabilidades · Skills = habilidades adicionales · Entrenamiento = capacitaciones recibidas · Métricas = evaluación de desempeño · Bitácora = registro de actividad. Y **Negocio = la documentación interna de la empresa**: todos los empleados la consultan, ninguno la posee. Esa analogía es lo que hace que un gerente entienda el producto sin manual.

**Advertencia de UX:** Flujos / Skills / Entrenamiento pueden confundirse si solo se ven los nombres. Solución barata: subtítulo de una línea por pestaña ("Cómo trabaja" / "Qué más puede hacer" / "Cómo lo capacitaste").

**Regla de disciplina** para decidir dónde va cada cosa: *¿esto es un HECHO del hotel o una FORMA de trabajar?* Hecho → Negocio. Forma → el agente.

---

## 10. Entrenamiento: frontera, jerarquía anti-choque y plantillas de fábrica

### 10.1 Qué va en Entrenamiento (y no en Negocio) — ejemplos para Aura en captación

1. **Guía de manejo de objeciones** — *"Si dicen que es caro, destacá el desayuno incluido y la ubicación; nunca ofrezcas descuento de entrada."*
2. **Argumentario por tipo de huésped** — *"Familia → pileta y desayuno; pareja → vista al lago y late checkout; negocios → wifi y factura A."*
3. **Manual de tono de marca** — palabras que usamos/evitamos, cuándo tutear, emojis sí/no.
4. **Protocolo de calificación de leads del hotel** — *"Estadía larga en temporada baja vale más que un finde en alta."*
5. **Política comercial interna** — qué no prometer nunca, cuándo mencionar la promo, cuándo derivar a humano.
6. **Ejemplos de conversaciones bien resueltas** — para imitar el estilo.

**La frontera:** ninguno responde una pregunta del huésped ("¿aceptan mascotas?" → Negocio); todos moldean cómo Aura vende. *Negocio alimenta las respuestas; Entrenamiento moldea al que responde.*

### 10.2 ¿Choca con lo hardcodeado? — Solapamiento real y jerarquía que lo resuelve

| Contenido | ¿Ya está en el código? | Forma |
|---|---|---|
| Tono de marca | Sí | Genérico (carácter cálido, voseo) |
| Política de descuentos | Sí | Genérica ("herramienta de cierre") |
| Cuándo capturar lead / qué datos | Sí | Genérico |
| Objeciones específicas / argumentario / calificación propia / ejemplos | No | — |

El código tiene la versión **genérica**; el entrenamiento aporta la **específica** del hotel. Para que no choquen, **jerarquía de instrucciones de 3 niveles** (práctica estándar):

1. **Seguridad y estructura** (código, inamovible): alergias, precios server-side, no inventar, límites de dominio. **Nada lo pisa.**
2. **Estilo comercial base** (código, genérico): el piso fail-open. Aplica salvo que el entrenamiento diga otra cosa.
3. **Entrenamiento del hotel** (DB): refina y especifica. Gana sobre (2), **nunca** sobre (1).

El prompt lo declara explícito al inyectar. **No se saca nada del código:** el nivel 2 es el paracaídas — si el cliente borra su entrenamiento, Aura sigue vendiendo bien.

### 10.3 Plantillas de fábrica (pre-creadas y activas)

Los documentos de entrenamiento **vienen sembrados de fábrica** — sugeridos, visibles y editables. Resuelve tres problemas de un tiro: el *empty state* (el legajo llega con contenido real), el choque del 10.2 (las plantillas se escriben alineadas 1:1 con el prompt actual → activarlas = paridad) y la educación del cliente (ve qué tipo de documento tiene sentido subir).

Diseño:
- `TrainingDocument` gana **`category`**: `tono_marca` · `objeciones` · `argumentario` · `calificacion_leads` · `politica_comercial` · `ejemplos` (mismo patrón de categorías que Conocimiento). Una plantilla por categoría, por agente.
- Flag **`is_default`** + botón **"Restaurar plantilla de fábrica"** por documento (editás sin miedo; siempre volvés).
- Creación del cliente por **dos caminos**: formulario simple (título + categoría + texto) o **subir un documento que la IA interpreta** y propone como entrenamiento (reusa el patrón `/api/knowledge/extract` que ya funciona en Conocimiento).
- **Timing seguro:** las plantillas se siembran y se ven desde ya (sin inyección = cero riesgo); la inyección real al prompt llega con la capa de conexión, gobernada por el kill switch y la jerarquía del 10.2.
- **Cuidado de tokens:** plantillas concisas (media página máx) e inyección **selectiva por contexto** (pre-venta inyecta objeciones/argumentario; post-venta, protocolo de quejas — no todo siempre).

---

## 11. Alineación con buenas prácticas mundiales (evaluación honesta)

**Donde la arquitectura está alineada** (en algunos puntos, por encima del promedio del mercado):
- **Separación conocimiento (RAG) / comportamiento (prompt+flujos) / capacidad (tools)** — la tríada canónica del diseño de agentes, materializada en producto (Negocio / Flujos / Skills).
- **"El LLM nunca decide dinero"** — precios recalculados server-side, techos duros validados en el servidor. Práctica de oro que muchos productos en producción no cumplen.
- **Ruteo determinístico por identidad + orquestación de intención** — patrones de routing/orquestación de la guía "Building Effective Agents" (Anthropic).
- **Prompts versionados en código + parámetros en config** — principio central de "12-Factor Agents".
- **Kill switch + fail-open + paridad antes de avanzar** — *progressive delivery* con feature flags, el estándar para desplegar cambios de comportamiento sin riesgo.
- **Skills modulares con políticas por instancia** — misma dirección que Agent Skills / tools MCP / registries por tenant, con el plus de los techos duros.
- **Observabilidad por agente** (tokens, costo, tools, fuentes RAG, legajo) — AgentOps/LLMOps básico bien hecho.
- **Escalación a humano (HITL)** — estándar indiscutido; existe con takeover + analizador de escalación.
- **Jerarquía de instrucciones** (§10.2) — coherente con la práctica de *instruction hierarchy* de plataforma vs. tenant.

**Brechas conocidas respecto del estado del arte** (todas ya identificadas como fases futuras — la lista de brechas ES el roadmap):
1. **Evals automatizadas** — la brecha #1: la batería de paridad de la Fase A es la semilla correcta, pero manual; la práctica seria es una suite de regresión que corre ante cada cambio.
2. **Auditoría de cambios de config** — quién cambió qué perilla y cuándo.
3. **A/B testing de variantes de flujo** — medir con datos si "agresiva" convierte mejor que "estándar".
4. **Scheduler interno** (disparos por tiempo) y **RAG aislado por agente**.

*Nota de honestidad: evaluación basada en el conocimiento de las prácticas hasta inicios de 2026; los patrones de fondo son estables.*

---

## 12. Conclusión y camino sugerido

1. El cerebro existe pero está oculto y desconectado del legajo → hay que **reflejarlo** (mostrar lo que el agente ya hace) y, por etapas, **conectarlo** (que entrenamiento/flujos tengan efecto). La verificación del §5 confirma que la conexión es barata.
2. El vehículo correcto son **flujos elegibles + parámetros seguros**, que extienden el modelo de Skills ya construido. El plan por fases del §6 es el camino: paridad primero (Fase A), variantes después (B), UI (C), la primera función premium (D) y los agentes nuevos (E).
3. **Empezar chico:** la Fase A conecta con cero cambio de comportamiento; recién después se habilitan variantes. El seguimiento temporal (scheduler) y la biblioteca de flujos por rubro son etapas posteriores.
4. **Comercialmente:** flujos estándar por suscripción + flujos a medida cotizados aparte. El producto es vertical, no horizontal.

> En una frase: **el cliente elige cómo trabaja su empleado entre flujos probados, ajusta las perillas a su gusto, y no puede romperlo.** Eso es producto, no chatbot.
