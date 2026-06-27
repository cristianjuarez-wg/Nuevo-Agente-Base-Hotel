# Visión — El Empleado Digital

**Documento de visión y posicionamiento de producto**
**Autor de referencia:** Barba (Wigou)
**Caso piloto / demo:** Aura — Capa de Experiencia del Huésped (Hampton by Hilton Bariloche)
**Propósito del documento:** fijar la visión de lo que es un *empleado digital* —no un chatbot— para guiar (a) el guion de la demo y (b) la reutilización del agente base en otros rubros.
**Última actualización:** 2026-06

---

## 0. Por qué existe este documento

La demo de Aura no se construyó para venderle a *un* hotel. Se construyó para tener algo **tangible** que demuestre qué es un empleado digital de verdad, en un mercado donde casi todos se quedan en "el bot crea el lead".

Este documento separa dos planos que conviene no mezclar:

1. **La capacidad genérica** ("el empleado digital") → es el producto reutilizable. Vive en el agente base.
2. **La aplicación al rubro** ("el hotel", "la clínica", "la inmobiliaria") → son las tareas que se le asignan a ese empleado según el negocio.

Todo lo que sea capacidad del *empleado* se generaliza a otros verticales. Todo lo que sea tarea del *hotel* se reemplaza al cambiar de rubro. La regla de diseño que sostiene todo el producto es: **construir las capacidades como parte del agente base, no como features del hotel.**

---

## 1. El diagnóstico de mercado

El 95% de las soluciones de "agente IA" del mercado se quedan en un solo verbo: **conversar**. El bot atiende, responde y, en el mejor caso, captura un lead. Eso ya no impresiona a nadie y, sobre todo, no es un empleado: es un formulario que habla.

Conversar es barato. Lo difícil —y lo que define a un empleado— son otros cuatro verbos que casi nadie muestra:

> **actuar · decidir · rendir cuentas · persistir**

Si la demo exhibe estos verbos en acción, la conversación deja de ser sobre "otro chatbot" y pasa a ser sobre "un empleado que trabaja solo". Esa es la frontera competitiva.

---

## 2. Las cinco capacidades núcleo del empleado digital

Estas cinco capacidades son **del agente base**, no del hotel. Son las que hay que mostrar en la demo y las que se reutilizan en cualquier vertical.

### 2.1 Acción que cruza la frontera del negocio

El agente no se limita a *responderle al cliente*: sale a **coordinar con un tercero** para resolver.

- **En el hotel:** el huésped pide un remís al aeropuerto → Aura le escribe sola al WhatsApp de la remisería, propone horario, recibe la confirmación y le cierra el loop al huésped.
- **Por qué impacta:** rompe la idea de "esto es un chat". Ver al agente hablándole a *otro* WhatsApp es el momento que deja a la gente con la boca abierta.
- **Cómo generaliza:** inmobiliaria → coordina con el del service; clínica → con el laboratorio; logística → con el transportista; constructora → con el proveedor de materiales.

**Patrón técnico:** acción saliente (outbound) + negociación asincrónica con un tercero + cierre del loop con el solicitante. Requiere manejo de estado entre dos conversaciones paralelas.

### 2.2 Iniciativa con disparador de tiempo

Un bot **reacciona**; un empleado **arranca solo**. El agente ejecuta tareas que nadie le pidió en el momento, disparadas por tiempo o por evento.

- **En el hotel:** auditoría nocturna automática. A las 3am el agente concilia, detecta anomalías (habitación marcada ocupada sin check-in, folio sin cerrar, reserva sin pago) y a la mañana el gerente se despierta con el parte ya hecho.
- **Por qué impacta:** el mensaje implícito es brutal —*trabajó mientras todos dormían*. En la demo se muestra con el timestamp real de la madrugada.
- **Cómo generaliza:** "el turno noche que nadie tiene" aplica a cualquier rubro: cierre de caja, conciliación, alertas tempranas, follow-ups programados.

**Patrón técnico:** scheduler / cron + reglas de detección de anomalías + reporte proactivo. No depende de que el cliente escriba.

### 2.3 Criterio, no script

