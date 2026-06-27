import { useEffect, useState } from 'react'
import { MessageCircle, CheckCircle2, ArrowUpRight, PiggyBank, UserCheck, Coins, DollarSign } from 'lucide-react'
import { getAgentPerformance } from '../../../services/api'
import { StatCard, Loading, formatNumber, formatUSD } from '../../ui'
import PeriodSelector from '../../components/PeriodSelector'

// Métricas de DESEMPEÑO del agente (cómo trabajó), separadas de su costo de IA (cuánto
// salió). Dos miradas distintas en el mismo legajo: la del supervisor y la del que paga.
export default function EmployeeMetrics({ agent }) {
  const [period, setPeriod] = useState('mes')
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    getAgentPerformance(agent.id, period)
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false))
  }, [agent.id, period])

  const perf = data?.performance ?? {}
  const cost = data?.cost ?? { tokens: 0, usd: 0, by_model: [] }

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h2 className="font-serif text-lg font-600 text-ink">Desempeño de {agent.name}</h2>
        <PeriodSelector value={period} onChange={setPeriod} />
      </div>

      {loading ? (
        <Loading label="Cargando desempeño…" />
      ) : (
        <>
          {/* Desempeño (cómo trabajó) */}
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <StatCard icon={MessageCircle} label="Conversaciones atendidas" value={formatNumber(perf.conversations || 0, 0)} tone="hilton" />
            {agent.role === 'guest' && (
              <>
                <StatCard icon={UserCheck} label="Leads convertidos" value={formatNumber(perf.leads_converted || 0, 0)} tone="green" />
                <StatCard icon={CheckCircle2} label="Reservas directas" value={formatNumber(perf.bookings_closed || 0, 0)} tone="hilton" />
                <StatCard icon={PiggyBank} label="Ahorro comisión OTA" value={formatUSD(perf.ota_savings_usd || 0, 0)} tone="green" />
              </>
            )}
            {agent.role === 'staff' && (
              <>
                <StatCard icon={CheckCircle2} label="Tickets resueltos" value={formatNumber(perf.resolved || 0, 0)} tone="green" />
                <StatCard icon={ArrowUpRight} label="Escalados a humano" value={formatNumber(perf.escalated || 0, 0)} tone="amber" />
              </>
            )}
          </div>

          {/* Costo de IA (cuánto salió) */}
          <div className="mt-6 rounded-2xl bg-white p-5 shadow-card">
            <h3 className="mb-4 font-serif text-base font-600 text-ink">Consumo de IA de este agente</h3>
            <div className="grid grid-cols-2 gap-4 lg:grid-cols-3">
              <StatCard icon={Coins} label="Tokens" value={formatNumber(cost.tokens || 0, 0)} tone="hilton" />
              <StatCard icon={DollarSign} label="Costo estimado (USD)" value={formatUSD(cost.usd || 0, 2)} tone="amber" />
            </div>
            {cost.by_model?.length > 0 && (
              <ul className="mt-4 divide-y divide-mist">
                {cost.by_model.map((m) => (
                  <li key={m.model} className="flex items-center justify-between py-2.5 text-sm">
                    <span className="font-medium text-ink">{m.model}</span>
                    <span className="flex items-center gap-4 text-slatey">
                      <span className="tabular-nums">{formatNumber(m.tokens, 0)} tokens</span>
                      <span className="font-semibold tabular-nums text-hilton-700">{formatUSD(m.usd, 2)}</span>
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </>
      )}
    </div>
  )
}
