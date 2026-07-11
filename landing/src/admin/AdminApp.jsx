import { useState, useEffect, lazy, Suspense } from 'react'
import {
  LayoutDashboard, CalendarCheck, UserPlus, LifeBuoy, Menu, X, ExternalLink, Hotel,
  Users, BarChart3, UtensilsCrossed, LineChart, MessagesSquare, BadgeCheck,
  Store, SlidersHorizontal, Sparkles, Waypoints,
} from 'lucide-react'
import DashboardView from './views/DashboardView'
import BookingsView from './views/BookingsView'
import LeadsView from './views/LeadsView'
import PassengersView from './views/PassengersView'
import TicketsView from './views/TicketsView'
import AsesoriaView from './views/AsesoriaView'
import RestaurantSection from './views/restaurant/RestaurantSection'
import ConfiguracionSection from './views/sistema/ConfiguracionSection'
import ComoFuncionaView from './views/agente/ComoFuncionaView'
import { Toaster } from './toast'
import HandoffAlert from './components/HandoffAlert'
import { Loading } from './ui'
import { getMe, logout } from '../services/api'
import { LogOut } from 'lucide-react'
import { useBusinessProfile } from '../hooks/useBusinessProfile'

// Lazy: AnalyticsView arrastra Recharts (~130 KB) y NegocioSection arrastra KnowledgeView
// (pesada). Se cargan solo cuando el usuario entra a esas secciones, aliviando el bundle.
const AnalyticsView = lazy(() => import('./views/AnalyticsView'))
const NegocioSection = lazy(() => import('./views/negocio/NegocioSection'))
const OnboardingWizard = lazy(() => import('./views/negocio/OnboardingWizard'))
const EmployeeHubSection = lazy(() => import('./views/centro/EmployeeHubSection'))
// Bandeja en vivo: hace polling; lazy para no cargarla hasta que se entra a la sección.
const LiveConversationsView = lazy(() => import('./views/LiveConversationsView'))