El agente toma una **decisión**, no sigue un árbol de respuestas. Y —clave— sabe **cuándo NO le corresponde decidir** y escala.

- **En el hotel:** un huésped escribe enojado → el agente detecta el sentimiento, baja la temperatura, ofrece una compensación *dentro de la política* y escala a humano solo si supera el umbral de criticidad.
- **Regla de oro:** la autonomía no es "hace todo solo", es "sabe qué puede resolver y qué no". Un problema de seguridad nunca lo resuelve el agente: siempre salta a humano.
- **Por qué impacta:** el criterio es lo único que un chatbot no puede fingir. Hay que **hacerlo visible en pantalla** ("esto lo resuelvo yo / esto no me corresponde"), no esconderlo en el backend.
- **Cómo generaliza:** todo rubro tiene su frontera de decisión (montos, riesgos, casos sensibles). La capacidad de discriminar y escalar es transversal.

**Patrón técnico:** análisis de escalación obligatorio antes de responder + umbrales explícitos + fallback a humano con contexto traspasado.

### 2.4 Rinde cuentas de su propio trabajo

El empleado **reporta su propia productividad**. Esta es la capacidad que nadie muestra y que más pesa en la cabeza del dueño.

- **En el hotel:** al cierre del día, el agente le manda al gerente un parte: *"Hoy atendí 47 consultas, cerré 6 reservas directas (te ahorré ~X de comisión OTA), resolví 8 tickets, escalé 2, y hay 3 leads tibios que voy a re-enganchar mañana."*
- **Por qué impacta:** reposiciona todo. Ya no es un gasto de software: es un empleado que **justifica su sueldo cada noche**. Conecta directo con el Asesor de Gerencia ya construido.
- **Cómo generaliza:** el "parte de fin de turno" funciona idéntico en cualquier vertical. Cambia qué cuenta; no cambia que rinde cuentas.

**Patrón técnico:** agregación de métricas de la jornada + traducción a lenguaje de negocio (ahorro, conversión, tickets) + envío proactivo al rol gerencia.

### 2.5 Persistencia: tareas multi-día con estado

Un bot vive en un turno; un empleado **arrastra una tarea por días**.

- **En el hotel:** el transfer al aeropuerto. Hoy lo agenda → el día antes confirma con la remisería → el día de la salida le recuerda al huésped y valida el pickup. Una sola tarea, con estado, que sobrevive entre conversaciones.
- **Por qué importa:** es justo lo que necesita el CRM para que el agente sepa qué hacer cuando se le asigna una tarea de seguimiento. Es la base del "empleado al que le delegás y se encarga".
- **Cómo generaliza:** seguimiento comercial, post-venta, recordatorios, renovaciones, cobranzas — todo es "tarea con estado que persiste". 100% transversal.

**Patrón técnico:** modelo de tarea con estado persistente + máquina de estados (agendado → confirmado → recordado → validado/cerrado) + disparadores temporales asociados a la tarea, independientes de la conversación.

---

## 3. El concepto de los dos tipos de empleado

La plataforma introduce una distinción que es parte del posicionamiento:

| | **Empleado humano** | **Empleado digital (agente)** |
|---|---|---|
| **Qué hace** | Dirige, decide lo sensible, da el toque humano | Ejecuta, registra, actúa sin supervisión constante |
| **Cómo carga datos** | Con teclado / a mano | Conversando (incluso desde un audio de WhatsApp) |
| **Disponibilidad** | Su turno | 24/7/365, no se enferma, no rota |
| **Relación** | El humano *delega* | El agente *se encarga* y *rinde cuentas* |

El humano y el agente **conviven en el mismo CRM**: una persona crea un lead y se lo *asigna al agente* para que le dé seguimiento. Para que eso funcione, las tareas/callings del agente tienen que estar bien definidas: qué hacer, con qué criterio, cuándo escalar, cuándo cerrar.

> Insight de producto: el cambio no es "reemplazar al equipo". Es **liberar al equipo de lo repetitivo** para que se dedique a lo que importa —en el hotel, la experiencia del huésped que ya está en casa.

---

