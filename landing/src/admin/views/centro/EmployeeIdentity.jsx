import { useState, useEffect } from 'react'
import {
  MessageCircle, Globe, Pencil, Power, X, Lock, Cpu, Workflow, GraduationCap, Wrench,
  ChevronRight,
} from 'lucide-react'
import {
  updateAgent, getAgentCapabilities, listAgentSkills, listAgentTraining,
} from '../../../services/api'
import { Badge, Loading } from '../../ui'
import { toast } from '../../toast'
import { useAdminGate } from '../../components/useAdminGate'

// Etiqueta legible del rol (atributo del agente, no su identidad).
const ROLE_LABEL = {
  guest: 'Huésped (pre + post venta)',
  management: 'Gerencia',
  staff: 'Operaciones',
}
const ROLE_TONE = { guest: 'blue', management: 'amber', staff: 'green' }
const CHANNEL_ICON = { whatsapp: MessageCircle, web: Globe }
const CHANNEL_LABEL = { whatsapp: 'WhatsApp', web: 'Web' }

// Contextos por rol (para la ficha técnica). Aura cambia de contexto según la conversación.
const ROLE_CONTEXTS = {
  guest: ['Charla', 'Pre-venta', 'Post-venta'],
  management: ['Consultas de gerencia'],
  staff: ['Operaciones e incidencias'],
}
const ENGINE_LABEL = {
  sdk: 'IA con herramientas',
  completions: 'IA conversacional',
}

