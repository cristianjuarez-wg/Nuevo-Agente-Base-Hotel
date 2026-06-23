import { useState } from 'react'
import { CalendarClock, Check, Loader2, BedDouble } from 'lucide-react'
import { getStrings } from '../../i18n/chat'
import { createTableReservation } from '../../services/api'

// Fecha de hoy en YYYY-MM-DD (para el min del input).
function todayISO() {
  const t = new Date()
  return `${t.getFullYear()}-${String(t.getMonth() + 1).padStart(2, '0')}-${String(t.getDate()).padStart(2, '0')}`
}

function Stepper({ label, value, set, min = 1, max = 20 }) {
  return (
    <div className="flex items-center justify-between">
      <p className="text-sm font-medium text-ink">{label}</p>
      <div className="flex items-center gap-2">
        <button type="button" onClick={() => set(Math.max(min, value - 1))} disabled={value <= min}
          className="flex h-7 w-7 items-center justify-center rounded-full border border-stone-200 text-ink transition hover:bg-stone-50 disabled:opacity-40">–</button>
        <span className="w-5 text-center text-sm font-semibold tabular-nums text-ink">{value}</span>
        <button type="button" onClick={() => set(Math.min(max, value + 1))} disabled={value >= max}
          className="flex h-7 w-7 items-center justify-center rounded-full border border-stone-200 text-ink transition hover:bg-stone-50 disabled:opacity-40">+</button>
      </div>
    </div>
  )
}

/**
 * Selector de reserva de mesa embebido en el chat (Fase 2). Estilo el DatePickerCard.
 * Props: card { slots:{almuerzo:[],cena:[]}, session_id, preset }, onAction, lang
 */