## 4. La experiencia ideal del huésped (aplicación al rubro hotel)

Esta sección es la *aplicación* de las capacidades núcleo al vertical hotel. Diseña el viaje del huésped para que sea increíble, con la menor pérdida de tiempo posible: anticipar, resolver, sorprender.

### 4.1 Antes de la llegada — perfilado sin fricción
WhatsApp personalizado (no spam, inteligente) días antes. Pregunta tipo de experiencia (familia/pareja, aventura/relax), restricciones dietarias, y permite **pre-cargar preferencias**: piso, almohada, temperatura, horario de check-in. Todo conversacional.

### 4.2 Llegada — check-in express
Llega y recibe QR o PIN por WhatsApp. Entra directo a la habitación, ya ajustada a sus preferencias. Sin cola, sin recepción. El agente ya sabe quién es y qué necesita.

### 4.3 Durante la estadía — anticipación, no reacción
Acá pasa la magia: el agente **anticipa sin ser invasivo**.
- *Contexto + relevancia:* noche de lluvia y frío en Bariloche → "Vi que llueve, ¿te interesa una recomendación de spots cubiertos, o preferís quedarte con un buen vino en la habitación?".
- *Detección, no reporte:* si el huésped no aparece en el restaurante a la hora reservada, el agente pregunta si hubo cambio de planes. El problema operativo lo **detecta**, no espera a que lo reporten.
- *Resolución invisible:* si el aire está roto → ticket, asignación, resolución y validación de cierre con el huésped, sin que tenga que hacer nada más.

### 4.4 Upsells contextuales y naturales
No son ventas forzadas. Se ofrecen cuando son relevantes (el huésped pregunta qué hacer → tours, restaurante partner, spa). Y si **detecta patrones** (dos días sin salir de la habitación), ofrece algo relajante para la habitación, sin sacarlo de su zona de confort.

### 4.5 Después de la salida — checkout y memoria
Checkout automático: el agente valida que no haya nada roto, genera la factura sin intervención humana. Personaliza la salida según el tipo de viaje (resumen de gastos si fue negocios) y **recuerda al huésped recurrente** cuando vuelve.

### 4.6 El concierge invisible
Todo orquestado por un agente que **no se siente como un agente**. Parece un concierge humano que anticipa, escucha y resuelve. El cliente nunca siente fricción ni "robot".

### 4.7 Datos y decisiones (la capa del dueño)
El gerente ve en tiempo real ocupación, satisfacción (sentimiento en mensajes), qué experiencias funcionan, dónde hay fricción. Y el agente le entrega *insights*, no solo números: *"La gente que hace check-in antes de las 15h tiene 40% más de probabilidad de usar el spa."* Eso es oro para decidir.

---

## 5. Catálogo de tareas de alto impacto para la demo (hotel)

Tareas concretas que muestran al empleado digital operando de verdad. Marcadas según su valor demostrativo.

| Tarea | Capacidad que demuestra | Impacto en demo |
|---|---|---|
| Coordinar remís con la remisería (WhatsApp ↔ WhatsApp) | 2.1 Acción cross-frontera | ★★★ |
| Auditoría nocturna automática (3am) | 2.2 Iniciativa temporal | ★★★ |
| Parte de productividad de fin de día al gerente | 2.4 Rinde cuentas | ★★★ |
| Transfer al aeropuerto multi-día (agenda→confirma→recuerda→valida) | 2.5 Persistencia | ★★★ |
| Huésped enojado → baja temperatura, compensa o escala | 2.3 Criterio | ★★ |
| Ticket de mantenimiento con loop de doble validación | 2.3 + ejecución | ★★ |
| Reserva fuera de horario (sábado 2am) → cotiza y confirma | conversa + actúa | ★★ |
| Pedido al restaurante cargado al folio (room charge) | ejecución + integración | ★★ |
| Re-enganche de lead tibio con la promo vigente | 2.5 + comercial | ★★ |
| Pedido de comida a un restaurante externo → entrega a la habitación | 2.1 Acción cross-frontera | ★★★ |
| Reserva de actividad/excursión según clima y fecha | anticipación | ★★ |
| Asesor de gerencia: pregunta suelta → diagnóstico + plan + seguimiento | 2.4 + 2.5 | ★★★ |

