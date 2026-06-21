import { useEffect, useState } from 'react'
import {
  RefreshCw, MessageSquare, UserPlus, CalendarCheck, MessageCircle, Globe, TrendingDown,
} from 'lucide-react'
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, Cell, LabelList,
} from 'recharts'
import { getFunnel, getHeatmap, getChannelStats, getAgentQualityMetrics } from '../../services/api'
import { PageHeader, StatCard, Loading } from '../ui'

// Selector de canal: Todos / Web / WhatsApp. Filtra funnel + heatmap.
const CHANNELS = [
  { id: 'all', label: 'Todos', icon: null },
  { id: 'web', label: 'Web', icon: Globe },
  { id: 'whatsapp', label: 'WhatsApp', icon: MessageCircle },
]

function ChannelTabs({ value, onChange }) {
  return (
    <div className="inline-flex rounded-xl bg-mist p-1" role="tablist" aria-label="Filtrar por canal">
      {CHANNELS.map((c) => {
        const Icon = c.icon
        const active = value === c.id
        return (
          <button
            key={c.id}
            role="tab"
            aria-selected={active}
            onClick={() => onChange(c.id)}
            className={`flex items-center gap-1.5 rounded-lg px-3.5 py-2 text-xs font-medium transition ${
              active ? 'bg-white text-hilton-700 shadow-card' : 'text-slatey hover:text-ink'
            }`}
          >
            {Icon && <Icon size={14} />}
            {c.label}
          </button>
        )
      })}
    </div>
  )
}

// ── Embudo de conversión: barras horizontales decrecientes + tasas ───────────
const FUNNEL_COLORS = ['#005aa9', '#2b82c9', '#62a8dd']

