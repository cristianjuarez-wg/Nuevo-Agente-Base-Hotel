import { useState } from 'react'
import { MessageCircle, Globe, Pencil, Power, X } from 'lucide-react'
import { updateAgent } from '../../../services/api'
import { Badge } from '../../ui'
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

export default function EmployeeIdentity({ agent, onChanged }) {
  const { runProtected, gateModal } = useAdminGate()
  const [editing, setEditing] = useState(false)

  const initial = (agent.name || '?').trim().charAt(0).toUpperCase()
  const paused = agent.status === 'paused'

  const toggleStatus = () =>
    runProtected(async () => {
      const next = paused ? 'active' : 'paused'
      const updated = await updateAgent(agent.id, { status: next })
      onChanged?.(updated)
      toast.success(next === 'active' ? 'Agente activado' : 'Agente pausado')
    })

  return (
    <div>
      {gateModal}

      {/* Cabecera tipo ficha de legajo */}
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
            <div className="mt-2 flex flex-wrap items-center gap-2">
              {(agent.channels || []).map((ch) => {
                const Icon = CHANNEL_ICON[ch] || Globe
                return (
                  <span key={ch} className="inline-flex items-center gap-1.5 rounded-full bg-mist px-2.5 py-1 text-xs text-slatey">
                    <Icon size={13} /> {ch}
                  </span>
                )
              })}
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={toggleStatus}
              className={`inline-flex items-center gap-1.5 rounded-xl px-3 py-2 text-sm font-medium transition ${
                paused ? 'bg-green-50 text-green-700 hover:bg-green-100' : 'bg-mist text-slatey hover:bg-stone-100'
              }`}
            >
              <Power size={15} /> {paused ? 'Activar' : 'Pausar'}
            </button>
            <button
              onClick={() => setEditing(true)}
              className="inline-flex items-center gap-1.5 rounded-xl bg-hilton-50 px-3 py-2 text-sm font-medium text-hilton-700 hover:bg-hilton-100"
            >
              <Pencil size={15} /> Editar
            </button>
          </div>
        </div>
      </div>

      {/* Nota: el rol es estructural (define qué hace el agente) y no se edita desde acá. */}
      <p className="mt-3 text-xs text-slatey">
        El rol es estructural y no se modifica desde el legajo. Pre-venta y post-venta son contextos del mismo agente huésped.
      </p>

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
    </div>
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