---

## 6. Guion sugerido de la demo (orden de impacto creciente)

La demo debe **escalar** el asombro. Orden propuesto:

1. **Abrir con lo familiar pero bien hecho:** consulta fuera de horario que cotiza y reserva sola (sienta la base: "atiende y vende").
2. **Subir a la ejecución:** un reclamo se convierte en ticket, se asigna, se resuelve y se valida el cierre con el huésped (muestra que *hace*, no solo habla).
3. **Mostrar criterio en vivo:** huésped enojado, el agente decide qué resuelve y qué escala —razonamiento visible en pantalla.
4. **Cruzar la frontera (momento "wow"):** el agente le escribe a la remisería y cierra el transfer. Acá la sala se da cuenta de que no es un chat.
5. **Revelar la iniciativa:** mostrar el parte de la auditoría nocturna con timestamp de las 3am —"trabajó mientras dormían".
6. **Cerrar con el dueño:** el Asesor de Gerencia responde una pregunta de negocio, propone un plan y agenda el seguimiento. El empleado rinde cuentas.

> Nota de honestidad comercial: presentar siempre como **demo sobre datos simulados**, no como integración productiva ya conectada al PMS del hotel. La transparencia suma más de lo que resta, sobre todo frente a una marca con estándares como Hilton.

---

## 7. Reutilización en otros rubros

El agente base (las 5 capacidades) se mantiene; se reemplaza la **capa de tareas del rubro**.

| Rubro | Acción cross-frontera (2.1) | Iniciativa temporal (2.2) | Persistencia (2.5) |
|---|---|---|---|
| **Hotel** | Coordinar remís/delivery | Auditoría nocturna | Transfer multi-día |
| **Clínica / Sanatorio** | Coordinar con laboratorio/estudios | Recordatorio de turnos del día siguiente | Seguimiento post-consulta / tratamiento |
| **Inmobiliaria** | Coordinar con el service / escribano | Cierre diario de visitas | Seguimiento de operación hasta la firma |
| **Concesionaria (auto/moto)** | Coordinar con taller / repuestos | Recordatorio de service programado | Seguimiento de la venta y la post-venta |
| **Logística / Transporte** | Coordinar con transportista | Conciliación nocturna de viajes | Seguimiento de orden puerta a puerta |
| **Constructora** | Coordinar con proveedores | Control diario de asistencia/avance | Seguimiento de trámites multi-etapa |

> Estrategia de productización: las 5 capacidades núcleo son el **acelerador horizontal**. Cada rubro es un **acelerador vertical** que se monta encima. Esto es coherente con el patrón Wigou (KawaGestión automotive, TravelControl turismo): un núcleo reutilizable + verticales productizados.

---

## 8. Principios de diseño (no negociables)

1. **Construir capacidades en el agente base, no features en el rubro.** Si una capacidad solo sirve para el hotel, está mal puesta.
2. **Autonomía = saber cuándo NO decidir.** El criterio de escalación es parte del producto, no un agregado.
3. **El precio/monto nunca lo define el LLM.** El servidor recalcula siempre. (Ya implementado en restaurante; mantener como regla global.)
4. **Todo lo sensible pasa por humano.** Seguridad, salud, montos altos: escalan sí o sí.
5. **El agente rinde cuentas.** Si trabajó, lo reporta. La productividad visible es parte del valor.
6. **Transparencia en la demo.** Datos simulados se presentan como simulados.
7. **Trazabilidad completa.** Cada acción del agente queda registrada (qué hizo, con qué criterio, qué escaló).

---

## 9. Build vs. Buy y la frontera del valor

### 9.1 El runtime se está comoditizando

El "motor del agente" —el loop agéntico, el tool use, la memoria, los adaptadores de canal— está dejando de ser un diferencial. Proyectos open source (OpenClaw, LangGraph, CrewAI, AutoGPT) lo resuelven y avanzan rápido. **Competir en la capa de runtime es competir contra software gratis con cientos de miles de estrellas.** No se gana ahí.

