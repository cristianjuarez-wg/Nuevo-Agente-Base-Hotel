# Centro del Empleado Digital — Documento de arquitectura

**Tipo:** módulo horizontal reutilizable (núcleo de producto)
**Relación:** complementa `VISION_EMPLEADO_DIGITAL.md` (§0, §2, §10)
**Origen:** nace en la app del hotel (Aura / Hampton), diseñado para promoverse a genérico
**Destino:** alimentar contexto a Claude Code para el desarrollo del módulo
**Última actualización:** 2026-06

---

## 0. Qué es esto en una frase

El **Centro del Empleado Digital** es el lugar del backoffice donde vive cada agente —su legajo, sus métricas, su entrenamiento y sus skills— y el modelo de datos que lo sostiene. No es una sección del hotel: es **el núcleo reutilizable de cualquier app de empleados digitales**, sea hotel, clínica, concesionaria, inmobiliaria o constructora.

> Es el componente que convierte el trabajo de "un proyecto por cliente" en "un producto con verticales". Materializa el diferencial que se vende: el *empleado* digital, no el chatbot.

---

## 1. El problema que resuelve

Hoy, todo lo relativo al agente está **desperdigado** por el backoffice:

- las métricas, repartidas entre "analíticas del negocio" y "consumo de IA";
- el entrenamiento, mezclado con el conocimiento general (RAG);
- el comportamiento, fijado en código sin un lugar donde el cliente lo gobierne.

Si el diferencial es el empleado digital, ese empleado necesita su **legajo**: un lugar único donde vive todo lo de *ese* agente —igual que RRHH tiene una carpeta por empleado. Eso es lo que falta.

Además, hay dos preguntas que hoy están fundidas y son distintas:

| Pregunta | Dónde vive |
|---|---|
| ¿Cómo va el negocio? (ocupación, ingresos) | Analíticas del negocio |
| ¿Cómo trabaja **este agente**? (qué resolvió, qué escaló, qué ahorró) | **Centro del Empleado Digital** ← nuevo |

---

## 2. Las cinco decisiones de diseño

### 2.1 Un "Centro del Empleado Digital" en el backoffice
Sección nueva y propia donde vive cada agente. Una vista **por agente**, no por función.

### 2.2 El agente como entidad de primera clase, no como rol
El agente tiene `agente_id`, nombre, estado, y **todo lo referencia a él** (tickets, conversaciones, leads, métricas). El **rol** pasa a ser un *atributo* del agente, no su identidad.

> Esta es la decisión que habilita todo lo demás: tener dos agentes del mismo rol, monitorearlos por separado y entrenarlos distinto. Si se modela `agente = rol` (un enum), nada de esto es posible sin una migración dolorosa más adelante.

**Regla práctica:** *modelá multiplicable, mostrá simple.* El modelo soporta N agentes por rol desde el día uno; la UI, al principio, expone **un agente por rol**. Cuando un vertical pida dos comerciales o un tipo nuevo, se levanta la restricción de UI — cero migración.

### 2.3 Métricas por agente, separadas de las del negocio
El legajo muestra el rendimiento *del agente*: cuánto trabajó, qué resolvió, qué escaló, qué ahorró, cuánto costó en IA. Distinto de las analíticas del negocio.

### 2.4 Entrenamiento por agente
Los documentos de aprendizaje (visión §10.2, nivel 2) se asignan a **un agente puntual**, no a un rol global. Dos agentes del mismo rol pueden estar entrenados distinto.

### 2.5 El modelo de tres capas (el corazón)

```
Agente  ──tiene asignadas──▶  Skills  ──cada una con──▶  Políticas
(entidad con legajo)         (plantillas de             (parámetros configurables,
                              capacidad)                  con valores por agente)
```

- La **Skill** define *qué parámetros existen* (ej. "negociar con proveedor": monto máximo, margen mínimo, umbral de escalación). Es la **plantilla**.
- El **Agente**, en su legajo, define *los valores* de esos parámetros para él. Es la **instancia**.
- Así, una misma skill la usan dos agentes con **políticas distintas** —uno más agresivo, otro más conservador— sin duplicar nada.

