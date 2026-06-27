import { useEffect, useState } from 'react'
import { Wrench, Settings2, X, ShieldCheck } from 'lucide-react'
import { listAgentSkills, updateAgentSkill } from '../../../services/api'
import { Loading, EmptyState, Badge } from '../../ui'
import { toast } from '../../toast'
import { useAdminGate } from '../../components/useAdminGate'

// Skills + políticas: capacidades gobernables del agente. Cada skill es una plantilla
// (qué parámetros existen + sus techos); el agente fija los valores. El TECHO DURO se
// hace visible en el control y, además, se recorta server-side (invariante §2.5).
export default function EmployeeSkills({ agent }) {
  const { runProtected, gateModal } = useAdminGate()
  const [skills, setSkills] = useState([])
  const [loading, setLoading] = useState(true)
  const [editing, setEditing] = useState(null)   // { skill, enabled, policy_values }

  const load = () => {
    setLoading(true)
    listAgentSkills(agent.id)
      .then(setSkills)
      .catch(() => setSkills([]))
      .finally(() => setLoading(false))
  }
  useEffect(() => { load() }, [agent.id])

  const toggle = (row) =>
    runProtected(async () => {
      await updateAgentSkill(agent.id, row.skill.id, { enabled: !row.enabled })
      toast.success(!row.enabled ? 'Skill habilitada' : 'Skill deshabilitada')
      load()
    })

  return (
    <div>
      {gateModal}

      <div className="mb-4">
        <h2 className="font-serif text-lg font-600 text-ink">Skills de {agent.name}</h2>
        <p className="mt-0.5 text-sm text-slatey">
          Capacidades que podés activar y configurar. Los límites sensibles tienen un techo
          que no se puede superar.
        </p>
      </div>

      {loading ? (
        <Loading label="Cargando skills…" />
      ) : skills.length === 0 ? (
        <EmptyState icon={Wrench} title="No hay skills disponibles" desc="La biblioteca de skills se carga al iniciar el sistema." />
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          {skills.map((row) => (
            <div key={row.skill.id} className="rounded-2xl bg-white p-4 shadow-card">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <p className="font-600 text-ink">{row.skill.name}</p>
                    <Badge tone={row.enabled ? 'green' : 'gray'}>{row.enabled ? 'Habilitada' : 'Apagada'}</Badge>
                  </div>
                  {row.skill.description && <p className="mt-1 text-sm text-slatey">{row.skill.description}</p>}
                </div>
                {/* Toggle on/off */}
                <button
                  onClick={() => toggle(row)}
                  role="switch"
                  aria-checked={row.enabled}
                  className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition ${
                    row.enabled ? 'bg-hilton-600' : 'bg-stone-300'
                  }`}
                >
                  <span className={`inline-block h-5 w-5 transform rounded-full bg-white transition ${
                    row.enabled ? 'translate-x-5' : 'translate-x-0.5'
                  }`} />
                </button>
              </div>
              <button
                onClick={() => setEditing(row)}
                className="mt-3 inline-flex items-center gap-1.5 rounded-xl bg-mist px-3 py-1.5 text-sm font-medium text-slatey hover:bg-stone-100"
              >
                <Settings2 size={14} /> Configurar
              </button>
            </div>
          ))}
        </div>
      )}

      {editing && (
        <PolicyModal
          agent={agent}
          row={editing}
          onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); load() }}
          runProtected={runProtected}
        />
      )}
    </div>
  )
}

function PolicyModal({ agent, row, onClose, onSaved, runProtected }) {
  const schema = row.skill.parameter_schema || []
  const limits = row.skill.parameter_limits || {}
  const [values, setValues] = useState(() => {
    const init = {}
    for (const p of schema) init[p.key] = row.policy_values?.[p.key] ?? p.default ?? ''
    return init
  })

  const setVal = (key, v) => setValues((prev) => ({ ...prev, [key]: v }))

  const save = () =>
    runProtected(async () => {
      const res = await updateAgentSkill(agent.id, row.skill.id, { policy_values: values })
      if (res.notes?.length) {
        // El server recortó algún valor al techo: avisamos.
        res.notes.forEach((n) => toast.info(n))
      } else {
        toast.success('Políticas guardadas')
      }
      onSaved()
    })

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center sm:items-center">
      <div className="absolute inset-0 bg-ink/40" onClick={onClose} />
      <div className="relative max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-t-3xl bg-white p-6 shadow-card-lg animate-slide-up sm:rounded-3xl">
        <header className="mb-5 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-hilton-50 text-hilton-600">
              <Wrench size={18} />
            </div>
            <h3 className="font-serif text-lg font-700 text-ink">Políticas · {row.skill.name}</h3>
          </div>
          <button onClick={onClose} aria-label="Cerrar" className="rounded-lg p-1.5 text-slatey hover:bg-mist">
            <X size={20} />
          </button>
        </header>

        <div className="space-y-4">
          {schema.map((p) => {
            const ceiling = limits[p.key]?.ceiling
            return (
              <div key={p.key}>
                <div className="mb-1 flex items-center justify-between">
                  <label className="text-sm font-medium text-ink">{p.label}</label>
                  {ceiling != null && (
                    <span className="inline-flex items-center gap-1 text-xs text-amber-700">
                      <ShieldCheck size={12} /> máx permitido: {ceiling}
                    </span>
                  )}
                </div>

                {p.type === 'bool' ? (
                  <label className="flex cursor-pointer items-center gap-2 text-sm text-slatey">
                    <input
                      type="checkbox"
                      checked={!!values[p.key]}
                      onChange={(e) => setVal(p.key, e.target.checked)}
                      className="h-4 w-4 rounded border-hilton-300 text-hilton-600 focus:ring-hilton-200"
                    />
                    Activado
                  </label>
                ) : p.type === 'number' || p.type === 'percent' ? (
                  <input
                    type="number"
                    value={values[p.key]}
                    max={ceiling != null ? ceiling : undefined}
                    onChange={(e) => {
                      let v = e.target.value === '' ? '' : Number(e.target.value)
                      // Techo duro visible: no dejar escribir por encima del máximo.
                      if (ceiling != null && v !== '' && v > ceiling) v = ceiling
                      setVal(p.key, v)
                    }}
                    className="w-full rounded-xl border border-hilton-200 px-3.5 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-hilton-100"
                  />
                ) : (
                  <input
                    type="text"
                    value={values[p.key]}
                    onChange={(e) => setVal(p.key, e.target.value)}
                    className="w-full rounded-xl border border-hilton-200 px-3.5 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-hilton-100"
                  />
                )}
              </div>
            )
          })}
        </div>

        <div className="mt-6 flex justify-end gap-2">
          <button onClick={onClose} className="rounded-xl px-4 py-2 text-sm font-medium text-slatey hover:bg-mist">
            Cancelar
          </button>
          <button onClick={save} className="rounded-xl bg-hilton-600 px-4 py-2 text-sm font-medium text-white hover:bg-hilton-700">
            Guardar
          </button>
        </div>
      </div>
    </div>
  )
}
