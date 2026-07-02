import { useEffect, useState } from 'react'
import { Gauge, Save, ShieldCheck, DollarSign, RefreshCw, Loader2, Power } from 'lucide-react'
import {
  getUsageSummary, getUsageConfig, updateUsageConfig, getAdminConfig,
  getExchangeRate, updateExchangeRate, getCentroConfig, updateCentroConfig,
} from '../../../services/api'
import { PageHeader, Loading, Badge, formatARS, formatDateTime } from '../../ui'
import { useAdminGate } from '../../components/useAdminGate'
import { toast } from '../../toast'

export default function LimitsView() {
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [savedMsg, setSavedMsg] = useState('')
  const [security, setSecurity] = useState(null)
  const { runProtected, gateModal } = useAdminGate()

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
    const payload = {
      daily_limit_usd: daily === '' ? null : Number(daily),
      monthly_limit_usd: monthly === '' ? null : Number(monthly),
      enabled,
    }
    try {
      await runProtected(async () => {
        await updateUsageConfig(payload)
        setSavedMsg('Topes guardados.')
        getUsageSummary().catch(() => {})
      })
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

      {gateModal}

      {/* Kill switch de la capa de configuración de agentes (Centro) */}
      <CentroSwitchPanel />

      {/* Tipo de cambio USD → ARS */}
      <ExchangeRatePanel />


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

// ── Panel del tipo de cambio USD → ARS ──────────────────────────────────────

function ExchangeRatePanel() {
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [savedMsg, setSavedMsg] = useState('')
  const [current, setCurrent] = useState(null)   // { rate, mode, source, updated_at }
  const [mode, setMode] = useState('auto')
  const [manualRate, setManualRate] = useState('')
  const { runProtected, gateModal } = useAdminGate()

  const load = () => {
    setLoading(true)
    getExchangeRate()
      .then((d) => {
        setCurrent(d.current || null)
        setMode(d.config?.mode || 'auto')
        setManualRate(d.config?.manual_rate ?? '')
      })
      .catch(() => setCurrent(null))
      .finally(() => setLoading(false))
  }
  useEffect(load, [])

  const save = async () => {
    if (mode === 'manual' && (manualRate === '' || isNaN(Number(manualRate)) || Number(manualRate) <= 0)) {
      setSavedMsg('Ingresá un valor manual válido.')
      setTimeout(() => setSavedMsg(''), 4000)
      return
    }
    setSaving(true)
    setSavedMsg('')
    try {
      await runProtected(async () => {
        const d = await updateExchangeRate({
          mode,
          manual_rate: mode === 'manual' ? Number(manualRate) : (manualRate === '' ? null : Number(manualRate)),
        })
        setCurrent(d.current || null)
        setSavedMsg('Cotización guardada.')
      })
    } catch {
      setSavedMsg('No se pudo guardar. Intentá de nuevo.')
    } finally {
      setSaving(false)
      setTimeout(() => setSavedMsg(''), 4000)
    }
  }

  return (
    <div className="mb-6 rounded-2xl bg-white p-5 shadow-card">
      {gateModal}
      <div className="mb-4 flex items-center gap-2">
        <DollarSign size={18} className="text-hilton-600" />
        <h2 className="font-serif text-lg font-600 text-ink">Tipo de cambio (USD → ARS)</h2>
        {current && (
          <Badge tone={current.mode === 'manual' ? 'amber' : 'green'}>
            {current.mode === 'manual' ? 'Manual' : 'Automático'}
          </Badge>
        )}
      </div>

      <p className="mb-4 text-sm text-slatey">
        Los precios se cargan en USD; el valor en pesos se calcula con esta cotización. En modo
        automático se toma el dólar oficial (venta); en manual, el valor que fijes vos.
      </p>

      {loading ? (
        <div className="flex items-center gap-2 text-sm text-slatey">
          <Loader2 size={15} className="animate-spin" /> Cargando…
        </div>
      ) : (
        <>
          {/* Cotización vigente */}
          {current && (
            <div className="mb-4 flex flex-wrap items-center gap-x-3 gap-y-1 rounded-xl bg-mist/60 px-4 py-3">
              <span className="font-display text-2xl font-700 tabular-nums text-ink">
                {formatARS(current.rate)}
              </span>
              <span className="text-xs text-slatey">por dólar</span>
              <span className="text-xs text-slatey">· {current.source}</span>
              {current.updated_at && (
                <span className="text-xs text-slatey">· act. {formatDateTime(current.updated_at)}</span>
              )}
            </div>
          )}

          {/* Selector de modo */}
          <div className="mb-4 inline-flex rounded-xl border border-hilton-200 p-1">
            <button
              onClick={() => setMode('auto')}
              className={`rounded-lg px-4 py-1.5 text-sm font-medium transition ${
                mode === 'auto' ? 'bg-hilton-600 text-white' : 'text-slatey hover:text-ink'
              }`}
            >
              Automático
            </button>
            <button
              onClick={() => setMode('manual')}
              className={`rounded-lg px-4 py-1.5 text-sm font-medium transition ${
                mode === 'manual' ? 'bg-hilton-600 text-white' : 'text-slatey hover:text-ink'
              }`}
            >
              Manual
            </button>
          </div>

          {mode === 'manual' ? (
            <label className="block max-w-xs">
              <span className="mb-1 block text-sm font-medium text-ink">Valor fijo (ARS por USD)</span>
              <input
                type="number" min="0" step="0.01" inputMode="decimal"
                value={manualRate} onChange={(e) => setManualRate(e.target.value)}
                placeholder="1050"
                className="w-full rounded-xl border border-hilton-200 px-3.5 py-2.5 text-sm focus:border-hilton-500 focus:outline-none focus:ring-2 focus:ring-hilton-100"
              />
            </label>
          ) : (
            <p className="flex items-center gap-1.5 text-sm text-slatey">
              <RefreshCw size={14} /> La cotización se actualiza sola desde el dólar oficial (se cachea ~15 min).
            </p>
          )}

          <div className="mt-5 flex items-center gap-3">
            <button
              onClick={save} disabled={saving}
              className="inline-flex items-center gap-2 rounded-xl bg-hilton-600 px-4 py-2.5 text-sm font-medium text-white shadow-card transition hover:bg-hilton-700 disabled:opacity-60"
            >
              {saving ? <Loader2 size={15} className="animate-spin" /> : <Save size={15} />}
              {saving ? 'Guardando…' : 'Guardar cotización'}
            </button>
            {savedMsg && <span className="text-sm text-slatey">{savedMsg}</span>}
          </div>
        </>
      )}
    </div>
  )
}

// Kill switch global de la capa de configuración de agentes (flujos + skills del Centro).
// Apagado → los empleados digitales corren con su comportamiento de fábrica, al instante.
// Con valores de fábrica el comportamiento es idéntico: este switch es el botón de emergencia.
function CentroSwitchPanel() {
  const { runProtected, gateModal } = useAdminGate()
  const [enabled, setEnabled] = useState(null)   // null = cargando
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    getCentroConfig()
      .then((c) => setEnabled(!!c.use_agent_config))
      .catch(() => setEnabled(true))
  }, [])

  const toggle = () => {
    const next = !enabled
    setSaving(true)
    runProtected(async () => {
      const c = await updateCentroConfig({ use_agent_config: next })
      setEnabled(!!c.use_agent_config)
      toast.success(next
        ? 'Configuración de agentes activada.'
        : 'Configuración de agentes desactivada: los agentes corren con su comportamiento de fábrica.')
    }).finally(() => setSaving(false))
  }

  return (
    <div className="mb-6 rounded-2xl bg-white p-5 shadow-card">
      {gateModal}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-start gap-2.5">
          <Power size={18} className="mt-0.5 text-hilton-600" />
          <div>
            <div className="flex items-center gap-2">
              <h2 className="font-serif text-lg font-600 text-ink">Configuración de agentes (Centro)</h2>
              {enabled != null && (
                <Badge tone={enabled ? 'green' : 'red'}>{enabled ? 'Activa' : 'Desactivada'}</Badge>
              )}
            </div>
            <p className="mt-1 max-w-xl text-sm text-slatey">
              Interruptor de emergencia: apagado, los empleados digitales ignoran los flujos y
              skills configurados y vuelven a su comportamiento de fábrica al instante.
            </p>
          </div>
        </div>
        <button
          onClick={toggle}
          disabled={enabled == null || saving}
          role="switch"
          aria-checked={!!enabled}
          className={`relative inline-flex h-7 w-13 shrink-0 items-center rounded-full transition disabled:opacity-50 ${
            enabled ? 'bg-hilton-600' : 'bg-stone-300'
          }`}
          style={{ width: '3.25rem' }}
        >
          <span className={`inline-block h-6 w-6 transform rounded-full bg-white shadow transition ${
            enabled ? 'translate-x-6' : 'translate-x-0.5'
          }`} />
        </button>
      </div>
    </div>
  )
}
