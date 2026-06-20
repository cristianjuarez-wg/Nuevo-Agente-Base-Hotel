import { useState } from 'react'
import { CalendarDays } from 'lucide-react'

// Fecha de hoy en YYYY-MM-DD (para el min de los inputs).
function todayISO() {
  const t = new Date()
  return `${t.getFullYear()}-${String(t.getMonth() + 1).padStart(2, '0')}-${String(t.getDate()).padStart(2, '0')}`
}

// Suma días a una fecha ISO y devuelve ISO (sin líos de timezone: usa partes).
function addDaysISO(iso, days) {
  const [y, m, d] = iso.split('-').map(Number)
  const dt = new Date(y, m - 1, d + days)
  return `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, '0')}-${String(dt.getDate()).padStart(2, '0')}`
}

// Noches entre dos fechas ISO (0 si inválido).
function nightsBetween(a, b) {
  if (!a || !b) return 0
  const [ay, am, ad] = a.split('-').map(Number)
  const [by, bm, bd] = b.split('-').map(Number)
  const diff = (new Date(by, bm - 1, bd) - new Date(ay, am - 1, ad)) / 86400000
  return diff > 0 ? Math.round(diff) : 0
}

function Stepper({ label, hint, value, set, min = 0, max = 9 }) {
  return (
    <div className="flex items-center justify-between">
      <div>
        <p className="text-sm font-medium text-ink">{label}</p>
        {hint && <p className="text-[11px] text-slatey">{hint}</p>}
      </div>
      <div className="flex items-center gap-2">
        <button
          type="button" onClick={() => set(Math.max(min, value - 1))}
          disabled={value <= min}
          className="flex h-7 w-7 items-center justify-center rounded-full border border-stone-200 text-ink transition hover:bg-stone-50 disabled:opacity-40"
        >–</button>
        <span className="w-5 text-center text-sm font-semibold tabular-nums text-ink">{value}</span>
        <button
          type="button" onClick={() => set(Math.min(max, value + 1))}
          disabled={value >= max}
          className="flex h-7 w-7 items-center justify-center rounded-full border border-stone-200 text-ink transition hover:bg-stone-50 disabled:opacity-40"
        >+</button>
      </div>
    </div>
  )
}

/**
 * Selector compacto de fechas + huéspedes dentro del chat (Fase 2).
 * Al confirmar, compone un mensaje en lenguaje natural y lo inyecta vía onAction.
 */
export default function DatePickerCard({ card, onAction }) {
  const [checkIn, setCheckIn] = useState('')
  const [checkOut, setCheckOut] = useState('')
  const [adults, setAdults] = useState(2)
  const [children, setChildren] = useState(0)
  const [infants, setInfants] = useState(0)
  const [error, setError] = useState('')

  const minOut = checkIn ? addDaysISO(checkIn, 1) : todayISO()
  const nights = nightsBetween(checkIn, checkOut)

  // Al elegir check-in, sugerir automáticamente check-out (+2 noches) si está vacío o
  // quedó antes del nuevo check-in. La mayoría de las estadías son cortas.
  const onCheckIn = (value) => {
    setCheckIn(value)
    if (!checkOut || checkOut <= value) {
      setCheckOut(addDaysISO(value, 2))
    }
  }

  const confirm = () => {
    if (!checkIn || !checkOut) { setError('Elegí las dos fechas.'); return }
    if (checkOut <= checkIn) { setError('El check-out debe ser posterior al check-in.'); return }
    setError('')
    // Mensaje natural para el agente (incluye desglose de huéspedes).
    const partes = [`${adults} adulto${adults !== 1 ? 's' : ''}`]
    if (children) partes.push(`${children} niño${children !== 1 ? 's' : ''}`)
    if (infants) partes.push(`${infants} bebé${infants !== 1 ? 's' : ''} en cuna`)
    const msg =
      `Quiero consultar disponibilidad del ${checkIn} al ${checkOut} para ${partes.join(', ')}.`
    onAction?.({ kind: 'send_message', message: msg })
  }

  return (
    <div className="overflow-hidden rounded-2xl border border-stone-200 bg-white shadow-card">
      <div className="flex items-center gap-2 bg-linen px-4 py-2.5">
        <CalendarDays size={16} className="text-hilton-600" />
        <p className="text-sm font-medium text-ink">{card.title || 'Elegí tus fechas'}</p>
      </div>

      <div className="space-y-3 p-4">
        {/* Fechas */}
        <div className="grid grid-cols-2 gap-2.5">
          <label className="block">
            <span className="mb-1 block text-[11px] uppercase tracking-wide text-slatey">Check-in</span>
            <input
              type="date" value={checkIn} min={todayISO()}
              onChange={(e) => onCheckIn(e.target.value)}
              className="w-full rounded-xl border border-stone-200 bg-linen px-2.5 py-2 text-sm text-ink focus:border-hilton-300 focus:bg-white focus:outline-none focus:ring-2 focus:ring-hilton-100"
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-[11px] uppercase tracking-wide text-slatey">Check-out</span>
            <input
              type="date" value={checkOut} min={minOut}
              onChange={(e) => setCheckOut(e.target.value)}
              className="w-full rounded-xl border border-stone-200 bg-linen px-2.5 py-2 text-sm text-ink focus:border-hilton-300 focus:bg-white focus:outline-none focus:ring-2 focus:ring-hilton-100"
            />
          </label>
        </div>

        {/* Contador de noches en vivo + aviso si la estadía es larga */}
        {nights > 0 && (
          <div className={`flex items-center gap-1.5 text-xs ${nights > 14 ? 'text-amber-600' : 'text-slatey'}`}>
            <span className="font-medium">{nights} {nights === 1 ? 'noche' : 'noches'}</span>
            {nights > 14 && <span>· estadía larga, ¿es correcto?</span>}
          </div>
        )}

        {/* Huéspedes */}
        <div className="space-y-2 rounded-xl border border-stone-200 p-3">
          <Stepper label="Adultos" value={adults} set={setAdults} min={1} />
          <div className="h-px bg-stone-100" />
          <Stepper label="Niños" hint="3 a 17 años" value={children} set={setChildren} />
          <div className="h-px bg-stone-100" />
          <Stepper label="Bebés" hint="0 a 2, en cuna" value={infants} set={setInfants} />
        </div>

        {error && <p className="text-xs text-red-600">{error}</p>}

        <button
          onClick={confirm}
          className="w-full rounded-xl bg-hilton-600 px-3 py-2.5 text-sm font-medium text-white transition hover:bg-hilton-700 active:scale-[0.99]"
        >
          {card.action?.label || 'Ver disponibilidad'}
          {nights > 0 ? ` · ${nights} ${nights === 1 ? 'noche' : 'noches'}` : ''}
        </button>
      </div>
    </div>
  )
}
