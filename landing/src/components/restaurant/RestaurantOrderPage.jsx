import { useEffect, useState } from 'react'
import { Plus, Minus, ShoppingCart, ArrowLeft, Check, Loader2 } from 'lucide-react'
import { listMenuPublic, createOrder } from '../../services/api'
import { formatUSD, formatARS } from '../../lib/format'
import { CATEGORIES, MENU_FALLBACK_IMG as FALLBACK, TagBadge } from './menuShared'
import { useCart } from './useCart'
import CheckoutPanel from './CheckoutPanel'

function sessionFromHash() {
  const m = window.location.hash.match(/session=([^&]+)/)
  return m ? decodeURIComponent(m[1]) : null
}

export default function RestaurantOrderPage() {
  const [menu, setMenu] = useState([])
  const [loading, setLoading] = useState(true)
  const [cat, setCat] = useState('tapas')
  const [notes, setNotes] = useState('')
  const [placing, setPlacing] = useState(false)
  const [done, setDone] = useState(null)         // pedido confirmado
  // Checkout en dos pasos
  const [checkout, setCheckout] = useState(false)   // abre el panel de checkout
  const [validated, setValidated] = useState(null)  // reserva validada in-house | null
  const sessionId = sessionFromHash()

  const { cart, cartItems, totalUsd, totalArs, cartCount, add, sub, orderItems } = useCart(menu)

  useEffect(() => {
    listMenuPublic().then(setMenu).catch(() => setMenu([])).finally(() => setLoading(false))
  }, [])

  const visible = menu.filter((m) => m.category === cat)
  const cats = CATEGORIES.filter((c) => menu.some((m) => m.category === c.id))

  // Confirma el pedido. `opts` = { fulfillment, payment_mode, booking_code }
  const placeOrder = async (opts) => {
    if (!cartCount) return
    setPlacing(true)
    try {
      const order = await createOrder({
        items: orderItems(),
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
