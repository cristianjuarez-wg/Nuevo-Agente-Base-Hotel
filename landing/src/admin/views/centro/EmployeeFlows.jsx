import { useEffect, useState } from 'react'
import { Workflow, Settings2, X, ShieldCheck, RotateCcw, AlertTriangle, Info } from 'lucide-react'
import { listAgentFlows, updateAgentSkill, getCentroConfig } from '../../../services/api'
import { Loading, EmptyState, Badge } from '../../ui'
import { toast } from '../../toast'
import { useAdminGate } from '../../components/useAdminGate'

// Pestaña "Flujos" del legajo (Fase C): el trabajo principal del agente, elegible y
// parametrizable. Cada card muestra QUÉ hace el flujo en lenguaje claro (el espejo del
// cerebro, solo lectura); el modal edita la variante y las perillas dentro de sus techos.
// Los flujos NO se apagan (solo el kill switch global): acá no hay toggles.

// Devuelve el parámetro de variante del schema (si el flujo lo tiene), y los demás.
function splitParams(schema) {
  const variante = (schema || []).find((p) => p.key === 'variante' && p.type === 'select')
  const others = (schema || []).filter((p) => p !== variante)
  return { variante, others }
}

function defaultsFromSchema(schema) {
  const out = {}
  for (const p of schema || []) if ('default' in p) out[p.key] = p.default
  return out
}

