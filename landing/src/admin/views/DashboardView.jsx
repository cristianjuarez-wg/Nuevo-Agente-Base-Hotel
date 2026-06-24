import { useEffect, useState } from 'react'
import {
  CalendarCheck, UserPlus, LifeBuoy, DollarSign, Bot, ArrowRight, AlertTriangle, BedDouble, UtensilsCrossed,
} from 'lucide-react'
import { getDashboardSummary, listBookings, getTicketStats, getRestaurantStats } from '../../services/api'
import { PageHeader, StatCard, Loading, OriginBadge, formatUSD, formatDate } from '../ui'
import PeriodSelector from '../components/PeriodSelector'

export default function DashboardView({ go }) {
  const [period, setPeriod] = useState('mes')
  const [data, setData] = useState(null)
  const [recent, setRecent] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    Promise.all([
      getDashboardSummary(period).catch(() => null),
      getTicketStats().catch(() => ({ total: 0, escalated: 0, resolved: 0, open: 0 })),
      getRestaurantStats().catch(() => ({ revenue_fnb_usd: 0, orders_total: 0, orders_today: 0 })),
      listBookings().catch(() => []),
    ])
      .then(([summary, tickets, fnb, bookings]) => {
        const bArr = Array.isArray(bookings) ? bookings : []
        setData({ summary, tickets, fnb })
        setRecent(bArr.slice(0, 5))
      })
      .finally(() => setLoading(false))
  }, [period])

  if (loading) return <Loading label="Cargando panel…" />
  if (!data) return null

  const pc = data.summary?.period_cards || {}
  const today = data.summary?.today || {}

  return (
    <div>
      <PageHeader
        title="Dashboard"
        subtitle={`Resumen del Hampton by Hilton Bariloche${pc.period_label ? ` · ${pc.period_label}` : ''}.`}
        right={<PeriodSelector value={period} onChange={setPeriod} />}
      />

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-3 xl:grid-cols-6">
        <StatCard
          icon={BedDouble}
          label={`En casa hoy${today.guests ? ` · ${today.guests} huésp.` : ''}`}
          value={today.rooms_occupied ?? 0}
          tone="green"
        />
        <StatCard icon={CalendarCheck} label="Reservas" value={pc.bookings_count ?? 0} tone="hilton" />
        <StatCard icon={DollarSign} label="Ingresos (USD)" value={formatUSD(pc.revenue_usd || 0)} tone="green" />
        <StatCard
          icon={UtensilsCrossed}
          label={`Restaurante${data.fnb?.orders_today ? ` · ${data.fnb.orders_today} hoy` : ''}`}
          value={formatUSD(data.fnb?.revenue_fnb_usd || 0)}
          tone="amber"
        />
        <StatCard icon={UserPlus} label="Leads captados" value={pc.leads ?? 0} tone="amber" />
        <StatCard icon={LifeBuoy} label="Tickets soporte" value={pc.tickets_total ?? 0} tone="hilton" />
      </div>

      {/* Insight del agente */}
      <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="rounded-2xl bg-gradient-to-br from-hilton-700 to-hilton-500 p-5 text-white lg:col-span-2">
          <div className="flex items-center gap-2 text-sm font-medium text-white/80">
            <Bot size={18} /> Impacto del agente Aura
          </div>
          <div className="mt-4 grid grid-cols-3 gap-4">
            <div>
              <p className="font-serif text-3xl font-700 tabular-nums">{pc.bookings_count ?? 0}</p>
              <p className="text-xs text-white/75">reservas del período</p>
            </div>
            <div>
              <p className="font-serif text-3xl font-700 tabular-nums">{pc.leads ?? 0}</p>
              <p className="text-xs text-white/75">leads captados</p>
            </div>
            <div>
              <p className="font-serif text-3xl font-700 tabular-nums">{data.tickets.resolved}</p>
              <p className="text-xs text-white/75">consultas auto-resueltas</p>
            </div>
          </div>
        </div>

        <div className="rounded-2xl bg-white p-5 shadow-card">
          <p className="text-sm font-medium text-ink">Soporte</p>
          <div className="mt-4 space-y-3">
            <div className="flex items-center justify-between text-sm">
              <span className="flex items-center gap-2 text-slatey"><Bot size={15} className="text-green-600" /> Auto-resueltos</span>
              <span className="font-semibold tabular-nums">{data.tickets.resolved}</span>
            </div>
            <div className="flex items-center justify-between text-sm">
              <span className="flex items-center gap-2 text-slatey"><AlertTriangle size={15} className="text-red-500" /> Escalados</span>
              <span className="font-semibold tabular-nums">{data.tickets.escalated}</span>
            </div>
          </div>
        </div>
      </div>

      {/* Reservas recientes */}
      <div className="mt-6 rounded-2xl bg-white p-5 shadow-card">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="font-serif text-lg font-600 text-ink">Reservas recientes</h2>
          <button onClick={() => go('reservas')} className="inline-flex items-center gap-1 text-sm font-medium text-hilton-600 hover:text-hilton-700">
            Ver todas <ArrowRight size={15} />
          </button>
        </div>
        {recent.length === 0 ? (
          <p className="py-6 text-center text-sm text-slatey">Todavía no hay reservas.</p>
        ) : (
          <ul className="divide-y divide-mist">
            {recent.map((b) => (
              <li key={b.code} className="flex items-center justify-between py-3">
                <div className="min-w-0">
                  <p className="flex items-center gap-2 font-medium text-ink">
                    {b.guest_name}
                    <OriginBadge origin={b.origin} />
                  </p>
                  <p className="truncate text-xs text-slatey">
                    {b.code} · {b.room_type} · {formatDate(b.check_in)}
                  </p>
                </div>
                <span className="shrink-0 text-sm font-semibold tabular-nums text-hilton-700">{formatUSD(b.total_price_usd)}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
