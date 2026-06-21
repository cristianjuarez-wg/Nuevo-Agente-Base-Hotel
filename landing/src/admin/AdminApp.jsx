import { useState, useEffect, lazy, Suspense } from 'react'
import {
  LayoutDashboard, CalendarCheck, UserPlus, LifeBuoy, Menu, X, ExternalLink, Hotel,
  Users, BarChart3, Briefcase, Bot,
} from 'lucide-react'
import DashboardView from './views/DashboardView'
import BookingsView from './views/BookingsView'
import HabitacionesView from './views/HabitacionesView'
import LeadsView from './views/LeadsView'
import PassengersView from './views/PassengersView'
import TicketsView from './views/TicketsView'
import EquipoView from './views/EquipoView'
import AsesoriaView from './views/AsesoriaView'
import { Toaster } from './toast'
import { Loading } from './ui'

// Lazy: AnalyticsView arrastra Recharts (~130 KB) y AgentSection es pesado. Se cargan
// solo cuando el usuario entra a esas secciones, aliviando el bundle inicial.
const AnalyticsView = lazy(() => import('./views/AnalyticsView'))
const AgentSection = lazy(() => import('./views/agente/AgentSection'))

const NAV = [
  { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { id: 'analiticas', label: 'Analíticas', icon: BarChart3 },
  { id: 'reservas', label: 'Reservas', icon: CalendarCheck },
  { id: 'habitaciones', label: 'Habitaciones', icon: Hotel },
  { id: 'pasajeros', label: 'Pasajeros', icon: Users },
  { id: 'leads', label: 'Leads', icon: UserPlus },
  { id: 'tickets', label: 'Soporte', icon: LifeBuoy },
  { id: 'equipo', label: 'Equipo', icon: Briefcase },
  { id: 'agente', label: 'Pre-Pos Venta', icon: Bot },
  { id: 'asesoria', label: 'Asesor', icon: Bot },
]

// Devuelve el primer segmento tras #admin/ (ej "agente" en "#admin/agente/conocimiento").
function currentTab() {
  const h = window.location.hash.replace('#admin/', '').replace('#admin', '')
  const top = h.split('/')[0]
  return NAV.find((n) => n.id === top)?.id || 'dashboard'
}

export default function AdminApp() {
  const [tab, setTab] = useState(currentTab())
  const [navOpen, setNavOpen] = useState(false)

  useEffect(() => {
    const onHash = () => setTab(currentTab())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  const go = (id) => {
    window.location.hash = `admin/${id}`
    setTab(id)
    setNavOpen(false)
  }

  return (
    <div className="flex min-h-dvh bg-mist text-ink">
      <Toaster />
      {/* Sidebar desktop */}
      <aside className="hidden w-60 shrink-0 flex-col border-r border-hilton-100 bg-white lg:flex">
        <SidebarContent tab={tab} go={go} />
      </aside>

      {/* Drawer móvil */}
      {navOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-ink/40" onClick={() => setNavOpen(false)} />
          <aside className="absolute left-0 top-0 flex h-full w-64 flex-col bg-white shadow-card-lg animate-slide-up">
            <SidebarContent tab={tab} go={go} onClose={() => setNavOpen(false)} />
          </aside>
        </div>
      )}

      {/* Contenido */}
      <div className="flex min-w-0 flex-1 flex-col">
        {/* Topbar móvil */}
        <header className="flex items-center justify-between border-b border-hilton-100 bg-white px-4 py-3 lg:hidden">
          <button
            onClick={() => setNavOpen(true)}
            aria-label="Abrir menú"
            className="flex h-10 w-10 items-center justify-center rounded-lg text-hilton-700 hover:bg-hilton-50"
          >
            <Menu size={22} />
          </button>
          <span className="font-serif text-base font-600 text-hilton-700">Backoffice</span>
          <a href="#inicio" className="flex h-10 w-10 items-center justify-center rounded-lg text-slatey hover:bg-mist" aria-label="Ver sitio">
            <ExternalLink size={18} />
          </a>
        </header>

        <main className="flex-1 overflow-y-auto p-4 sm:p-6 lg:p-8">
          <Suspense fallback={<Loading />}>
            {tab === 'dashboard' && <DashboardView go={go} />}
            {tab === 'analiticas' && <AnalyticsView />}
            {tab === 'reservas' && <BookingsView />}
            {tab === 'habitaciones' && <HabitacionesView />}
            {tab === 'pasajeros' && <PassengersView />}
            {tab === 'leads' && <LeadsView />}
            {tab === 'tickets' && <TicketsView />}
            {tab === 'equipo' && <EquipoView />}
            {tab === 'asesoria' && <AsesoriaView />}
            {tab === 'agente' && <AgentSection />}
          </Suspense>
        </main>
      </div>
    </div>
  )
}

function SidebarContent({ tab, go, onClose }) {
  return (
    <>
      <div className="flex items-center justify-between border-b border-hilton-100 px-5 py-4">
        <div className="flex items-center gap-2.5">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-hilton-600 text-white">
            <Hotel size={18} />
          </div>
          <div className="leading-tight">
            <p className="font-serif text-sm font-700 text-hilton-700">Hampton</p>
            <p className="text-[10px] uppercase tracking-wide text-slatey">Backoffice</p>
          </div>
        </div>
        {onClose && (
          <button onClick={onClose} aria-label="Cerrar menú" className="text-slatey lg:hidden">
            <X size={20} />
          </button>
        )}
      </div>

      <nav className="flex flex-1 flex-col gap-1 p-3">
        {NAV.map((n) => {
          const Icon = n.icon
          const active = tab === n.id
          return (
            <button
              key={n.id}
              onClick={() => go(n.id)}
              className={`flex items-center gap-3 rounded-xl px-3.5 py-2.5 text-sm font-medium transition ${
                active
                  ? 'bg-hilton-600 text-white shadow-card'
                  : 'text-ink hover:bg-hilton-50'
              }`}
            >
              <Icon size={18} className={active ? 'text-white' : 'text-hilton-500'} />
              {n.label}
            </button>
          )
        })}
      </nav>

      <div className="border-t border-hilton-100 p-3">
        <a
          href="#inicio"
          className="flex items-center gap-2 rounded-xl px-3.5 py-2.5 text-sm font-medium text-slatey hover:bg-mist"
        >
          <ExternalLink size={16} />
          Ver sitio público
        </a>
      </div>
    </>
  )
}