// Sidebar en DOS MUNDOS (rediseño F0): "Operar" (el día a día) arriba y "El agente" (configurar
// y entender el producto) abajo, más "Sistema" para la config global adminOnly. Los `id` NO
// cambian (hash routing intacto): solo cambian `group`, el orden y las etiquetas visibles.
// `hidden: true` mantiene la RUTA viva (currentTab la resuelve por NAV.find) pero la saca del
// sidebar — se usa para `asesoria`, que se accede desde la ficha del Asesor en "Empleados
// Digitales", no como entrada de menú suelta.
const NAV = [
  // ── Operar: el trabajo diario del hotel ──
  { id: 'dashboard', label: 'Panel', icon: LayoutDashboard, group: 'Operar' },
  { id: 'conversaciones', label: 'Conversaciones', icon: MessagesSquare, group: 'Operar' },
  { id: 'reservas', label: 'Reservas', icon: CalendarCheck, group: 'Operar' },
  { id: 'pasajeros', label: 'Huéspedes', icon: Users, group: 'Operar' },
  { id: 'tickets', label: 'Operaciones', icon: LifeBuoy, group: 'Operar' },
  { id: 'restaurante', label: 'Restaurante', icon: UtensilsCrossed, group: 'Operar' },
  { id: 'leads', label: 'Leads', icon: UserPlus, group: 'Operar' },
  { id: 'analiticas', label: 'Analíticas', icon: BarChart3, group: 'Operar' },
  // ── El agente: configurar y ENTENDER el producto ──
  // "Cómo funciona" va primero: da el modelo mental completo del sistema (F2). NUEVO.
  { id: 'como-funciona', label: 'Cómo funciona', icon: Waypoints, group: 'El agente' },
  // Empleados Digitales: el diferencial del producto. Contiene a Aura, Operaciones y el Asesor.
  { id: 'centro', label: 'Empleados Digitales', icon: BadgeCheck, group: 'El agente' },
  // Negocio: recursos del hotel que el agente CONSUME (Conocimiento/Promos/Habitaciones).
  { id: 'negocio', label: 'Negocio', icon: Store, group: 'El agente' },
  // Configuración inicial: wizard que guía el alta de un cliente (Fase 3.2). adminOnly.
  { id: 'onboarding', label: 'Configuración inicial', icon: Sparkles, group: 'El agente', adminOnly: true },
  // ── Sistema: config global (Equipo/Temas/Límites/Consumo/Demo). adminOnly. ──
  { id: 'configuracion', label: 'Configuración', icon: SlidersHorizontal, group: 'Sistema', adminOnly: true },
  // Asesor de gerencia: es uno de los 3 empleados digitales → se accede desde su ficha en
  // "Empleados Digitales". `hidden` lo saca del menú pero mantiene su ruta (#admin/asesoria)
  // viva para no romper links guardados ni la resolución de currentTab(). adminOnly.
  { id: 'asesoria', label: 'Asesor de gerencia', icon: LineChart, group: 'Sistema', adminOnly: true, hidden: true },
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
  const [me, setMe] = useState(null)

  useEffect(() => {
    const onHash = () => setTab(currentTab())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  // Identidad del usuario logueado: define qué secciones ve (adminOnly). Fase 2.5.
  useEffect(() => {
    getMe().then(setMe).catch(() => setMe(null))
  }, [])

  const isAdmin = me?.role === 'admin'
  // El sidebar oculta lo adminOnly a los operadores y lo `hidden` a todos (rutas vivas sin ítem
  // de menú, ej. `asesoria`). El guard de render (effectiveTab) sigue protegiendo por adminOnly.
  const nav = NAV.filter((n) => !n.hidden && (!n.adminOnly || isAdmin))

  const go = (id) => {
    window.location.hash = `admin/${id}`
    setTab(id)
    setNavOpen(false)
  }

  const onLogout = () => {
    logout()
    window.dispatchEvent(new CustomEvent('auth:unauthorized'))
  }

  // Guard de render: si el operador fuerza el hash a una vista adminOnly, cae a dashboard.
  const activeItem = NAV.find((n) => n.id === tab)
  const effectiveTab = activeItem?.adminOnly && !isAdmin ? 'dashboard' : tab

  return (
    <div className="flex min-h-dvh bg-mist text-ink">
      <Toaster />
      <HandoffAlert />
      {/* Sidebar desktop */}
      <aside className="hidden w-60 shrink-0 flex-col border-r border-hilton-100 bg-white lg:flex">
        <SidebarContent tab={effectiveTab} go={go} nav={nav} me={me} onLogout={onLogout} />
      </aside>

      {/* Drawer móvil */}
      {navOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-ink/40" onClick={() => setNavOpen(false)} />
          <aside className="absolute left-0 top-0 flex h-full w-64 flex-col bg-white shadow-card-lg animate-slide-up">
            <SidebarContent tab={effectiveTab} go={go} nav={nav} me={me} onLogout={onLogout} onClose={() => setNavOpen(false)} />
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
        <main className={effectiveTab === 'conversaciones'
          ? 'flex min-h-0 flex-1 flex-col overflow-hidden p-3 sm:p-4'
          : 'flex-1 overflow-y-auto p-4 sm:p-6 lg:p-8'}>
          <Suspense fallback={<Loading />}>
            {effectiveTab === 'dashboard' && <DashboardView go={go} />}
            {effectiveTab === 'analiticas' && <AnalyticsView />}
            {effectiveTab === 'reservas' && <BookingsView />}
            {effectiveTab === 'conversaciones' && <LiveConversationsView />}
            {effectiveTab === 'restaurante' && <RestaurantSection />}
            {effectiveTab === 'pasajeros' && <PassengersView />}
            {effectiveTab === 'leads' && <LeadsView />}
            {effectiveTab === 'tickets' && <TicketsView />}
            {effectiveTab === 'asesoria' && <AsesoriaView />}
            {effectiveTab === 'centro' && <EmployeeHubSection />}
            {/* Cómo funciona: el esquema del sistema, informativo y estático (F2). */}
            {effectiveTab === 'como-funciona' && <ComoFuncionaView />}
            {/* Configuración inicial: wizard de onboarding (Fase 3.2), orquesta vistas existentes */}
            {effectiveTab === 'onboarding' && <OnboardingWizard />}
            {/* Negocio: Conocimiento / Promociones / Habitaciones (sub-pestañas internas) */}
            {effectiveTab === 'negocio' && <NegocioSection />}
            {/* Sistema: Equipo / Temas / Límites / Consumo / Demo (sub-pestañas internas) */}
            {effectiveTab === 'configuracion' && <ConfiguracionSection />}
          </Suspense>
        </main>
      </div>
    </div>
  )
}

function SidebarContent({ tab, go, nav = NAV, me, onLogout, onClose }) {
  const HOTEL = useBusinessProfile()
  return (
    <>
      <div className="flex items-center justify-between border-b border-hilton-100 px-5 py-4">
        <div className="flex items-center gap-2.5">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-hilton-600 text-white">
            <Hotel size={18} />
          </div>
          <div className="leading-tight">
            <p className="font-serif text-sm font-700 text-hilton-700">{HOTEL.name}</p>
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
        {nav.map((n, i) => {
          const Icon = n.icon
          const active = tab === n.id
          // Encabezado de grupo: se muestra cuando arranca un grupo nuevo.
          const showGroup = i === 0 || nav[i - 1].group !== n.group
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
        {me && (
          <div className="mb-1 flex items-center justify-between gap-2 px-3.5 py-1.5">
            <div className="min-w-0 leading-tight">
              <p className="truncate text-xs font-medium text-ink">{me.email}</p>
              <p className="text-[10px] uppercase tracking-wide text-slatey">{me.role}</p>
            </div>
            {onLogout && (
              <button
                onClick={onLogout}
                aria-label="Cerrar sesión"
                title="Cerrar sesión"
                className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-slatey hover:bg-hilton-50 hover:text-hilton-700"
              >
                <LogOut size={16} />
              </button>
            )}
          </div>
        )}
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