Esto es el "criterio, no script" de la visión (§2.3), pero hecho **configurable por el cliente** desde el backoffice.

> **Invariante de seguridad (desde el día uno, no como afterthought).** La Skill (plantilla) puede definir **techos duros no editables por el cliente** para parámetros sensibles (montos, márgenes, descuentos). `AgentSkill.policy_values` **nunca puede superar** ese techo: el servidor lo valida y lo recorta. Esto conecta con el principio de la visión "el precio nunca lo define el LLM / todo lo sensible pasa por humano". No es una configuración: es una regla estructural del modelo. (Ver §6 y §7.5.)

---

## 3. El "legajo" del agente — contenido de la vista

Cada agente, en su Centro, tiene:

| Pestaña | Contenido |
|---|---|
| **Identidad** | Nombre, rol asignado, estado (activo / pausado), canal(es), descripción |
| **Métricas** | Trabajo realizado, resueltos vs. escalados, ahorro generado, consumo de IA — todo *de este agente*, con corte temporal |
| **Entrenamiento** | Documentos de aprendizaje asignados a este agente (PDF/MD); tono, protocolos, políticas de marca |
| **Skills** | Skills asignadas + el panel de políticas de cada una (los valores de los parámetros para este agente) |
| **Bitácora** | Qué hizo y con qué criterio; trazabilidad (visión §8.7) |

---

## 4. Qué es horizontal y qué es vertical

La clave de la reutilización está en mantener esta frontera **explícita y disciplinada**.

| Capa | ¿Horizontal (genérico) o Vertical (del rubro)? |
|---|---|
| Modelo Agente / Skill / Política | **Horizontal** |
| Legajo, métricas por agente, entrenamiento por agente | **Horizontal** |
| El motor que ejecuta skills y aplica políticas | **Horizontal** |
| La *biblioteca* de skills disponibles | **Vertical** (cambia por rubro) |
| Los *parámetros* concretos de cada skill | **Vertical** (los define la skill del rubro) |
| Los documentos de aprendizaje | **Vertical** (los carga el cliente) |

> En una frase: **el Centro es idéntico en todos los rubros; lo que cambia es qué skills hay en la biblioteca y qué parámetros tiene cada una.** "Negociar con proveedor" en una constructora y "coordinar transfer" en un hotel son la misma *forma* (skill + políticas), distinto *contenido*.

---

## 5. Regla de construcción (lo más importante del documento)

> **Lo genérico se gana extrayendo, no anticipando.**

La tentación clásica que mata los productos genéricos es diseñar ahora el núcleo perfecto que sirva para los cinco rubros imaginados. Eso lleva a abstraer sobre casos que todavía no se conocen y produce un monstruo sobre-diseñado.

La jugada correcta:

1. **Nace en el hotel.** Se construye bien para Aura, con casos reales.
2. **Con la frontera marcada.** Desde el día uno se mantiene separado lo que es del agente (horizontal) de lo que es del hotel (vertical). Disciplina, no abstracción prematura.
3. **Se promueve a genérico cuando el segundo rubro lo confirme.** El segundo cliente es el que dice qué era *de verdad* genérico y qué solo lo parecía.

**Implicancia técnica concreta:** no construir el Centro como una *feature del hotel*. Construirlo como un **módulo independiente** —su propio modelo de datos, su propia UI— que la app del hotel *consume*, no que *contiene*. La diferencia es enorme: si está desacoplado, el día que arranque la app de la clínica, el Centro ya está hecho y solo se le cargan otras skills. Si está acoplado al hotel, se reescribe en cada rubro.

> **Visión genérica, ejecución disciplinada.** Se piensa genérico, se construye para el hotel, se extrae con el segundo caso real.

---

## 6. Boceto de modelo de datos

Esbozo orientativo (no definitivo) para Claude Code. Nombres y campos a ajustar.

