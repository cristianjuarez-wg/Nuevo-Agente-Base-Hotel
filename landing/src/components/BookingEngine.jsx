import { useState } from 'react'
import { format, addDays, differenceInCalendarDays } from 'date-fns'
import {
  CalendarDays, Users, Search, ArrowLeft, Check, Loader2, BedDouble, AlertCircle,
} from 'lucide-react'
import { getAvailability, createBooking } from '../services/api'

function todayISO() {
  return format(new Date(), 'yyyy-MM-dd')
}
function tomorrowISO() {
  return format(addDays(new Date(), 1), 'yyyy-MM-dd')
}
function formatARS(n) {
  return new Intl.NumberFormat('es-AR', { maximumFractionDigits: 0 }).format(n)
}

// ── Paso 1: búsqueda de fechas ───────────────────────────────────────────────
function SearchForm({ search, setSearch, onSearch, loading, error }) {
  const nights =
    search.checkIn && search.checkOut
      ? differenceInCalendarDays(new Date(search.checkOut), new Date(search.checkIn))
      : 0

  const submit = (e) => {
    e.preventDefault()
    onSearch()
  }

  return (
    <form onSubmit={submit} className="mx-auto max-w-3xl">
      <div className="grid grid-cols-1 gap-4 rounded-2xl bg-white p-5 shadow-card-lg sm:grid-cols-2 lg:grid-cols-4 lg:items-end">
        <div className="flex flex-col">
          <label htmlFor="checkIn" className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slatey">
            Check-in
          </label>
          <div className="relative">
            <CalendarDays size={18} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-hilton-500" />
            <input
              id="checkIn"
              type="date"
              min={todayISO()}
              value={search.checkIn}
              onChange={(e) => {
                const checkIn = e.target.value
                const checkOut =
                  search.checkOut && search.checkOut <= checkIn
                    ? format(addDays(new Date(checkIn), 1), 'yyyy-MM-dd')
                    : search.checkOut
                setSearch({ ...search, checkIn, checkOut })
              }}
              className="w-full rounded-xl border border-mist bg-white py-3 pl-10 pr-3 text-sm text-ink focus:border-hilton-400 focus:outline-none focus:ring-2 focus:ring-hilton-100"
              required
            />
          </div>
        </div>

        <div className="flex flex-col">
          <label htmlFor="checkOut" className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slatey">
            Check-out
          </label>
          <div className="relative">
            <CalendarDays size={18} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-hilton-500" />
            <input
              id="checkOut"
              type="date"
              min={search.checkIn ? format(addDays(new Date(search.checkIn), 1), 'yyyy-MM-dd') : tomorrowISO()}
              value={search.checkOut}
              onChange={(e) => setSearch({ ...search, checkOut: e.target.value })}
              className="w-full rounded-xl border border-mist bg-white py-3 pl-10 pr-3 text-sm text-ink focus:border-hilton-400 focus:outline-none focus:ring-2 focus:ring-hilton-100"
              required
            />
          </div>
        </div>

        <div className="flex flex-col">
          <label htmlFor="guests" className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slatey">
            Huéspedes
          </label>
          <div className="relative">
            <Users size={18} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-hilton-500" />
            <select
              id="guests"
              value={search.guests}
              onChange={(e) => setSearch({ ...search, guests: Number(e.target.value) })}
              className="w-full appearance-none rounded-xl border border-mist bg-white py-3 pl-10 pr-3 text-sm text-ink focus:border-hilton-400 focus:outline-none focus:ring-2 focus:ring-hilton-100"
            >
              {[1, 2, 3, 4].map((n) => (
                <option key={n} value={n}>
                  {n} {n === 1 ? 'huésped' : 'huéspedes'}
                </option>
              ))}
            </select>
          </div>
        </div>

        <button type="submit" disabled={loading} className="btn-primary w-full">
          {loading ? <Loader2 size={18} className="animate-spin" /> : <Search size={18} />}
          {loading ? 'Buscando…' : 'Buscar'}
        </button>
      </div>

      {nights > 0 && (
        <p className="mt-3 text-center text-sm text-white/85">
          {nights} {nights === 1 ? 'noche' : 'noches'} · llegada{' '}
          {format(new Date(search.checkIn), 'dd/MM/yyyy')}
        </p>
      )}

      {error && (
        <div className="mt-3 flex items-center justify-center gap-2 rounded-xl bg-white/15 px-4 py-2.5 text-sm text-white backdrop-blur">
          <AlertCircle size={16} />
          {error}
        </div>
      )}
    </form>
  )
}

