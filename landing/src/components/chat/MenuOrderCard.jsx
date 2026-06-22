import { useState } from 'react'
import { UtensilsCrossed, Ticket, Plus, Minus, ShoppingCart, ArrowRight, Check, Loader2 } from 'lucide-react'
import { getStrings } from '../../i18n/chat'
import { formatUSD, formatARS } from '../../lib/format'
import { CATEGORIES, MENU_FALLBACK_IMG as FALLBACK, TagBadge } from '../restaurant/menuShared'
import { useCart, preselectToCart } from '../restaurant/useCart'
import CheckoutPanel from '../restaurant/CheckoutPanel'
import { createOrder, createVoucher } from '../../services/api'

// Mini-checkout del VOUCHER: solo datos del comprador (visitante, pago directo, sin folio).
function VoucherCheckout({ totalUsd, totalArs, placing, onClose, onConfirm, t }) {
  const [name, setName] = useState('')
  const [phone, setPhone] = useState('')
  const [error, setError] = useState('')
  const submit = () => {
    if (!name.trim()) { setError(t.voucherErrName); return }
    setError('')
    onConfirm({ buyer_name: name.trim(), buyer_phone: phone.trim() || null })
  }
  return (
    <div className="rounded-2xl border border-stone-200 bg-white p-4">
      <p className="mb-3 text-sm text-slatey">{t.voucherTotal}: <strong className="text-ink">{formatUSD(totalUsd)}</strong> · {formatARS(totalArs)}</p>
      <label className="block">
        <span className="mb-1 block text-[11px] uppercase tracking-wide text-slatey">{t.voucherBuyer}</span>
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder={t.tableNamePh}
          className="w-full rounded-xl border border-stone-200 bg-linen px-2.5 py-2 text-sm text-ink focus:border-hilton-300 focus:bg-white focus:outline-none focus:ring-2 focus:ring-hilton-100" />
      </label>
      <label className="mt-2 block">
        <span className="mb-1 block text-[11px] uppercase tracking-wide text-slatey">{t.voucherPhone}</span>
        <input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="+54 9 …"
          className="w-full rounded-xl border border-stone-200 bg-linen px-2.5 py-2 text-sm text-ink focus:border-hilton-300 focus:bg-white focus:outline-none focus:ring-2 focus:ring-hilton-100" />
      </label>
      {error && <p className="mt-2 text-xs text-red-600">{error}</p>}
      <div className="mt-3 flex gap-2">
        <button onClick={onClose} className="flex-1 rounded-xl border border-stone-200 px-3 py-2.5 text-sm text-slatey transition hover:bg-mist">{t.voucherBack}</button>
        <button onClick={submit} disabled={placing} className="flex flex-1 items-center justify-center gap-2 rounded-xl bg-hilton-600 px-3 py-2.5 text-sm font-medium text-white transition hover:bg-hilton-700 disabled:opacity-60">
          {placing ? <Loader2 size={15} className="animate-spin" /> : <Ticket size={15} />} {t.voucherBuy}
        </button>
      </div>
    </div>
  )
}

/**
 * Carta interactiva embebida en el chat (Fase 1 del restaurante).
 * El huésped ve los platos, arma el pedido (+/-), y hace el mini-checkout — todo dentro del
 * chat. Si prefiere, "ver carta completa →" abre #pedido en otra pestaña SIN cerrar el chat.
 *
 * `card.purpose` = "order" (pedir ahora) | "voucher" (compra anticipada de visitante, Fase 3).
 * Props: card { items, session_id, fallback_url, preselect, purpose }, onAction(action), lang
 */
