import { useState } from 'react'
import { Check, Loader2, X, BedDouble, Store } from 'lucide-react'
import { validateBooking } from '../../services/api'
import { formatUSD, formatARS } from '../../lib/format'

/**
 * Checkout del restaurante: ¿huésped? → validar reserva → destino → confirmar.
 * Compartido por la pantalla #pedido (variant="modal") y la card del chat (variant="inline").
 *
 * Props:
 *  - totalUsd, totalArs, placing
 *  - validated, setValidated  (reserva in-house validada | null)
 *  - onClose, onConfirm({ fulfillment, payment_mode, booking_code })
 *  - variant: "modal" (overlay fullscreen) | "inline" (dentro de la card)
 */
export default function CheckoutPanel({
  totalUsd, totalArs, placing, validated, setValidated, onClose, onConfirm, variant = 'modal',
}) {
  const Body = (
    <CheckoutBody
      totalUsd={totalUsd} totalArs={totalArs} placing={placing}
      validated={validated} setValidated={setValidated} onClose={onClose} onConfirm={onConfirm}
      inline={variant === 'inline'}
    />
  )

  if (variant === 'inline') {
    return <div className="rounded-2xl border border-stone-200 bg-white p-4">{Body}</div>
  }

  return (
    <div className="fixed inset-0 z-40 flex items-end justify-center sm:items-center">
      <div className="absolute inset-0 bg-ink/40" onClick={onClose} />
      <div className="relative w-full max-w-md rounded-t-3xl bg-white p-6 shadow-card-lg animate-slide-up sm:rounded-3xl">
        {Body}
      </div>
    </div>
  )
}