Corolario estratégico, coherente con el posicionamiento de la propuesta comercial ("no vendemos tecnología, vendemos una metodología"):

> **No vale la pena ser dueño del motor. Vale la pena ser dueño del negocio que el motor opera.**

### 9.2 Dónde SÍ está el moat

| Capa | ¿Commodity? | ¿Moat? |
|---|---|---|
| Runtime del agente (loop, tool use, memoria, canales) | Sí, comoditizándose | No |
| Capacidades núcleo (las 5 del §2) como *patrón* | Replicable | Parcial |
| Modelado del dominio + flujos verticales | — | **Sí** |
| Cerebro Evolutivo (método + 15 años de operaciones reales) | — | **Sí** |
| Multi-tenancy, backoffice por cliente, gobernanza de datos | — | **Sí** |
| Integración a los sistemas del cliente (PMS, ERP, AFIP/ARCA) | — | **Sí** |
| Relación y confianza | — | **Sí** |

El valor que se cobra tiene que estar en las filas de abajo, no en "hice un agente que conversa".

### 9.3 Por qué NO basar el producto en OpenClaw (pero sí estudiarlo)

OpenClaw es un **asistente personal self-hosted, single-user** (un "Jarvis" para uno mismo), no una plataforma de negocio multi-tenant. Dos motivos por los que no sirve como backbone de un producto de cara al cliente:

- **Categoría equivocada.** No tiene la noción de "el cliente del hotel le habla a un agente acotado con permisos limitados". Da un agente con permisos amplios sobre la propia máquina (shell, browser, archivos). Eso es lo contrario de lo que necesita un producto que atiende a terceros.
- **Perfil de seguridad incompatible con PII de clientes.** Requiere permisos amplios y tuvo una vulnerabilidad RCE crítica (versiones previas a fines de enero 2026). Poner eso de cara a huéspedes con datos personales de por medio es un riesgo que no se asume.

La arquitectura actual de Aura —ruteo acotado por rol, guardrails, topes de gasto, precio recalculado server-side— es **más correcta** para un producto comercial que un runtime personal. No estamos atrasados: estamos resolviendo el problema bien.

---

## 10. Camino a investigar: replicar la metodología de "skills" (estilo OpenClaw) operables desde el backoffice

> **Estado: a evaluar / investigar.** No es un compromiso de build, es una línea de investigación para reforzar el agente base.

La idea no es adoptar OpenClaw, sino **replicar dos de sus patrones** que encajan exactamente con las capacidades del §2, y llevarlos a algo que el cliente pueda operar sin tocar código.

### 10.1 Qué patrones de OpenClaw vale la pena replicar

- **Skills como unidad modular.** Cada capacidad/tarea es una carpeta con un archivo de definición (tipo `SKILL.md`) que describe en lenguaje natural qué hace, cuándo se invoca y con qué límites. El LLM lo lee y decide usarlo. Esto mapea directo a nuestra "capa de tareas del rubro" (§0) y permite agregar/quitar capacidades sin redeploy.
- **Tareas proactivas / programadas.** El patrón "le doy una directiva y a la mañana está hecho" es, tal cual, nuestra **iniciativa con disparador de tiempo (§2.2)**: auditoría nocturna, parte de fin de día, recordatorios. Conviene estudiar cómo lo orquestan (scheduler + ejecución desatendida + entrega del resultado).
- **Marketplace de skills.** OpenClaw tiene un repositorio comunitario de skills. Para nosotros, el equivalente interno sería una **biblioteca de skills reutilizables por vertical** que se monta sobre el agente base.

### 10.2 La pieza nueva: skills operables desde el backoffice

Hoy el cliente ya configura **conocimiento** sin redeploy (re-ingesta instantánea al RAG). El próximo nivel es que también pueda **operar el comportamiento del agente** —sus skills— desde el backoffice. No "programar", sino **gobernar**.

Tres niveles de control, de menos a más ambicioso. Sugerencia: arrancar por los dos primeros; el tercero queda como exploración.