export default function TableReservationCard({ card, onAction, lang = 'es' }) {
  const t = getStrings(lang)
  const slots = card.slots || {}
  const preset = card.preset || {}

  const [fecha, setFecha] = useState(preset.fecha || '')
  const [franja, setFranja] = useState(preset.franja === 'almuerzo' ? 'almuerzo' : 'cena')  // almuerzo | cena
  const [hora, setHora] = useState(preset.hora || '')
  const [personas, setPersonas] = useState(preset.personas || 2)
  const [nombre, setNombre] = useState(preset.nombre || '')
  const [isGuest, setIsGuest] = useState(false)
  const [code, setCode] = useState('')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const [done, setDone] = useState(null)

  const horarios = slots[franja] || []

  const confirm = async () => {
    if (!fecha) { setError(t.tableErrDate); return }
    if (!hora) { setError(t.tableErrSlot); return }
    if (!nombre.trim()) { setError(t.tableErrName); return }
    setError('')
    setSaving(true)
    try {
      const r = await createTableReservation({
        fecha, hora, party_size: personas,
        guest_name: nombre.trim(),
        booking_code: isGuest && code.trim() ? code.trim().toUpperCase() : null,
        session_id: card.session_id || null,
      })
      if (r?.error) { setError(r.error); setSaving(false); return }
      setDone(r)
      if (r?.code) onAction?.({ kind: 'send_message', message: t.tableConfirmedMsg(r.code) })
    } catch (e) {
      setError(e?.response?.data?.detail || t.tableError)
      setSaving(false)
    }
  }

  if (done) {
    return (
      <div className="overflow-hidden rounded-2xl border border-stone-200 bg-white shadow-card">
        <div className="p-4 text-center">
          <div className="mx-auto mb-2 flex h-11 w-11 items-center justify-center rounded-full bg-forest-100 text-forest-600">
            <Check size={22} />
          </div>
          <p className="font-display text-base font-600 text-ink">{t.tableConfirmed}</p>
          <p className="text-xs text-slatey">{t.code} <strong>{done.code}</strong></p>
          <p className="mt-1 text-xs text-slatey">
            {fecha} · {hora} · {personas} {personas === 1 ? t.tablePerson : t.tablePeople}
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="overflow-hidden rounded-2xl border border-stone-200 bg-white shadow-card">
      <div className="flex items-center gap-2 bg-linen px-4 py-2.5">
        <CalendarClock size={16} className="text-hilton-600" />
        <p className="text-sm font-medium text-ink">{t.tableTitle}</p>
      </div>

      <div className="space-y-3 p-4">
        {/* Día */}
        <label className="block">
          <span className="mb-1 block text-[11px] uppercase tracking-wide text-slatey">{t.tableDay}</span>
          <input type="date" value={fecha} min={todayISO()} onChange={(e) => setFecha(e.target.value)}
            className="w-full rounded-xl border border-stone-200 bg-linen px-2.5 py-2 text-sm text-ink focus:border-hilton-300 focus:bg-white focus:outline-none focus:ring-2 focus:ring-hilton-100" />
        </label>

        {/* Turno: almuerzo / cena */}
        <div>
          <span className="mb-1 block text-[11px] uppercase tracking-wide text-slatey">{t.tableShift}</span>
          <div className="flex gap-2">
            {Object.keys(slots).map((f) => (
              <button key={f} onClick={() => { setFranja(f); setHora('') }}
                className={`flex-1 rounded-xl px-3 py-1.5 text-xs font-medium transition ${
                  franja === f ? 'bg-hilton-600 text-white' : 'bg-stone-50 text-slatey hover:bg-stone-100'
                }`}>{t.tableShiftName(f)}</button>
            ))}
          </div>
        </div>

        {/* Horarios del turno */}
        <div className="flex flex-wrap gap-1.5">
          {horarios.map((h) => (
            <button key={h} onClick={() => setHora(h)}
              className={`rounded-lg px-2.5 py-1 text-xs font-medium tabular-nums transition ${
                hora === h ? 'bg-hilton-600 text-white' : 'bg-stone-50 text-slatey hover:bg-stone-100'
              }`}>{h}</button>
          ))}
        </div>

        {/* Personas */}
        <div className="rounded-xl border border-stone-200 p-3">
          <Stepper label={t.tablePeopleLabel} value={personas} set={setPersonas} min={1} max={20} />
        </div>

        {/* Nombre */}
        <label className="block">
          <span className="mb-1 block text-[11px] uppercase tracking-wide text-slatey">{t.tableName}</span>
          <input value={nombre} onChange={(e) => setNombre(e.target.value)} placeholder={t.tableNamePh}
            className="w-full rounded-xl border border-stone-200 bg-linen px-2.5 py-2 text-sm text-ink focus:border-hilton-300 focus:bg-white focus:outline-none focus:ring-2 focus:ring-hilton-100" />
        </label>

        {/* ¿Alojado? → código de reserva opcional */}
        <button onClick={() => setIsGuest((v) => !v)}
          className="flex items-center gap-1.5 text-xs text-slatey hover:text-ink">
          <BedDouble size={13} /> {isGuest ? t.tableGuestHide : t.tableGuestShow}
        </button>
        {isGuest && (
          <input value={code} onChange={(e) => setCode(e.target.value.toUpperCase())} placeholder="HTL-XXXX"
            className="w-full rounded-xl border border-hilton-200 px-2.5 py-2 text-sm uppercase focus:border-hilton-500 focus:outline-none focus:ring-2 focus:ring-hilton-100" />
        )}

        {error && <p className="text-xs text-red-600">{error}</p>}

        <button onClick={confirm} disabled={saving}
          className="flex w-full items-center justify-center gap-2 rounded-xl bg-hilton-600 px-3 py-2.5 text-sm font-medium text-white transition hover:bg-hilton-700 active:scale-[0.99] disabled:opacity-60">
          {saving ? <Loader2 size={15} className="animate-spin" /> : <CalendarClock size={15} />} {t.tableReserve}
        </button>
      </div>
    </div>
  )
}
