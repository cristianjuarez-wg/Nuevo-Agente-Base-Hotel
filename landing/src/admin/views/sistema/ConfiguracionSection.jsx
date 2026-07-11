import { useState, useEffect } from 'react'
import { Briefcase, Palette, ShieldCheck, Gauge, Database, Headphones } from 'lucide-react'
import EquipoView from '../EquipoView'
import ThemesView from '../agente/ThemesView'
import LimitsView from '../agente/LimitsView'
import UsageView from '../UsageView'
import DemoView from '../agente/DemoView'
import AtencionHumanaView from './AtencionHumanaView'

// Capa Plataforma/Sistema (doc §9.2): config global del sistema, agrupada con sub-pestañas.
const SUBNAV = [
  { id: 'equipo', label: 'Equipo', icon: Briefcase },
  { id: 'atencion', label: 'Atención humana', icon: Headphones },
  { id: 'temas', label: 'Temas del chat', icon: Palette },
  { id: 'limites', label: 'Límites y seguridad', icon: ShieldCheck },
  { id: 'consumo', label: 'Consumo IA', icon: Gauge },
  { id: 'demo', label: 'Demo', icon: Database },
]

function currentSub() {
  const h = window.location.hash.replace('#admin/', '').replace('#admin', '')
  const sub = h.split('/')[1]
  return SUBNAV.find((s) => s.id === sub)?.id || 'equipo'
}

export default function ConfiguracionSection() {
  const [sub, setSub] = useState(currentSub())

  useEffect(() => {
    const onHash = () => setSub(currentSub())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  const go = (id) => {
    window.location.hash = `admin/configuracion/${id}`
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

      {sub === 'equipo' && <EquipoView />}
      {sub === 'atencion' && <AtencionHumanaView />}
      {sub === 'temas' && <ThemesView />}
      {sub === 'limites' && <LimitsView />}
      {sub === 'consumo' && <UsageView />}
      {sub === 'demo' && <DemoView />}
    </div>
  )
}