export default function EmployeeIdentity({ agent, go, onChanged }) {
  const { runProtected, gateModal } = useAdminGate()
  const [editing, setEditing] = useState(false)
  const [caps, setCaps] = useState(null)
  const [counts, setCounts] = useState({ skills: null, training: null })

  const initial = (agent.name || '?').trim().charAt(0).toUpperCase()
  const paused = agent.status === 'paused'

  // Capacidades (F0.2) + contadores de la zona editable. Todo lectura, sin bloquear la ficha.
  useEffect(() => {
    let alive = true
    setCaps(null)
    getAgentCapabilities(agent.id).then((d) => alive && setCaps(d)).catch(() => alive && setCaps({}))

    setCounts({ skills: null, training: null })
    Promise.all([
      listAgentSkills(agent.id).catch(() => []),
      listAgentTraining(agent.id).catch(() => []),
    ]).then(([skills, docs]) => {
      if (!alive) return
      const active = (skills || []).filter((s) => s.enabled).length
      setCounts({ skills: active, training: (docs || []).length })
    })
    return () => { alive = false }
  }, [agent.id])

  const toggleStatus = () =>
    runProtected(async () => {
      const next = paused ? 'active' : 'paused'
      const updated = await updateAgent(agent.id, { status: next })
      onChanged?.(updated)
      toast.success(next === 'active' ? 'Agente activado' : 'Agente pausado')
    })

  const contexts = ROLE_CONTEXTS[agent.role] || []

  return (
    <div className="space-y-4">
      {gateModal}

      {/* ── ZONA 1 · Así está construido (◉ solo lectura) ── */}
      <div className="rounded-2xl bg-white p-5 shadow-card sm:p-6">
        <div className="flex flex-wrap items-center gap-4">
          <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-hilton-600 font-serif text-2xl font-700 text-white">
            {initial}
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="font-serif text-xl font-700 text-ink">{agent.name}</h2>
              <Badge tone={ROLE_TONE[agent.role] || 'gray'}>{ROLE_LABEL[agent.role] || agent.role}</Badge>
              <Badge tone={paused ? 'red' : 'green'}>{paused ? 'Pausado' : 'Activo'}</Badge>
            </div>
            {agent.description && <p className="mt-1 text-sm text-slatey">{agent.description}</p>}
          </div>

          <button
            onClick={toggleStatus}
            className={`inline-flex items-center gap-1.5 rounded-xl px-3 py-2 text-sm font-medium transition ${
              paused ? 'bg-green-50 text-green-700 hover:bg-green-100' : 'bg-mist text-slatey hover:bg-stone-100'
            }`}
          >
            <Power size={15} /> {paused ? 'Activar' : 'Pausar'}
          </button>
        </div>

        {/* Ficha técnica: lo que define el sistema. Fondo tenue + candado = solo lectura, sin disculpas. */}
        <div className="mt-5 rounded-xl border border-hilton-100 bg-hilton-50/40 p-4">
          <div className="mb-3 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-slatey/70">
            <Lock size={12} /> Así está construido
          </div>
          <dl className="grid grid-cols-1 gap-x-6 gap-y-3 sm:grid-cols-2">
            <SpecRow label="Rol">{ROLE_LABEL[agent.role] || agent.role}</SpecRow>
            <SpecRow label="Contextos">
              {contexts.length ? contexts.join(' · ') : '—'}
            </SpecRow>
            <SpecRow label="Canales">
              <span className="flex flex-wrap items-center gap-2">
                {(agent.channels || []).map((ch) => {
                  const Icon = CHANNEL_ICON[ch] || Globe
                  return (
                    <span key={ch} className="inline-flex items-center gap-1 text-ink">
                      <Icon size={13} className="text-slatey" /> {CHANNEL_LABEL[ch] || ch}
                    </span>
                  )
                })}
              </span>
            </SpecRow>
            <SpecRow label="Motor">
              <span className="inline-flex items-center gap-1.5 text-ink">
                <Cpu size={13} className="text-slatey" /> {ENGINE_LABEL[caps?.engine] || 'IA con herramientas'}
              </span>
            </SpecRow>
          </dl>
          <p className="mt-3 text-xs text-slatey/80">
            {agent.role === 'guest'
              ? 'Aura es un solo empleado que cambia de contexto según la conversación. El rol lo define el sistema y no se modifica desde acá.'
              : 'El rol es estructural: define qué hace el empleado y lo fija el sistema. No se modifica desde el legajo.'}
          </p>
        </div>
      </div>

      {/* ── ZONA 2 · Qué puede hacer (◉ solo lectura, capacidades) ── */}
      <div className="rounded-2xl bg-white p-5 shadow-card sm:p-6">
        <div className="mb-3 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-slatey/70">
          <Lock size={12} /> Qué puede hacer
        </div>
        {caps === null ? (
          <Loading label="Cargando capacidades…" />
        ) : (caps.capability_groups || []).length === 0 ? (
          <p className="text-sm text-slatey">Sin capacidades declaradas.</p>
        ) : (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {caps.capability_groups.map((g) => (
              <div key={g.group} className="rounded-xl border border-hilton-100 bg-white p-3.5">
                <p className="text-sm font-semibold text-ink">{g.group}</p>
                <p className="mt-0.5 text-xs leading-relaxed text-slatey">{g.summary}</p>
              </div>
            ))}
          </div>
        )}
        <p className="mt-3 text-xs text-slatey/80">
          Estas capacidades vienen con el empleado. Para sumar una nueva, contactá al equipo técnico.
        </p>
      </div>

      {/* ── ZONA 3 · Qué configurás vos (✎ editable) ── */}
      <div className="rounded-2xl bg-white p-5 shadow-card sm:p-6">
        <div className="mb-3 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-hilton-700">
          <Pencil size={12} /> Qué configurás vos
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <ConfigCard
            icon={Workflow} title="Flujo de venta"
            state="Elegí la variante y sus perillas"
            onClick={() => go?.('flujos')}
          />
          <ConfigCard
            icon={GraduationCap} title="Tono y política"
            state={counts.training == null ? 'Entrenamiento del empleado'
              : `${counts.training} ${counts.training === 1 ? 'sección' : 'secciones'}`}
            onClick={() => go?.('entrenamiento')}
          />
          <ConfigCard
            icon={Wrench} title="Skills"
            state={counts.skills == null ? 'Con tope de seguridad'
              : `${counts.skills} ${counts.skills === 1 ? 'activa' : 'activas'} · con tope`}
            onClick={() => go?.('skills')}
          />
        </div>
        <p className="mt-3 text-xs text-slatey/80">
          Lo que ajustás acá cambia cómo responde {agent.name}, dentro de los límites que fija el
          sistema. Nunca puede pasar de ese tope.
        </p>
      </div>

      {editing && (
        <EditIdentityModal
          agent={agent}
          onClose={() => setEditing(false)}
          onSave={(payload) =>
            runProtected(async () => {
              const updated = await updateAgent(agent.id, payload)
              onChanged?.(updated)
              setEditing(false)
              toast.success('Identidad actualizada')
            })
          }
        />
      )}

      {/* Editar nombre/descripción: acción secundaria, al pie. */}
      <div className="flex justify-end">
        <button
          onClick={() => setEditing(true)}
          className="inline-flex items-center gap-1.5 rounded-xl bg-hilton-50 px-3 py-2 text-sm font-medium text-hilton-700 hover:bg-hilton-100"
        >
          <Pencil size={15} /> Editar nombre y descripción
        </button>
      </div>
    </div>
  )
}

