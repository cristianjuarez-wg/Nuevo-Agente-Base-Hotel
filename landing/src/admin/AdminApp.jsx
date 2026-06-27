import { useState, useEffect, lazy, Suspense } from 'react'
import {
  LayoutDashboard, CalendarCheck, UserPlus, LifeBuoy, Menu, X, ExternalLink, Hotel,
  Users, BarChart3, Briefcase, UtensilsCrossed, LineChart, MessagesSquare, BadgeCheck,
  BookOpen, Tag, Palette, Gauge, ShieldCheck, Database,
} from 'lucide-react'
import DashboardView from './views/DashboardView'
import BookingsView from './views/BookingsView'
import HabitacionesView from './views/HabitacionesView'
import LeadsView from './views/LeadsView'
import PassengersView from './views/PassengersView'
import TicketsView from './views/TicketsView'
import EquipoView from './views/EquipoView'
import AsesoriaView from './views/AsesoriaView'
import RestaurantSection from './views/restaurant/RestaurantSection'
import PromotionsView from './views/agente/PromotionsView'
import ThemesView from './views/agente/ThemesView'
import LimitsView from './views/agente/LimitsView'
import DemoView from './views/agente/DemoView'
import UsageView from './views/UsageView'
import { Toaster } from './toast'
import { Loading } from './ui'

// Lazy: AnalyticsView arrastra Recharts (~130 KB) y KnowledgeView es pesada. Se cargan
// solo cuando el usuario entra a esas secciones, aliviando el bundle inicial.
const AnalyticsView = lazy(() => import('./views/AnalyticsView'))
const KnowledgeView = lazy(() => import('./views/agente/KnowledgeView'))
const EmployeeHubSection = lazy(() => import('./views/centro/EmployeeHubSection'))
// Bandeja en vivo: hace polling; lazy para no cargarla hasta que se entra a la sección.
const LiveConversationsView = lazy(() => import('./views/LiveConversationsView'))

// Sidebar agrupado por USO real del gerente: lo operativo del día arriba, lo comercial en
// el medio, y la configuración/herramientas abajo. Los `id` NO cambian (hash routing intacto);
// solo cambian las etiquetas y el orden, y se suman encabezados de grupo.
const NAV = [
  { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard, group: 'Operación' },
  { id: 'conversaciones', label: 'Conversaciones', icon: MessagesSquare, group: 'Operación' },
  { id: 'reservas', label: 'Reservas', icon: CalendarCheck, group: 'Operación' },
  { id: 'pasajeros', label: 'Huéspedes', icon: Users, group: 'Operación' },
  { id: 'tickets', label: 'Operaciones', icon: LifeBuoy, group: 'Operación' },
  { id: 'restaurante', label: 'Restaurante', icon: UtensilsCrossed, group: 'Operación' },
  { id: 'leads', label: 'Leads', icon: UserPlus, group: 'Comercial' },
  { id: 'analiticas', label: 'Analíticas', icon: BarChart3, group: 'Comercial' },
  // Negocio: recursos del hotel que el agente CONSUME (no son del agente). Doc §9.2.
  { id: 'conocimiento', label: 'Conocimiento', icon: BookOpen, group: 'Negocio' },
  { id: 'promociones', label: 'Promociones', icon: Tag, group: 'Negocio' },
  { id: 'habitaciones', label: 'Habitaciones', icon: Hotel, group: 'Negocio' },
  // Plataforma: el agente (su legajo) + config global del sistema.
  { id: 'centro', label: 'Centro del Empleado Digital', icon: BadgeCheck, group: 'Plataforma' },
  { id: 'equipo', label: 'Equipo', icon: Briefcase, group: 'Plataforma' },
  { id: 'asesoria', label: 'Asesor de gerencia', icon: LineChart, group: 'Plataforma' },
  { id: 'temas', label: 'Temas del chat', icon: Palette, group: 'Plataforma' },
  { id: 'limites', label: 'Límites y seguridad', icon: ShieldCheck, group: 'Plataforma' },
  { id: 'consumo', label: 'Consumo IA', icon: Gauge, group: 'Plataforma' },
  { id: 'demo', label: 'Demo', icon: Database, group: 'Plataforma' },
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

        {/* Conversaciones es una bandeja tipo "inbox": ocupa TODO el alto/ancho sin padding ni
            scroll del main (su propio layout maneja el scroll). El resto de las vistas conserva
            el padding y el scroll vertical habitual. */}
        <main className={tab === 'conversaciones'
          ? 'flex min-h-0 flex-1 flex-col overflow-hidden p-3 sm:p-4'
          : 'flex-1 overflow-y-auto p-4 sm:p-6 lg:p-8'}>
          <Suspense fallback={<Loading />}>
            {tab === 'dashboard' && <DashboardView go={go} />}
            {tab === 'analiticas' && <AnalyticsView />}
            {tab === 'reservas' && <BookingsView />}
            {tab === 'conversaciones' && <LiveConversationsView />}
            {tab === 'habitaciones' && <HabitacionesView />}
            {tab === 'restaurante' && <RestaurantSection />}
            {tab === 'pasajeros' && <PassengersView />}
            {tab === 'leads' && <LeadsView />}
            {tab === 'tickets' && <TicketsView />}
            {tab === 'equipo' && <EquipoView />}
            {tab === 'asesoria' && <AsesoriaView />}
            {tab === 'centro' && <EmployeeHubSection />}
            {/* Negocio (recursos que el agente consume) */}
            {tab === 'conocimiento' && <KnowledgeView />}
            {tab === 'promociones' && <PromotionsView />}
            {/* Plataforma (config global) */}
            {tab === 'temas' && <ThemesView />}
            {tab === 'limites' && <LimitsView />}
            {tab === 'consumo' && <UsageView />}
            {tab === 'demo' && <DemoView />}
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
        {NAV.map((n, i) => {
          const Icon = n.icon
          const active = tab === n.id
          // Encabezado de grupo: se muestra cuando arranca un grupo nuevo.
          const showGroup = i === 0 || NAV[i - 1].group !== n.group
          return (
            <div key={n.id}>
              {showGroup && (
                <p className={`px-3.5 pb-1 text-[10px] font-semibold uppercase tracking-wide text-slatey ${i === 0 ? 'pt-1' : 'pt-4'}`}>
                  {n.group}
                </p>
              )}
              <button
                onClick={() => go(n.id)}
                className={`flex w-full items-center gap-3 rounded-xl px-3.5 py-2.5 text-sm font-medium transition ${
                  active
                    ? 'bg-hilton-600 text-white shadow-card'
                    : 'text-ink hover:bg-hilton-50'
                }`}
              >
                <Icon size={18} className={active ? 'text-white' : 'text-hilton-500'} />
                {n.label}
              </button>
            </div>
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
