import { useState, useEffect } from 'react'
import { FileText, Gauge, GraduationCap, Wrench, ScrollText } from 'lucide-react'
import { listAgents } from '../../../services/api'
import { PageHeader, Loading } from '../../ui'
import { FilterChip } from '../../components/FilterChip'
import EmployeeIdentity from './EmployeeIdentity'
import EmployeeMetrics from './EmployeeMetrics'

// El "Centro del Empleado Digital": una vista POR AGENTE (no por función). El legajo de
// cada empleado digital. Etapa 1: pestañas Identidad y Métricas; el resto llega luego.
const SUBNAV = [
  { id: 'identidad', label: 'Identidad', icon: FileText },
  { id: 'metricas', label: 'Métricas', icon: Gauge },
  // Próximas etapas (deshabilitadas por ahora).
  { id: 'entrenamiento', label: 'Entrenamiento', icon: GraduationCap, soon: true },
  { id: 'skills', label: 'Skills', icon: Wrench, soon: true },
  { id: 'bitacora', label: 'Bitácora', icon: ScrollText, soon: true },
]

// Lee el sub-segmento de "#admin/centro/<sub>".
function currentSub() {
  const h = window.location.hash.replace('#admin/', '').replace('#admin', '')
  const sub = h.split('/')[1]
  return SUBNAV.find((s) => s.id === sub && !s.soon)?.id || 'identidad'
}

export default function EmployeeHubSection() {
  const [agents, setAgents] = useState([])
  const [agentId, setAgentId] = useState(null)
  const [sub, setSub] = useState(currentSub())
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    listAgents()
      .then((list) => {
        setAgents(list)
        setAgentId((prev) => prev ?? list[0]?.id ?? null)
      })
      .catch(() => setAgents([]))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    const onHash = () => setSub(currentSub())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  const go = (id) => {
    window.location.hash = `admin/centro/${id}`
    setSub(id)
  }

  if (loading) return <Loading label="Cargando agentes…" />

  const agent = agents.find((a) => a.id === agentId) || agents[0]

  return (
    <div>
      <PageHeader
        title="Centro del Empleado Digital"
        subtitle="El legajo de cada empleado digital: identidad, desempeño y, próximamente, entrenamiento y skills."
        right={
          <div className="flex flex-wrap items-center gap-1.5">
            {agents.map((a) => (
              <FilterChip
                key={a.id}
                active={agent?.id === a.id}
                onClick={() => setAgentId(a.id)}
                label={a.name}
              />
            ))}
          </div>
        }
      />

      {/* Sub-pestañas del legajo */}
      <div className="mb-6 flex flex-wrap gap-1 border-b border-hilton-100">
        {SUBNAV.map((s) => {
          const Icon = s.icon
          const active = sub === s.id
          return (
            <button
              key={s.id}
              onClick={() => !s.soon && go(s.id)}
              disabled={s.soon}
              title={s.soon ? 'Próximamente' : undefined}
              className={`-mb-px flex items-center gap-2 border-b-2 px-4 py-2.5 text-sm font-medium transition ${
                active
                  ? 'border-hilton-600 text-hilton-700'
                  : s.soon
                  ? 'cursor-not-allowed border-transparent text-slatey/40'
                  : 'border-transparent text-slatey hover:text-ink'
              }`}
            >
              <Icon size={16} className={active ? 'text-hilton-600' : 'text-slatey'} />
              {s.label}
              {s.soon && <span className="text-[10px] uppercase tracking-wide">pronto</span>}
            </button>
          )
        })}
      </div>

      {!agent ? (
        <p className="py-12 text-center text-sm text-slatey">No hay agentes configurados.</p>
      ) : sub === 'identidad' ? (
        <EmployeeIdentity agent={agent} onChanged={(updated) =>
          setAgents((prev) => prev.map((a) => (a.id === updated.id ? updated : a)))} />
      ) : (
        <EmployeeMetrics agent={agent} />
      )}
    </div>
  )
}