// ── Paso 2: resultados de disponibilidad ──────────────────────────────────────
function Results({ rooms, search, onPick, onBack }) {
  return (
    <div className="mx-auto max-w-4xl">
      <button onClick={onBack} className="mb-5 inline-flex items-center gap-1.5 text-sm font-medium text-white/85 hover:text-white">
        <ArrowLeft size={16} /> Cambiar fechas
      </button>

      {rooms.length === 0 ? (
        <div className="rounded-2xl bg-white p-8 text-center shadow-card-lg">
          <BedDouble size={32} className="mx-auto mb-3 text-slatey" />
          <p className="font-serif text-lg font-600 text-ink">Sin disponibilidad</p>
          <p className="mt-1 text-sm text-slatey">
            No hay habitaciones para esas fechas y cantidad de huéspedes. Probá con otras fechas.
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {rooms.map((r) => (
            <div
              key={r.id}
              className="flex flex-col gap-4 rounded-2xl bg-white p-4 shadow-card-lg sm:flex-row sm:items-center"
            >
              <img
                src={(r.images && r.images[0]) || 'https://lirp.cdn-website.com/02afd0e4/dms3rep/multi/opt/BRCHXHX_HAB_02-0b2b9eb8-1920w.jpg'}
                alt={`Habitación ${r.room_type}`}
                loading="lazy"
                className="h-40 w-full rounded-xl object-cover sm:h-24 sm:w-36"
              />
              <div className="flex-1">
                <h3 className="font-serif text-lg font-600 text-ink">{r.room_type}</h3>
                <p className="text-xs text-slatey">
                  {r.bed_config} · hasta {r.capacity} huéspedes · {r.units_available} disponible(s)
                </p>
                <p className="mt-1 text-xs text-slatey">
                  {r.nights} {r.nights === 1 ? 'noche' : 'noches'}
                </p>
              </div>
              <div className="text-right sm:w-44">
                <p className="font-serif text-xl font-700 tabular-nums text-hilton-700">
                  USD {r.total_price_usd}
                </p>
                <p className="text-xs tabular-nums text-slatey">ARS {formatARS(r.total_price_ars)}</p>
                <button onClick={() => onPick(r)} className="btn-primary mt-2 w-full px-4 py-2.5 text-xs">
                  Elegir
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Paso 3: datos del huésped ─────────────────────────────────────────────────
function GuestForm({ room, search, onConfirm, onBack, submitting, error }) {
  const [form, setForm] = useState({ name: '', email: '', phone: '' })
  const valid = form.name.trim().length >= 2

  const submit = (e) => {
    e.preventDefault()
    if (valid) onConfirm(form)
  }

  return (
    <div className="mx-auto max-w-2xl">
      <button onClick={onBack} className="mb-5 inline-flex items-center gap-1.5 text-sm font-medium text-white/85 hover:text-white">
        <ArrowLeft size={16} /> Volver a habitaciones
      </button>

      <div className="rounded-2xl bg-white p-6 shadow-card-lg">
        <div className="mb-5 flex items-center justify-between border-b border-mist pb-4">
          <div>
            <h3 className="font-serif text-lg font-600 text-ink">{room.room_type}</h3>
            <p className="text-xs text-slatey">
              {format(new Date(search.checkIn), 'dd/MM')} → {format(new Date(search.checkOut), 'dd/MM/yyyy')} ·{' '}
              {search.guests} {search.guests === 1 ? 'huésped' : 'huéspedes'}
            </p>
          </div>
          <div className="text-right">
            <p className="font-serif text-lg font-700 tabular-nums text-hilton-700">USD {room.total_price_usd}</p>
            <p className="text-xs tabular-nums text-slatey">ARS {formatARS(room.total_price_ars)}</p>
          </div>
        </div>

        <form onSubmit={submit} className="space-y-4">
          <div>
            <label htmlFor="g-name" className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-slatey">
              Nombre completo <span className="text-hilton-600">*</span>
            </label>
            <input
              id="g-name"
              type="text"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder="Tu nombre y apellido"
              className="w-full rounded-xl border border-mist py-3 px-3 text-sm text-ink focus:border-hilton-400 focus:outline-none focus:ring-2 focus:ring-hilton-100"
              required
              minLength={2}
            />
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label htmlFor="g-email" className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-slatey">
                Email
              </label>
              <input
                id="g-email"
                type="email"
                inputMode="email"
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
                placeholder="tu@email.com"
                className="w-full rounded-xl border border-mist py-3 px-3 text-sm text-ink focus:border-hilton-400 focus:outline-none focus:ring-2 focus:ring-hilton-100"
              />
            </div>
            <div>
              <label htmlFor="g-phone" className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-slatey">
                Teléfono
              </label>
              <input
                id="g-phone"
                type="tel"
                inputMode="tel"
                value={form.phone}
                onChange={(e) => setForm({ ...form, phone: e.target.value })}
                placeholder="+54 …"
                className="w-full rounded-xl border border-mist py-3 px-3 text-sm text-ink focus:border-hilton-400 focus:outline-none focus:ring-2 focus:ring-hilton-100"
              />
            </div>
          </div>

          <p className="text-xs text-slatey">
            Pago simulado para esta demo — la reserva se confirma al instante.
          </p>

          {error && (
            <div className="flex items-center gap-2 rounded-xl bg-red-50 px-4 py-2.5 text-sm text-red-700">
              <AlertCircle size={16} /> {error}
            </div>
          )}

          <button type="submit" disabled={!valid || submitting} className="btn-primary w-full">
            {submitting ? <Loader2 size={18} className="animate-spin" /> : <Check size={18} />}
            {submitting ? 'Confirmando…' : 'Confirmar reserva'}
          </button>
        </form>
      </div>
    </div>
  )
}

// ── Paso 4: confirmación ──────────────────────────────────────────────────────
function Confirmation({ booking, onReset }) {
  return (
    <div className="mx-auto max-w-lg animate-fade-in text-center">
      <div className="rounded-2xl bg-white p-8 shadow-card-lg">
        <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-green-100 text-green-600">
          <Check size={32} />
        </div>
        <h3 className="font-serif text-2xl font-700 text-ink">¡Reserva confirmada!</h3>
        <p className="mt-2 text-sm text-slatey">
          Te esperamos en el Hampton by Hilton Bariloche, {booking.guest_name}.
        </p>

        <div className="my-6 rounded-xl border border-dashed border-hilton-200 bg-hilton-50 py-4">
          <p className="text-xs uppercase tracking-wide text-slatey">Código de reserva</p>
          <p className="font-serif text-2xl font-700 tracking-wider text-hilton-700">{booking.code}</p>
        </div>

        <dl className="space-y-2 text-left text-sm">
          <div className="flex justify-between">
            <dt className="text-slatey">Habitación</dt>
            <dd className="font-medium text-ink">{booking.room_type}</dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-slatey">Check-in</dt>
            <dd className="font-medium text-ink">{booking.check_in}</dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-slatey">Check-out</dt>
            <dd className="font-medium text-ink">{booking.check_out}</dd>
          </div>
          <div className="flex justify-between border-t border-mist pt-2">
            <dt className="text-slatey">Total</dt>
            <dd className="font-semibold tabular-nums text-hilton-700">
              USD {booking.total_price_usd} / ARS {formatARS(booking.total_price_ars)}
            </dd>
          </div>
        </dl>

        <p className="mt-5 text-xs text-slatey">
          Guardá tu código <strong>{booking.code}</strong>: con él podés consultar tu reserva
          con nuestra concierge virtual.
        </p>

        <button onClick={onReset} className="btn-secondary mt-6 w-full">
          Hacer otra reserva
        </button>
      </div>
    </div>
  )
}

// ── Contenedor del motor ──────────────────────────────────────────────────────
export default function BookingEngine() {
  const [step, setStep] = useState('search') // search | results | guest | done
  const [search, setSearch] = useState({ checkIn: '', checkOut: '', guests: 2 })
  const [rooms, setRooms] = useState([])
  const [picked, setPicked] = useState(null)
  const [booking, setBooking] = useState(null)
  const [loading, setLoading] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  const runSearch = async () => {
    setError('')
    if (!search.checkIn || !search.checkOut) {
      setError('Elegí las fechas de check-in y check-out.')
      return
    }
    if (search.checkOut <= search.checkIn) {
      setError('El check-out debe ser posterior al check-in.')
      return
    }
    setLoading(true)
    try {
      const data = await getAvailability({
        checkIn: search.checkIn,
        checkOut: search.checkOut,
        guests: search.guests,
      })
      setRooms(Array.isArray(data) ? data : [])
      setStep('results')
    } catch (e) {
      setError('No pudimos consultar disponibilidad. Intentá de nuevo en un momento.')
    } finally {
      setLoading(false)
    }
  }

  const confirm = async (guest) => {
    setError('')
    setSubmitting(true)
    try {
      const result = await createBooking({
        room_id: picked.id,
        check_in: search.checkIn,
        check_out: search.checkOut,
        guest_name: guest.name,
        guest_email: guest.email || null,
        guest_phone: guest.phone || null,
        guests: search.guests,
        source: 'web',
      })
      setBooking(result)
      setStep('done')
    } catch (e) {
      const detail = e?.response?.data?.detail
      setError(detail || 'No pudimos confirmar la reserva. Intentá nuevamente.')
    } finally {
      setSubmitting(false)
    }
  }

  const reset = () => {
    setStep('search')
    setRooms([])
    setPicked(null)
    setBooking(null)
    setError('')
  }

  return (
    <section id="reservar" className="section-pad bg-gradient-to-br from-hilton-800 via-hilton-700 to-hilton-500">
      <div className="container-x">
        <header className="mx-auto mb-10 max-w-2xl text-center">
          <p className="mb-2 text-sm font-semibold uppercase tracking-wider text-sand-300">
            Reservá tu estadía
          </p>
          <h2 className="font-serif text-3xl font-700 text-white sm:text-4xl">
            Disponibilidad en tiempo real
          </h2>
          <p className="mt-3 text-base text-white/80">
            Elegí tus fechas y reservá al instante. Pago simulado para esta demostración.
          </p>
        </header>

        {step === 'search' && (
          <SearchForm
            search={search}
            setSearch={setSearch}
            onSearch={runSearch}
            loading={loading}
            error={error}
          />
        )}
        {step === 'results' && (
          <Results rooms={rooms} search={search} onPick={(r) => { setPicked(r); setStep('guest') }} onBack={reset} />
        )}
        {step === 'guest' && (
          <GuestForm
            room={picked}
            search={search}
            onConfirm={confirm}
            onBack={() => setStep('results')}
            submitting={submitting}
            error={error}
          />
        )}
        {step === 'done' && <Confirmation booking={booking} onReset={reset} />}
      </div>
    </section>
  )
}
