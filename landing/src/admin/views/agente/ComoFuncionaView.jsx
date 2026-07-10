import {
  MessageSquare, ShieldCheck, Zap, Users, Wrench, Send, Lock, Pencil, ArrowDown,
} from 'lucide-react'
import { PageHeader } from '../../ui'
import { useBusinessProfile } from '../../../hooks/useBusinessProfile'

// "Cómo funciona" (F2): el recorrido de un mensaje de principio a fin, en un solo esquema.
// Estático (sin backend). Se personaliza por cliente con useBusinessProfile (nombre del agente
// / del negocio). Leyenda transversal: ✎ lo configurás vos · ◉ así está construido.

// Marca ✎ (editable) u ◉ (solo lectura) para cada paso, con el tono del backoffice.
function Tag({ kind }) {
  const editable = kind === 'edit'
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ${
        editable ? 'bg-hilton-50 text-hilton-700' : 'bg-mist text-slatey'
      }`}
    >
      {editable ? <Pencil size={11} /> : <Lock size={11} />}
      {editable ? 'Lo configurás vos' : 'Así está construido'}
    </span>
  )
}

function Step({ icon: Icon, n, title, children, tag }) {
  return (
    <div className="relative rounded-2xl border border-hilton-100 bg-white p-4 shadow-card sm:p-5">
      <div className="flex items-start gap-3.5">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-hilton-600 text-white">
          <Icon size={18} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[11px] font-semibold uppercase tracking-wide text-slatey/60">Paso {n}</span>
            {tag && <Tag kind={tag} />}
          </div>
          <h3 className="mt-0.5 font-serif text-base font-700 text-ink">{title}</h3>
          <p className="mt-1 text-sm leading-relaxed text-slatey">{children}</p>
        </div>
      </div>
    </div>
  )
}

function Arrow() {
  return (
    <div className="flex justify-center py-1.5" aria-hidden="true">
      <ArrowDown size={18} className="text-hilton-300" />
    </div>
  )
}

export default function ComoFuncionaView() {
  const HOTEL = useBusinessProfile()
  const aura = HOTEL.agentName || HOTEL.name || 'el agente'

  return (
    <div className="mx-auto max-w-2xl">
      <PageHeader
        title="Cómo funciona"
        subtitle="El recorrido de un mensaje, de principio a fin — y qué configurás vos en cada paso."
      />

      {/* Leyenda transversal */}
      <div className="mb-5 flex flex-wrap items-center gap-3 rounded-xl bg-mist/60 px-4 py-3 text-xs text-slatey">
        <span className="font-semibold text-ink">Cómo leer este esquema:</span>
        <Tag kind="edit" />
        <span>ajustás cómo responde el empleado, dentro de sus límites.</span>
        <Tag kind="read" />
        <span>lo define el sistema y no se toca.</span>
      </div>

      <Step icon={MessageSquare} n={1} title="Entra un mensaje" tag="read">
        Un huésped escribe por el chat de la web o por WhatsApp. Da igual el canal: el mensaje
        entra por la misma puerta.
      </Step>
      <Arrow />

      <Step icon={ShieldCheck} n={2} title="Se clasifica y se protege" tag="read">
        El sistema entiende qué necesita el mensaje y lo protege: descarta intentos de manipular
        al agente y trata el contenido externo como no confiable. Recién ahí decide a quién
        derivarlo.
      </Step>
      <Arrow />

      <Step icon={Zap} n={3} title="Atajo sin IA para códigos de reserva" tag="read">
        Si el mensaje trae un código de reserva, se resuelve al instante por una vía directa, sin
        pasar por la IA. Más rápido y sin margen de error.
      </Step>
      <Arrow />

      <Step icon={Users} n={4} title="Va al empleado correcto" tag="read">
        Según lo que se necesite, el mensaje llega a <strong className="text-ink">{aura}</strong>{' '}
        (huésped: pre-venta, post-venta y charla), al <strong className="text-ink">Asesor</strong>{' '}
        (gerencia) o a <strong className="text-ink">Operaciones</strong> (incidencias). Quién
        atiende cada caso lo define el sistema.
      </Step>
      <Arrow />

      <Step icon={Pencil} n={5} title="Arma la respuesta" tag="edit">
        El empleado combina sus <em>reglas base</em> (cómo está construido) con{' '}
        <em>tu configuración</em>: la variante del flujo de venta, el entrenamiento (tono y
        política) y las skills activas. Esto es lo que ajustás vos en el legajo de cada empleado —
        siempre dentro de un tope de seguridad que no puede superar.
      </Step>
      <Arrow />

      <Step icon={Wrench} n={6} title="Usa sus herramientas" tag="read">
        Para responder de verdad, el empleado usa sus capacidades: consultar disponibilidad,
        cotizar, mostrar la carta, tomar un pedido, escalar un reclamo. Cada empleado trae las
        suyas (las ves en "Qué puede hacer", en su ficha).
      </Step>
      <Arrow />

      <Step icon={Send} n={7} title="Responde" tag="read">
        El huésped recibe la respuesta por el mismo canal por el que escribió. Todo el recorrido
        queda registrado para que puedas verlo en Conversaciones.
      </Step>

      <p className="mt-6 text-center text-xs text-slatey/70">
        Este esquema es informativo: te da el mapa completo del sistema. Lo que configurás está en
        el legajo de cada empleado, dentro de "Empleados Digitales".
      </p>
    </div>
  )
}