```
Agent
  id (agente_id)            # PK — entidad de primera clase
  name                      # "Aura", "Comercial Norte"
  role                      # atributo, NO identidad: pre_sale | post_sale | management | staff | ...
  status                    # active | paused
  channels                  # [whatsapp, web, ...]
  created_at, ...

AgentMetric                 # métricas por agente (o vista materializada sobre eventos)
  agent_id (FK)
  period
  tasks_handled, resolved, escalated, savings_generated, ai_cost, ...

TrainingDocument            # documentos de aprendizaje por agente
  id
  agent_id (FK)             # asignado a UN agente
  skill_id (FK, nullable)   # opcional: acotado a una skill (ver §7, pregunta abierta)
  source (pdf/md/texto)
  ...

Skill                       # PLANTILLA de capacidad (horizontal)
  id
  key                       # "negotiate_supplier", "coordinate_transfer"
  name, description
  vertical                  # a qué rubro/biblioteca pertenece (o "core")
  parameter_schema          # define QUÉ parámetros existen (monto_max, margen_min, umbral_escalacion...)
  parameter_limits          # TECHOS DUROS no editables por el cliente (invariante §2.5):
                            #   p.ej. {"monto_max": {"ceiling": 50000}, "descuento": {"ceiling": 0.15}}
                            #   AgentSkill.policy_values NUNCA puede superar estos límites.
  is_active

AgentSkill                  # INSTANCIA: skill asignada a un agente con SUS valores
  id
  agent_id (FK)
  skill_id (FK)
  policy_values             # los VALORES de los parámetros para este agente
                            # VALIDADO server-side contra parameter_schema Y recortado a parameter_limits
  enabled

# Reasignación de FKs a agent_id: BAJO DEMANDA, no de entrada (ver §8).
#   HotelTicket.agent_id, Conversation.agent_id, Lead.agent_id, ...
#   Hoy se atribuye por context_type / prefijo de session_id; la FK formal
#   se agrega cuando una feature concreta la pida (ej. filtrar bandeja por agente).
```

Nota sobre la atribución: hoy lo que ocurre se puede atribuir a un agente **sin migrar el esquema**, leyendo `context_type` y el prefijo de `session_id` (que el relevamiento confirmó que existen). La FK formal a `agent_id` se agrega **cuando una feature concreta la necesite**, no de entrada (ver §8). Así se honra la regla del §5: extraer a medida que un caso real lo pide, no migrar sobre especulación.

---

## 7. Preguntas abiertas (a decidir antes de construir)

1. **Ruteo con múltiples agentes del mismo rol.** Cuando haya dos comerciales, ¿quién agarra el lead? (round-robin / por carga / por especialización). *Diferible:* mientras sea uno por rol, el ruteo es trivial. No bloquea el diseño, pero hay que tenerlo presente.
2. **Documentos de aprendizaje: ¿RAG general o índice por skill?** (visión §10.4). Riesgo: si todo va al mismo índice, el tono del protocolo de quejas se filtra en una respuesta de disponibilidad. **Enfoque por etapas** (recomendado): hoy ChromaDB indexa todo en una colección global, así que *(a)* primero se agrega el vínculo en datos —campo `skill_id` en `TrainingDocument`, que es barato—, y *(b)* después se hace que el retrieval filtre por skill, lo que requiere tocar `rag_service`. El vínculo en datos no obliga a resolver el filtrado de entrada.
4. **Versionado de skills y documentos** sin romper conversaciones en curso.

> **§7.3 (política: skill vs. agente) y §7.5 (seguridad de políticas) ya no son preguntas abiertas — se resolvieron como invariantes del modelo:** la skill define el *schema* y los *techos duros*; el agente define los *valores*, validados y recortados server-side (ver §2.5 y §6). El techo de parámetros sensibles entra desde el día uno, no como afterthought.

---

## 8. Orden de construcción sugerido

> Recordatorio: esto es la **arquitectura objetivo**, no el plan del lunes. El ejemplo de "negociar con proveedor" es el caso que *valida* que el diseño aguanta, **no la primera feature**.

