import { useEffect, useState } from 'react'
import { Coins, DollarSign, CalendarDays, Gauge, ShieldAlert, Save } from 'lucide-react'
import { getUsageSummary, getUsageConfig, updateUsageConfig } from '../../services/api'
import { PageHeader, StatCard, Loading, Badge } from '../ui'

function formatTokens(n) {
  if (n == null) return '—'
  return new Intl.NumberFormat('es-AR', { maximumFractionDigits: 0 }).format(n)
}

function formatUsd(n) {
  if (n == null) return '—'
  return `$${Number(n).toFixed(4)}`
}

export default function UsageView() {
  const [summary, setSummary] = useState(null)
  const [config, setConfig] = useState(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [savedMsg, setSavedMsg] = useState('')

  // Form de topes
  const [daily, setDaily] = useState('')
  const [monthly, setMonthly] = useState('')
  const [enabled, setEnabled] = useState(false)

  const load = () => {
    setLoading(true)
    Promise.all([getUsageSummary().catch(() => null), getUsageConfig().catch(() => null)])
      .then(([s, c]) => {
        setSummary(s)
        setConfig(c)
        if (c) {
          setDaily(c.daily_limit_usd ?? '')
          setMonthly(c.monthly_limit_usd ?? '')
          setEnabled(!!c.enabled)
        }
      })
      .finally(() => setLoading(false))
  }

  useEffect(load, [])

  const save = async () => {
    setSaving(true)
    setSavedMsg('')
    try {
      const payload = {
        daily_limit_usd: daily === '' ? null : Number(daily),
        monthly_limit_usd: monthly === '' ? null : Number(monthly),
        enabled,
      }
      const updated = await updateUsageConfig(payload)
      setConfig(updated)
      setSavedMsg('Topes guardados.')
      // Refrescar el resumen para recalcular bloqueo.
      getUsageSummary().then(setSummary).catch(() => {})
    } catch (e) {
      setSavedMsg('No se pudo guardar. Intentá de nuevo.')
    } finally {
      setSaving(false)
      setTimeout(() => setSavedMsg(''), 4000)
    }
  }

  if (loading) return <Loading label="Cargando consumo…" />

  const today = summary?.today ?? { tokens: 0, usd: 0, by_model: [] }
  const month = summary?.month ?? { tokens: 0, usd: 0, by_model: [] }
  const blocked = summary?.blocked

  return (
    <div>
      <PageHeader
        title="Consumo IA"
        subtitle="Tokens y costo estimado del agente Aura. Configurá topes de gasto para proteger la cuenta."
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

      {/* Topes de gasto */}
      <div className="mt-6 rounded-2xl bg-white p-5 shadow-card">
        <div className="mb-4 flex items-center gap-2">
          <Gauge size={18} className="text-hilton-600" />
          <h2 className="font-serif text-lg font-600 text-ink">Topes de gasto</h2>
          <Badge tone={enabled ? 'green' : 'gray'}>{enabled ? 'Activo' : 'Inactivo'}</Badge>
        </div>

        <p className="mb-4 text-sm text-slatey">
          Cuando el gasto estimado supera un tope, el agente se pausa automáticamente y deja de consumir tokens.
          Dejá un campo vacío para no aplicar ese tope.
        </p>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <label className="block">
            <span className="mb-1 block text-sm font-medium text-ink">Tope diario (USD)</span>
            <input
              type="number" min="0" step="0.01" inputMode="decimal"
              value={daily}
              onChange={(e) => setDaily(e.target.value)}
              placeholder="Sin tope"
              className="w-full rounded-xl border border-hilton-200 px-3.5 py-2.5 text-sm focus:border-hilton-500 focus:outline-none focus:ring-2 focus:ring-hilton-100"
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-sm font-medium text-ink">Tope mensual (USD)</span>
            <input
              type="number" min="0" step="0.01" inputMode="decimal"
              value={monthly}
              onChange={(e) => setMonthly(e.target.value)}
              placeholder="Sin tope"
              className="w-full rounded-xl border border-hilton-200 px-3.5 py-2.5 text-sm focus:border-hilton-500 focus:outline-none focus:ring-2 focus:ring-hilton-100"
            />
          </label>
        </div>

        <label className="mt-4 flex items-center gap-3">
          <input
            type="checkbox"
            checked={enabled}
            onChange={(e) => setEnabled(e.target.checked)}
            className="h-4 w-4 rounded border-hilton-300 text-hilton-600 focus:ring-hilton-200"
          />
          <span className="text-sm text-ink">Activar tope (pausar el agente al superar el límite)</span>
        </label>

        <div className="mt-5 flex items-center gap-3">
          <button
            onClick={save}
            disabled={saving}
            className="inline-flex items-center gap-2 rounded-xl bg-hilton-600 px-4 py-2.5 text-sm font-medium text-white shadow-card transition hover:bg-hilton-700 disabled:opacity-60"
          >
            <Save size={16} />
            {saving ? 'Guardando…' : 'Guardar topes'}
          </button>
          {savedMsg && <span className="text-sm text-slatey">{savedMsg}</span>}
        </div>

        <p className="mt-4 text-xs text-slatey">
          Los importes en USD son una estimación según las tarifas publicadas de OpenAI; pueden variar.
        </p>
      </div>
    </div>
  )
}
