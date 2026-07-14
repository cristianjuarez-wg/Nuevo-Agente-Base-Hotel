import { useEffect, useState } from 'react'
import { Coins, DollarSign, CalendarDays, ShieldAlert, MessageCircle } from 'lucide-react'
import { getUsageSummary } from '../../services/api'
import { PageHeader, StatCard, Loading, formatNumber, formatUSD } from '../ui'

const formatTokens = (n) => formatNumber(n, 0)
const formatUsd = (n) => formatUSD(n, 2)
const formatCostPerConv = (usd, convs) => {
  if (!convs) return '—'
  return formatUSD(usd / convs, 2)
}

// Barra de progreso consumo/tope. Antes solo se veía `blocked` (rojo o nada); ahora el dueño
// ve cuánto le queda antes del corte. Verde <70%, ámbar <100%, rojo al llegar al tope.
function LimitBar({ label, spent, limit }) {
  if (limit == null) return null
  const pct = limit > 0 ? Math.min((spent / limit) * 100, 100) : 0
  const tone = pct >= 100 ? 'bg-red-500' : pct >= 70 ? 'bg-amber-500' : 'bg-green-500'
  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-sm">
        <span className="text-slatey">{label}</span>
        <span className="tabular-nums text-ink">
          {formatUsd(spent)} <span className="text-slatey">/ {formatUsd(limit)}</span>
          <span className="ml-1.5 text-xs text-slatey">({Math.round(pct)}%)</span>
        </span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-mist">
        <div className={`h-full rounded-full transition-all ${tone}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

export default function UsageView() {
  const [summary, setSummary] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    getUsageSummary()
      .then(setSummary)
      .catch(() => setSummary(null))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <Loading label="Cargando consumo…" />

  const today = summary?.today ?? { tokens: 0, usd: 0, by_model: [] }
  const month = summary?.month ?? { tokens: 0, usd: 0, by_model: [] }
  const blocked = summary?.blocked
  const limits = summary?.limits ?? { enabled: false }
  const hasLimits = limits.enabled && (limits.daily_limit_usd != null || limits.monthly_limit_usd != null)
  // Mensaje del bloqueo, diferenciando cuál tope se superó.
  const blockedMsg = summary?.daily_exceeded && summary?.monthly_exceeded
    ? 'Se superaron los topes diario y mensual.'
    : summary?.daily_exceeded ? 'Se superó el tope diario.'
    : summary?.monthly_exceeded ? 'Se superó el tope mensual.' : ''

  return (
    <div>
      <PageHeader
        title="Consumo IA"
        subtitle="Tokens y costo estimado del agente Aura. Los topes de gasto se configuran en Límites y seguridad."
      />

      {blocked && (
        <div className="mb-5 flex items-start gap-3 rounded-2xl border border-red-200 bg-red-50 p-4 text-red-700">
          <ShieldAlert size={20} className="mt-0.5 shrink-0" />
          <div>
            <p className="font-semibold">Tope de gasto alcanzado</p>
            <p className="text-sm">
              {blockedMsg} El agente está pausado y no responderá hasta que baje el consumo o subas el tope.
            </p>
          </div>
        </div>
      )}

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard icon={Coins} label="Tokens hoy" value={formatTokens(today.tokens)} tone="hilton" />
        <StatCard icon={DollarSign} label="USD hoy (estimado)" value={formatUsd(today.usd)} tone="green" />
        <StatCard icon={CalendarDays} label="Tokens este mes" value={formatTokens(month.tokens)} tone="hilton" />
        <StatCard icon={DollarSign} label="USD este mes (estimado)" value={formatUsd(month.usd)} tone="amber" />
      </div>

      <div className="mt-4 grid grid-cols-2 gap-4 lg:grid-cols-3">
        <StatCard icon={MessageCircle} label="Conversaciones hoy" value={formatNumber(today.conversations, 0)} tone="hilton" />
        <StatCard icon={MessageCircle} label="Conversaciones este mes" value={formatNumber(month.conversations, 0)} tone="hilton" />
        <StatCard
          icon={DollarSign}
          label="Costo por conversación (mes)"
          value={formatCostPerConv(month.usd, month.conversations)}
          tone="green"
        />
      </div>

      {/* Progreso hacia el tope de gasto: para que el corte no llegue de golpe. */}
      {hasLimits && (
        <div className="mt-6 rounded-2xl bg-white p-5 shadow-card">
          <h2 className="mb-4 font-serif text-lg font-600 text-ink">Progreso hacia el tope</h2>
          <div className="space-y-4">
            <LimitBar label="Gasto de hoy" spent={today.usd} limit={limits.daily_limit_usd} />
            <LimitBar label="Gasto del mes" spent={month.usd} limit={limits.monthly_limit_usd} />
          </div>
          <p className="mt-3 text-xs text-slatey">Los topes se configuran en Límites y seguridad.</p>
        </div>
      )}

      {/* Desglose por modelo (mes) */}
      <div className="mt-6 rounded-2xl bg-white p-5 shadow-card">
        <h2 className="mb-4 font-serif text-lg font-600 text-ink">Desglose por modelo (este mes)</h2>
        {month.by_model?.length ? (
          <ul className="divide-y divide-mist">
            {month.by_model.map((m) => (
              <li key={m.model} className="flex items-center justify-between py-3 text-sm">
                <span className="font-medium text-ink">{m.model}</span>
                <span className="flex items-center gap-4 text-slatey">
                  <span className="tabular-nums">{formatTokens(m.tokens)} tokens</span>
                  <span className="font-semibold tabular-nums text-hilton-700">{formatUsd(m.usd)}</span>
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="py-4 text-center text-sm text-slatey">Todavía no hay consumo registrado este mes.</p>
        )}
      </div>
    </div>
  )
}