> **Principio de secuencia (resuelve la tensión con §5):** se arranca por una **rebanada vertical delgada** que da valor visible con migración casi cero. La reasignación de FKs (`HotelTicket`, `Conversation`, `Lead` → `agent_id`) es una migración grande sobre un solo caso real (el hotel): hacerla *antes* de mostrar valor sería el sobre-diseño anticipado que el §5 advierte. Por eso se hace **bajo demanda**, cuando una feature la pida.

1. **Rebanada delgada primero (entidad `Agent` + legajo de métricas).**
   Crear la entidad `Agent` y dar de alta los **3 agentes que ya existen** (Aura/pre-venta, Asesor/gerencia, Operaciones/staff). Construir el legajo con métricas —incluido el "parte de fin de día"— **leyendo lo que ya es atribuible hoy** por `context_type` y prefijo de `session_id`. Valor visible en pantalla, **sin migrar FKs todavía**. Esta es la primera etapa y la prioridad explícita.

2. **Reasignación de FKs a `agent_id`: bajo demanda.**
   Recién cuando una funcionalidad concreta lo necesite (ej. filtrar la bandeja de conversaciones por agente, o tickets por agente), se agrega la FK formal para ese caso. No antes, y no todo junto.

3. **Entrenamiento por agente.** Reaprovechar la ingesta PDF/MD existente, asociada al agente. Sumar el vínculo `skill_id` en datos (§7.2, etapa a); el filtrado en retrieval queda para después.

4. **Skills como plantilla + políticas como config (panel básico).** Empezar con skills ya existentes (activar/configurar — visión §10.2 niveles 1 y 2). **El techo duro de parámetros sensibles (§2.5) entra desde acá como invariante, no después.**

5. **Caso de validación:** una skill con políticas no triviales (ej. negociación con proveedor) para probar que el modelo Skill/Política aguanta. Recién acá.

6. **Diferido:** multi-agente real por rol + reglas de ruteo (§7.1). Creación de skills nuevas por el cliente queda **fuera de alcance** (visión §10.2 nivel 3).

> En síntesis: **rebanada delgada → FKs bajo demanda → entrenamiento → skills+políticas → caso de validación → diferidos.** Se extrae el genérico a medida que un caso real lo pide.

---

## 9. Las tres capas: Negocio / Agente / Plataforma

> **Sección foundational.** Ordena qué dato vive dónde. Resuelve la pregunta de navegación del backoffice y es la base de la reutilización entre rubros. El Anexo A ya la usa ("capa Negocio", "capa Agente"); acá queda formalizada.

### 9.1 El hallazgo

**No todo lo que hoy vive en "la sección del agente" pertenece al agente.** En el backoffice actual, la pantalla dice "Base de conocimiento **del agente**", pero la cancelación, las promos o un comercio amigo no son del agente: son **del hotel**. El agente los *consume*. Hay tres naturalezas distintas mezcladas, y separarlas es lo que hace que el modelo aguante múltiples agentes y el cambio de rubro.

### 9.2 Las tres capas

| Capa | Qué contiene | Naturaleza |
|---|---|---|
| **Negocio** (del hotel/rubro) | Conocimiento (pagos, check-in, cancelación, mascotas, servicios, FAQ), lugares y comercios amigos, promociones, documentos | Recursos del negocio que **los agentes consumen**. El agente los referencia, no los posee. |
| **Agente** (identidad y comportamiento) | Nombre, rol, estado, métricas, entrenamiento, skills + políticas | **Por-agente**. Es el legajo (§3). |
| **Plataforma** (transversal) | Límites y gasto de IA, seguridad, cotización USD→ARS, temas/branding | **Config global** del sistema. Ni del negocio ni de un agente puntual. |

### 9.3 Recursos compartidos: referencia, no duplicación

Una promoción vive **una sola vez** en la capa Negocio. Que esté "del negocio" no significa que todos los agentes la usen automáticamente: una **relación** define *qué agentes pueden usarla*. Es referencia, no copia. Igual que un documento de la empresa existe una vez y varios empleados lo consultan.