function SpecRow({ label, children }) {
  return (
    <div>
      <dt className="text-xs text-slatey/70">{label}</dt>
      <dd className="mt-0.5 text-sm text-ink">{children}</dd>
    </div>
  )
}

function ConfigCard({ icon: Icon, title, state, onClick }) {
  return (
    <button
      onClick={onClick}
      className="group flex items-start gap-3 rounded-xl border border-hilton-200 bg-white p-3.5 text-left transition hover:border-hilton-400 hover:bg-hilton-50/40"
    >
      <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-hilton-50 text-hilton-600">
        <Icon size={16} />
      </span>
      <span className="min-w-0 flex-1">
        <span className="flex items-center justify-between gap-1">
          <span className="text-sm font-semibold text-ink">{title}</span>
          <ChevronRight size={16} className="shrink-0 text-slatey/50 transition group-hover:translate-x-0.5 group-hover:text-hilton-600" />
        </span>
        <span className="mt-0.5 block text-xs text-slatey">{state}</span>
      </span>
    </button>
  )
}

function EditIdentityModal({ agent, onClose, onSave }) {
  const [name, setName] = useState(agent.name || '')
  const [description, setDescription] = useState(agent.description || '')

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center sm:items-center">
      <div className="absolute inset-0 bg-ink/40" onClick={onClose} />
      <div className="relative max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-t-3xl bg-white p-6 shadow-card-lg animate-slide-up sm:rounded-3xl">
        <header className="mb-5 flex items-center justify-between">
          <h3 className="font-serif text-lg font-700 text-ink">Editar identidad</h3>
          <button onClick={onClose} aria-label="Cerrar" className="rounded-lg p-1.5 text-slatey hover:bg-mist">
            <X size={20} />
          </button>
        </header>

        <label className="mb-1 block text-sm font-medium text-ink">Nombre</label>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="mb-4 w-full rounded-xl border border-hilton-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-hilton-100"
        />

        <label className="mb-1 block text-sm font-medium text-ink">Descripción</label>
        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          rows={3}
          className="mb-5 w-full rounded-xl border border-hilton-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-hilton-100"
        />

        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="rounded-xl px-4 py-2 text-sm font-medium text-slatey hover:bg-mist">
            Cancelar
          </button>
          <button
            onClick={() => onSave({ name: name.trim(), description: description.trim() })}
            className="rounded-xl bg-hilton-600 px-4 py-2 text-sm font-medium text-white hover:bg-hilton-700"
          >
            Guardar
          </button>
        </div>
      </div>
    </div>
  )
}