export default function EmployeeFlows({ agent }) {
  const { runProtected, gateModal } = useAdminGate()
  const [flows, setFlows] = useState([])
  const [centroOn, setCentroOn] = useState(true)
  const [loading, setLoading] = useState(true)
  const [editing, setEditing] = useState(null)   // row en edición

  const load = () => {
    setLoading(true)
    Promise.all([
      listAgentFlows(agent.id).catch(() => []),
      getCentroConfig().catch(() => ({ use_agent_config: true })),
    ])
      .then(([f, c]) => { setFlows(f); setCentroOn(!!c.use_agent_config) })
      .finally(() => setLoading(false))
  }
  useEffect(() => { load() }, [agent.id])

  if (loading) return <Loading label="Cargando flujos…" />

  return (
    <div>
      {gateModal}

      <div className="mb-4">
        <h2 className="font-serif text-lg font-600 text-ink">Flujos de {agent.name}</h2>
        <p className="mt-0.5 text-sm text-slatey">
          El trabajo principal del agente: elegí el estilo y ajustá los parámetros. Los flujos
          no se apagan; el cerebro queda protegido.
        </p>
      </div>

      {/* Aviso: la capa global está desactivada → estos ajustes no tienen efecto */}
      {!centroOn && (
        <div className="mb-4 flex items-start gap-3 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-amber-800">
          <AlertTriangle size={18} className="mt-0.5 shrink-0" />
          <p className="text-sm">
            <span className="font-semibold">La configuración de agentes está desactivada globalmente.</span>{' '}
            Estos ajustes no tienen efecto hasta reactivarla en Configuración → Límites y seguridad.
          </p>
        </div>
      )}

      {flows.length === 0 ? (
        <EmptyState
          icon={Workflow}
          title="Este agente no tiene flujos configurables"
          desc="Su comportamiento es fijo por ahora. Los flujos elegibles llegan primero a los agentes comerciales y operativos."
        />
      ) : (
        <>
          <div className="grid gap-3 lg:grid-cols-2">
            {flows.map((row) => {
              const { variante } = splitParams(row.skill.parameter_schema)
              const current = row.policy_values?.variante ?? variante?.default
              const currentOpt = variante?.options?.find((o) => o.value === current)
              return (
                <div key={row.skill.id} className="rounded-2xl bg-white p-5 shadow-card">
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex items-center gap-2">
                      <Workflow size={17} className="text-hilton-600" />
                      <p className="font-serif text-base font-600 text-ink">{row.skill.name}</p>
                    </div>
                    <Badge tone="green">Activo</Badge>
                  </div>

                  {variante && currentOpt && (
                    <p className="mt-2 text-sm">
                      <span className="text-slatey">Estilo: </span>
                      <span className="font-semibold text-hilton-700">{currentOpt.label}</span>
                    </p>
                  )}

                  {/* ¿Qué hace este flujo? — espejo del cerebro, solo lectura */}
                  <p className="mt-2 text-sm leading-relaxed text-slatey">
                    {currentOpt?.description || row.skill.description}
                  </p>

                  <button
                    onClick={() => setEditing(row)}
                    className="mt-4 inline-flex items-center gap-1.5 rounded-xl bg-hilton-50 px-3.5 py-2 text-sm font-medium text-hilton-700 hover:bg-hilton-100"
                  >
                    <Settings2 size={15} /> Configurar
                  </button>
                </div>
              )
            })}
          </div>

          <p className="mt-4 flex items-center gap-1.5 text-xs text-slatey">
            <Info size={13} /> Los cambios aplican en la próxima conversación (no afectan chats ya en curso).
          </p>
        </>
      )}

      {editing && (
        <FlowConfigModal
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

function FlowConfigModal({ agent, row, onClose, onSaved, runProtected }) {
  const schema = row.skill.parameter_schema || []
  const limits = row.skill.parameter_limits || {}
  const { variante, others } = splitParams(schema)
  const [values, setValues] = useState(() => {
    const init = {}
    for (const p of schema) init[p.key] = row.policy_values?.[p.key] ?? p.default ?? ''
    return init
  })

  const setVal = (key, v) => setValues((prev) => ({ ...prev, [key]: v }))
  const selectedOpt = variante?.options?.find((o) => o.value === values[variante?.key])

  const restore = () => {
    setValues(defaultsFromSchema(schema))
    toast.info('Valores de fábrica cargados. Guardá para aplicarlos.')
  }

  const save = () =>
    runProtected(async () => {
      const res = await updateAgentSkill(agent.id, row.skill.id, { policy_values: values })
      if (res.notes?.length) res.notes.forEach((n) => toast.info(n))
      else toast.success('Flujo actualizado')
      onSaved()
    })

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center sm:items-center">
      <div className="absolute inset-0 bg-ink/40" onClick={onClose} />
      <div className="relative max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-t-3xl bg-white p-6 shadow-card-lg animate-slide-up sm:rounded-3xl">
        <header className="mb-5 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-hilton-50 text-hilton-600">
              <Workflow size={18} />
            </div>
            <h3 className="font-serif text-lg font-700 text-ink">{row.skill.name}</h3>
          </div>
          <button onClick={onClose} aria-label="Cerrar" className="rounded-lg p-1.5 text-slatey hover:bg-mist">
            <X size={20} />
          </button>
        </header>

        <div className="space-y-4">
          {/* Selector de variante (solo si el flujo lo define en su schema) */}
          {variante && (
            <div>
              <label className="mb-1 block text-sm font-medium text-ink">{variante.label}</label>
              <select
                value={values[variante.key]}
                onChange={(e) => setVal(variante.key, e.target.value)}
                className="w-full rounded-xl border border-hilton-200 px-3.5 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-hilton-100"
              >
                {variante.options.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
              {/* Qué hace la variante elegida, en lenguaje claro */}
              {selectedOpt?.description && (
                <p className="mt-2 rounded-xl bg-mist px-3.5 py-2.5 text-sm leading-relaxed text-slatey">
                  {selectedOpt.description}
                </p>
              )}
            </div>
          )}

          {/* Perillas (con techo visible) */}
          {others.map((p) => {
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
                {p.type === 'multiselect' ? (
                  <div>
                    <div className="flex flex-wrap gap-3">
                      {(p.options || []).map((opt) => {
                        const selected = (values[p.key] || []).includes(opt)
                        return (
                          <label key={opt} className="flex cursor-pointer items-center gap-1.5 text-sm text-slatey">
                            <input
                              type="checkbox"
                              checked={selected}
                              onChange={() => {
                                const cur = values[p.key] || []
                                setVal(p.key, selected ? cur.filter((c) => c !== opt) : [...cur, opt])
                              }}
                              className="h-4 w-4 rounded border-hilton-300 text-hilton-600 focus:ring-hilton-200"
                            />
                            {opt === 'web' ? 'Chat web' : opt.charAt(0).toUpperCase() + opt.slice(1)}
                          </label>
                        )
                      })}
                    </div>
                    {(values[p.key] || []).length === 0 && (
                      <p className="mt-1.5 text-xs text-amber-700">
                        ⚠ Sin canales asignados: el agente no atenderá este flujo en ningún canal.
                      </p>
                    )}
                  </div>
                ) : p.type === 'bool' ? (
                  <label className="flex cursor-pointer items-center gap-2 text-sm text-slatey">
                    <input
                      type="checkbox"
                      checked={!!values[p.key]}
                      onChange={(e) => setVal(p.key, e.target.checked)}
                      className="h-4 w-4 rounded border-hilton-300 text-hilton-600 focus:ring-hilton-200"
                    />
                    Activado
                  </label>
                ) : (
                  <input
                    type="number"
                    value={values[p.key]}
                    max={ceiling != null ? ceiling : undefined}
                    onChange={(e) => {
                      let v = e.target.value === '' ? '' : Number(e.target.value)
                      if (ceiling != null && v !== '' && v > ceiling) v = ceiling
                      setVal(p.key, v)
                    }}
                    className="w-full rounded-xl border border-hilton-200 px-3.5 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-hilton-100"
                  />
                )}
              </div>
            )
          })}
        </div>

        <div className="mt-6 flex flex-wrap items-center justify-between gap-2">
          <button
            onClick={restore}
            className="inline-flex items-center gap-1.5 rounded-xl px-3 py-2 text-sm font-medium text-slatey hover:bg-mist"
          >
            <RotateCcw size={14} /> Restaurar valores de fábrica
          </button>
          <div className="flex gap-2">
            <button onClick={onClose} className="rounded-xl px-4 py-2 text-sm font-medium text-slatey hover:bg-mist">
              Cancelar
            </button>
            <button onClick={save} className="rounded-xl bg-hilton-600 px-4 py-2 text-sm font-medium text-white hover:bg-hilton-700">
              Guardar
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