> Esto resuelve la preocupación de "no debería generarse varias veces": no se genera varias veces, se **referencia**. Aplica a promos, conocimiento, lugares y documentos.

### 9.4 Conocimiento ≠ Entrenamiento (no confundir)

- **Conocimiento** = datos del negocio que el agente *consulta* (capa Negocio). Ej: la política de cancelación.
- **Entrenamiento** = *cómo se comporta* el agente (capa Agente). Ej: el tono, el protocolo de respuesta.

Son capas distintas. "Conocimiento" del backoffice actual **no** se vuelve "Entrenamiento" del legajo: el conocimiento se queda en Negocio; el entrenamiento es nuevo y vive en el Agente.

### 9.5 Horizontal / vertical aplicado a los datos

La **estructura** de las tres capas es horizontal (vale para hotel, clínica, concesionaria). Lo que cambia por rubro es el **contenido** de la capa Negocio:

| | Hotel | Clínica |
|---|---|---|
| Capa Negocio (contenido) | cancelación, comercios amigos, excursiones | obras sociales, preparación de estudios |
| Capa Agente | legajo, skills, políticas | **idéntica** |
| Capa Plataforma | límites, seguridad, cotización | **idéntica** |

### 9.6 Respuesta a la pregunta de navegación del backoffice

La sección "del agente" actual (Conocimiento, Promociones, Temas, Consumo IA, Límites, Demo) **no se reemplaza, ni convive, ni se absorbe** tal cual. Se **desarma**, y cada cosa va a su capa:

- **"Negocio"** → conocimiento, lugares, promos, documentos. (Hoy etiquetados "del agente"; pasan a "del negocio".)
- **"Agentes"** (el Centro) → lista de agentes + legajo de cada uno. El "Consumo IA" actual es Plataforma, pero su *corte por agente* aparece en el legajo como Métricas.
- **"Plataforma / Configuración"** → límites, seguridad, cotización, temas.

> El Centro se queda **solo con lo que es del agente**. Todo lo demás se reubica en la capa que le corresponde.

---

## 10. Orquestación: ruteo de identidad vs. orquestación de intención

> Resuelve cómo se decide qué agente atiende y cómo se cambia de contexto en el medio de una charla. Antes estaba implícito (el triage); acá queda explícito.

### 10.1 Dos ejes de ruteo que se confunden

1. **Ruteo de identidad** (determinístico, por teléfono/canal). Define *quién* habla: huésped / staff / gerencia → resuelve **qué agente**. Ya existe y es fijo: el teléfono de un huésped no se vuelve gerente a mitad de charla.
2. **Orquestación de intención** (interpretativo, dentro de una identidad). Define *qué necesita* esa persona ahora: pre-venta / post-venta / casual → resuelve **qué contexto** del agente. Ya existe como el triage.

### 10.2 El principio que ordena todo

> **Un agente por identidad de cara al usuario. Las distintas intenciones hacia la misma identidad son contextos del agente, no agentes separados.**

Consecuencia directa:

- **Pre-venta y post-venta NO son dos agentes.** Atienden a la misma identidad (el huésped), por el mismo canal. Son dos *contextos* del agente huésped (Aura) — dos sombreros del mismo empleado.
- **El Asesor (gerencia) y Operaciones (staff) SÍ son agentes distintos.** Son identidades distintas, frente a usuarios distintos, con permisos distintos.

Regla: *identidad distinta → agente distinto; intención distinta hacia la misma identidad → contexto, no agente.*

### 10.3 El cambio de contexto en el medio de una charla

Un huésped entra por **post-venta** (consulta su reserva) y en el medio quiere reservar otra habitación (**pre-venta**). Como son contextos del mismo agente, es un **cambio de contexto interno**: sin handoff, sin perder el hilo. Si fueran dos agentes, habría que traspasar la conversación cuidando que no se pierda contexto — frágil, para resolver un problema autoinfligido al separarlos.

