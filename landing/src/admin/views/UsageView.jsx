import { useEffect, useState } from 'react'
import { Coins, DollarSign, CalendarDays, ShieldAlert } from 'lucide-react'
import { getUsageSummary } from '../../services/api'
import { PageHeader, StatCard, Loading, formatNumber, formatUSD } from '../ui'

const formatTokens = (n) => formatNumber(n, 0)
const formatUsd = (n) => formatUSD(n, 4)

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
              El agente está pausado y no responderá hasta que baje el consumo o subas el tope.
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
