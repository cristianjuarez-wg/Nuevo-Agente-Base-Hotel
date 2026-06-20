import { useEffect, useState } from 'react'
import { Gauge, Save, ShieldCheck } from 'lucide-react'
import { getUsageSummary, getUsageConfig, updateUsageConfig, getAdminConfig } from '../../../services/api'
import { PageHeader, Loading, Badge } from '../../ui'

export default function LimitsView() {
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [savedMsg, setSavedMsg] = useState('')
  const [security, setSecurity] = useState(null)

  // Form de topes
  const [daily, setDaily] = useState('')
  const [monthly, setMonthly] = useState('')
  const [enabled, setEnabled] = useState(false)

  useEffect(() => {
    setLoading(true)
    Promise.all([
      getUsageConfig().catch(() => null),
      getAdminConfig().catch(() => null),
    ])
      .then(([c, admin]) => {
        if (c) {
          setDaily(c.daily_limit_usd ?? '')
          setMonthly(c.monthly_limit_usd ?? '')
          setEnabled(!!c.enabled)
        }
        setSecurity(admin?.security_config ?? null)
      })
      .finally(() => setLoading(false))
  }, [])

  const save = async () => {
    setSaving(true)
    setSavedMsg('')
    try {
      const payload = {
        daily_limit_usd: daily === '' ? null : Number(daily),
        monthly_limit_usd: monthly === '' ? null : Number(monthly),
        enabled,
      }
      await updateUsageConfig(payload)
      setSavedMsg('Topes guardados.')
      getUsageSummary().catch(() => {})
    } catch (e) {
      setSavedMsg('No se pudo guardar. Intentá de nuevo.')
    } finally {
      setSaving(false)
      setTimeout(() => setSavedMsg(''), 4000)
    }
  }

  if (loading) return <Loading label="Cargando configuración…" />

  return (
    <div>
      <PageHeader
        title="Límites y seguridad"
        subtitle="Protegé la cuenta del agente: topes de gasto y límite de mensajes por usuario."
      />

      {/* Topes de gasto */}
      <div className="rounded-2xl bg-white p-5 shadow-card">
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

      {/* Rate limit (read-only) */}
      <div className="mt-6 rounded-2xl bg-white p-5 shadow-card">
        <div className="mb-4 flex items-center gap-2">
          <ShieldCheck size={18} className="text-hilton-600" />
          <h2 className="font-serif text-lg font-600 text-ink">Protección contra abuso</h2>
          <Badge tone={security?.rate_limit_enabled ? 'green' : 'gray'}>
            {security?.rate_limit_enabled ? 'Activa' : 'Inactiva'}
          </Badge>
        </div>
        <p className="mb-4 text-sm text-slatey">
          El agente limita automáticamente cuántos mensajes puede enviar un mismo usuario, para evitar
          bots y uso abusivo. Estos valores se configuran en el servidor.
        </p>
        <div className="grid grid-cols-2 gap-4">
          <div className="rounded-xl bg-mist/60 p-4">
            <p className="font-serif text-2xl font-700 tabular-nums text-ink">
              {security?.rate_limit_per_minute ?? '—'}
            </p>
            <p className="text-xs text-slatey">mensajes por minuto / usuario</p>
          </div>
          <div className="rounded-xl bg-mist/60 p-4">
            <p className="font-serif text-2xl font-700 tabular-nums text-ink">
              {security?.rate_limit_per_hour ?? '—'}
            </p>
            <p className="text-xs text-slatey">mensajes por hora / usuario</p>
          </div>
        </div>
      </div>
    </div>
  )
}
