import { useEffect, useState, useMemo } from 'react'
import { Plus, Minus, ShoppingCart, ArrowLeft, Check, Loader2, Leaf, WheatOff, X, BedDouble, Store } from 'lucide-react'
import { listMenuPublic, createOrder, validateBooking } from '../../services/api'
import { formatUSD, formatARS } from '../../lib/format'

const CATEGORIES = [
  { id: 'tapas', label: 'Tapas' },
  { id: 'plato', label: 'Platos' },
  { id: 'sandwich', label: 'Sándwiches' },
  { id: 'ensalada', label: 'Ensaladas' },
  { id: 'pizza', label: 'Pizzas' },
  { id: 'postre', label: 'Postres' },
  { id: 'cerveza', label: 'Cervezas' },
  { id: 'trago', label: 'Tragos' },
  { id: 'vino', label: 'Vinos' },
  { id: 'cafeteria', label: 'Café' },
  { id: 'merienda', label: 'Merienda' },
]

const FALLBACK = 'https://images.unsplash.com/photo-1414235077428-338989a2e8c0?w=800&q=80'

function sessionFromHash() {
  const m = window.location.hash.match(/session=([^&]+)/)
  return m ? decodeURIComponent(m[1]) : null
}

function TagBadge({ tag }) {
  const map = {
    vegetariano: { icon: Leaf, label: 'Veggie', cls: 'bg-forest-50 text-forest-600' },
    vegano: { icon: Leaf, label: 'Vegano', cls: 'bg-forest-50 text-forest-600' },
    sin_tacc: { icon: WheatOff, label: 'Sin TACC', cls: 'bg-amber-50 text-amber-700' },
  }
  const t = map[tag]
  if (!t) return null
  const Icon = t.icon
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium ${t.cls}`}>
      <Icon size={10} /> {t.label}
    </span>
  )
}

export default function RestaurantOrderPage() {
  const [menu, setMenu] = useState([])
  const [loading, setLoading] = useState(true)
  const [cat, setCat] = useState('tapas')
  const [cart, setCart] = useState({})           // { menu_item_id: qty }
  const [notes, setNotes] = useState('')
  const [placing, setPlacing] = useState(false)
  const [done, setDone] = useState(null)         // pedido confirmado
  // Checkout en dos pasos
  const [checkout, setCheckout] = useState(false)   // abre el panel de checkout
  const [validated, setValidated] = useState(null)  // reserva validada in-house | null
  const sessionId = sessionFromHash()

  useEffect(() => {
    listMenuPublic().then(setMenu).catch(() => setMenu([])).finally(() => setLoading(false))
  }, [])

  const byId = useMemo(() => Object.fromEntries(menu.map((m) => [m.id, m])), [menu])
  const cartItems = Object.entries(cart).filter(([, q]) => q > 0)
  const totalUsd = cartItems.reduce((s, [id, q]) => s + (byId[id]?.price_usd || 0) * q, 0)
  const totalArs = cartItems.reduce((s, [id, q]) => s + (byId[id]?.price_ars || 0) * q, 0)
  const cartCount = cartItems.reduce((s, [, q]) => s + q, 0)

  const add = (id) => setCart((c) => ({ ...c, [id]: (c[id] || 0) + 1 }))
  const sub = (id) => setCart((c) => ({ ...c, [id]: Math.max(0, (c[id] || 0) - 1) }))

  const visible = menu.filter((m) => m.category === cat)
  const cats = CATEGORIES.filter((c) => menu.some((m) => m.category === c.id))

  // Confirma el pedido. `opts` = { fulfillment, payment_mode, booking_code }
  const placeOrder = async (opts) => {
    if (!cartCount) return
    setPlacing(true)
    try {
      const order = await createOrder({
        items: cartItems.map(([id, qty]) => ({ menu_item_id: Number(id), qty })),
        session_id: sessionId,
        channel: 'web',
        fulfillment: opts.fulfillment,
        payment_mode: opts.payment_mode,
        booking_code: opts.booking_code || null,
        notes: notes.trim() || null,
      })
      setDone(order)
      setCheckout(false)
    } catch {
      alert('No se pudo confirmar el pedido. Intentá de nuevo.')
    } finally {
      setPlacing(false)
    }
  }

  const backToChat = () => {
    // Vuelve a la home con el código para que el agente lo registre/confirme.
    if (done?.order_code) window.location.hash = `inicio?order=${done.order_code}`
    else window.location.hash = 'inicio'
  }

  if (loading) {
    return (
      <div className="flex min-h-dvh items-center justify-center bg-linen text-slatey">
        <Loader2 className="animate-spin" /> <span className="ml-2">Cargando la carta…</span>
      </div>
    )
  }

  if (done) {
    const pago = done.payment_mode === 'folio'
      ? `Cargado a tu habitación${done.booking_code ? ` (reserva ${done.booking_code})` : ''}.`
      : 'Te enviaremos el link de pago.'
    return (
      <div className="flex min-h-dvh items-center justify-center bg-linen px-5">
        <div className="w-full max-w-md rounded-3xl bg-white p-8 text-center shadow-soft">
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-forest-100 text-forest-600">
            <Check size={28} />
          </div>
          <h2 className="font-display text-2xl font-600 text-ink">¡Pedido confirmado!</h2>
          <p className="mt-1 text-sm text-slatey">Código <strong>{done.order_code}</strong></p>
          <div className="mt-4 space-y-1 text-left text-sm">
            {done.items?.map((it) => (
              <div key={it.id} className="flex justify-between">
                <span>{it.qty}× {it.name}</span>
              </div>
            ))}
          </div>
          <p className="mt-4 font-display text-xl font-700 tabular-nums text-hilton-700">{formatUSD(done.total_usd)}</p>
          <p className="text-xs text-slatey">{formatARS(done.total_ars)} · {pago}</p>
          <button onClick={backToChat} className="btn-primary mt-6 w-full">Volver al chat con Aura</button>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-dvh bg-linen pb-32">
      {/* Header */}
      <header className="sticky top-0 z-20 border-b border-stone-200 bg-linen/90 px-5 py-4 backdrop-blur">
        <div className="mx-auto flex max-w-5xl items-center justify-between">
          <a href="#inicio" className="inline-flex items-center gap-2 text-sm text-slatey hover:text-ink">
            <ArrowLeft size={16} /> Volver
          </a>
          <h1 className="font-display text-lg font-600 text-ink">PLAZA · Hacé tu pedido</h1>
          <div className="w-16" />
        </div>
      </header>

      {/* Tabs de categoría */}
      <div className="sticky top-[57px] z-10 overflow-x-auto border-b border-stone-200 bg-linen/90 px-5 py-2 backdrop-blur">
        <div className="mx-auto flex max-w-5xl gap-2">
          {cats.map((c) => (
            <button
              key={c.id}
              onClick={() => setCat(c.id)}
              className={`whitespace-nowrap rounded-full px-3.5 py-1.5 text-xs font-medium transition ${
                cat === c.id ? 'bg-hilton-600 text-white' : 'bg-white text-slatey hover:bg-stone-50'
              }`}
            >
              {c.label}
            </button>
          ))}
        </div>
      </div>

      {/* Grilla de platos */}
      <div className="mx-auto max-w-5xl px-5 py-6">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {visible.map((m) => (
            <div key={m.id} className="flex overflow-hidden rounded-2xl bg-white shadow-card">
              <img src={m.image_url || FALLBACK} alt={m.name} loading="lazy" className="h-auto w-28 shrink-0 object-cover" />
              <div className="flex flex-1 flex-col p-3">
                <div className="flex items-start justify-between gap-2">
                  <p className="text-sm font-600 leading-tight text-ink">{m.name}</p>
                </div>
                {m.description && <p className="mt-0.5 line-clamp-2 text-xs text-slatey">{m.description}</p>}
                <div className="mt-1 flex flex-wrap gap-1">
                  {(m.tags || []).map((t) => <TagBadge key={t} tag={t} />)}
                </div>
                <div className="mt-auto flex items-center justify-between pt-2">
                  <span className="text-sm font-700 tabular-nums text-hilton-700">{formatUSD(m.price_usd)}</span>
                  {cart[m.id] > 0 ? (
                    <div className="flex items-center gap-2">
                      <button onClick={() => sub(m.id)} className="flex h-7 w-7 items-center justify-center rounded-full bg-stone-100 text-ink hover:bg-stone-200"><Minus size={14} /></button>
                      <span className="w-5 text-center text-sm font-600 tabular-nums">{cart[m.id]}</span>
                      <button onClick={() => add(m.id)} className="flex h-7 w-7 items-center justify-center rounded-full bg-hilton-600 text-white hover:bg-hilton-700"><Plus size={14} /></button>
                    </div>
                  ) : (
                    <button onClick={() => add(m.id)} className="flex h-7 w-7 items-center justify-center rounded-full bg-hilton-600 text-white hover:bg-hilton-700"><Plus size={14} /></button>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Barra de carrito (fija abajo) */}
      {cartCount > 0 && (
        <div className="fixed inset-x-0 bottom-0 z-30 border-t border-stone-200 bg-white px-5 py-3 shadow-widget">
          <div className="mx-auto flex max-w-5xl flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-center gap-3">
              <span className="relative flex h-10 w-10 items-center justify-center rounded-full bg-hilton-50 text-hilton-700">
                <ShoppingCart size={18} />
                <span className="absolute -right-1 -top-1 flex h-5 w-5 items-center justify-center rounded-full bg-hilton-600 text-[11px] font-bold text-white">{cartCount}</span>
              </span>
              <div>
                <p className="font-display text-lg font-700 tabular-nums text-ink">{formatUSD(totalUsd)}</p>
                <p className="text-xs text-slatey">{formatARS(totalArs)}</p>
              </div>
            </div>
            <button onClick={() => setCheckout(true)} className="btn-primary px-6 py-2.5">
              Continuar
            </button>
          </div>
        </div>
      )}

      {/* Checkout en dos pasos */}
      {checkout && (
        <CheckoutPanel
          totalUsd={totalUsd}
          totalArs={totalArs}
          placing={placing}
          validated={validated}
          setValidated={setValidated}
          onClose={() => setCheckout(false)}
          onConfirm={placeOrder}
        />
      )}
    </div>
  )
}

// ── Panel de checkout: ¿huésped? → validar reserva → destino → confirmar ─────
function CheckoutPanel({ totalUsd, totalArs, placing, validated, setValidated, onClose, onConfirm }) {
  const [mode, setMode] = useState(null)        // null | 'guest' | 'visitor'
  const [code, setCode] = useState('')
  const [checking, setChecking] = useState(false)
  const [vError, setVError] = useState('')
  const [fulfillment, setFulfillment] = useState('salon')

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
    <div className="fixed inset-0 z-40 flex items-end justify-center sm:items-center">
      <div className="absolute inset-0 bg-ink/40" onClick={onClose} />
      <div className="relative w-full max-w-md rounded-t-3xl bg-white p-6 shadow-card-lg animate-slide-up sm:rounded-3xl">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="font-display text-xl font-600 text-ink">Confirmar pedido</h3>
          <button onClick={onClose} aria-label="Cerrar" className="rounded-lg p-1.5 text-slatey hover:bg-mist"><X size={20} /></button>
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
      </div>
    </div>
  )
}