1. **Activar / desactivar y configurar skills existentes (recomendado, bajo riesgo).**
   El cliente prende o apaga capacidades ya construidas y ajusta sus parámetros: ¿el agente coordina remís? ¿hace upsell de spa? ¿en qué umbral escala una queja? ¿en qué horario corre la auditoría nocturna? Todo con switches y campos, no con código. Es la extensión natural del backoffice que ya existe.

2. **Reforzar skills con documentos de aprendizaje (recomendado, alto valor).**
   El cliente sube documentos que **moldean cómo** el agente ejecuta una skill: el manual de atención del hotel, el tono de marca, las políticas de compensación, el protocolo de quejas, los libros de gestión para el asesor de gerencia. No cambian *qué* hace el agente, sino *con qué criterio y voz* lo hace. Reaprovecha la ingesta de PDF/MD que ya tenemos, pero asociada a una skill, no solo al RAG general. **Esto es lo de más alto impacto y menor riesgo: el cliente "entrena" a su empleado sin tocar lógica.**

3. **Crear skills nuevas desde el backoffice (a evaluar — probablemente demasiado por ahora).**
   Que el cliente defina una tarea nueva en lenguaje natural y el sistema arme la skill. Es lo más poderoso y lo más peligroso: superficie de error, seguridad, calidad impredecible. **Recomendación: NO abrir esto al cliente todavía.** La creación de skills nuevas queda del lado de Wigou (o de Claude Code), bien revisada. Al cliente le damos *gobierno* sobre skills existentes, no *autoría* de skills nuevas.

### 10.3 Por qué este enfoque es coherente con el resto de la visión

- Respeta el **principio de autonomía controlada (§8.2)**: el cliente afina límites, no inventa comportamientos sin control.
- Convierte cada skill en **producto reutilizable** (§0): una skill bien definida + sus documentos de aprendizaje se llevan de un hotel a otro, o de hotel a clínica adaptando el documento.
- Hace tangible el concepto de **"capacitás al empleado una vez y queda"** de la propuesta comercial: ahora el cliente *ve y opera* esa capacitación desde el backoffice.

### 10.4 Preguntas abiertas para la investigación

- ¿Cómo versionar una skill y sus documentos de aprendizaje sin romper conversaciones en curso?
- ¿Qué pasa cuando dos skills compiten por la misma intención? (prioridad/ruteo)
- ¿Cómo medir si una skill funciona bien? (tasa de escalación, satisfacción, errores) → conecta con el principio de **trazabilidad (§8.7)**.
- ¿Documentos de aprendizaje por skill van al RAG general o a un índice acotado a esa skill?
- Límites de seguridad: ¿qué parámetros de una skill puede tocar el cliente y cuáles quedan bloqueados con clave de admin?

---

## 11. Próximos pasos (a definir con Barba)

- [ ] Elegir cuál de las 5 capacidades construir/pulir primero según lo que ya está a medio camino.
- [ ] Definir el modelo de "tarea con estado" para persistencia (2.5) — base del seguimiento del CRM.
- [ ] Prototipar la acción cross-frontera (2.1) con una remisería real para validar fricción de canal (WhatsApp vs. teléfono).
- [ ] Diseñar el formato del "parte de fin de día" (2.4) y su disparador.
- [ ] Armar el set de datos simulados para que el guion de demo (§6) corra de punta a punta.
- [ ] **Investigar el patrón de "skills" estilo OpenClaw (§10.1):** definición modular tipo `SKILL.md` + tareas programadas. Estudiar, no adoptar el runtime.
- [ ] **Diseñar el panel de skills en el backoffice (§10.2, nivel 1):** activar/desactivar y configurar parámetros de skills existentes.
- [ ] **Prototipar "documentos de aprendizaje por skill" (§10.2, nivel 2):** reaprovechar la ingesta PDF/MD asociándola a una skill puntual. Alto valor, bajo riesgo.
- [ ] Dejar fuera del alcance del cliente, por ahora, la creación de skills nuevas (§10.2, nivel 3).

---

## 12. Devolución: estado real vs. visión

> Sección agregada como *due diligence* técnico: separa **lo que la visión describe** de **lo que el repo ya hace**, anclado en código real (no en la aspiración del documento). Marca quick-wins y advierte el único riesgo serio. Tono equilibrado.

