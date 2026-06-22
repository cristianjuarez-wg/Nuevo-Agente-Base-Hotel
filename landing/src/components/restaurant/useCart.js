import { useMemo, useState } from 'react'

/**
 * Estado del carrito del restaurante, compartido por la pantalla #pedido y la card del chat.
 *
 * @param {Array} menu  - lista de platos (cada uno con id, price_usd, price_ars)
 * @param {Object} initial - carrito inicial { menu_item_id: qty } (para precargar, caso 2)
 */
export function useCart(menu, initial = {}) {
  const [cart, setCart] = useState(initial)

  const byId = useMemo(() => Object.fromEntries((menu || []).map((m) => [m.id, m])), [menu])
  const cartItems = Object.entries(cart).filter(([, q]) => q > 0)
  const totalUsd = cartItems.reduce((s, [id, q]) => s + (byId[id]?.price_usd || 0) * q, 0)
  const totalArs = cartItems.reduce((s, [id, q]) => s + (byId[id]?.price_ars || 0) * q, 0)
  const cartCount = cartItems.reduce((s, [, q]) => s + q, 0)

  const add = (id) => setCart((c) => ({ ...c, [id]: (c[id] || 0) + 1 }))
  const sub = (id) => setCart((c) => ({ ...c, [id]: Math.max(0, (c[id] || 0) - 1) }))
  const clear = () => setCart({})

  // Líneas listas para POST /api/restaurant/orders.
  const orderItems = () => cartItems.map(([id, qty]) => ({ menu_item_id: Number(id), qty }))

  return { cart, setCart, byId, cartItems, totalUsd, totalArs, cartCount, add, sub, clear, orderItems }
}

// Convierte un preselect del backend [{menu_item_id, qty}] al shape del carrito { id: qty }.
export function preselectToCart(preselect) {
  const c = {}
  for (const p of preselect || []) {
    if (p?.menu_item_id) c[p.menu_item_id] = (c[p.menu_item_id] || 0) + (p.qty || 1)
  }
  return c
}
