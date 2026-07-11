import { useEffect, useState } from 'react'
import { Headphones, Save } from 'lucide-react'
import { getHumanAttention, updateHumanAttention } from '../../../services/api'
import { PageHeader, Loading, Badge } from '../../ui'
import { useAdminGate } from '../../components/useAdminGate'
import { toast } from '../../toast'

// 0 = lunes … 6 = domingo (coincide con datetime.weekday() del backend).
const DIAS = [
  { k: '0', label: 'Lunes' }, { k: '1', label: 'Martes' }, { k: '2', label: 'Miércoles' },
  { k: '3', label: 'Jueves' }, { k: '4', label: 'Viernes' }, { k: '5', label: 'Sábado' },
  { k: '6', label: 'Domingo' },
]
const _defDia = () => ({ active: false, from: '09:00', to: '18:00' })

export default function AtencionHumanaView() {
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [enabled, setEnabled] = useState(false)
  const [onCall, setOnCall] = useState(false)
  const [schedule, setSchedule] = useState(() =>
    Object.fromEntries(DIAS.map((d) => [d.k, _defDia()])))
  const [availableNow, setAvailableNow] = useState(false)
  const { runProtected, gateModal } = useAdminGate()

  useEffect(() => {
    setLoading(true)
    getHumanAttention()
      .then((d) => {
        const cfg = d?.config || {}
        setEnabled(!!cfg.enabled)
        setOnCall(!!cfg.on_call)
        setSchedule(Object.fromEntries(DIAS.map((day) => [day.k, { ..._defDia(), ...(cfg.schedule?.[day.k] || {}) }])))
        setAvailableNow(!!d?.available_now)
      })
      .catch(() => toast.error('No se pudo cargar la configuración de atención humana'))
      .finally(() => setLoading(false))
  }, [])

  const setDia = (k, patch) => setSchedule((prev) => ({ ...prev, [k]: { ...prev[k], ...patch } }))

  const save = async () => {
    setSaving(true)
    try {
      await runProtected(async () => {
        const d = await updateHumanAttention({ enabled, on_call: onCall, schedule })
        setAvailableNow(!!d?.available_now)
        toast.success('Atención humana actualizada')
      })
    } catch (e) {
      toast.error('No se pudo guardar. Intentá de nuevo.')
    } finally {
      setSaving(false)
    }
  }

  if (loading) return <Loading label="Cargando…" />

  return (
    <div>
      <PageHeader
        title="Atención humana"
        subtitle="Cuándo hay una persona para tomar conversaciones en vivo. Aura solo ofrece pasar con alguien si hay atención disponible."
      />
      {gateModal}

      {/* Estado actual */}
      <div className="mb-4 flex flex-wrap items-center gap-3 rounded-2xl bg-white p-5 shadow-card">
        <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-hilton-50 text-hilton-600">
          <Headphones size={18} />
        </span>
        <div className="flex-1">
          <p className="text-sm font-semibold text-ink">Disponibilidad ahora</p>
          <p className="text-xs text-slatey">Según la guardia y el horario configurado, en hora local del hotel.</p>
        </div>
        <Badge tone={availableNow ? 'green' : 'gray'}>
          {availableNow ? 'Hay atención disponible' : 'Sin atención en vivo'}
        </Badge>
      </div>

      {/* Interruptores */}
      <div className="mb-4 rounded-2xl bg-white p-5 shadow-card">
        <label className="flex items-center justify-between gap-4 py-1">
          <span>
            <span className="block text-sm font-semibold text-ink">Función activada</span>
            <span className="block text-xs text-slatey">Si está apagada, Aura nunca ofrece pasar con una persona.</span>
          </span>
          <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)}
                 className="h-5 w-5 accent-hilton-600" />
        </label>
        <label className="mt-3 flex items-center justify-between gap-4 border-t border-hilton-100 pt-3">
          <span>
            <span className="block text-sm font-semibold text-ink">Guardia activa ahora</span>
            <span className="block text-xs text-slatey">Hay alguien de guardia en este momento, sin importar el horario.</span>
          </span>
          <input type="checkbox" checked={onCall} onChange={(e) => setOnCall(e.target.checked)}
                 disabled={!enabled} className="h-5 w-5 accent-hilton-600 disabled:opacity-40" />
        </label>
      </div>

      {/* Horario por día */}
      <div className={`rounded-2xl bg-white p-5 shadow-card ${!enabled ? 'opacity-50' : ''}`}>
        <p className="mb-3 text-sm font-semibold text-ink">Horario de atención</p>
        <div className="flex flex-col gap-2">
          {DIAS.map((d) => {
            const cfg = schedule[d.k] || _defDia()
            return (
              <div key={d.k} className="flex flex-wrap items-center gap-3">
                <label className="flex w-32 items-center gap-2">
                  <input type="checkbox" checked={cfg.active} disabled={!enabled}
                         onChange={(e) => setDia(d.k, { active: e.target.checked })}
                         className="h-4 w-4 accent-hilton-600 disabled:opacity-40" />
                  <span className="text-sm text-ink">{d.label}</span>
                </label>
                <input type="time" value={cfg.from} disabled={!enabled || !cfg.active}
                       onChange={(e) => setDia(d.k, { from: e.target.value })}
                       className="rounded-lg border border-hilton-200 px-2 py-1 text-sm disabled:opacity-40" />
                <span className="text-slatey">a</span>
                <input type="time" value={cfg.to} disabled={!enabled || !cfg.active}
                       onChange={(e) => setDia(d.k, { to: e.target.value })}
                       className="rounded-lg border border-hilton-200 px-2 py-1 text-sm disabled:opacity-40" />
                {!cfg.active && <span className="text-xs text-slatey/60">cerrado</span>}
              </div>
            )
          })}
        </div>
      </div>

      <div className="mt-5">
        <button onClick={save} disabled={saving}
                className="inline-flex items-center gap-2 rounded-xl bg-hilton-600 px-4 py-2 text-sm font-medium text-white hover:bg-hilton-700 disabled:opacity-50">
          <Save size={15} /> {saving ? 'Guardando…' : 'Guardar'}
        </button>
      </div>
    </div>
  )
}
