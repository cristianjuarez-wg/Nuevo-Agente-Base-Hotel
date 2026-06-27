import { useEffect, useState } from 'react'
import { MessageCircle, CheckCircle2, ArrowUpRight, PiggyBank, UserCheck, Coins, DollarSign,
  ClipboardList, Send, Settings2, X } from 'lucide-react'
import {
  getAgentPerformance, getAgentDailyReport, updateAgentDailyReportConfig,
  sendAgentDailyReport, listStaff,
} from '../../../services/api'
import { StatCard, Loading, formatNumber, formatUSD } from '../../ui'
import PeriodSelector from '../../components/PeriodSelector'
import { toast } from '../../toast'
import { useAdminGate } from '../../components/useAdminGate'

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

      {/* Parte de fin de día (siempre se muestra; el envío es opt-in) */}
      <DailyReportCard agent={agent} />

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

// Card del "parte de fin de día": muestra el texto del parte de hoy y permite enviarlo
// (opt-in) a los miembros del staff configurados. El envío NUNCA es por defecto.
function DailyReportCard({ agent }) {
  const { runProtected, gateModal } = useAdminGate()
  const [data, setData] = useState(null)
  const [configuring, setConfiguring] = useState(false)
  const [sending, setSending] = useState(false)

  const load = () => getAgentDailyReport(agent.id).then(setData).catch(() => setData(null))
  useEffect(() => { load() }, [agent.id])

  const cfg = data?.config ?? { enabled: false, recipient_staff_ids: [] }
  const recipients = cfg.recipient_staff_ids?.length || 0

  const sendNow = () => {
    if (recipients === 0) {
      toast.error('No hay destinatarios. Configurá el envío primero.')
      setConfiguring(true)
      return
    }
    setSending(true)
    runProtected(async () => {
      const res = await sendAgentDailyReport(agent.id)
      const ok = res.sent?.length || 0
      const skip = res.skipped?.length || 0
      if (ok) toast.success(`Parte enviado a ${ok} destinatario${ok > 1 ? 's' : ''}.`)
      else toast.error(`No se pudo enviar (${skip} omitido${skip > 1 ? 's' : ''}). Revisá los teléfonos / WhatsApp.`)
    }).finally(() => setSending(false))
  }

  return (
    <div className="mb-6 rounded-2xl border border-hilton-100 bg-linen p-5 shadow-card">
      {gateModal}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-hilton-600 text-white">
            <ClipboardList size={18} />
          </div>
          <div className="min-w-0">
            <h3 className="font-serif text-base font-600 text-ink">Parte de fin de día</h3>
            <p className="mt-1 text-sm text-ink/80">{data?.text || 'Calculando…'}</p>
            <p className="mt-1.5 text-xs text-slatey">
              {cfg.enabled
                ? `Envío automático activo · ${recipients} destinatario${recipients !== 1 ? 's' : ''}`
                : 'Envío automático desactivado'}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setConfiguring(true)}
            className="inline-flex items-center gap-1.5 rounded-xl bg-white px-3 py-2 text-sm font-medium text-slatey ring-1 ring-mist hover:bg-mist"
          >
            <Settings2 size={15} /> Configurar envío
          </button>
          <button
            onClick={sendNow}
            disabled={sending}
            className="inline-flex items-center gap-1.5 rounded-xl bg-hilton-600 px-3 py-2 text-sm font-medium text-white hover:bg-hilton-700 disabled:opacity-50"
          >
            <Send size={15} /> {sending ? 'Enviando…' : 'Enviar ahora'}
          </button>
        </div>
      </div>

      {configuring && (
        <DailyReportConfigModal
          agent={agent}
          config={cfg}
          onClose={() => setConfiguring(false)}
          onSaved={() => { setConfiguring(false); load() }}
          runProtected={runProtected}
        />
      )}
    </div>
  )
}

function DailyReportConfigModal({ agent, config, onClose, onSaved, runProtected }) {
  const [enabled, setEnabled] = useState(!!config.enabled)
  const [selected, setSelected] = useState(config.recipient_staff_ids || [])
  const [staff, setStaff] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    listStaff().then((list) => setStaff(list || [])).catch(() => setStaff([])).finally(() => setLoading(false))
  }, [])

  const toggle = (id) =>
    setSelected((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]))

  const save = () =>
    runProtected(async () => {
      await updateAgentDailyReportConfig(agent.id, { enabled, recipient_staff_ids: selected })
      toast.success('Configuración guardada')
      onSaved()
    })

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center sm:items-center">
      <div className="absolute inset-0 bg-ink/40" onClick={onClose} />
      <div className="relative max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-t-3xl bg-white p-6 shadow-card-lg animate-slide-up sm:rounded-3xl">
        <header className="mb-5 flex items-center justify-between">
          <h3 className="font-serif text-lg font-700 text-ink">Envío del parte — {agent.name}</h3>
          <button onClick={onClose} aria-label="Cerrar" className="rounded-lg p-1.5 text-slatey hover:bg-mist">
            <X size={20} />
          </button>
        </header>

        {/* Switch activo/inactivo */}
        <label className="mb-4 flex items-center justify-between gap-3 rounded-xl bg-mist px-4 py-3">
          <span className="text-sm font-medium text-ink">Envío automático diario</span>
          <input
            type="checkbox"
            checked={enabled}
            onChange={(e) => setEnabled(e.target.checked)}
            className="h-5 w-5 rounded border-hilton-300 text-hilton-600 focus:ring-hilton-200"
          />
        </label>

        <p className="mb-2 text-sm font-medium text-ink">Destinatarios (equipo)</p>
        {loading ? (
          <p className="py-4 text-center text-sm text-slatey">Cargando equipo…</p>
        ) : staff.length === 0 ? (
          <p className="py-4 text-center text-sm text-slatey">No hay miembros del equipo cargados.</p>
        ) : (
          <ul className="mb-5 max-h-56 divide-y divide-mist overflow-y-auto rounded-xl border border-mist">
            {staff.map((s) => (
              <li key={s.id}>
                <label className="flex cursor-pointer items-center gap-3 px-3.5 py-2.5 text-sm hover:bg-mist">
                  <input
                    type="checkbox"
                    checked={selected.includes(s.id)}
                    onChange={() => toggle(s.id)}
                    className="h-4 w-4 rounded border-hilton-300 text-hilton-600 focus:ring-hilton-200"
                  />
                  <span className="font-medium text-ink">{s.name}</span>
                  <span className="ml-auto tabular-nums text-xs text-slatey">{s.phone}</span>
                </label>
              </li>
            ))}
          </ul>
        )}

        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="rounded-xl px-4 py-2 text-sm font-medium text-slatey hover:bg-mist">
            Cancelar
          </button>
          <button onClick={save} className="rounded-xl bg-hilton-600 px-4 py-2 text-sm font-medium text-white hover:bg-hilton-700">
            Guardar
          </button>
        </div>
      </div>
    </div>
  )
}