function CheckoutBody({ totalUsd, totalArs, placing, validated, setValidated, onClose, onConfirm, inline }) {
  // Si entra con una reserva ya validada (huésped alojado reconocido en el chat), arrancamos
  // directo en modo huésped → saltamos "¿sos huésped?" y "código". El botón "← Volver" sigue
  // permitiendo elegir "soy visitante" si igual quisiera pagar directo.
  const [mode, setMode] = useState(validated?.valid ? 'guest' : null)  // null | 'guest' | 'visitor'
  const [code, setCode] = useState('')
  const [checking, setChecking] = useState(false)
  const [vError, setVError] = useState('')
  const [fulfillment, setFulfillment] = useState(validated?.valid ? 'room_service' : 'salon')

  const isGuest = mode === 'guest' && validated?.valid

  const doValidate = async () => {
    if (!code.trim()) return
    setChecking(true)
    setVError('')
    try {
      const r = await validateBooking(code.trim())
      if (r.valid) {
        setValidated(r)
        setFulfillment('room_service')
      } else {
        setValidated(null)
        setVError(r.reason === 'no_alojado'
          ? 'Esa reserva no figura como alojada hoy. ¿La cargás como retiro/salón con pago directo?'
          : 'No encontramos una reserva activa con ese código.')
      }
    } catch {
      setVError('No se pudo validar. Intentá de nuevo.')
    } finally {
      setChecking(false)
    }
  }

  const confirmGuest = () => onConfirm({ fulfillment, payment_mode: 'folio', booking_code: validated.booking_code })
  const confirmVisitor = (ff) => onConfirm({ fulfillment: ff, payment_mode: 'link' })

  return (
    <>
      <div className="mb-4 flex items-center justify-between">
        <h3 className={`font-display font-600 text-ink ${inline ? 'text-base' : 'text-xl'}`}>Confirmar pedido</h3>
        <button onClick={onClose} aria-label="Cerrar" className="rounded-lg p-1.5 text-slatey hover:bg-mist"><X size={inline ? 18 : 20} /></button>
      </div>
      <p className="mb-5 text-sm text-slatey">Total: <strong className="text-ink">{formatUSD(totalUsd)}</strong> · {formatARS(totalArs)}</p>

      {/* Paso 1: ¿huésped o visitante? */}
      {!mode && (
        <div className="space-y-3">
          <p className="text-sm font-medium text-ink">¿Estás alojado en el hotel?</p>
          <button onClick={() => setMode('guest')} className="flex w-full items-center gap-3 rounded-xl border border-hilton-200 px-4 py-3 text-left transition hover:bg-hilton-50">
            <BedDouble size={20} className="text-hilton-600" />
            <div><p className="text-sm font-medium text-ink">Sí, soy huésped</p><p className="text-xs text-slatey">Cargá el pedido a tu habitación</p></div>
          </button>
          <button onClick={() => setMode('visitor')} className="flex w-full items-center gap-3 rounded-xl border border-stone-200 px-4 py-3 text-left transition hover:bg-stone-50">
            <Store size={20} className="text-slatey" />
            <div><p className="text-sm font-medium text-ink">No, soy visitante</p><p className="text-xs text-slatey">Pago directo, para salón o retiro</p></div>
          </button>
        </div>
      )}

      {/* Paso 2a: huésped → validar reserva */}
      {mode === 'guest' && !isGuest && (
        <div className="space-y-3">
          <button onClick={() => { setMode(null); setValidated(null); setVError('') }} className="text-xs text-slatey hover:text-ink">← Volver</button>
          <label className="block">
            <span className="mb-1 block text-sm font-medium text-ink">Código de reserva</span>
            <input value={code} onChange={(e) => setCode(e.target.value.toUpperCase())} placeholder="HTL-XXXX"
                   className="w-full rounded-xl border border-hilton-200 px-3.5 py-2.5 text-sm uppercase focus:border-hilton-500 focus:outline-none focus:ring-2 focus:ring-hilton-100" />
          </label>
          {vError && (
            <div className="rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-700">
              {vError}
              <button onClick={() => confirmVisitor('salon')} className="mt-1 block font-medium underline">Continuar con pago directo →</button>
            </div>
          )}
          <button onClick={doValidate} disabled={checking || !code.trim()} className="btn-primary w-full disabled:opacity-60">
            {checking ? <Loader2 size={16} className="animate-spin" /> : 'Validar reserva'}
          </button>
        </div>
      )}

      {/* Paso 3a: huésped validado → destino + confirmar al folio */}
      {isGuest && (
        <div className="space-y-3">
          <button onClick={() => { setMode('visitor'); setValidated(null) }} className="text-xs text-slatey hover:text-ink">← No soy yo / pagar directo</button>
          <div className="flex items-center gap-2 rounded-xl bg-forest-50 px-4 py-3 text-sm text-forest-700">
            <Check size={16} /> Reserva de <strong>{validated.guest_name}</strong>
            {validated.room_number && <span>· Hab. {validated.room_number}</span>}
          </div>
          <label className="block">
            <span className="mb-1 block text-sm font-medium text-ink">¿Dónde lo querés?</span>
            <select value={fulfillment} onChange={(e) => setFulfillment(e.target.value)} className="w-full rounded-xl border border-hilton-200 px-3.5 py-2.5 text-sm focus:border-hilton-500 focus:outline-none">
              <option value="room_service">A mi habitación</option>
              <option value="salon">En el salón</option>
              <option value="retiro">Para retirar</option>
            </select>
          </label>
          <button onClick={confirmGuest} disabled={placing} className="btn-primary w-full disabled:opacity-60">
            {placing ? <Loader2 size={16} className="animate-spin" /> : 'Cargar a mi habitación'}
          </button>
        </div>
      )}

      {/* Paso 2b: visitante → destino (salón/retiro) + pago directo */}
      {mode === 'visitor' && (
        <div className="space-y-3">
          <button onClick={() => setMode(null)} className="text-xs text-slatey hover:text-ink">← Volver</button>
          <label className="block">
            <span className="mb-1 block text-sm font-medium text-ink">¿Dónde lo querés?</span>
            <select value={fulfillment} onChange={(e) => setFulfillment(e.target.value)} className="w-full rounded-xl border border-stone-200 px-3.5 py-2.5 text-sm focus:border-hilton-400 focus:outline-none">
              <option value="salon">En el salón</option>
              <option value="retiro">Para retirar</option>
            </select>
          </label>
          <button onClick={() => confirmVisitor(fulfillment)} disabled={placing} className="btn-primary w-full disabled:opacity-60">
            {placing ? <Loader2 size={16} className="animate-spin" /> : 'Confirmar y pagar'}
          </button>
          <p className="text-center text-xs text-slatey">Te enviaremos el link de pago.</p>
        </div>
      )}
    </>
  )
}