### 12.1 Veredicto general

Con los bloques §9 y §10, el documento pasó de "buena visión de capacidades" a **"visión + tesis estratégica defendible"**:

- El eje **conversar es barato; lo caro es actuar · decidir · rendir cuentas · persistir** es la frontera competitiva real.
- **§9 (Build vs. Buy)** nombra una decisión que el repo ya venía tomando bien: invertir en el moat (dominio, gobernanza, integración, seguridad), no en el runtime.
- **§10 (Skills gobernables)** le da hogar arquitectónico a las capacidades y las vuelve producto reutilizable.

El único riesgo transversal es de **alcance** (§12.6).

### 12.2 Estado real por capacidad (visión vs. código)

| Capacidad | Estado | Ya existe (archivos) | Último tramo que falta |
|---|---|---|---|
| **2.1 Acción cross-frontera** | Parcial | `whatsapp_service.py` manda outbound a cualquier número; `checkin_express_service.py` ya hace outbound proactivo | Hilar **dos conversaciones** (huésped ↔ proveedor) con estado compartido |
| **2.2 Iniciativa temporal** | Parcial | `routers/checkin.py` `/api/checkin/cron/tomorrow` (patrón cron listo) + estado persistente | Scheduler que dispare solo + lógica de auditoría nocturna |
| **2.3 Criterio / escalación** | Existe (no enchufado) | `escalation_analyzer.py` + takeover HITL en `conversation_control_service.py` | Conectarlo al orquestador **del hotel** + hacerlo **visible en pantalla** |
| **2.4 Rinde cuentas (parte de fin de día)** | **Falta la parte proactiva** | Asesor de Gerencia on-demand (`owner_orchestrator.py`) + `business_metrics.py` (queries listas) | El **envío proactivo** del parte. Es el 100% del valor que falta |
| **2.5 Persistencia multi-día** | Parcial | `Booking.pre_checkin` + `HotelTicket`/`TicketEvent` (máquinas de estado persistentes) | Modelo **`Task` genérico** con disparadores temporales propios |

**Lectura clave:** no se parte de cero en ninguna. Lo que cambia es el tamaño del tramo final.

### 12.3 Quick-wins (alto WOW / bajo esfuerzo)

Ordenados por relación impacto/esfuerzo, no por vistosidad:

1. **Parte de fin de día (2.4) — el mejor quick-win.** Las métricas ya están en `business_metrics.py`; falta empaquetarlas en un mensaje y dispararlas. Es lo que más pesa en la cabeza del dueño ("justifica su sueldo cada noche") y de lo más barato. Se vuelve, además, el ejemplo canónico de "skill proactiva" del §10.
2. **Enchufar el criterio (2.3).** `escalation_analyzer` ya existe y es bueno, pero está conectado solo en turismo/postsale, **no en el agente hotelero**. Conectarlo + *hacer visible en pantalla* el "esto lo resuelvo / esto no me corresponde" (hoy vive escondido en el backend, justo lo que §2.3 pide evitar).
3. **Auditoría nocturna (2.2).** Reusa el patrón cron del check-in. El timestamp de las 3am da el mensaje "trabajó mientras dormían".

El **WOW más fuerte de sala** sigue siendo **2.1 (cross-frontera)** —ver a Aura escribirle a *otro* WhatsApp— pero es el más caro: requiere estado entre dos conversaciones. Vale como objetivo, no como primer paso.

### 12.4 La pieza arquitectónica clave para reutilizar en otros rubros

El **modelo `Task` genérico (2.5)** es lo que convierte esto en "núcleo horizontal" (§0 y §7). Hoy el estado persistente existe pero está **acoplado al hotel** (`pre_checkin` vive en `Booking`; los tickets son `HotelTicket`). Para vender en clínica/inmobiliaria/concesionaria, un modelo `Task` con máquina de estados + disparadores temporales es lo que se reutiliza sin tocar.

