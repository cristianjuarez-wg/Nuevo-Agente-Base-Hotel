import { useEffect, useState } from 'react'
import {
  CalendarCheck, UserPlus, LifeBuoy, DollarSign, Bot, Globe, ArrowRight, AlertTriangle,
} from 'lucide-react'
import { listBookings, listLeads, getTicketStats } from '../../services/api'
import { PageHeader, StatCard, Loading, Badge, formatARS, formatDate } from '../ui'

export default function DashboardView({ go }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([
      listBookings().catch(() => []),
      listLeads().catch(() => []),
      getTicketStats().catch(() => ({ total: 0, escalated: 0, resolved: 0, open: 0 })),
    ])
      .then(([bookings, leads, tickets]) => {
        const bArr = Array.isArray(bookings) ? bookings : []
        const lArr = Array.isArray(leads) ? leads : leads?.leads || []
        const revenueUsd = bArr
          .filter((b) => b.status !== 'cancelled')
          .reduce((sum, b) => sum + (b.total_price_usd || 0), 0)
        const fromAgent = bArr.filter((b) => b.source === 'agente').length
        setData({ bookings: bArr, leads: lArr, tickets, revenueUsd, fromAgent })
      })
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <Loading label="Cargando panel…" />
  if (!data) return null

  const recent = [...data.bookings].slice(0, 5)

  return (
    <div>
      <PageHeader title="Dashboard" subtitle="Resumen de actividad del Hampton by Hilton Bariloche." />

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard icon={CalendarCheck} label="Reservas totales" value={data.bookings.length} tone="hilton" />
        <StatCard icon={DollarSign} label="Ingresos (USD)" value={`$${formatARS(data.revenueUsd)}`} tone="green" />
        <StatCard icon={UserPlus} label="Leads captados" value={data.leads.length} tone="amber" />
        <StatCard icon={LifeBuoy} label="Tickets soporte" value={data.tickets.total} tone="hilton" />
      </div>

      {/* Insight del agente */}
      <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="rounded-2xl bg-gradient-to-br from-hilton-700 to-hilton-500 p-5 text-white lg:col-span-2">
          <div className="flex items-center gap-2 text-sm font-medium text-white/80">
            <Bot size={18} /> Impacto del agente Aura
          </div>
          <div className="mt-4 grid grid-cols-3 gap-4">
            <div>
              <p className="font-serif text-3xl font-700 tabular-nums">{data.fromAgent}</p>
              <p className="text-xs text-white/75">reservas vía agente</p>
            </div>
            <div>
              <p className="font-serif text-3xl font-700 tabular-nums">{data.leads.length}</p>
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
                    {b.source === 'agente' ? (
                      <Badge tone="blue"><Bot size={11} className="mr-1" />Agente</Badge>
                    ) : (
                      <Badge tone="gray"><Globe size={11} className="mr-1" />Web</Badge>
                    )}
                  </p>
                  <p className="truncate text-xs text-slatey">
                    {b.code} · {b.room_type} · {formatDate(b.check_in)}
                  </p>
                </div>
                <span className="shrink-0 text-sm font-semibold tabular-nums text-hilton-700">USD {b.total_price_usd}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
