import { useState, useEffect } from 'react'
import { BookOpen, Gauge, ShieldCheck } from 'lucide-react'
import KnowledgeView from './KnowledgeView'
import UsageView from '../UsageView'
import LimitsView from './LimitsView'

const SUBNAV = [
  { id: 'conocimiento', label: 'Conocimiento', icon: BookOpen },
  { id: 'consumo', label: 'Consumo IA', icon: Gauge },
  { id: 'limites', label: 'Límites y seguridad', icon: ShieldCheck },
]

// Lee el sub-segmento de "#admin/agente/<sub>".
function currentSub() {
  const h = window.location.hash.replace('#admin/', '').replace('#admin', '')
  const sub = h.split('/')[1]
  return SUBNAV.find((s) => s.id === sub)?.id || 'conocimiento'
}

export default function AgentSection() {
  const [sub, setSub] = useState(currentSub())

  useEffect(() => {
    const onHash = () => setSub(currentSub())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  const go = (id) => {
    window.location.hash = `admin/agente/${id}`
    setSub(id)
  }

  return (
    <div>
      {/* Sub-pestañas */}
      <div className="mb-6 flex flex-wrap gap-1 border-b border-hilton-100">
        {SUBNAV.map((s) => {
          const Icon = s.icon
          const active = sub === s.id
          return (
            <button
              key={s.id}
              onClick={() => go(s.id)}
              className={`-mb-px flex items-center gap-2 border-b-2 px-4 py-2.5 text-sm font-medium transition ${
                active
                  ? 'border-hilton-600 text-hilton-700'
                  : 'border-transparent text-slatey hover:text-ink'
              }`}
            >
              <Icon size={16} className={active ? 'text-hilton-600' : 'text-slatey'} />
              {s.label}
            </button>
          )
        })}
      </div>

      {sub === 'conocimiento' && <KnowledgeView />}
      {sub === 'consumo' && <UsageView />}
      {sub === 'limites' && <LimitsView />}
    </div>
  )
}