export default function MenuOrderCard({ card, onAction, lang = 'es' }) {
  const t = getStrings(lang)
  const menu = card.items || []
  const sessionId = card.session_id || null
  const isVoucher = card.purpose === 'voucher'

  const firstCat = CATEGORIES.find((c) => menu.some((m) => m.category === c.id))?.id || 'plato'
  const [cat, setCat] = useState(firstCat)
  const { cart, cartItems, totalUsd, totalArs, cartCount, add, sub, orderItems } =
    useCart(menu, preselectToCart(card.preselect))

  const [stage, setStage] = useState('browse')   // 'browse' | 'checkout' | 'done'
  const [placing, setPlacing] = useState(false)
  const [validated, setValidated] = useState(null)
  const [done, setDone] = useState(null)

  const cats = CATEGORIES.filter((c) => menu.some((m) => m.category === c.id))
  const visible = menu.filter((m) => m.category === cat)

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
      })
      setDone(order)
      setStage('done')
      // Avisamos a Aura para que cierre con calidez (reusa registrar_pedido).
      if (order?.order_code) onAction?.({ kind: 'send_message', message: t.orderConfirmedMsg(order.order_code) })
    } catch {
      alert(t.orderError)
    } finally {
      setPlacing(false)
    }
  }

  const buyVoucher = async (buyer) => {
    if (!cartCount) return
    setPlacing(true)
    try {
      const v = await createVoucher({
        items: orderItems(),
        session_id: sessionId,
        buyer_name: buyer.buyer_name,
        buyer_phone: buyer.buyer_phone,
      })
      if (v?.error) { alert(v.error); setPlacing(false); return }
      setDone(v)
      setStage('done')
      if (v?.code) onAction?.({ kind: 'send_message', message: t.voucherIssuedMsg(v.code) })
    } catch {
      alert(t.voucherError)
    } finally {
      setPlacing(false)
    }
  }

  // ── Confirmación ──────────────────────────────────────────────────────────
  if (stage === 'done' && done) {
    if (isVoucher) {
      return (
        <div className="overflow-hidden rounded-2xl border border-stone-200 bg-white shadow-card">
          <div className="p-4 text-center">
            <div className="mx-auto mb-2 flex h-11 w-11 items-center justify-center rounded-full bg-forest-100 text-forest-600">
              <Ticket size={22} />
            </div>
            <p className="font-display text-base font-600 text-ink">{t.voucherIssued}</p>
            <p className="text-xs text-slatey">{t.code} <strong>{done.code}</strong></p>
            <p className="mt-2 font-display text-lg font-700 tabular-nums text-hilton-700">{formatUSD(done.total_usd)}</p>
            <p className="mt-1 text-[11px] text-slatey">{t.voucherKeep}</p>
          </div>
        </div>
      )
    }
    const pago = done.payment_mode === 'folio'
      ? t.chargedToRoom(done.booking_code)
      : t.payByLink
    return (
      <div className="overflow-hidden rounded-2xl border border-stone-200 bg-white shadow-card">
        <div className="p-4 text-center">
          <div className="mx-auto mb-2 flex h-11 w-11 items-center justify-center rounded-full bg-forest-100 text-forest-600">
            <Check size={22} />
          </div>
          <p className="font-display text-base font-600 text-ink">{t.orderConfirmed}</p>
          <p className="text-xs text-slatey">{t.code} <strong>{done.order_code}</strong></p>
          <p className="mt-2 font-display text-lg font-700 tabular-nums text-hilton-700">{formatUSD(done.total_usd)}</p>
          <p className="text-[11px] text-slatey">{formatARS(done.total_ars)} · {pago}</p>
        </div>
      </div>
    )
  }

  // ── Mini-checkout embebido ────────────────────────────────────────────────
  if (stage === 'checkout') {
    if (isVoucher) {
      return (
        <VoucherCheckout totalUsd={totalUsd} totalArs={totalArs} placing={placing}
          onClose={() => setStage('browse')} onConfirm={buyVoucher} t={t} />
      )
    }
    return (
      <CheckoutPanel
        variant="inline"
        totalUsd={totalUsd}
        totalArs={totalArs}
        placing={placing}
        validated={validated}
        setValidated={setValidated}
        onClose={() => setStage('browse')}
        onConfirm={placeOrder}
      />
    )
  }

  // ── Carta (browse) ────────────────────────────────────────────────────────
  return (
    <div className="overflow-hidden rounded-2xl border border-stone-200 bg-white shadow-card">
      {/* Encabezado */}
      <div className="flex items-center gap-2.5 border-b border-stone-100 px-3.5 py-3">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-timber-50 text-timber-500">
          {isVoucher ? <Ticket size={18} /> : <UtensilsCrossed size={18} />}
        </div>
        <div className="min-w-0">
          <h4 className="font-display text-sm font-600 leading-tight text-ink">{card.title || t.menuTitle}</h4>
          <p className="truncate text-[11px] text-slatey">{card.description || t.menuDesc}</p>
        </div>
      </div>

      {/* Tabs de categoría */}
      <div className="flex gap-1.5 overflow-x-auto border-b border-stone-100 px-3 py-2">
        {cats.map((c) => (
          <button
            key={c.id} onClick={() => setCat(c.id)}
            className={`whitespace-nowrap rounded-full px-3 py-1 text-[11px] font-medium transition ${
              cat === c.id ? 'bg-hilton-600 text-white' : 'bg-stone-50 text-slatey hover:bg-stone-100'
            }`}
          >{c.label}</button>
        ))}
      </div>

      {/* Lista de platos (scroll interno: no empuja la conversación) */}
      <div className="max-h-72 overflow-y-auto px-3 py-2">
        {visible.map((m) => (
          <div key={m.id} className="flex items-center gap-2.5 border-b border-stone-50 py-2 last:border-0">
            <img src={m.image_url || FALLBACK} alt={m.name} loading="lazy" className="h-12 w-12 shrink-0 rounded-lg object-cover" />
            <div className="min-w-0 flex-1">
              <p className="text-xs font-600 leading-tight text-ink">{m.name}</p>
              <div className="mt-0.5 flex flex-wrap items-center gap-1">
                <span className="text-xs font-700 tabular-nums text-hilton-700">{formatUSD(m.price_usd)}</span>
                {(m.tags || []).map((tg) => <TagBadge key={tg} tag={tg} />)}
              </div>
            </div>
            {cart[m.id] > 0 ? (
              <div className="flex items-center gap-1.5">
                <button onClick={() => sub(m.id)} className="flex h-6 w-6 items-center justify-center rounded-full bg-stone-100 text-ink hover:bg-stone-200"><Minus size={12} /></button>
                <span className="w-4 text-center text-xs font-600 tabular-nums">{cart[m.id]}</span>
                <button onClick={() => add(m.id)} className="flex h-6 w-6 items-center justify-center rounded-full bg-hilton-600 text-white hover:bg-hilton-700"><Plus size={12} /></button>
              </div>
            ) : (
              <button onClick={() => add(m.id)} className="flex h-6 w-6 items-center justify-center rounded-full bg-hilton-600 text-white hover:bg-hilton-700"><Plus size={12} /></button>
            )}
          </div>
        ))}
      </div>

      {/* Pie: total + Pedir (solo si hay ítems) + link a carta completa */}
      <div className="border-t border-stone-100 px-3.5 py-2.5">
        {cartCount > 0 && (
          <button
            onClick={() => setStage('checkout')}
            className="mb-2 flex w-full items-center justify-between rounded-xl bg-hilton-600 px-3.5 py-2.5 text-sm font-medium text-white transition hover:bg-hilton-700 active:scale-[0.99]"
          >
            <span className="inline-flex items-center gap-1.5">
              <ShoppingCart size={15} />
              <span className="tabular-nums">{formatUSD(totalUsd)}</span>
              <span className="text-white/70 text-xs">({cartCount})</span>
            </span>
            <span className="inline-flex items-center gap-1">{placing ? <Loader2 size={14} className="animate-spin" /> : null}{isVoucher ? t.voucherBuy : t.order} <ArrowRight size={14} /></span>
          </button>
        )}
        {card.fallback_url && (
          <button
            onClick={() => onAction?.({ kind: 'open_url', url: card.fallback_url })}
            className="block w-full text-center text-[11px] text-slatey underline-offset-2 hover:text-ink hover:underline"
          >{t.viewFullMenu}</button>
        )}
      </div>
    </div>
  )
}
