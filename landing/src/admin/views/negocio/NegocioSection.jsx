import { useState, useEffect } from 'react'
import { Building2, BookOpen, Tag, Hotel } from 'lucide-react'
import BusinessIdentityView from './BusinessIdentityView'
import KnowledgeView from '../agente/KnowledgeView'
import PromotionsView from '../agente/PromotionsView'
import HabitacionesView from '../HabitacionesView'

// Capa Negocio (doc §9.2): recursos del hotel que el agente CONSUME (no son del agente).
// Agrupados con sub-pestañas para no inflar el sidebar.
const SUBNAV = [
  { id: 'identidad', label: 'Identidad', icon: Building2 },
  { id: 'conocimiento', label: 'Conocimiento', icon: BookOpen },
  { id: 'promociones', label: 'Promociones', icon: Tag },
  { id: 'habitaciones', label: 'Habitaciones', icon: Hotel },
]

function currentSub() {
  const h = window.location.hash.replace('#admin/', '').replace('#admin', '')
  const sub = h.split('/')[1]
  return SUBNAV.find((s) => s.id === sub)?.id || 'identidad'
}

export default function NegocioSection() {
  const [sub, setSub] = useState(currentSub())

  useEffect(() => {
    const onHash = () => setSub(currentSub())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  const go = (id) => {
    window.location.hash = `admin/negocio/${id}`
    setSub(id)
  }

  return (
    <div>
      <div className="mb-6 flex flex-wrap gap-1 border-b border-hilton-100">
        {SUBNAV.map((s) => {
          const Icon = s.icon
          const active = sub === s.id
          return (
            <button
              key={s.id}
              onClick={() => go(s.id)}
              className={`-mb-px flex items-center gap-2 border-b-2 px-4 py-2.5 text-sm font-medium transition ${
                active ? 'border-hilton-600 text-hilton-700' : 'border-transparent text-slatey hover:text-ink'
              }`}
            >
              <Icon size={16} className={active ? 'text-hilton-600' : 'text-slatey'} />
              {s.label}
            </button>
          )
        })}
      </div>

      {sub === 'identidad' && <BusinessIdentityView />}
      {sub === 'conocimiento' && <KnowledgeView />}
      {sub === 'promociones' && <PromotionsView />}
      {sub === 'habitaciones' && <HabitacionesView />}
    </div>
  )
}