**Cruce de identidad NO ocurre:** un huésped nunca pasa a hablar con gerencia. Son universos separados por diseño y por seguridad (un huésped jamás ve los números del negocio).

### 10.4 Por qué contextos y no agentes (para pre/post)

- **UX:** el huésped siente *una* relación continua, no que lo transfieren de "Aura Ventas" a "Aura Soporte".
- **Continuidad:** el cambio en el medio es gratis.
- **Métricas igual de separables:** el tag `context_type` (que ya existe) permite cortar "ventas vs. soporte" *dentro* del legajo de Aura. **No hace falta dos agentes para medir por separado.**

> **Modelá multiplicable, mostrá simple (§2.2):** la arquitectura *puede* soportar pre/post como agentes separados si un rubro lo pidiera. Pero el **default recomendado es un agente huésped con contextos**. No te armes el problema de orquestación entre agentes para algo que se resuelve mejor adentro de uno.

### 10.5 Las tres capas de ruteo (resumen)

| Capa de ruteo | Cómo decide | Resuelve | Estado |
|---|---|---|---|
| **Identidad** | Por teléfono / canal (determinístico) | Qué agente | Existe |
| **Intención** | Interpretación de la charla (triage) | Qué contexto/skill del agente | Existe |
| **Carga** | Entre N agentes del mismo rol | Cuál de los iguales | **Diferido (§7.1)** |

---

## 11. Memoria del cliente: el histórico 360° y su uso por contexto

> Dónde se contempla que el agente recuerde y use el historial del cliente (qué comió, preferencias, alergias, fechas) según el contexto que le toque.

### 11.1 El dato ya existe; el uso activo es lo que falta

El **histórico ya está en el modelo:** el `Contact` (visión 360°) consolida reservas, consumo F&B por estadía, preferencias y —clave— **alergias separadas de dietas**, persistidas vía `guardar_preferencia`. El sistema *sabe* que el huésped es alérgico al maní y qué comió cada vez.

Lo que **falta formalizar** es que el agente **use ese histórico de forma activa y distinta según el contexto**. Hoy el dato se guarda; traerlo al frente en el momento justo es comportamiento que no estaba escrito.

### 11.2 Dónde encaja (sin inventar nada nuevo)

- **El histórico vive en la capa Negocio** (§9): es un recurso del negocio —el `Contact` 360°— que el agente **consume**, no posee.
- **El cómo y el cuándo usarlo es comportamiento del agente** → **skill + política** (§2.5).

### 11.3 Dos naturalezas distintas (no confundir)

| | Salvaguarda **obligatoria** | Oportunidad **opcional** |
|---|---|---|
| Ejemplo | Recordar la alergia al maní antes de un pedido | "¿Querés revivir tus vacaciones del último invierno?" |
| Naturaleza | **Regla dura del contexto** — no negociable | **Criterio** — se usa si tiene sentido |
| Implementación | **Invariante** del contexto de pedido: chequear alergias del `Contact` y bloquear/avisar ante conflicto, antes de confirmar | **Skill con política** (ej. `reconocer_huesped_recurrente`): desde cuántos meses sin venir se activa, qué tono, si se ofrece siempre o solo si el huésped abre la puerta |
| Analogía en el modelo | Mismo nivel que "el precio nunca lo define el LLM" | Es la "anticipación" de la visión §4.3/§4.5 |

> La salvaguarda de alergias **no es una skill opcional**: es una regla obligatoria del contexto, porque si se olvida hay riesgo real. Entra como invariante, igual que los techos de políticas sensibles (§2.5).

### 11.4 Un mismo dato, tres usos según el contexto

Esto cierra con la orquestación (§10): el **mismo histórico**, leído por **contextos distintos**, se usa distinto.

| Contexto | Uso del histórico |
|---|---|
| Pre-venta | Reconexión emocional ("reviví lo del último invierno") |
| Post-venta / pedido | Salvaguarda de alergias |
| Gerencia (asesor) | Estadística agregada ("¿cuántos huéspedes recurrentes tuvimos?") |

Un solo dato (capa Negocio), tres usos según el contexto del agente. Es el modelo funcionando.