function FunnelChart({ stages }) {
  const max = Math.max(...stages.map((s) => s.count), 1)
  return (
    <div className="space-y-4">
      {stages.map((s, i) => {
        const widthPct = Math.max((s.count / max) * 100, 2)
        return (
          <div key={s.name}>
            <div className="mb-1 flex items-baseline justify-between text-sm">
              <span className="font-medium text-ink">{s.name}</span>
              <span className="tabular-nums text-slatey">
                <span className="font-700 text-ink">{s.count}</span>
                {i > 0 && <span className="ml-2 text-xs">({s.percentage}% del total)</span>}
              </span>
            </div>
            <div className="h-9 overflow-hidden rounded-lg bg-mist">
              <div
                className="flex h-full items-center rounded-lg px-3 text-xs font-semibold text-white transition-all duration-500"
                style={{ width: `${widthPct}%`, backgroundColor: FUNNEL_COLORS[i] || '#62a8dd' }}
              >
                {widthPct > 12 && <span className="tabular-nums">{s.count}</span>}
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}

function ConversionRates({ rates }) {
  const items = [
    { label: 'Conversación → Lead', value: rates?.conversation_to_lead ?? 0 },
    { label: 'Lead → Reserva', value: rates?.lead_to_reservation ?? 0 },
  ]
  return (
    <div className="mt-5 grid grid-cols-2 gap-3 border-t border-hilton-100 pt-4">
      {items.map((it) => (
        <div key={it.label} className="rounded-xl bg-mist px-4 py-3">
          <p className="text-xs text-slatey">{it.label}</p>
          <p className="mt-0.5 font-serif text-xl font-700 tabular-nums text-hilton-700">{it.value}%</p>
        </div>
      ))}
    </div>
  )
}

// ── Mapa de calor día × hora ─────────────────────────────────────────────────
const DAYS = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom']
// El backend usa dow 0=Domingo..6=Sábado; reordenamos para mostrar Lun→Dom.
const DOW_ORDER = [1, 2, 3, 4, 5, 6, 0]

function heatColor(count, max) {
  if (!count) return 'bg-mist'
  const ratio = count / max
  if (ratio > 0.75) return 'bg-hilton-700 text-white'
  if (ratio > 0.5) return 'bg-hilton-500 text-white'
  if (ratio > 0.25) return 'bg-hilton-300 text-hilton-900'
  return 'bg-hilton-100 text-hilton-800'
}

function Heatmap({ data, maxCount }) {
  // Indexar por (day_index, hour) para lookup rápido.
  const map = {}
  for (const d of data) map[`${d.day_index}_${d.hour}`] = d.count
  const max = maxCount || 1
  const hours = Array.from({ length: 24 }, (_, h) => h)

  return (
    <div className="overflow-x-auto">
      <div className="min-w-[640px]">
        {/* Encabezado de horas */}
        <div className="mb-1 flex pl-9">
          {hours.map((h) => (
            <div key={h} className="flex-1 text-center text-[9px] tabular-nums text-slatey">
              {h % 3 === 0 ? `${h}h` : ''}
            </div>
          ))}
        </div>
        {DOW_ORDER.map((dow, idx) => (
          <div key={dow} className="mb-1 flex items-center">
            <div className="w-9 shrink-0 text-[11px] font-medium text-slatey">{DAYS[idx]}</div>
            <div className="flex flex-1 gap-0.5">
              {hours.map((h) => {
                const count = map[`${dow}_${h}`] || 0
                return (
                  <div
                    key={h}
                    title={`${DAYS[idx]} ${h}:00 — ${count} conversación${count === 1 ? '' : 'es'}`}
                    className={`flex h-6 flex-1 items-center justify-center rounded text-[9px] font-semibold tabular-nums ${heatColor(count, max)}`}
                  >
                    {count > 0 ? count : ''}
                  </div>
                )
              })}
            </div>
          </div>
        ))}
        {/* Leyenda */}
        <div className="mt-3 flex items-center gap-2 pl-9 text-[10px] text-slatey">
          <span>Menos</span>
          <div className="h-3 w-4 rounded bg-mist" />
          <div className="h-3 w-4 rounded bg-hilton-100" />
          <div className="h-3 w-4 rounded bg-hilton-300" />
          <div className="h-3 w-4 rounded bg-hilton-500" />
          <div className="h-3 w-4 rounded bg-hilton-700" />
          <span>Más</span>
        </div>
      </div>
    </div>
  )
}

// ── Distribución por canal (barras, no pie: solo 2 categorías) ────────────────
function ChannelBars({ channels }) {
  const colorFor = (key) => (key === 'whatsapp' ? '#16a34a' : '#005aa9')
  return (
    <ResponsiveContainer width="100%" height={140}>
      <BarChart data={channels} layout="vertical" margin={{ left: 8, right: 24 }}>
        <XAxis type="number" hide />
        <YAxis type="category" dataKey="name" width={80} tickLine={false} axisLine={false}
               tick={{ fill: '#5b6b80', fontSize: 12 }} />
        <Tooltip
          cursor={{ fill: 'rgba(0,90,169,0.05)' }}
          formatter={(v, _n, p) => [`${v} (${p.payload.percentage}%)`, 'Conversaciones']}
        />
        <Bar dataKey="count" radius={[0, 6, 6, 0]} barSize={28}>
          {channels.map((c) => <Cell key={c.channel} fill={colorFor(c.channel)} />)}
          <LabelList dataKey="count" position="right" className="tabular-nums"
                     style={{ fill: '#1b2433', fontSize: 12, fontWeight: 600 }} />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

function Panel({ title, subtitle, children }) {
  return (
    <div className="rounded-2xl bg-white p-5 shadow-card">
      <div className="mb-4">
        <h2 className="font-serif text-lg font-700 text-ink">{title}</h2>
        {subtitle && <p className="text-xs text-slatey">{subtitle}</p>}
      </div>
      {children}
    </div>
  )
}

export default function AnalyticsView() {
  const [channel, setChannel] = useState('all')
  const [funnel, setFunnel] = useState(null)
  const [heatmap, setHeatmap] = useState(null)
  const [channels, setChannels] = useState(null)
  const [quality, setQuality] = useState(null)
  const [loading, setLoading] = useState(true)

  const load = () => {
    setLoading(true)
    Promise.all([
      getFunnel(channel), getHeatmap(channel, 30), getChannelStats(),
      getAgentQualityMetrics().catch(() => null),
    ])
      .then(([f, h, c, q]) => {
        setFunnel(f)
        setHeatmap(h)
        setChannels(c)
        setQuality(q)
      })
      .catch(() => {
        setFunnel(null)
        setHeatmap(null)
        setChannels(null)
        setQuality(null)
      })
      .finally(() => setLoading(false))
  }
  useEffect(load, [channel])

  const stages = funnel?.stages || []
  const conv = stages[0]?.count ?? 0
  const leads = stages[1]?.count ?? 0
  const reservas = stages[2]?.count ?? 0

  return (
    <div>
      <PageHeader
        title="Analíticas"
        subtitle="Embudo de conversión y actividad del agente por canal."
        right={
          <div className="flex items-center gap-2">
            <ChannelTabs value={channel} onChange={setChannel} />
            <button onClick={load} className="btn-secondary px-4 py-2 text-xs" aria-label="Actualizar">
              <RefreshCw size={14} /> Actualizar
            </button>
          </div>
        }
      />

      {loading ? (
        <Loading />
      ) : (
        <div className="space-y-6">
          {/* KPIs del embudo */}
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <StatCard icon={MessageSquare} label="Conversaciones" value={conv} tone="hilton" />
            <StatCard icon={UserPlus} label="Leads captados" value={leads} tone="amber" />
            <StatCard icon={CalendarCheck} label="Reservas" value={reservas} tone="green" />
            <StatCard
              icon={TrendingDown}
              label="Conversión total"
              value={`${conv ? Math.round((reservas / conv) * 100) : 0}%`}
              tone="hilton"
            />
          </div>

          {/* Calidad del agente en soporte (post-venta): containment */}
          {quality && quality.total_tickets > 0 && (
            <Panel
              title="Calidad del agente · soporte al huésped"
              subtitle="Qué resuelve Aura sola vs. qué deriva al equipo (consultas de huéspedes con reserva)."
            >
              <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
                <div className="rounded-xl bg-green-50 px-4 py-3">
                  <p className="text-xs text-slatey">Resueltas sin humano</p>
                  <p className="mt-0.5 font-serif text-2xl font-700 tabular-nums text-green-700">{quality.containment_rate}%</p>
                </div>
                <div className="rounded-xl bg-mist px-4 py-3">
                  <p className="text-xs text-slatey">Auto-resueltas</p>
                  <p className="mt-0.5 font-serif text-2xl font-700 tabular-nums text-hilton-700">{quality.auto_resolved_tickets}</p>
                </div>
                <div className="rounded-xl bg-mist px-4 py-3">
                  <p className="text-xs text-slatey">Pedidos al staff</p>
                  <p className="mt-0.5 font-serif text-2xl font-700 tabular-nums text-hilton-700">{quality.service_requests}</p>
                </div>
                <div className="rounded-xl bg-amber-50 px-4 py-3">
                  <p className="text-xs text-slatey">Escaladas a humano</p>
                  <p className="mt-0.5 font-serif text-2xl font-700 tabular-nums text-amber-700">{quality.escalation_rate}%</p>
                </div>
              </div>
            </Panel>
          )}

          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            {/* Embudo */}
            <Panel title="Embudo de conversión" subtitle="De conversación a reserva confirmada.">
              {conv === 0 ? (
                <p className="py-8 text-center text-sm text-slatey">
                  Aún no hay conversaciones para este canal.
                </p>
              ) : (
                <>
                  <FunnelChart stages={stages} />
                  <ConversionRates rates={funnel?.conversion_rates} />
                </>
              )}
            </Panel>

            {/* Distribución por canal */}
            <Panel title="Conversaciones por canal" subtitle="Distribución real entre web y WhatsApp.">
              {(channels?.total_conversations ?? 0) === 0 ? (
                <p className="py-8 text-center text-sm text-slatey">Todavía no hay conversaciones registradas.</p>
              ) : (
                <ChannelBars channels={channels.channels} />
              )}
            </Panel>
          </div>

          {/* Mapa de calor */}
          <Panel
            title="Mapa de calor de actividad"
            subtitle="Cuándo conversan los huéspedes (últimos 30 días, por día y hora)."
          >
            {(heatmap?.total_conversations ?? 0) === 0 ? (
              <p className="py-8 text-center text-sm text-slatey">
                Sin actividad registrada en el período para este canal.
              </p>
            ) : (
              <Heatmap data={heatmap.data || []} maxCount={heatmap.max_count} />
            )}
          </Panel>
        </div>
      )}
    </div>
  )
}
