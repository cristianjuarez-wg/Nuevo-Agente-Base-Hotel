import { useEffect, useState } from 'react'
import {
  CalendarCheck, UserPlus, LifeBuoy, DollarSign, Bot, ArrowRight, AlertTriangle, BedDouble, UtensilsCrossed,
  Percent, TrendingUp, TrendingDown, Sparkles,
} from 'lucide-react'
import { getDashboardSummary, listBookings, getTicketStats, getRestaurantStats } from '../../services/api'
import { PageHeader, StatCard, Loading, OriginBadge, formatUSD, formatDate } from '../ui'
import PeriodSelector from '../components/PeriodSelector'
import { useBusinessProfile } from '../../hooks/useBusinessProfile'

// Flecha de tendencia (▲/▼ con %) vs. los 30 días previos — cálculo del agente/negocio.
function Trend({ value }) {
  const v = Number(value) || 0
  if (v === 0) return <span className="text-xs text-white/60">sin cambio</span>
  const up = v > 0
  const Icon = up ? TrendingUp : TrendingDown
  return (
    <span className={`inline-flex items-center gap-0.5 text-xs font-medium ${up ? 'text-green-200' : 'text-red-200'}`}>
      <Icon size={12} /> {up ? '+' : ''}{v}%
    </span>
  )
}

export default function DashboardView({ go }) {
  const HOTEL = useBusinessProfile()
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
  const trends = data.summary?.trends || {}

  return (
    <div>
      <PageHeader
        title="Dashboard"
        subtitle={`Resumen de ${HOTEL.name} ${HOTEL.city}${pc.period_label ? ` · ${pc.period_label}` : ''}.`}
        right={<PeriodSelector value={period} onChange={setPeriod} />}
      />

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-3 xl:grid-cols-7">
        <StatCard
          icon={BedDouble}
          label={`En casa hoy${today.guests ? ` · ${today.guests} huésp.` : ''}`}
          value={today.rooms_occupied ?? 0}
          tone="green"
        />
        <StatCard icon={Percent} label="Ocupación del período" value={`${pc.occupancy_pct ?? 0}%`} tone="hilton" />
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
              <p className="flex items-baseline gap-1.5">
                <span className="font-serif text-3xl font-700 tabular-nums">{pc.leads ?? 0}</span>
                <Trend value={trends.leads_trend} />
              </p>
              <p className="text-xs text-white/75">leads captados</p>
            </div>
            <div>
              <p className="font-serif text-3xl font-700 tabular-nums">{data.tickets.resolved}</p>
              <p className="text-xs text-white/75">consultas auto-resueltas</p>
            </div>
          </div>
          {/* Cierre del embudo: cuántos leads terminaron en reserva (lo calcula Aura). */}
          <div className="mt-4 flex items-center gap-2 border-t border-white/20 pt-3 text-sm text-white/85">
            <Sparkles size={15} className="text-white/80" />
            <span>
              Aura cerró <span className="font-700 tabular-nums">{pc.leads_closed ?? 0}</span> de esos leads
              {' · '}<span className="font-700 tabular-nums">{pc.conversion_pct ?? 0}%</span> de conversión
            </span>
            <span className="ml-auto"><Trend value={trends.conversion_trend} /></span>
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