### 11.5 Es horizontal: el patrón se reutiliza en cualquier rubro

El **patrón** —histórico 360° del cliente + uso contextual por skills/reglas— es genérico. Lo que cambia por rubro es **qué hay en el histórico**:

| Rubro | Qué recuerda el histórico 360° |
|---|---|
| **Hotel** | Estadías, consumo F&B, alergias, preferencias de habitación |
| **Retail de ropa** | Compras, **talle**, marcas, estilos, devoluciones → "te llegó el talle M de la temporada pasada, ¿seguís en M?" |
| **Concesionaria** | Vehículos, services, próximos vencimientos |
| **Gastronomía** | Pedidos habituales, alergias, mesa preferida |

La **estructura** (Contact 360° + skills que lo usan por contexto) es **idéntica**; los **campos** cambian por vertical. Es, otra vez, acelerador horizontal + contenido vertical.

### 11.6 Nota de privacidad

El histórico incluye PII y a veces dato sensible (las alergias son dato de salud). Su uso debe respetar protección de datos (Ley 25.326), con consentimiento y los controles de seguridad ya previstos. La precisión importa especialmente en el uso-salvaguarda: un error de alergia no es un detalle de UX, es un riesgo.

---

## 12. Por qué esto importa estratégicamente

- Es, probablemente, **el componente horizontal más valioso** del producto: el que materializa el diferencial vendido (el empleado digital).
- Convierte cada skill bien definida en **activo reutilizable** entre clientes y entre rubros.
- Da al cliente **control y gobierno** sobre su empleado → argumento de retención y de "no es enlatado".
- Es coherente con el patrón Wigou: **acelerador horizontal** (el Centro) + **aceleradores verticales** (las bibliotecas de skills por rubro).

---

## Anexo A — Ejemplo trazado: skill de negociación con proveedor

Caso de prueba que **valida** que el modelo de tres capas aguanta un caso real complejo. (No es la primera feature: llega en el §8, paso 5. Sirve para confirmar que el diseño lo soporta sin reescribir nada.)

**Escenario:** un agente coordina con un proveedor de autos para reservarle un vehículo al huésped.

### A.1 — La capacidad no es "una cosa": son tres, en tres capas

| Pieza | Capa | ¿Existe hoy? |
|---|---|---|
| El proveedor ("AutoRent Bariloche", su WhatsApp, la tarifa preferencial) | **Negocio** | **Sí** — es un `Place` con `is_partner=true`, categoría transporte (igual que el "Traslado Aeropuerto ↔ Hotel"). No es del agente; cualquier agente habilitado lo usa. |
| La capacidad de negociar (qué sabe hacer + qué parámetros necesita) | **Agente → Skill** (plantilla) | Nuevo |
| Las políticas concretas de ESE agente (los valores) | **Agente → AgentSkill** (instancia) | Nuevo |

> El error de percepción común es mezclar las tres en un solo bloque. Separarlas es lo que hace que el modelo cierre.

### A.2 — La Skill (plantilla: define *qué parámetros existen* y los techos)

```
Skill: negociar_reserva_vehiculo
  parameter_schema:
    - presupuesto_max_por_dia (USD)
    - categoria_preferida (económico / SUV / premium)
    - proveedores_habilitados (referencia a Places partner)   ← apunta a capa Negocio
    - margen_de_negociacion (% hasta donde puede ceder)
    - umbral_escalacion (cuándo para y llama a un humano)
    - datos_a_confirmar (fechas, conductor, seguro)
  parameter_limits:                          # TECHO DURO — el cliente NO lo puede subir
    - presupuesto_max_por_dia: ceiling 100
    - requiere_humano_si: monto_total > 500
```

### A.3 — El AgentSkill (instancia: el cliente carga *los valores* en el legajo)

