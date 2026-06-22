import { useState, useEffect } from 'react'
import { BookOpen, ClipboardList } from 'lucide-react'
import MenuView from './MenuView'
import OrdersView from './OrdersView'

const SUBNAV = [
  { id: 'carta', label: 'Carta', icon: BookOpen },
  { id: 'pedidos', label: 'Pedidos', icon: ClipboardList },
]

function currentSub() {
  const h = window.location.hash.replace('#admin/', '').replace('#admin', '')
  const sub = h.split('/')[1]
  return SUBNAV.find((s) => s.id === sub)?.id || 'carta'
}

export default function RestaurantSection() {
  const [sub, setSub] = useState(currentSub())

  useEffect(() => {
    const onHash = () => setSub(currentSub())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  const go = (id) => {
    window.location.hash = `admin/restaurante/${id}`
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

      {sub === 'carta' && <MenuView />}
      {sub === 'pedidos' && <OrdersView />}
    </div>
  )
}