Invertir ahí temprano **destraba 2.1, 2.2 y 2.5 a la vez**, y además sostiene las "tareas programadas" del §10.1. No es el WOW más vistoso, pero es la inversión de mayor retorno estructural.

### 12.5 Sobre los bloques nuevos §9 y §10

**§9 Build vs. Buy — coincido fuerte.** La tesis "el runtime se comoditiza; el moat está abajo" es correcta **y ya la estás ejecutando sin haberla nombrado**: precio recalculado server-side, ruteo acotado por rol, guardrails, topes de gasto. Eso es exactamente la fila "del moat" del §9.2.

- Sobre §9.3 (no basarse en OpenClaw): bien argumentado y defendible — "asistente single-user con permisos amplios sobre la máquina" es categóricamente lo opuesto a "producto que atiende a terceros con PII".
- **Agregado sugerido:** sumar la **trazabilidad por mensaje** (modelo, tokens, tools, fuentes RAG — ya existe) como evidencia concreta en la fila "multi-tenancy/gobernanza" del §9.2. Hoy aparece solo como principio en §8.7; es algo que tenés y que un runtime personal no te da.

**§10 Skills gobernables — la idea con más potencial, con dos cuidados.**

- **Cuidado 1 — RAG por skill (nivel 2) no es gratis.** Hoy la ingesta PDF/MD va a **un único índice ChromaDB global** (filtrado por `doc_source`/similitud). "Documentos asociados a *una* skill, no al RAG general" requiere **namespaces/colecciones por skill**, que **no existen hoy**. Es justo la pregunta abierta de §10.4. **Cerrar esa decisión antes de prometer el nivel 2**, porque define si es un retoque o un refactor del RAG.
- **Cuidado 2 — separar "skill como gobierno" de "skill como ejecución".** Hoy las capacidades son **tools de Python registradas por orquestador** (`hotel_tools.py`, etc.), con aislamiento por rol (parte del moat de seguridad). Conviene no mezclar:
  - **Skill como unidad de gobierno/configuración** (prender/apagar + parámetros sobre tools existentes) → **viable y de bajo riesgo, construir ya**. Es la extensión natural del backoffice.
  - **Skill como unidad de ejecución estilo OpenClaw** (carpeta `SKILL.md` que el LLM lee y decide) → **otro modelo de ejecución; dejar como investigación (§10.1)**.

  Para la demo y el nivel 1 **no hace falta tocar el motor**: alcanza un registro de skills con flags + parámetros sobre las tools que ya existen.

Coincido con el orden de riesgo de §10.2: nivel 1 y 2 sí, nivel 3 (cliente crea skills nuevas) no todavía. El propio §9 da el argumento para no meterse en el runtime de skills aún.

### 12.6 El único riesgo serio: alcance

§10 puede tentar a construir un **"motor de skills"** cuando, para la demo y el primer cliente, lo que rinde es mucho más chico:

- registro de skills con **flags + parámetros** sobre las tools actuales (nivel 1),
- el **parte proactivo** (2.4) como primera skill programada,
- **cerrar la decisión RAG-por-skill** antes de prometer el nivel 2.

No meterse en el runtime de skills estilo OpenClaw todavía. El §9 ya da el argumento: el moat no está en el motor.

### 12.7 Síntesis

| | |
|---|---|
| **Qué está muy bien** | El eje de los 4 verbos; §9 (moat) nombra lo que ya hacías bien; §10 vuelve las capacidades producto reutilizable |
| **Quick-win #1** | Parte de fin de día (2.4): métricas listas, falta el envío proactivo |
| **Inversión estructural** | Modelo `Task` genérico (2.5): destraba 2.1/2.2/2.5 y habilita otros rubros |
| **Victoria barata** | Enchufar `escalation_analyzer` en el hotel (2.3) y hacer el criterio visible |
| **Riesgo a vigilar** | Sobre-construir el "motor de skills" (§10); empezar por flags + parte proactivo |
| **Decisión a cerrar ya** | RAG global vs. RAG por skill (§10.4) — define el esfuerzo del nivel 2 |

---

*Documento vivo. Pensado para revisión del equipo y para alimentar contexto a Claude Code en el desarrollo del agente base.*