```
AgentSkill: (agente "Conserje") + (skill negociar_reserva_vehiculo)
  policy_values:
    - presupuesto_max_por_dia: 70            # configurado por el cliente (≤ 100, el techo)
    - categoria_preferida: económico
    - proveedores_habilitados: [AutoRent Bariloche, RentaSur]
    - margen_de_negociacion: 10%
    - umbral_escalacion: proveedor pide > 70/día o no hay stock
  enabled: true
```

Si un segundo agente "Concierge VIP" quisiera `presupuesto_max_por_dia: 120`, **el techo duro (100) lo impide** → ese caso requiere confirmación humana. El cliente configura *dentro de un corral* que define la plantilla. (Invariante §2.5.)

### A.4 — Cómo corre en vivo (tres capacidades de la visión, juntas)

1. Huésped: "necesito un auto para mañana y pasado".
2. El agente lee su `AgentSkill`, ve la skill habilitada y sus políticas. Le escribe solo al WhatsApp de AutoRent — **acción cross-frontera (visión §2.1)**: "¿Económico para el 28 y 29? Tarifa Hampton".
3. AutoRent: "USD 65/día". Está dentro del presupuesto (70) → el agente **decide cerrar solo** — **criterio, no script (§2.3)**.
   - Si decía "85/día" → supera el umbral → **no cierra, escala a humano**.
4. Como es para mañana, arrastra la tarea: hoy la agenda, mañana confirma el pickup — **persistencia multi-día (§2.5)**.
5. Todo queda en la **bitácora** del legajo.

### A.5 — Qué impacta en el modelo actual

- **Se reutiliza (no se toca):** el proveedor como `Place` partner; la infraestructura de mandar/recibir WhatsApp.
- **Es nuevo:** las tablas `Skill` y `AgentSkill`; el panel de políticas en el legajo; la orquestación de la negociación **con estado** (la conversación con el proveedor sobrevive entre mensajes y entre días).
- **NO cambia:** el conocimiento, las promos, los lugares siguen en la capa Negocio. La skill **referencia** al proveedor, no se lo apropia.

---

*Documento vivo. Arquitectura objetivo del módulo. Pensado para revisión del equipo y para alimentar contexto a Claude Code.*

---

### Nota de revisión (2026-06)

Cambios respecto de la versión anterior, a partir de la devolución del equipo:

- **§8 reescrito** — se resuelve la tensión §5/§8: el paso 1 es ahora una **rebanada vertical delgada** (entidad `Agent` + legajo de métricas leyendo `context_type`/`session_id`), con migración casi cero. La reasignación de FKs a `agent_id` pasa a ser **bajo demanda**, no "modelo completo primero".
- **§2.5 + §6** — el **techo duro de parámetros sensibles** sube de pregunta abierta a **invariante del modelo** desde el día uno (`Skill.parameter_limits`; `AgentSkill.policy_values` validado y recortado server-side).
- **§7** — §7.3 y §7.5 dejan de ser preguntas abiertas (resueltas como invariantes). §7.2 (RAG por skill) se reformula en **dos etapas**: vínculo en datos primero, filtrado en `rag_service` después.
- **Anexo A** — nuevo: ejemplo trazado de skill de negociación con proveedor (valida el modelo de tres capas con un caso real).
- **§9 nueva (Las tres capas: Negocio / Agente / Plataforma)** — separa qué dato vive en qué capa; recursos compartidos por referencia, no duplicación; respuesta a la navegación del backoffice (la sección "del agente" se desarma, no se reemplaza).
- **§10 nueva (Orquestación)** — ruteo de identidad (determinístico) vs. orquestación de intención (interpretativo). Pre-venta/post-venta = **contextos de un agente huésped, no agentes separados**. El cambio en el medio es interno. Métricas separables por `context_type`.
- **§11 nueva (Memoria del cliente)** — el histórico 360° vive en capa Negocio; su uso es comportamiento del agente. Distinción **salvaguarda obligatoria** (alergias = invariante) vs. **oportunidad opcional** (reconexión = skill+política). Mismo dato, distinto uso por contexto. Patrón horizontal (retail: talle/compras; concesionaria: services; etc.).
- **§12** — la sección estratégica se renumera (antes §9 → §11 → §12).
